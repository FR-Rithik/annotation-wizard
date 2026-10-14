from __future__ import annotations

import io
import json
import shutil
import stat
import tempfile
import uuid
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image as PILImage
from sqlalchemy.orm import Session

from app.config import settings
from app.logger import get_logger
from app.model_service import get_model, predict_image
from app.models import Annotation, DatasetImage, DatasetJob

logger = get_logger(__name__)

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
CHUNK_SIZE = 1024 * 1024  # 1 MB


def _validate_member_path(filename: str) -> Path:
    """
    Validate a ZIP member path and return a safe relative Path.

    Rejects:
    - absolute paths
    - '..' path traversal
    - Windows drive-style paths
    """
    normalized = filename.replace("\\", "/")
    path = PurePosixPath(normalized)

    if path.is_absolute():
        raise ValueError(f"Unsafe absolute path in ZIP: {filename}")

    if any(part == ".." for part in path.parts):
        raise ValueError(f"Unsafe path traversal in ZIP: {filename}")

    if path.parts and ":" in path.parts[0]:
        raise ValueError(f"Unsafe drive path in ZIP: {filename}")

    if not path.parts:
        raise ValueError("ZIP contains an empty filename")

    return Path(*path.parts)


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    """
    Detect Unix symlink entries stored inside a ZIP.
    """
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK

def _validate_unique_label_paths(
    image_infos: list[tuple[zipfile.ZipInfo, Path]],
) -> None:
    """
    Reject images that would generate the same YOLO label path.
    """
    seen_labels: dict[str, str] = {}

    for _, relative_path in image_infos:
        label_relative_path = relative_path.with_suffix(".txt")
        label_key = label_relative_path.as_posix().casefold()

        previous_image = seen_labels.get(label_key)

        if previous_image is not None:
            raise ValueError(
                "Multiple images would overwrite the same label file: "
                f"'{previous_image}' and '{relative_path.as_posix()}'. "
                "Rename one of the images or remove the duplicate."
            )

        seen_labels[label_key] = relative_path.as_posix()

def _read_member_with_limit(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    max_bytes: int,
) -> bytes:
    """
    Read one ZIP entry while enforcing a hard uncompressed size limit.
    """
    buffer = io.BytesIO()
    total = 0

    with archive.open(info, "r") as source:
        while True:
            chunk = source.read(CHUNK_SIZE)

            if not chunk:
                break

            total += len(chunk)

            if total > max_bytes:
                raise ValueError(
                    f"ZIP entry '{info.filename}' exceeds the "
                    f"{max_bytes // (1024 * 1024)} MB file limit"
                )

            buffer.write(chunk)

    return buffer.getvalue()


def _get_model_names() -> dict[int, str]:
    """
    Get class names from the loaded YOLO model.
    """
    model = get_model()
    names = getattr(model, "names", {}) or {}

    if isinstance(names, dict):
        return {
            int(class_id): str(class_name)
            for class_id, class_name in names.items()
        }

    if isinstance(names, list):
        return {
            class_id: str(class_name)
            for class_id, class_name in enumerate(names)
        }

    raise ValueError("Unable to read class names from the YOLO model")


def _convert_detections_to_yolo(
    detections: list[dict[str, Any]],
    image_width: int,
    image_height: int,
) -> list[str]:
    """
    Convert xyxy bounding boxes into normalized YOLO format.

    YOLO format:
        class_id x_center y_center width height
    """
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Invalid image dimensions")

    lines: list[str] = []

    for detection in detections:
        try:
            class_id = int(detection["class_id"])
            x1, y1, x2, y2 = (
                float(value)
                for value in detection["bbox"]
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("Skipping malformed detection: %s", detection)
            continue

        # Clamp coordinates to image boundaries.
        x1 = max(0.0, min(x1, float(image_width)))
        y1 = max(0.0, min(y1, float(image_height)))
        x2 = max(0.0, min(x2, float(image_width)))
        y2 = max(0.0, min(y2, float(image_height)))

        box_width = x2 - x1
        box_height = y2 - y1

        if box_width <= 0 or box_height <= 0:
            logger.warning("Skipping invalid bounding box: %s", detection)
            continue

        x_center = (x1 + x2) / 2.0
        y_center = (y1 + y2) / 2.0

        # Normalize to [0, 1].
        x_center /= image_width
        y_center /= image_height
        box_width /= image_width
        box_height /= image_height

        lines.append(
            f"{class_id} "
            f"{x_center:.6f} "
            f"{y_center:.6f} "
            f"{box_width:.6f} "
            f"{box_height:.6f}"
        )

    return lines


def _write_class_files(
    output_root: Path,
    class_names: dict[int, str],
) -> None:
    """
    Create classes.txt and data.yaml.
    """
    classes_path = output_root / "classes.txt"

    with classes_path.open("w", encoding="utf-8") as file:
        for class_id in sorted(class_names):
            file.write(f"{class_names[class_id]}\n")

    data_yaml_path = output_root / "data.yaml"

    yaml_lines = [
        "# Generated by Annotation Wizard",
        "# This dataset has not been split into train/validation sets.",
        "path: .",
        "names:",
    ]

    for class_id in sorted(class_names):
        # JSON strings are valid YAML strings.
        yaml_lines.append(
            f"  {class_id}: {json.dumps(class_names[class_id])}"
        )

    with data_yaml_path.open("w", encoding="utf-8") as file:
        file.write("\n".join(yaml_lines))
        file.write("\n")


def _write_dataset_info(
    output_root: Path,
    processed_images: int,
    images_with_detections: int,
    total_detections: int,
    failed_images: list[dict[str, str]],
) -> None:
    """
    Create a small metadata file describing the labeling result.
    """
    info_path = output_root / "dataset_info.txt"

    with info_path.open("w", encoding="utf-8") as file:
        file.write("Annotation Wizard Dataset\n")
        file.write("========================\n\n")

        file.write(f"Processed images: {processed_images}\n")
        file.write(
            f"Images with detections: {images_with_detections}\n"
        )
        file.write(f"Total detections: {total_detections}\n")
        file.write(f"Failed images: {len(failed_images)}\n")

        if failed_images:
            file.write("\nFailed images:\n")

            for failure in failed_images:
                file.write(
                    f"- {failure['filename']}: {failure['error']}\n"
                )


def _create_output_zip(
    output_root: Path,
    zip_path: Path,
) -> None:
    """
    Create the final downloadable ZIP.
    """
    with zipfile.ZipFile(
        zip_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        for file_path in output_root.rglob("*"):
            if not file_path.is_file():
                continue

            relative_path = file_path.relative_to(output_root)

            archive.write(
                file_path,
                relative_path.as_posix(),
            )


def save_uploaded_zip(
    source,
    destination: Path,
) -> None:
    """
    Save UploadFile content to disk without loading the entire ZIP
    into memory.
    """
    total = 0

    with destination.open("wb") as output:
        while True:
            chunk = source.read(CHUNK_SIZE)

            if not chunk:
                break

            total += len(chunk)

            if total > settings.max_dataset_zip_bytes:
                raise ValueError(
                    "Dataset ZIP is too large. "
                    f"Maximum size is "
                    f"{settings.max_dataset_zip_bytes // (1024 * 1024)} MB"
                )

            output.write(chunk)


def label_dataset_zip(
    zip_path: Path,
    working_directory: Path,
) -> tuple[Path, dict[str, int]]:
    """
    Main dataset auto-labeling pipeline.

    Input:
        zip_path

    Output:
        labeled ZIP containing:
            labels/
            classes.txt
            data.yaml
            dataset_info.txt
    """
    if not zipfile.is_zipfile(zip_path):
        raise ValueError("Uploaded file is not a valid ZIP archive")

    output_root = working_directory / "labeled_dataset"
    labels_root = output_root / "labels"

    labels_root.mkdir(parents=True, exist_ok=True)

    try:
        archive = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile as exc:
        raise ValueError("Uploaded file is not a valid ZIP archive") from exc

    with archive:
        infos = archive.infolist()

        if not infos:
            raise ValueError("The ZIP archive is empty")

        seen_paths: set[str] = set()
        image_infos: list[tuple[zipfile.ZipInfo, Path]] = []

        total_uncompressed_bytes = 0

        for info in infos:
            if info.is_dir():
                continue

            if _is_symlink(info):
                raise ValueError(
                    f"ZIP contains an unsupported symbolic link: "
                    f"{info.filename}"
                )

            safe_path = _validate_member_path(info.filename)

            key = safe_path.as_posix().lower()

            if key in seen_paths:
                raise ValueError(
                    f"ZIP contains duplicate paths: {info.filename}"
                )

            seen_paths.add(key)

            total_uncompressed_bytes += info.file_size

            if (
                total_uncompressed_bytes
                > settings.max_dataset_uncompressed_bytes
            ):
                raise ValueError(
                    "The uncompressed dataset is too large. "
                    f"Maximum is "
                    f"{settings.max_dataset_uncompressed_bytes // (1024 * 1024)} MB"
                )

            extension = safe_path.suffix.lower()

            if extension not in ALLOWED_IMAGE_EXTENSIONS:
                # Ignore non-image files such as existing .txt labels,
                # README files, metadata, etc.
                continue

            if info.file_size > settings.max_dataset_image_bytes:
                raise ValueError(
                    f"Image '{info.filename}' is too large. "
                    f"Maximum image size is "
                    f"{settings.max_dataset_image_bytes // (1024 * 1024)} MB"
                )

            image_infos.append((info, safe_path))

        if not image_infos:
            raise ValueError(
                "No supported images found. "
                "Use JPG, JPEG, PNG or WebP images."
            )
        _validate_unique_label_paths(image_infos)
        if len(image_infos) > settings.max_dataset_images:
            raise ValueError(
                f"Dataset contains {len(image_infos)} images. "
                f"Maximum is {settings.max_dataset_images}."
            )

        # Load the model once to obtain the class list.
        class_names = _get_model_names()

        processed_images = 0
        images_with_detections = 0
        total_detections = 0
        failed_images: list[dict[str, str]] = []

        for index, (info, relative_path) in enumerate(
            image_infos,
            start=1,
        ):
            logger.info(
                "Processing image %d/%d: %s",
                index,
                len(image_infos),
                relative_path.as_posix(),
            )

            try:
                image_bytes = _read_member_with_limit(
                    archive,
                    info,
                    settings.max_dataset_image_bytes,
                )

                prediction = predict_image(
                    image_bytes,
                    relative_path.as_posix(),
                )

                image_width = int(prediction["image_width"])
                image_height = int(prediction["image_height"])

                detections = prediction["detections"]

                label_lines = _convert_detections_to_yolo(
                    detections,
                    image_width,
                    image_height,
                )

                # Save the YOLO label.
                label_relative_path = relative_path.with_suffix(
                    ".txt"
                )

                destination_label = (
                    labels_root / label_relative_path
                ).resolve()

                destination_label.relative_to(
                    labels_root.resolve()
                )

                destination_label.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                destination_label.write_text(
                    (
                        "\n".join(label_lines)
                        + ("\n" if label_lines else "")
                    ),
                    encoding="utf-8",
                )

                processed_images += 1

                if detections:
                    images_with_detections += 1

                total_detections += len(detections)

            except ValueError as exc:
                # Bad image files should not destroy the entire job.
                failed_images.append(
                    {
                        "filename": relative_path.as_posix(),
                        "error": str(exc),
                    }
                )

                logger.warning(
                    "Skipping image %s: %s",
                    relative_path.as_posix(),
                    exc,
                )

            except FileNotFoundError:
                # Usually means the model checkpoint is unavailable.
                logger.exception(
                    "Road-damage model checkpoint is unavailable"
                )
                raise

            except Exception:
                logger.exception(
                    "Unexpected error while processing %s",
                    relative_path.as_posix(),
                )
                raise

        if processed_images == 0:
            raise ValueError(
                "No images could be successfully processed."
            )

        _write_class_files(
            output_root,
            class_names,
        )

        _write_dataset_info(
            output_root,
            processed_images,
            images_with_detections,
            total_detections,
            failed_images,
        )

        output_zip = working_directory / "annotation-wizard-labeled.zip"

        _create_output_zip(
            output_root,
            output_zip,
        )

    stats = {
        "total_images": len(image_infos),
        "processed_images": processed_images,
        "images_with_detections": images_with_detections,
        "total_detections": total_detections,
        "failed_images": len(failed_images),
    }

    logger.info(
        "Dataset labeling completed: %s",
        stats,
    )

    return output_zip, stats


def create_working_directory() -> Path:
    """
    Create a temporary directory for one labeling request.
    """
    return Path(
        tempfile.mkdtemp(
            prefix="annotation_wizard_"
        )
    )


def cleanup_working_directory(path: Path) -> None:
    """
    Remove temporary job files.
    """
    shutil.rmtree(
        path,
        ignore_errors=True,
    )


# ─── Dataset Job & Human-in-the-Loop Annotation Service ─────────────

CLASS_DESCRIPTIONS = {
    "D00": "Longitudinal Crack",
    "D10": "Transverse Crack",
    "D20": "Alligator Crack",
    "D40": "Pothole",
}

CLASS_IDS = {
    "D00": 0,
    "D10": 1,
    "D20": 2,
    "D40": 3,
}

ID_TO_CLASS = {v: k for k, v in CLASS_IDS.items()}


def create_dataset_job(
    db: Session,
    client_id: int | None,
    job_name: str,
    files_data: list[tuple[str, bytes]],
) -> DatasetJob:
    """
    Create a dataset job from an uploaded ZIP archive or individual image files.
    Runs YOLO ONNX prediction on each image and persists initial bounding boxes.
    """
    if not files_data:
        raise ValueError("No files provided for dataset job.")

    job_id = uuid.uuid4().hex[:12]
    clean_name = Path(job_name).stem if job_name.lower().endswith(".zip") else (job_name or f"dataset_{job_id}")

    storage_root = (Path(settings.dataset_storage_dir) / job_id).resolve()
    images_dir = storage_root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    extracted_images: list[tuple[str, bytes]] = []

    # Check if single uploaded file is a ZIP archive
    if len(files_data) == 1 and files_data[0][0].lower().endswith(".zip"):
        zip_filename, zip_bytes = files_data[0]
        if len(zip_bytes) > settings.max_dataset_zip_bytes:
            raise ValueError(
                f"Dataset ZIP is too large. Maximum size is "
                f"{settings.max_dataset_zip_bytes // (1024 * 1024)} MB"
            )

        try:
            archive = zipfile.ZipFile(io.BytesIO(zip_bytes), "r")
        except zipfile.BadZipFile as exc:
            raise ValueError("Uploaded file is not a valid ZIP archive") from exc

        with archive:
            infos = archive.infolist()
            if not infos:
                raise ValueError("The ZIP archive is empty")

            seen_names: set[str] = set()
            total_uncompressed = 0

            for info in infos:
                if info.is_dir() or _is_symlink(info):
                    continue

                safe_path = _validate_member_path(info.filename)
                ext = safe_path.suffix.lower()
                if ext not in ALLOWED_IMAGE_EXTENSIONS:
                    continue

                if info.file_size > settings.max_dataset_image_bytes:
                    raise ValueError(
                        f"Image '{info.filename}' exceeds {settings.max_dataset_image_bytes // (1024 * 1024)} MB limit"
                    )

                total_uncompressed += info.file_size
                if total_uncompressed > settings.max_dataset_uncompressed_bytes:
                    raise ValueError("The uncompressed dataset is too large.")

                img_name = safe_path.name
                # Avoid collision if multiple folders have same filename
                counter = 1
                base_stem = safe_path.stem
                while img_name.lower() in seen_names:
                    img_name = f"{base_stem}_{counter}{ext}"
                    counter += 1
                seen_names.add(img_name.lower())

                with archive.open(info, "r") as src:
                    content = src.read()
                    extracted_images.append((img_name, content))

                if len(extracted_images) > settings.max_dataset_images:
                    raise ValueError(f"Dataset exceeds limit of {settings.max_dataset_images} images.")
    else:
        # Multiple or single image files
        seen_names: set[str] = set()
        for filename, content in files_data:
            ext = Path(filename).suffix.lower()
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                continue

            if len(content) > settings.max_dataset_image_bytes:
                raise ValueError(
                    f"Image '{filename}' exceeds {settings.max_dataset_image_bytes // (1024 * 1024)} MB limit"
                )

            img_name = Path(filename).name
            counter = 1
            base_stem = Path(filename).stem
            while img_name.lower() in seen_names:
                img_name = f"{base_stem}_{counter}{ext}"
                counter += 1
            seen_names.add(img_name.lower())
            extracted_images.append((img_name, content))

    if not extracted_images:
        raise ValueError("No supported images found (JPG, PNG, or WebP).")

    # Sort images naturally by filename
    extracted_images.sort(key=lambda item: item[0])

    job = DatasetJob(
        id=job_id,
        name=clean_name,
        client_id=client_id,
        status="processing",
        total_images=len(extracted_images),
        reviewed_images=0,
        total_annotations=0,
        storage_dir=str(storage_root),
    )
    db.add(job)
    db.commit()

    total_annotations_count = 0
    saved_images_count = 0

    for index, (img_name, img_bytes) in enumerate(extracted_images):
        dest_path = images_dir / img_name
        dest_path.write_bytes(img_bytes)

        # Get dimensions
        try:
            with PILImage.open(io.BytesIO(img_bytes)) as pil_img:
                width, height = pil_img.size
        except Exception:
            width, height = 640, 640

        # Run YOLO ONNX inference
        try:
            prediction = predict_image(img_bytes, img_name)
            detections = prediction.get("detections", [])
        except Exception as exc:
            logger.warning("Prediction failed for image %s: %s", img_name, exc)
            detections = []

        rel_path = f"images/{img_name}"
        dataset_image = DatasetImage(
            job_id=job.id,
            filename=img_name,
            relative_path=rel_path,
            width=width,
            height=height,
            status="not_reviewed",
            order_index=index,
        )
        db.add(dataset_image)
        db.flush()

        for det in detections:
            try:
                x1, y1, x2, y2 = (float(v) for v in det["bbox"])
                class_id = int(det["class_id"])
                class_name = str(det.get("class_name", ID_TO_CLASS.get(class_id, "D00")))
                conf = float(det.get("confidence", 0.0))
            except (KeyError, TypeError, ValueError):
                continue

            # Clamp coordinates
            x1 = max(0.0, min(x1, float(width)))
            y1 = max(0.0, min(y1, float(height)))
            x2 = max(0.0, min(x2, float(width)))
            y2 = max(0.0, min(y2, float(height)))

            if x2 <= x1 or y2 <= y1:
                continue

            annotation = Annotation(
                image_id=dataset_image.id,
                class_id=class_id,
                class_name=class_name,
                x_min=round(x1, 2),
                y_min=round(y1, 2),
                x_max=round(x2, 2),
                y_max=round(y2, 2),
                confidence=round(conf, 4),
                is_prediction=True,
                is_modified=False,
            )
            db.add(annotation)
            total_annotations_count += 1

        saved_images_count += 1

    job.total_images = saved_images_count
    job.total_annotations = total_annotations_count
    job.status = "ready_for_review"
    db.commit()
    db.refresh(job)

    logger.info(
        "Dataset job created: id=%s name=%s images=%d annotations=%d",
        job.id,
        job.name,
        job.total_images,
        job.total_annotations,
    )
    return job


def list_dataset_jobs(db: Session, client_id: int | None = None) -> list[dict[str, Any]]:
    """List recent dataset jobs."""
    query = db.query(DatasetJob)
    if client_id is not None:
        query = query.filter(DatasetJob.client_id == client_id)
    jobs = query.order_by(DatasetJob.created_at.desc()).limit(50).all()

    results = []
    for job in jobs:
        results.append({
            "id": job.id,
            "name": job.name,
            "status": job.status,
            "total_images": job.total_images,
            "reviewed_images": job.reviewed_images,
            "total_annotations": job.total_annotations,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        })
    return results


def get_dataset_job_dict(db: Session, job_id: str) -> dict[str, Any] | None:
    """Retrieve full job details including image listing and review progress."""
    job = db.query(DatasetJob).filter(DatasetJob.id == job_id).first()
    if not job:
        return None

    images_data = []
    reviewed_count = 0
    total_annotations = 0

    for img in job.images:
        if img.status == "reviewed":
            reviewed_count += 1
        ann_count = len(img.annotations)
        total_annotations += ann_count

        images_data.append({
            "id": img.id,
            "filename": img.filename,
            "status": img.status,
            "width": img.width,
            "height": img.height,
            "order_index": img.order_index,
            "annotation_count": ann_count,
            "image_url": f"/datasets/jobs/{job.id}/images/{img.id}/file",
        })

    # Keep counts consistent
    job.reviewed_images = reviewed_count
    job.total_annotations = total_annotations
    db.commit()

    return {
        "id": job.id,
        "name": job.name,
        "status": job.status,
        "total_images": job.total_images,
        "reviewed_images": reviewed_count,
        "total_annotations": total_annotations,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "images": images_data,
    }


def get_dataset_image_dict(db: Session, job_id: str, image_id: int) -> dict[str, Any] | None:
    """Get image details and its current annotations for canvas editing."""
    img = (
        db.query(DatasetImage)
        .filter(DatasetImage.id == image_id, DatasetImage.job_id == job_id)
        .first()
    )
    if not img:
        return None

    annotations_data = []
    for ann in img.annotations:
        annotations_data.append({
            "id": ann.id,
            "class_id": ann.class_id,
            "class_name": ann.class_name,
            "class_label": CLASS_DESCRIPTIONS.get(ann.class_name, ann.class_name),
            "x_min": round(ann.x_min, 2),
            "y_min": round(ann.y_min, 2),
            "x_max": round(ann.x_max, 2),
            "y_max": round(ann.y_max, 2),
            "confidence": ann.confidence,
            "is_prediction": ann.is_prediction,
            "is_modified": ann.is_modified,
        })

    return {
        "id": img.id,
        "job_id": img.job_id,
        "filename": img.filename,
        "status": img.status,
        "width": img.width,
        "height": img.height,
        "order_index": img.order_index,
        "image_url": f"/datasets/jobs/{img.job_id}/images/{img.id}/file",
        "annotations": annotations_data,
    }


def save_dataset_image_annotations(
    db: Session,
    job_id: str,
    image_id: int,
    status: str,
    annotations_payload: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Persist human-in-the-loop edits for a single image:
    Updates, adds, or removes bounding boxes, updates status, and recalculates job progress.
    """
    img = (
        db.query(DatasetImage)
        .filter(DatasetImage.id == image_id, DatasetImage.job_id == job_id)
        .first()
    )
    if not img:
        return None

    # Replace existing annotations with corrected set
    db.query(Annotation).filter(Annotation.image_id == image_id).delete()

    for item in annotations_payload:
        try:
            x1 = float(item["x_min"])
            y1 = float(item["y_min"])
            x2 = float(item["x_max"])
            y2 = float(item["y_max"])
        except (KeyError, TypeError, ValueError):
            continue

        # Sort coordinates if inverted
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1

        # Clamp to image boundaries
        w = float(img.width) if img.width > 0 else 640.0
        h = float(img.height) if img.height > 0 else 640.0
        x1 = max(0.0, min(x1, w))
        y1 = max(0.0, min(y1, h))
        x2 = max(0.0, min(x2, w))
        y2 = max(0.0, min(y2, h))

        # Enforce minimum box dimensions (at least 2 pixels)
        if (x2 - x1) < 2.0 or (y2 - y1) < 2.0:
            continue

        raw_class_name = str(item.get("class_name", "D00")).upper()
        if raw_class_name not in CLASS_IDS:
            # Fallback by class_id
            cid = int(item.get("class_id", 0))
            raw_class_name = ID_TO_CLASS.get(cid, "D00")

        class_id = CLASS_IDS[raw_class_name]
        class_name = raw_class_name

        conf = item.get("confidence")
        conf_val = float(conf) if conf is not None else None
        is_pred = bool(item.get("is_prediction", False))
        is_mod = bool(item.get("is_modified", True))

        ann = Annotation(
            image_id=img.id,
            class_id=class_id,
            class_name=class_name,
            x_min=round(x1, 2),
            y_min=round(y1, 2),
            x_max=round(x2, 2),
            y_max=round(y2, 2),
            confidence=conf_val,
            is_prediction=is_pred,
            is_modified=is_mod,
        )
        db.add(ann)

    # Valid status values: "not_reviewed", "editing", "reviewed"
    valid_statuses = {"not_reviewed", "editing", "reviewed"}
    img.status = status if status in valid_statuses else "reviewed"

    job = db.query(DatasetJob).filter(DatasetJob.id == job_id).first()
    if job:
        job.updated_at = datetime.utcnow()
        job.reviewed_images = (
            db.query(DatasetImage)
            .filter(DatasetImage.job_id == job_id, DatasetImage.status == "reviewed")
            .count()
        )
        job.total_annotations = (
            db.query(Annotation)
            .join(DatasetImage)
            .filter(DatasetImage.job_id == job_id)
            .count()
        )

    db.commit()
    return get_dataset_image_dict(db, job_id, image_id)


def update_dataset_image_status(
    db: Session,
    job_id: str,
    image_id: int,
    status: str,
) -> dict[str, Any] | None:
    """Quick update of image review status."""
    img = (
        db.query(DatasetImage)
        .filter(DatasetImage.id == image_id, DatasetImage.job_id == job_id)
        .first()
    )
    if not img:
        return None

    img.status = status if status in {"not_reviewed", "editing", "reviewed"} else "reviewed"
    job = db.query(DatasetJob).filter(DatasetJob.id == job_id).first()
    if job:
        job.updated_at = datetime.utcnow()
        job.reviewed_images = (
            db.query(DatasetImage)
            .filter(DatasetImage.job_id == job_id, DatasetImage.status == "reviewed")
            .count()
        )
    db.commit()
    return {"id": img.id, "status": img.status}


def export_dataset_job_yolo(db: Session, job_id: str) -> tuple[Path, dict[str, Any]]:
    """
    Generate downloadable ZIP containing final human-corrected YOLO label files:
    - labels/<image_name>.txt
    - classes.txt
    - data.yaml
    - dataset_info.txt
    """
    job = db.query(DatasetJob).filter(DatasetJob.id == job_id).first()
    if not job:
        raise ValueError(f"Dataset job '{job_id}' not found.")

    storage_root = Path(job.storage_dir)
    export_root = storage_root / "export_yolo"
    labels_root = export_root / "labels"

    # Reset clean export folder
    shutil.rmtree(export_root, ignore_errors=True)
    labels_root.mkdir(parents=True, exist_ok=True)

    class_names = {0: "D00", 1: "D10", 2: "D20", 3: "D40"}
    total_images = len(job.images)
    images_with_boxes = 0
    total_boxes = 0
    class_counts = {"D00": 0, "D10": 0, "D20": 0, "D40": 0}

    for img in job.images:
        label_lines: list[str] = []
        w = float(img.width) if img.width > 0 else 640.0
        h = float(img.height) if img.height > 0 else 640.0

        for ann in img.annotations:
            class_id = ann.class_id
            cname = ann.class_name
            if cname in class_counts:
                class_counts[cname] += 1

            x_center = ((ann.x_min + ann.x_max) / 2.0) / w
            y_center = ((ann.y_min + ann.y_max) / 2.0) / h
            box_w = (ann.x_max - ann.x_min) / w
            box_h = (ann.y_max - ann.y_min) / h

            # Clamp normalized coordinates to [0.0, 1.0]
            x_center = max(0.0, min(1.0, x_center))
            y_center = max(0.0, min(1.0, y_center))
            box_w = max(0.0, min(1.0, box_w))
            box_h = max(0.0, min(1.0, box_h))

            label_lines.append(
                f"{class_id} {x_center:.6f} {y_center:.6f} {box_w:.6f} {box_h:.6f}"
            )

        if label_lines:
            images_with_boxes += 1
            total_boxes += len(label_lines)

        label_path = labels_root / f"{Path(img.filename).stem}.txt"
        label_path.write_text(
            "\n".join(label_lines) + ("\n" if label_lines else ""),
            encoding="utf-8",
        )

    # Write classes.txt
    classes_file = export_root / "classes.txt"
    with classes_file.open("w", encoding="utf-8") as f:
        for cid in sorted(class_names):
            f.write(f"{class_names[cid]}\n")

    # Write data.yaml
    yaml_file = export_root / "data.yaml"
    yaml_content = [
        "# Generated by Annotation Wizard — Human-in-the-Loop Review",
        "path: .",
        "names:",
    ]
    for cid in sorted(class_names):
        yaml_content.append(f"  {cid}: {json.dumps(class_names[cid])}")
    yaml_file.write_text("\n".join(yaml_content) + "\n", encoding="utf-8")

    # Write dataset_info.txt
    info_file = export_root / "dataset_info.txt"
    with info_file.open("w", encoding="utf-8") as f:
        f.write("Annotation Wizard Labeled Dataset\n")
        f.write("=================================\n\n")
        f.write(f"Dataset Name: {job.name}\n")
        f.write(f"Job ID: {job.id}\n")
        f.write(f"Total images: {total_images}\n")
        f.write(f"Reviewed images: {job.reviewed_images}\n")
        f.write(f"Images with annotations: {images_with_boxes}\n")
        f.write(f"Total annotations: {total_boxes}\n\n")
        f.write("Class Breakdown:\n")
        for cname, count in class_counts.items():
            f.write(f"- {cname} ({CLASS_DESCRIPTIONS.get(cname, '')}): {count}\n")
        f.write(f"\nExported at: {datetime.utcnow().isoformat()}Z\n")

    output_zip = storage_root / f"{job.name}_yolo_labels.zip"
    _create_output_zip(export_root, output_zip)

    stats = {
        "job_id": job.id,
        "name": job.name,
        "total_images": total_images,
        "reviewed_images": job.reviewed_images,
        "total_annotations": total_boxes,
        "class_breakdown": class_counts,
    }
    return output_zip, stats


def delete_dataset_job(db: Session, job_id: str) -> bool:
    """Delete dataset job, annotations, and storage files."""
    job = db.query(DatasetJob).filter(DatasetJob.id == job_id).first()
    if not job:
        return False

    storage_root = Path(job.storage_dir)
    shutil.rmtree(storage_root, ignore_errors=True)

    db.delete(job)
    db.commit()
    return True
