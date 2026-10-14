from sqlalchemy.exc import OperationalError

from app.errors import database_error_handler


def test_health_when_model_is_ready(client, monkeypatch):
    monkeypatch.setattr("app.main.is_model_ready", lambda: True)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "db": "connected",
        "model": "ready",
    }

def test_health_when_model_is_unavailable(client, monkeypatch):
    monkeypatch.setattr("app.main.is_model_ready", lambda: False)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "db": "connected",
        "model": "unavailable",
    }

def test_frontend_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Annotation Wizard" in response.text
    assert "Turn road images into labeled datasets." in response.text
    assert "D00 / Longitudinal Cracks" in response.text
    assert "D10 / Transverse Cracks" in response.text
    assert "D20 / Alligator Cracks" in response.text
    assert "D40 / Potholes" in response.text


def test_workspace_is_served(client):
    response = client.get("/workspace")
    assert response.status_code == 200
    assert "Annotation Wizard" in response.text
    assert "Try the sample dataset" in response.text
    assert "Dataset labeling" in response.text


def test_sample_dataset_is_served(client):
    import io
    import zipfile

    response = client.get("/sample-dataset")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    # Verify it is a valid zip archive
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    filenames = archive.namelist()
    assert len(filenames) >= 1
    assert any(fn.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) for fn in filenames)



def test_database_errors_return_a_service_unavailable_response(client):
    response = database_error_handler(
        client,
        OperationalError("SELECT 1", {}, RuntimeError("Database is offline")),
    )
    assert response.status_code == 503
    assert response.body == (
        b'{"detail":"Database unavailable. Start the Postgres service and try again."}'
    )


def test_not_found_handler(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Resource not found"}


def test_predict_route_returns_model_results(client, monkeypatch):
    expected = {
        "filename": "sample.jpg",
        "image_width": 100,
        "image_height": 100,
        "num_detections": 1,
        "detections": [
            {
                "class_id": 0,
                "class_name": "D00",
                "confidence": 0.91,
                "bbox": [10.0, 20.0, 30.0, 40.0],
            }
        ],
        "report": {
            "status": "damage_detected",
            "total_detections": 1,
            "damage_types": [
                {
                    "class_id": 0,
                    "class_name": "D00",
                    "count": 1,
                    "highest_confidence": 0.91,
                }
            ],
            "summary": "Detected 1 road-damage instance(s) (D00: 1).",
        },
    }

    def fake_predict_image(image_bytes, filename="image.jpg"):
        assert isinstance(image_bytes, bytes)
        assert filename == "sample.jpg"
        return expected

    monkeypatch.setattr("app.routers.predict.predict_image", fake_predict_image)

    response = client.post(
        "/predict",
        files={"file": ("sample.jpg", b"fake-image-bytes", "image/jpeg")},
        headers={"X-API-Key": "valid-key-123"},
    )

    assert response.status_code == 200
    assert response.json() == expected


def test_upload_returns_prediction_report(client, monkeypatch, tmp_path):
    expected_prediction = {
        "filename": "road.jpg",
        "image_width": 100,
        "image_height": 100,
        "num_detections": 0,
        "detections": [],
        "report": {
            "status": "no_damage_detected",
            "total_detections": 0,
            "damage_types": [],
            "summary": "No road damage was detected.",
        },
    }

    def fake_predict_image(image_bytes, filename):
        return expected_prediction

    monkeypatch.setattr("app.routers.images.predict_image", fake_predict_image)
    monkeypatch.setattr("app.routers.images.UPLOAD_DIR", str(tmp_path))

    response = client.post(
        "/images",
        files={"file": ("road.jpg", b"image-bytes", "image/jpeg")},
        headers={"X-API-Key": "valid-key-123"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["prediction"] == expected_prediction
    assert data["report"] == expected_prediction["report"]
    assert (tmp_path / data["filename"]).is_file()
