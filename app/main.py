from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine, get_db
from app.errors import database_error_handler, internal_error_handler, not_found_handler
from app.logger import get_logger
from app.model_service import get_model, is_model_ready
from app.models import Base
from app.routers import auth, datasets, images, predict

logger = get_logger(__name__)
PROJECT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_DIR / "app" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize model checkpoint, tables, and storage before accepting requests."""
    try:
        Path(settings.dataset_storage_dir).mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        logger.warning("Storage/database initialization warning: %s", exc)

    try:
        await run_in_threadpool(get_model)
    except Exception as exc:  # pragma: no cover - depends on deployment assets
        # Keep the service available for diagnostics; /health will advertise
        # that prediction is unavailable rather than claiming the app is ready.
        app.state.model_load_error = str(exc)
        logger.exception("Road-damage model failed to load during startup")
    else:
        app.state.model_load_error = None

    yield


app = FastAPI(
    title=settings.app_name,
    description="Automatically generate dataset annotations from uploaded images.",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(
    datasets.router,
    tags=["Datasets"],
)
app.include_router(images.router, prefix="/images", tags=["Images"])
app.include_router(predict.router, prefix="", tags=["Prediction"])

app.add_exception_handler(404, not_found_handler)
app.add_exception_handler(500, internal_error_handler)
app.add_exception_handler(SQLAlchemyError, database_error_handler)


@app.get("/", include_in_schema=False)
def frontend():
    """Serve the landing page introducing Annotation Wizard."""
    return FileResponse(STATIC_DIR / "landing.html")


@app.get("/workspace", include_in_schema=False)
def workspace():
    """Serve the interactive annotation workspace."""
    return FileResponse(STATIC_DIR / "index.html")


REFERENCE_IMAGE = STATIC_DIR / "reference-image.png"
SAMPLE_DATASET_FILE = STATIC_DIR / "sample_dataset.zip"


@app.get("/reference-image", include_in_schema=False)
def reference_image():
    return FileResponse(REFERENCE_IMAGE)


@app.get("/sample-dataset", include_in_schema=False)
def sample_dataset():
    """Serve sample dataset ZIP for recruiters and developers to test."""
    if not SAMPLE_DATASET_FILE.is_file():
        return JSONResponse(status_code=404, content={"detail": "Sample dataset not found"})
    return FileResponse(
        SAMPLE_DATASET_FILE,
        media_type="application/zip",
        filename="sample-road-dataset.zip",
    )



@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    if not is_model_ready():
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "db": "connected",
                "model": "unavailable",
            },
        )

    return {"status": "ok", "db": "connected", "model": "ready"}
