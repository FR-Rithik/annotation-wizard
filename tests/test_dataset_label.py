import io
import zipfile
from pathlib import Path


def test_label_dataset_missing_key(client):
    response = client.post(
        "/datasets/label",
        files={"file": ("dataset.zip", b"fake-zip-data", "application/zip")},
    )
    assert response.status_code == 401


def test_label_dataset_invalid_key(client):
    response = client.post(
        "/datasets/label",
        files={"file": ("dataset.zip", b"fake-zip-data", "application/zip")},
        headers={"X-API-Key": "non-existent-key"},
    )
    assert response.status_code == 403


def test_label_dataset_inactive_key(client):
    response = client.post(
        "/datasets/label",
        files={"file": ("dataset.zip", b"fake-zip-data", "application/zip")},
        headers={"X-API-Key": "inactive-key-123"},
    )
    assert response.status_code == 403


def test_label_dataset_non_zip_file_rejected(client):
    response = client.post(
        "/datasets/label",
        files={"file": ("photo.png", b"fake-png-data", "image/png")},
        headers={"X-API-Key": "valid-key-123"},
    )
    assert response.status_code == 422


def test_label_sample_dataset_success(client):
    sample_zip_path = Path("app/static/sample_dataset.zip")
    assert sample_zip_path.is_file(), "Sample dataset zip must exist"

    with open(sample_zip_path, "rb") as f:
        zip_bytes = f.read()

    response = client.post(
        "/datasets/label",
        files={"file": ("sample_dataset.zip", zip_bytes, "application/zip")},
        headers={"X-API-Key": "valid-key-123"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    # Inspect generated ZIP structure
    out_archive = zipfile.ZipFile(io.BytesIO(response.content))
    out_files = out_archive.namelist()
    assert "classes.txt" in out_files
    assert "data.yaml" in out_files
    assert any(name.startswith("labels/") and name.endswith(".txt") for name in out_files)
