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

# These IDs MUST match the order used when the model was trained/exported.
CLASS_NAMES = {0: "D00", 1: "D10", 2: "D20", 3: "D40"}

_model: OnnxYoloModel | None = None
_model_load_lock = Lock()
_inference_lock = Lock()


class OnnxYoloModel:
    """CPU-only ONNX Runtime inference for YOLOv8 exports with or without NMS."""

    def __init__(self, model_path: Path) -> None:
        options = ort.SessionOptions()
        # Keep CPU thread pools modest for small-memory hosting.
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
            raise RuntimeError(f"Expected one ONNX input; found {len(inputs)}")

        self.input_name = inputs[0].name
        self.output_names = [item.name for item in self.session.get_outputs()]
        self.names = CLASS_NAMES  # dataset_service.py reads model.names
        self.input_size = int(settings.model_imgsz)

        logger.info(
            "ONNX model loaded: path=%s input_shape=%s outputs=%s providers=%s",
            model_path,
            inputs[0].shape,
            self.output_names,
            self.session.get_providers(),
        )

    def infer(self, image: Image.Image) -> list[dict[str, Any]]:
        original_width, original_height = image.size
        tensor, scale, pad_left, pad_top = _preprocess(image, self.input_size)
        outputs = self.session.run(
            self.output_names,
            {self.input_name: tensor},
        )
        if not outputs:
            raise RuntimeError("ONNX model returned no outputs")

        boxes, scores, class_ids, output_has_nms = _decode_output(
            outputs[0],
            confidence_threshold=settings.model_confidence_threshold,
        )
        if len(boxes) == 0:
            return []

        # Embedded-NMS exports have already suppressed duplicate boxes. Raw
        # YOLO outputs need class-aware NMS here.
        if not output_has_nms:
            keep: list[int] = []
            for class_id in np.unique(class_ids):
                indices = np.flatnonzero(class_ids == class_id)
                keep.extend(
                    indices[_nms(boxes[indices], scores[indices], 0.45)].tolist()
                )
            keep.sort(key=lambda index: float(scores[index]), reverse=True)
            boxes, scores, class_ids = boxes[keep], scores[keep], class_ids[keep]

        detections: list[dict[str, Any]] = []
        for box, score, class_id_value in zip(boxes, scores, class_ids):
            x1, y1, x2, y2 = box.astype(np.float32)
            # Both supported output formats use coordinates in model-input pixels.
            x1 = float(np.clip((x1 - pad_left) / scale, 0, original_width))
            y1 = float(np.clip((y1 - pad_top) / scale, 0, original_height))
            x2 = float(np.clip((x2 - pad_left) / scale, 0, original_width))
            y2 = float(np.clip((y2 - pad_top) / scale, 0, original_height))
            if x2 <= x1 or y2 <= y1:
                continue

            class_id = int(class_id_value)
            detections.append({
                "class_id": class_id,
                "class_name": self.names[class_id],
                "confidence": round(float(score), 4),
                "bbox": [x1, y1, x2, y2],
            })
        return detections


def get_model() -> OnnxYoloModel:
    """Load the model once per process, raising a clear error if unavailable."""
    global _model
    if _model is not None:
        return _model

    with _model_load_lock:
        if _model is not None:
            return _model
        model_path = Path(settings.model_path)
        if not model_path.is_absolute():
            model_path = (Path(__file__).resolve().parent.parent / model_path).resolve()
        if not model_path.is_file():
            raise FileNotFoundError(
                f"ONNX model not found at {model_path}. Set MODEL_PATH to your .onnx file."
            )
        if model_path.suffix.lower() != ".onnx":
            raise ValueError(f"Expected an .onnx model file, got {model_path.name}")
        logger.info("Loading ONNX model from %s", model_path)
        _model = OnnxYoloModel(model_path)
    return _model


def is_model_ready() -> bool:
    return _model is not None


def _preprocess(
    image: Image.Image,
    input_size: int,
) -> tuple[np.ndarray, float, int, int]:
    """YOLO-style square letterbox; RGB NCHW float32 input normalized to [0,1]."""
    image = image.convert("RGB")
    width, height = image.size
    if width <= 0 or height <= 0:
        raise ValueError("Image has invalid dimensions")

    scale = min(input_size / width, input_size / height)
    resized_width = max(1, int(round(width * scale)))
    resized_height = max(1, int(round(height * scale)))
    resized = image.resize((resized_width, resized_height), Image.Resampling.BILINEAR)

    pad_left = (input_size - resized_width) // 2
    pad_top = (input_size - resized_height) // 2
    canvas = Image.new("RGB", (input_size, input_size), (114, 114, 114))
    canvas.paste(resized, (pad_left, pad_top))
    array = np.asarray(canvas, dtype=np.float32) / 255.0
    tensor = np.transpose(array, (2, 0, 1))[None, ...]
    return np.ascontiguousarray(tensor), scale, pad_left, pad_top


def _decode_output(
    output: np.ndarray,
    confidence_threshold: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, bool]:
    """Decode either NMS rows [x1,y1,x2,y2,confidence,class_id] or raw YOLOv8."""
    prediction = np.asarray(output)
    if prediction.ndim == 3:
        if prediction.shape[0] != 1:
            raise RuntimeError(f"Expected batch size 1, got {prediction.shape}")
        prediction = prediction[0]
    if prediction.ndim != 2:
        raise RuntimeError(f"Unexpected ONNX output shape: {prediction.shape}")
    prediction = prediction.astype(np.float32, copy=False)
    if not np.isfinite(prediction).all():
        raise RuntimeError("ONNX output contains NaN or infinite values")

    # The actual model export on this branch returns 300 x 6, with NMS included.
    if prediction.shape[1] == 6:
        boxes = prediction[:, :4]
        scores = prediction[:, 4]
        raw_class_ids = prediction[:, 5]
        rounded_ids = np.rint(raw_class_ids)
        valid = (
            (scores >= confidence_threshold)
            & (np.abs(raw_class_ids - rounded_ids) < 1e-3)
            & (rounded_ids >= 0)
            & (rounded_ids < len(CLASS_NAMES))
            & (boxes[:, 2] > boxes[:, 0])
            & (boxes[:, 3] > boxes[:, 1])
        )
        return boxes[valid], scores[valid], rounded_ids[valid].astype(np.int64), True

    # Fallback for a standard raw YOLOv8 output: 4 box values + 4 class scores.
    feature_count = 4 + len(CLASS_NAMES)
    if prediction.shape[0] == feature_count:
        prediction = prediction.T
    elif prediction.shape[1] != feature_count:
        raise RuntimeError(
            f"Unsupported ONNX output shape {prediction.shape}; expected Nx6 NMS rows "
            f"or raw YOLO output with {feature_count} features."
        )

    boxes_xywh = prediction[:, :4]
    class_scores = prediction[:, 4:]
    class_ids = np.argmax(class_scores, axis=1)
    scores = class_scores[np.arange(len(class_scores)), class_ids]
    valid = scores >= confidence_threshold
    boxes_xywh, scores, class_ids = boxes_xywh[valid], scores[valid], class_ids[valid]
    boxes = np.empty_like(boxes_xywh, dtype=np.float32)
    boxes[:, 0] = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2
    boxes[:, 1] = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2
    boxes[:, 2] = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2
    boxes[:, 3] = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2
    return boxes, scores, class_ids.astype(np.int64), False


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    """Small NumPy-only greedy NMS; returned indices refer to the input arrays."""
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes.T
    areas = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    order = np.argsort(scores)[::-1]
    kept: list[int] = []
    while order.size:
        current = int(order[0])
        kept.append(current)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[current], x1[rest])
        yy1 = np.maximum(y1[current], y1[rest])
        xx2 = np.minimum(x2[current], x2[rest])
        yy2 = np.minimum(y2[current], y2[rest])
        intersection = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        union = areas[current] + areas[rest] - intersection
        iou = np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)
        order = rest[iou <= iou_threshold]
    return kept


def predict_image(image_bytes: bytes, filename: str = "image.jpg") -> dict[str, Any]:
    """Validate an uploaded image and return the API-compatible prediction response."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as opened_image:
            if opened_image.format not in ALLOWED_FORMATS:
                raise ValueError("Unsupported image format. Use JPEG, PNG or WebP")
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

    # Serialize inference to keep peak memory predictable on a 512 MB host.
    with _inference_lock:
        detections = get_model().infer(image)
    return {
        "filename": filename,
        "image_width": image_width,
        "image_height": image_height,
        "num_detections": len(detections),
        "detections": detections,
        "report": _build_report(detections),
    }


def _build_report(detections: list[dict[str, Any]]) -> dict[str, Any]:
    by_class: dict[tuple[int, str], list[float]] = {}
    for detection in detections:
        key = (detection["class_id"], detection["class_name"])
        by_class.setdefault(key, []).append(detection["confidence"])
    damage_types = [
        {
            "class_id": class_id,
            "class_name": class_name,
            "count": len(confidences),
            "highest_confidence": round(max(confidences), 4),
        }
        for (class_id, class_name), confidences in sorted(by_class.items())
    ]
    total = len(detections)
    if total == 0:
        summary = "No road damage was detected."
    else:
        breakdown = ", ".join(f"{item['class_name']}: {item['count']}" for item in damage_types)
        summary = f"Detected {total} road-damage instance(s) ({breakdown})."
    return {
        "status": "damage_detected" if total else "no_damage_detected",
        "total_detections": total,
        "damage_types": damage_types,
        "summary": summary,
    }
