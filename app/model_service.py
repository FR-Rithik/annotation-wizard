
from __future__ import annotations

import io
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
import onnxruntime as ort
from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

# These IDs must match the class order used when training/exporting the model.
CLASS_NAMES = {
    0: "D00",
    1: "D10",
    2: "D20",
    3: "D40",
}

_model: "OnnxYoloModel | None" = None
_model_load_lock = Lock()
_inference_lock = Lock()


class OnnxYoloModel:
    """Minimal ONNX Runtime wrapper for a standard YOLOv8 ONNX export."""

    def __init__(self, model_path: Path) -> None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

        self.session = ort.InferenceSession(
            str(model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )

        inputs = self.session.get_inputs()
        if len(inputs) != 1:
            raise RuntimeError(
                f"Expected one ONNX input, but found {len(inputs)}"
            )

        self.input_name = inputs[0].name
        self.output_names = [output.name for output in self.session.get_outputs()]
        self.names = CLASS_NAMES

        # This implementation uses a square model input.
        self.input_size = int(settings.model_imgsz)

        logger.info(
            "ONNX model loaded: %s; input=%s; outputs=%s; providers=%s",
            model_path,
            inputs[0].shape,
            self.output_names,
            self.session.get_providers(),
        )

    def infer(self, image: Image.Image) -> list[dict[str, Any]]:
        original_width, original_height = image.size

        input_tensor, scale, pad_left, pad_top = _preprocess(
            image,
            self.input_size,
        )

        outputs = self.session.run(
            self.output_names,
            {self.input_name: input_tensor},
        )

        if not outputs:
            raise RuntimeError("ONNX model returned no outputs")

        predictions = _decode_yolov8_output(
            outputs[0],
            confidence_threshold=settings.model_confidence_threshold,
        )

        detections: list[dict[str, Any]] = []

        if len(predictions) == 0:
            return detections

        boxes_xyxy = _xywh_to_xyxy(predictions[:, :4])
        class_scores = predictions[:, 4:]
        class_ids = np.argmax(class_scores, axis=1)
        confidences = class_scores[
            np.arange(len(class_scores)), class_ids
        ]

        # Run NMS separately for each class, so different damage classes
        # do not suppress each other's boxes.
        keep_indices: list[int] = []

        for class_id in np.unique(class_ids):
            class_indices = np.flatnonzero(class_ids == class_id)
            class_keep = _nms(
                boxes_xyxy[class_indices],
                confidences[class_indices],
                iou_threshold=0.45,
            )
            keep_indices.extend(class_indices[class_keep].tolist())

        # Stable output ordering: highest confidence first.
        keep_indices.sort(key=lambda idx: float(confidences[idx]), reverse=True)

        for idx in keep_indices:
            x1, y1, x2, y2 = boxes_xyxy[idx]

            # Undo letterboxing and map coordinates to the original image.
            x1 = (x1 - pad_left) / scale
            y1 = (y1 - pad_top) / scale
            x2 = (x2 - pad_left) / scale
            y2 = (y2 - pad_top) / scale

            x1 = float(np.clip(x1, 0, original_width))
            y1 = float(np.clip(y1, 0, original_height))
            x2 = float(np.clip(x2, 0, original_width))
            y2 = float(np.clip(y2, 0, original_height))

            if x2 <= x1 or y2 <= y1:
                continue

            class_id = int(class_ids[idx])
            detections.append(
                {
                    "class_id": class_id,
                    "class_name": self.names.get(
                        class_id, str(class_id)
                    ),
                    "confidence": round(float(confidences[idx]), 4),
                    "bbox": [x1, y1, x2, y2],
                }
            )

        return detections


def get_model() -> OnnxYoloModel:
    """Load the ONNX model once per process."""
    global _model

    if _model is not None:
        return _model

    with _model_load_lock:
        if _model is not None:
            return _model

        model_path = Path(settings.model_path)
        if not model_path.is_absolute():
            model_path = (
                Path(__file__).resolve().parent.parent / model_path
            ).resolve()

        if not model_path.is_file():
            raise FileNotFoundError(
                f"ONNX model not found at {model_path}. "
                "Set MODEL_PATH to the location of your .onnx file."
            )

        if model_path.suffix.lower() != ".onnx":
            raise ValueError(
                f"Expected an .onnx model file, got: {model_path.name}"
            )

        logger.info("Loading ONNX model from %s", model_path)
        _model = OnnxYoloModel(model_path)

    return _model


def is_model_ready() -> bool:
    """Return whether the ONNX model initialized successfully."""
    return _model is not None


def _preprocess(
    image: Image.Image,
    input_size: int,
) -> tuple[np.ndarray, float, int, int]:
    """
    Resize with YOLO-style letterboxing, convert RGB to NCHW float32,
    and normalize pixels to [0, 1].
    """
    image = image.convert("RGB")
    original_width, original_height = image.size

    scale = min(
        input_size / original_width,
        input_size / original_height,
    )

    resized_width = max(1, int(round(original_width * scale)))
    resized_height = max(1, int(round(original_height * scale)))

    resized = image.resize(
        (resized_width, resized_height),
        Image.Resampling.BILINEAR,
    )

    pad_left = (input_size - resized_width) // 2
    pad_top = (input_size - resized_height) // 2

    canvas = Image.new(
        "RGB",
        (input_size, input_size),
        (114, 114, 114),
    )
    canvas.paste(resized, (pad_left, pad_top))

    array = np.asarray(canvas, dtype=np.float32) / 255.0
    tensor = np.transpose(array, (2, 0, 1))[None, ...]

    return np.ascontiguousarray(tensor), scale, pad_left, pad_top


def _decode_yolov8_output(
    output: np.ndarray,
    confidence_threshold: float,
) -> np.ndarray:
    """
    Decode the raw output of a standard YOLOv8 ONNX model.

    Common output layouts:
      [1, 4 + number_of_classes, number_of_candidates]
      [1, number_of_candidates, 4 + number_of_classes]

    YOLOv8 raw output has box values (cx, cy, width, height)
    followed by one score per class. It has no separate objectness score.
    """
    predictions = np.asarray(output)

    if predictions.ndim == 3:
        if predictions.shape[0] != 1:
            raise RuntimeError(
                f"Expected batch size 1, got output shape {predictions.shape}"
            )
        predictions = predictions[0]
    elif predictions.ndim != 2:
        raise RuntimeError(
            f"Unexpected ONNX output shape: {predictions.shape}"
        )

    expected_features = 4 + len(CLASS_NAMES)

    # Transpose [features, candidates] to [candidates, features].
    if predictions.shape[0] == expected_features:
        predictions = predictions.T
    elif predictions.shape[1] != expected_features:
        raise RuntimeError(
            "Unexpected YOLOv8 output shape "
            f"{predictions.shape}; expected one dimension to be "
            f"{expected_features} (4 box values + {len(CLASS_NAMES)} classes). "
            "Check whether your ONNX model uses a different output format "
            "or has embedded NMS."
        )

    predictions = predictions.astype(np.float32, copy=False)

    if not np.isfinite(predictions).all():
        raise RuntimeError("ONNX output contains NaN or infinite values")

    class_scores = predictions[:, 4:]
    best_scores = np.max(class_scores, axis=1)

    mask = best_scores >= confidence_threshold
    return predictions[mask]


def _xywh_to_xyxy(boxes: np.ndarray) -> np.ndarray:
    """Convert center-x, center-y, width, height to corner coordinates."""
    result = np.empty_like(boxes, dtype=np.float32)
    result[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
    result[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
    result[:, 2] = boxes[:, 0] + boxes[:, 2] / 2
    result[:, 3] = boxes[:, 1] + boxes[:, 3] / 2
    return result


def _nms(
    boxes: np.ndarray,
    scores: np.ndarray,
    iou_threshold: float,
) -> list[int]:
    """Greedy non-maximum suppression; returns indices into the input arrays."""
    if len(boxes) == 0:
        return []

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]

    areas = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    order = np.argsort(scores)[::-1]
    keep: list[int] = []

    while order.size > 0:
        current = int(order[0])
        keep.append(current)

        if order.size == 1:
            break

        remaining = order[1:]

        xx1 = np.maximum(x1[current], x1[remaining])
        yy1 = np.maximum(y1[current], y1[remaining])
        xx2 = np.minimum(x2[current], x2[remaining])
        yy2 = np.minimum(y2[current], y2[remaining])

        intersection = (
            np.maximum(0, xx2 - xx1)
            * np.maximum(0, yy2 - yy1)
        )

        union = areas[current] + areas[remaining] - intersection
        iou = np.divide(
            intersection,
            union,
            out=np.zeros_like(intersection, dtype=np.float32),
            where=union > 0,
        )

        order = remaining[iou <= iou_threshold]

    return keep


def predict_image(
    image_bytes: bytes,
    filename: str = "image.jpg",
) -> dict[str, Any]:
    """Validate an uploaded image and return the API's prediction response."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as opened_image:
            if opened_image.format not in ALLOWED_FORMATS:
                raise ValueError(
                    "Unsupported image format. Use JPEG, PNG or WebP"
                )

            image_width, image_height = opened_image.size

            if image_width * image_height > settings.max_image_pixels:
                raise ValueError(
                    f"Image too large ({image_width}x{image_height}). "
                    f"Maximum is {settings.max_image_pixels:,} pixels"
                )

            opened_image.load()
            image = opened_image.convert("RGB")

    except Image.DecompressionBombError as exc:
        raise ValueError("Image dimensions are too large") from exc
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("The uploaded file is not a valid image") from exc

    # ONNX Runtime sessions can usually handle concurrent requests, but
    # serialize inference to keep memory use predictable on a 512 MB service.
    with _inference_lock:
        model = get_model()
        detections = model.infer(image)

    return {
        "filename": filename,
        "image_width": image_width,
        "image_height": image_height,
        "num_detections": len(detections),
        "detections": detections,
        "report": _build_report(detections),
    }


def _build_report(
    detections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create the same compact report structure used by the existing API."""
    by_class: dict[tuple[int, str], list[float]] = {}

    for detection in detections:
        key = (
            detection["class_id"],
            detection["class_name"],
        )
        by_class.setdefault(key, []).append(
            detection["confidence"]
        )

    damage_types = [
        {
            "class_id": class_id,
            "class_name": class_name,
            "count": len(confidences),
            "highest_confidence": round(max(confidences), 4),
        }
        for (class_id, class_name), confidences in sorted(
            by_class.items()
        )
    ]

    total_detections = len(detections)

    if not total_detections:
        summary = "No road damage was detected."
    else:
        breakdown = ", ".join(
            f"{item['class_name']}: {item['count']}"
            for item in damage_types
        )
        summary = (
            f"Detected {total_detections} road-damage instance(s) "
            f"({breakdown})."
        )

    return {
        "status": (
            "damage_detected"
            if total_detections
            else "no_damage_detected"
        ),
        "total_detections": total_detections,
        "damage_types": damage_types,
        "summary": summary,
    }
