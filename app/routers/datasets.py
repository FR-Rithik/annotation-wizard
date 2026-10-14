from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.auth import get_current_client
from app.database import get_db
from app.dataset_service import (
    cleanup_working_directory,
    create_dataset_job,
    create_working_directory,
    delete_dataset_job,
    export_dataset_job_yolo,
    get_dataset_image_dict,
    get_dataset_job_dict,
    label_dataset_zip,
    list_dataset_jobs,
    save_dataset_image_annotations,
    save_uploaded_zip,
    update_dataset_image_status,
)
from app.logger import get_logger
from app.models import ApiClient, DatasetImage, DatasetJob

logger = get_logger(__name__)

router = APIRouter(
    prefix="/datasets",
)


# ─── Pydantic Schemas ───────────────────────────────────────────────

class AnnotationItem(BaseModel):
    id: int | None = None
    class_id: int | None = None
    class_name: str | None = None
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    confidence: float | None = None
    is_prediction: bool | None = False
    is_modified: bool | None = True


class SaveAnnotationsRequest(BaseModel):
    status: str = Field(default="reviewed")
    annotations: list[AnnotationItem] = Field(default_factory=list)


class UpdateStatusRequest(BaseModel):
    status: str = Field(default="reviewed")


# ─── Legacy Auto-Label Endpoint (ZIP in -> Labeled ZIP out) ────────

@router.post("/label")
async def label_dataset(
    file: UploadFile = File(...),
    client: ApiClient = Depends(get_current_client),
):
    """
    Upload a ZIP of images and receive a YOLO-labeled dataset ZIP.
    Keeps legacy direct auto-labeling pipeline intact.
    """
    filename = file.filename or ""

    if not filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=422,
            detail="Please upload a .zip dataset",
        )

    working_directory: Path | None = None

    try:
        working_directory = create_working_directory()
        uploaded_zip = working_directory / "input.zip"

        await run_in_threadpool(
            save_uploaded_zip,
            file.file,
            uploaded_zip,
        )

        output_zip, stats = await run_in_threadpool(
            label_dataset_zip,
            uploaded_zip,
            working_directory,
        )

        logger.info(
            "Dataset labeled by client '%s': %s",
            client.name,
            stats,
        )

        return FileResponse(
            path=output_zip,
            media_type="application/zip",
            filename="annotation-wizard-labeled.zip",
            background=BackgroundTask(
                cleanup_working_directory,
                working_directory,
            ),
        )

    except ValueError as exc:
        if working_directory is not None:
            cleanup_working_directory(working_directory)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    except FileNotFoundError as exc:
        if working_directory is not None:
            cleanup_working_directory(working_directory)
        logger.exception("Model checkpoint is unavailable during dataset labeling")
        raise HTTPException(
            status_code=503,
            detail="Road-damage model is currently unavailable",
        ) from exc

    except Exception as exc:
        if working_directory is not None:
            cleanup_working_directory(working_directory)
        logger.exception("Dataset labeling failed")
        raise HTTPException(status_code=500, detail="Dataset labeling failed") from exc

    finally:
        await file.close()


# ─── Human-in-the-Loop Dataset Jobs Endpoints ───────────────────────

@router.post("/jobs", status_code=201)
async def create_job(
    file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
    name: str | None = Form(None),
    db: Session = Depends(get_db),
    client: ApiClient = Depends(get_current_client),
):
    """
    Upload a single image, multiple images, or a ZIP archive to create a dataset job.
    Model predictions are generated and saved for human-in-the-loop review.
    """
    uploaded_files: list[UploadFile] = []
    if files:
        uploaded_files.extend(files)
    if file and file not in uploaded_files:
        uploaded_files.append(file)

    if not uploaded_files:
        raise HTTPException(status_code=422, detail="No files uploaded. Provide an image or ZIP archive.")

    files_data: list[tuple[str, bytes]] = []
    primary_name = name or (uploaded_files[0].filename or "dataset")

    try:
        for f in uploaded_files:
            fname = f.filename or "upload.jpg"
            content = await f.read()
            if content:
                files_data.append((fname, content))
            await f.close()

        if not files_data:
            raise HTTPException(status_code=422, detail="Uploaded files were empty.")

        job = await run_in_threadpool(
            create_dataset_job,
            db=db,
            client_id=client.id,
            job_name=primary_name,
            files_data=files_data,
        )

        return {
            "job_id": job.id,
            "name": job.name,
            "status": job.status,
            "total_images": job.total_images,
            "reviewed_images": job.reviewed_images,
            "total_annotations": job.total_annotations,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        }

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        logger.exception("Model checkpoint unavailable during dataset job creation")
        raise HTTPException(status_code=503, detail="Road-damage model is currently unavailable") from exc
    except Exception as exc:
        logger.exception("Dataset job creation failed")
        raise HTTPException(status_code=500, detail=f"Failed to create dataset job: {exc}") from exc


@router.get("/jobs")
async def list_jobs(
    db: Session = Depends(get_db),
    client: ApiClient = Depends(get_current_client),
):
    """List recent dataset jobs."""
    return await run_in_threadpool(list_dataset_jobs, db=db, client_id=client.id)


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    client: ApiClient = Depends(get_current_client),
):
    """Retrieve details, image list, and review progress for a dataset job."""
    job_dict = await run_in_threadpool(get_dataset_job_dict, db=db, job_id=job_id)
    if not job_dict:
        raise HTTPException(status_code=404, detail="Dataset job not found")
    return job_dict


@router.get("/jobs/{job_id}/images/{image_id}")
async def get_image_annotations(
    job_id: str,
    image_id: int,
    db: Session = Depends(get_db),
    client: ApiClient = Depends(get_current_client),
):
    """Get metadata and bounding-box annotations for a specific image."""
    image_dict = await run_in_threadpool(get_dataset_image_dict, db=db, job_id=job_id, image_id=image_id)
    if not image_dict:
        raise HTTPException(status_code=404, detail="Image or job not found")
    return image_dict


@router.get("/jobs/{job_id}/images/{image_id}/file")
async def get_image_file(
    job_id: str,
    image_id: int,
    db: Session = Depends(get_db),
):
    """Serve the raw image file for canvas rendering and thumbnails."""
    img = (
        db.query(DatasetImage)
        .filter(DatasetImage.id == image_id, DatasetImage.job_id == job_id)
        .first()
    )
    if not img or not img.job:
        raise HTTPException(status_code=404, detail="Image not found")

    file_path = Path(img.job.storage_dir) / img.relative_path
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Image file missing from storage")

    ext = file_path.suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    return FileResponse(path=file_path, media_type=media_type)


@router.put("/jobs/{job_id}/images/{image_id}/annotations")
async def update_image_annotations(
    job_id: str,
    image_id: int,
    payload: SaveAnnotationsRequest,
    db: Session = Depends(get_db),
    client: ApiClient = Depends(get_current_client),
):
    """Save human-in-the-loop corrected bounding boxes for an image."""
    annotations_list = [ann.model_dump() for ann in payload.annotations]
    updated = await run_in_threadpool(
        save_dataset_image_annotations,
        db=db,
        job_id=job_id,
        image_id=image_id,
        status=payload.status,
        annotations_payload=annotations_list,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Image or dataset job not found")
    return updated


@router.post("/jobs/{job_id}/images/{image_id}/status")
async def set_image_status(
    job_id: str,
    image_id: int,
    payload: UpdateStatusRequest,
    db: Session = Depends(get_db),
    client: ApiClient = Depends(get_current_client),
):
    """Mark image status (reviewed, editing, not_reviewed)."""
    res = await run_in_threadpool(
        update_dataset_image_status,
        db=db,
        job_id=job_id,
        image_id=image_id,
        status=payload.status,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Image not found")
    return res


@router.get("/jobs/{job_id}/export")
async def export_job_labels(
    job_id: str,
    db: Session = Depends(get_db),
    client: ApiClient = Depends(get_current_client),
):
    """
    Download a ZIP archive containing the human-corrected YOLO label files,
    classes.txt, data.yaml, and dataset_info.txt summary.
    """
    try:
        output_zip, stats = await run_in_threadpool(export_dataset_job_yolo, db=db, job_id=job_id)
        job = db.query(DatasetJob).filter(DatasetJob.id == job_id).first()
        filename = f"{job.name if job else 'dataset'}-yolo-labels.zip"

        logger.info("Job %s exported by client %s: %s", job_id, client.name, stats)
        return FileResponse(
            path=output_zip,
            media_type="application/zip",
            filename=filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Export failed for job %s", job_id)
        raise HTTPException(status_code=500, detail="Failed to export dataset annotations") from exc


@router.delete("/jobs/{job_id}")
async def remove_job(
    job_id: str,
    db: Session = Depends(get_db),
    client: ApiClient = Depends(get_current_client),
):
    """Delete a dataset job and its associated files."""
    deleted = await run_in_threadpool(delete_dataset_job, db=db, job_id=job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset job not found")
    return {"message": "Dataset job deleted successfully", "job_id": job_id}