## Plan: Deploy Thesis Model into Road Damage API

Review the YOLO-based thesis model, package it for inference, and integrate a predictable /predict flow into the existing FastAPI service, with reproducible dependencies and basic validation for deployment.

**Steps**
1. Phase 0 - Confirm deployment interface: request/response schema, input type (image only vs image + metadata), and output format (boxes, class labels, confidence, optionally masks). *blocks rest*
2. Phase 1 - Freeze model choice and artifact location: select the best checkpoint (E7 resume best.pt) and place it in a stable path inside the service or in a mounted volume; document the checksum for reproducibility. *depends on 1*
3. Phase 2 - Export strategy: decide whether to keep .pt with Ultralytics runtime or export to ONNX; for unknown hardware, recommend ONNX for portability and PyTorch fallback. Add a repeatable export script. *depends on 2*
4. Phase 3 - Inference wrapper: add a small inference module that loads the model once on startup, runs prediction, and normalizes outputs into a stable response schema (class names D00/D10/D20/D40). *depends on 2, parallel with 3 if using .pt*
5. Phase 4 - API integration: add a new endpoint (e.g., POST /predict) to road-damage-api, validate image input, enforce size limits, and return structured detections. *depends on 4*
6. Phase 5 - Reproducibility and packaging: add requirements, pin versions for ultralytics/torch, and document GPU/CPU options; optional Dockerfile for inference. *depends on 2*
7. Phase 6 - Tests and smoke checks: add tests for model load, prediction output shape, and invalid input cases; add a sample image for manual verification. *depends on 4 and 5*

**Relevant files**
- /home/rithik/coding/thesis_road_damage_detection-main/README.md — current thesis overview and model claims
- /home/rithik/coding/thesis_road_damage_detection-main/scripts/train_onthefly_experiment.py — training configuration and dependencies
- /home/rithik/coding/thesis_road_damage_detection-main/configs/configs_baseline/data_v1.yaml — class names and dataset schema
- /home/rithik/coding/road-damage-api/app/main.py — add inference router
- /home/rithik/coding/road-damage-api/app/routers — add predict endpoint module
- /home/rithik/coding/road-damage-api/app/config.py — add model path and runtime settings

**Verification**
1. Local inference: run a single-image prediction and verify class labels match D00/D10/D20/D40.
2. API smoke: POST image to /predict and verify HTTP 200 with boxes and confidences.
3. Performance check: measure average latency over 10 images on the target hardware or CPU fallback.

**Decisions**
- Deployment target: integrate into the existing road-damage-api FastAPI service
- Model choice: E7 resume best.pt
- Export format: choose based on portability; recommend ONNX with PyTorch fallback
- Hardware: unknown; plan for CPU compatibility

**Further Considerations**
1. Define maximum input image size and whether to auto-resize or reject large images; recommend resize to 640 with letterboxing.
2. Decide confidence threshold default (e.g., 0.25 or 0.5) and whether it is configurable via query param or config.
3. Clarify whether detections should be saved as reports in the database or returned statelessly; recommend returning statelessly for MVP.
