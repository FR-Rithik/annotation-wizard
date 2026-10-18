# Annotation Wizard

**AI-Assisted Road Damage Detection and Dataset Annotation**

Annotation Wizard is a web-based dataset annotation tool built with FastAPI and a YOLO-based road damage detection model. It helps users generate object-detection annotations automatically, review and edit predictions, and export datasets in YOLO format.

The project evolved from **Road Damage API**, a single-image road damage detection backend, into a dataset annotation application with a web interface and a human-in-the-loop annotation workflow.

## Features

- **Interactive web interface:** Landing page and annotation workspace served by FastAPI.
- **API-key authentication:** Authenticate clients before accessing protected application features.
- **Single-image inference:** Run road damage detection on individual images.
- **Batch dataset annotation:** Upload a ZIP archive containing road images for automated annotation.
- **Dataset management:** Create and manage dataset jobs for annotation and review.
- **Manual annotation editing:** Inspect predictions and add, modify, move, resize, or delete bounding boxes using the annotation canvas.
- **YOLO-format export:** Export finalized annotations in a format suitable for object-detection training.
- **Lightweight downloads:** The direct batch auto-labeling endpoint returns generated label files without bundling the original images.
- **Four road damage classes:** D00, D10, D20, and D40.
- **Database integration:** PostgreSQL and SQLAlchemy for application data.
- **Containerized development:** Run the application and database with Docker Compose.
- **ONNX Runtime inference:** Run the exported model using ONNX Runtime without requiring PyTorch for inference.

## Application Workflow

The application provides two main annotation workflows.

### 1. Direct Dataset Auto-Labeling

1. Upload a ZIP archive containing road images.
2. The application validates and processes the archive.
3. The model generates road damage predictions.
4. Predictions are converted into YOLO-format label files.
5. Download a ZIP archive containing the generated labels.

This workflow is intended for users who need automatically generated annotations without manually reviewing each image inside the application.

### 2. Interactive Dataset Annotation

1. Open the landing page and provide a valid API key.
2. Enter the annotation workspace.
3. Upload an individual image, multiple images, or a supported ZIP archive.
4. Run model inference to generate initial predictions.
5. Review the predictions in the annotation workspace.
6. Edit bounding boxes and correct class assignments where necessary.
7. Export the finalized annotations in YOLO format.

The interactive workflow supports human review because automated predictions may contain incorrect or incomplete labels.

## Workspace

The workspace provides the following navigation areas:

| Section | Purpose |
|---|---|
| Single Image | Run inference on an individual road image. |
| Dataset Labeling | Upload datasets and generate annotations. |
| Annotation Canvas | Inspect and manually edit bounding boxes and classes. |
| Image Register | Review images associated with a dataset. |
| Activity Log | View activity information available in the workspace. |

The exact actions available in each section depend on the current application implementation and the dataset state.

## Supported Road Damage Classes

The current demo model supports four road damage categories.

| Class ID | Class | Description |
|---:|---|---|
| 0 | D00 | Longitudinal cracks |
| 1 | D10 | Transverse cracks |
| 2 | D20 | Alligator cracks |
| 3 | D40 | Potholes |

**Important:** The class IDs must match the class ordering expected by the trained model. Review generated annotations before using them as ground-truth labels for training.

## Technology Stack

- **Language:** Python
- **Backend framework:** FastAPI
- **Frontend:** HTML, CSS, and JavaScript
- **Object detection:** YOLO-based road damage detection model
- **Inference runtime:** ONNX Runtime
- **Image processing:** Pillow and NumPy
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy
- **Database migrations:** Alembic
- **Containerization:** Docker and Docker Compose
- **Testing:** Pytest

## Requirements

To run the application using Docker Compose, install:

- Git
- Docker
- Docker Compose

You will also need the required model artifact, environment configuration, and sufficient system resources to run the application and inference workload.

For local development without Docker, install a compatible Python version and the dependencies specified in `requirements.txt`.

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/FR-Rithik/annotation-wizard.git
cd annotation-wizard
```

### 2. Configure environment variables

Create a local environment file from the example:

**Linux/macOS:**

```bash
cp .env.example .env
```

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
```

Review `.env` and configure the database credentials, API-key settings, and model configuration.

The default configuration uses the following model settings:

```env
MODEL_PATH=best.onnx
MODEL_CONFIDENCE_THRESHOLD=0.25
MODEL_IMGSZ=640
```

Set `ADMIN_API_KEY` to a strong, private value. Use appropriate credentials for your environment, and never commit real secrets to version control.

Ensure that the model file specified by `MODEL_PATH` is available at the expected location.

### 3. Start the application

Build the application image and start the services:

```bash
docker compose up --build
```

Docker Compose starts the API and PostgreSQL services. The configured startup command runs database migrations before starting the FastAPI application.

Keep the terminal running while using the application. To stop the services, press `Ctrl+C` and then run:

```bash
docker compose down
```

This does not remove the named database volume. Use `docker compose down -v` only when you intentionally want to remove the persisted database volume and its data.

### 4. Open the application

When running locally with the default configuration, open:

- **Landing page:** http://localhost:8000/
- **Annotation workspace:** http://localhost:8000/workspace
- **Interactive API documentation:** http://localhost:8000/docs
- **Alternative API documentation:** http://localhost:8000/redoc
- **Health check:** http://localhost:8000/health
- **Sample dataset:** http://localhost:8000/sample-dataset

Use a valid API key to access protected features in the workspace.

The health endpoint reports the status of the database and model. A successful response indicates that the required components are available; a degraded response indicates that the model is unavailable.

## API Overview

FastAPI provides interactive API documentation at `/docs`. Use it to inspect the current request schemas, response formats, authentication requirements, and available endpoints.

| Endpoint | Purpose |
|---|---|
| `GET /` | Serve the landing page. |
| `GET /workspace` | Serve the annotation workspace. |
| `GET /health` | Check database and model availability. |
| `POST /predict` | Run individual-image road damage inference. |
| `POST /datasets/label` | Automatically annotate an uploaded ZIP archive and return generated labels. |
| `POST /datasets/jobs` | Create a dataset annotation job from supported uploaded files. |
| `/datasets/jobs/...` | Access dataset-job operations, including supported review, annotation, and export actions. |
| `/auth/...` | Access the authentication routes defined by the application. |
| `/images/...` | Access the image routes defined by the application. |

For the complete and authoritative endpoint list, consult `/docs` after starting the application. The exact methods and parameters for dataset-job and image operations are defined by the API implementation.

### API-Key Authentication

Protected endpoints use the `X-API-Key` HTTP header.

Example:

```http
X-API-Key: your-api-key-here
```

Replace the placeholder with a valid key for your environment. Never expose production API keys in public repositories, screenshots, or logs.

### Individual Image Prediction

Example request:

```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: your-api-key-here" \
  -F "file=@road.jpg"
```

Replace the example API key and image path with your own values. Refer to `/docs` for the response schema and the authentication configuration.

### Direct Dataset Auto-Labeling

The `/datasets/label` endpoint accepts a ZIP archive through the `file` form field.

The application processes the archive and returns a ZIP file containing generated annotation files. The original images are not included in this endpoint's output archive.

For the exact accepted archive structure, validation rules, and error responses, refer to `/docs`.

## Model Configuration

The application uses a trained road damage detection model exported to ONNX format for inference through ONNX Runtime.

The model path is configured through:

```env
MODEL_PATH=best.onnx
```

Other available configuration includes the confidence threshold and inference image size:

```env
MODEL_CONFIDENCE_THRESHOLD=0.25
MODEL_IMGSZ=640
```

These values control the configured inference behavior. Actual detection quality and resource consumption depend on the model, input images, runtime environment, and workload.

ONNX Runtime is used to avoid requiring the PyTorch and Ultralytics inference stack in the deployment environment. It does not guarantee a faster inference time or a specific memory footprint; these must be measured in the target environment.

## Dataset Export and Annotation Quality

The application generates YOLO-format annotations from model predictions and supports manual correction in the interactive workspace.

Automatically generated annotations should not be treated as ground truth without review. Model predictions can miss road damage, include false positives, or produce inaccurate bounding boxes.

Review the exported annotations and confirm the class mapping before using the resulting dataset to train another object-detection model.

## Running Tests

Install the required dependencies in your development environment and run:

```bash
pytest -q
```

Run the tests from the repository root. Some tests may require additional configuration or dependencies depending on the test setup.

## Project Structure

The main application components are organized as follows:

```text
annotation-wizard/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── auth.py
│   ├── errors.py
│   ├── logger.py
│   ├── model_service.py
│   ├── dataset_service.py
│   ├── routers/
│   │   ├── auth.py
│   │   ├── datasets.py
│   │   ├── images.py
│   │   └── predict.py
│   └── static/
│       ├── landing.html
│       ├── index.html
│       ├── styles.css
│       └── ...
├── alembic/
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
├── .env.example
└── best.onnx
```

This is a simplified overview. Consult the repository for the complete file structure and supporting frontend assets.

## Project Evolution

Annotation Wizard evolved from **Road Damage API**, originally designed for individual-image road damage detection.

The current application extends that foundation with ZIP-based auto-labeling, dataset jobs, an interactive annotation workspace, and manual review of model predictions.

The goal is to reduce repetitive annotation work while retaining the ability for users to inspect and correct labels before export.

## Limitations

- The current demo model supports four road damage classes.
- Prediction quality depends on the trained model and the input images.
- Automatic annotations may require manual correction.
- Resource usage and inference performance depend on the deployment environment.
- A successful local run does not guarantee that a deployment platform has sufficient memory or storage.
- The application should be tested with representative datasets before being used in a production annotation pipeline.

## Future Improvements

Potential areas for further development include:

- More object-detection models and configurable model selection.
- Improved dataset validation and annotation quality checks.
- More detailed progress reporting for large datasets.
- Additional annotation export formats.
- Improved performance and resource monitoring.
- Expanded automated tests and deployment verification.

---

**Repository:** https://github.com/FR-Rithik/annotation-wizard

**Project:** Annotation Wizard — AI-Assisted Road Damage Detection and Dataset Annotation
