# Annotation Wizard

**Automated Road Damage Dataset Annotation using YOLOv8 and FastAPI**

Previously presented as **Road Damage API**, Annotation Wizard has evolved from a single-image road-damage detection API into a tool for automating object-detection dataset annotation.

Annotation Wizard uses a trained road-damage detection model to process images in batches. Users upload a ZIP archive containing road images, and the application generates YOLO-format annotation files that can be downloaded as a separate ZIP archive without the original images.

## Features

- **Batch image processing:** Upload multiple road images in a single ZIP archive.
- **Automatic annotation:** Detect road damage using a trained YOLOv8 model.
- **YOLO-format labels:** Generate label files containing class IDs and normalized bounding-box coordinates.
- **Lightweight downloads:** Download generated label files without including the original images.
- **Four damage classes:** Detect D00, D10, D20, and D40.
- **REST API:** Access annotation and prediction functionality through FastAPI.
- **API-key authentication:** Protect supported endpoints using API keys.
- **Database integration:** Use PostgreSQL and SQLAlchemy for database operations.
- **Containerized deployment:** Run the application using Docker and Docker Compose.
- **ONNX Runtime inference:** Use the exported ONNX model for CPU-based inference.

## How It Works

1. **Upload:** Submit a ZIP archive containing road images.
2. **Inference:** The application processes the images using the trained road-damage detection model.
3. **Annotation generation:** Convert detections into YOLO-format label files.
4. **Download:** Receive a ZIP archive containing the generated labels, ready for use in a compatible object-detection dataset.

## Technology Stack

- **Language:** Python
- **Backend:** FastAPI
- **Object detection:** YOLOv8
- **Model inference:** ONNX Runtime
- **Image processing:** Pillow, NumPy
- **Database:** PostgreSQL, SQLAlchemy
- **Database migrations:** Alembic
- **Containerization:** Docker, Docker Compose
- **Testing:** Pytest

## Supported Classes

| Class ID | Label |
|---:|---|
| 0 | D00 — Longitudinal crack |
| 1 | D10 — Transverse crack |
| 2 | D20 — Alligator crack |
| 3 | D40 — Pothole |

The class IDs must match the class ordering used by the trained model. Incorrect class mappings can produce invalid annotations.

## Requirements

To run the application using Docker:

- Docker
- Docker Compose

For local development and testing, you will also need a compatible Python environment and the dependencies listed in `requirements.txt`.

## Getting Started

### 1. Clone the repository

The repository URL remains unchanged to preserve the link previously shared with recruiters.

```bash
git clone https://github.com/FR-Rithik/road-damage-api.git
cd road-damage-api
```

The current development branch is `deployment/onnx-runtime`. To check it out explicitly:

```bash
git switch deployment/onnx-runtime
```

### 2. Configure environment variables

Create your local environment file:

```bash
cp .env.example .env
```

Configure the database connection, API settings, authentication secrets, and model path as required by the application.

For the ONNX Runtime configuration, use:

```env
MODEL_PATH=best.onnx
```

Use a strong, private value for `ADMIN_API_KEY` if required by your configuration. Never commit your `.env` file or production secrets.

> On Windows PowerShell, if `cp` is unavailable in your environment, use `Copy-Item .env.example .env`.

### 3. Start the application

Build the Docker image and start the services:

```bash
docker compose up --build
```

The API container is configured to run database migrations during startup, so a separate migration command is normally unnecessary.

### 4. Access the API

When running locally with the default Docker Compose port mapping:

- **Interactive API documentation:** http://localhost:8000/docs
- **Alternative API documentation:** http://localhost:8000/redoc
- **Health check:** http://localhost:8000/health

The health endpoint can help verify the availability of the application's dependencies, including the database and model.

## API Usage

The application exposes its endpoints through FastAPI. Consult `/docs` for the current routes, required parameters, authentication requirements, upload limits, and response schemas.

### Authentication

Protected endpoints use an API key supplied through the `X-API-Key` HTTP header.

```http
X-API-Key: your-api-key-here
```

Replace the example value with a valid API key for your environment. Do not expose real API keys in public repositories, screenshots, or logs.

### Batch Dataset Annotation

The main workflow accepts a ZIP archive containing images.

1. Submit the archive to the dataset-annotation endpoint.
2. The application extracts and processes the supported images.
3. The model generates road-damage detections.
4. The application converts detections into YOLO-format label files.
5. Download the resulting ZIP archive containing the generated labels.

The output is intended to keep downloads lightweight by excluding the original images. Refer to `/docs` for the exact endpoint path, upload field name, accepted archive contents, and request limits.

### Individual Image Detection

The application also retains individual-image prediction functionality through the `/predict` endpoint.

Example:

```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: your-api-key-here" \
  -F "file=@road.jpg"
```

Replace the API key and image path with valid values. Consult `/docs` for the exact response format and authentication configuration.

## Model Configuration

The current deployment branch uses an exported ONNX model for CPU-based inference through ONNX Runtime.

Configure the model path using `MODEL_PATH`:

```env
MODEL_PATH=best.onnx
```

The repository contains the trained model artifacts. The ONNX model is used by the inference service in this deployment configuration; the original `.pt` checkpoint is retained as a model artifact but is not required for ONNX-only inference.

Using ONNX Runtime is intended to reduce deployment resource requirements. Actual memory consumption depends on the model, dependencies, application configuration, and workload, so it should be measured in the target deployment environment.

The model generates predictions for four classes:

- D00 — Longitudinal crack
- D10 — Transverse crack
- D20 — Alligator crack
- D40 — Pothole

Generated annotations depend on the model's predictions, confidence threshold, preprocessing, and class mapping. **Review automatically generated labels before treating them as ground truth.**

## Running Tests

Run tests from your local development environment with the required dependencies installed.

```bash
pytest -q
```

To run the application tests inside a local Python virtual environment, activate that environment first and install the project's development dependencies.

The Docker image is intended for running the application; the test suite is not included in the image.

## Project Structure

The repository includes the FastAPI application, API routers, database migrations, model artifacts, Docker configuration, and tests. The main directories are:

```text
app/
├── main.py
├── config.py
├── database.py
├── models.py
├── auth.py
├── errors.py
├── logger.py
├── model_service.py
├── dataset_service.py
└── routers/
    ├── auth.py
    ├── predict.py
    └── datasets.py

alembic/
tests/

Dockerfile
docker-compose.yml
requirements.txt
pyproject.toml
.env.example
best.onnx
```

This is a high-level overview; consult the repository for the complete file structure.

## Project Evolution

Annotation Wizard began as **Road Damage API**, a backend for detecting road damage in individual images. It has since evolved toward batch dataset annotation.

The trained road-damage model remains the inference engine, while the ZIP-based workflow enables users to generate annotations for multiple images in a single request. The ONNX Runtime deployment configuration is intended to make the application more practical to host in resource-constrained environments.

## Future Improvements

Potential improvements include:

- A web interface for uploading archives and downloading annotations.
- Annotation previews with bounding boxes and confidence scores.
- Configurable confidence thresholds.
- Progress reporting for large annotation jobs.
- Support for additional object-detection models and datasets.
- Additional export formats and dataset-validation tools.
- More comprehensive validation of generated labels.

---

**Repository:** https://github.com/FR-Rithik/annotation-wizard/tree/deployment/onnx-runtime

**Project:** Annotation Wizard — Automated Road Damage Dataset Annotation
