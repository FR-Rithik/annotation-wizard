import io
import zipfile
from PIL import Image as PILImage
import pytest


def _create_sample_image_bytes(width=100, height=100, color=(100, 150, 200)):
    buf = io.BytesIO()
    img = PILImage.new("RGB", (width, height), color=color)
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _create_test_zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("road_001.jpg", _create_sample_image_bytes(200, 200))
        zf.writestr("road_002.jpg", _create_sample_image_bytes(300, 300))
    return buf.getvalue()


def test_create_dataset_job_unauthorized(client):
    zip_bytes = _create_test_zip_bytes()
    response = client.post(
        "/datasets/jobs",
        files={"file": ("test.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 401


def test_create_dataset_job_from_zip_and_review_workflow(client):
    zip_bytes = _create_test_zip_bytes()
    headers = {"X-API-Key": "valid-key-123"}

    # 1. Create Job from ZIP
    response = client.post(
        "/datasets/jobs",
        files={"file": ("road_damage_test.zip", zip_bytes, "application/zip")},
        data={"name": "test_dataset"},
        headers=headers,
    )
    assert response.status_code == 201
    job_data = response.json()
    job_id = job_data["job_id"]
    assert job_data["total_images"] == 2
    assert job_data["status"] == "ready_for_review"

    # 2. Get Job details
    get_res = client.get(f"/datasets/jobs/{job_id}", headers=headers)
    assert get_res.status_code == 200
    job_details = get_res.json()
    assert job_details["total_images"] == 2
    assert len(job_details["images"]) == 2
    first_image = job_details["images"][0]
    image_id = first_image["id"]
    assert first_image["status"] == "not_reviewed"

    # 3. Serve Image file
    file_res = client.get(f"/datasets/jobs/{job_id}/images/{image_id}/file")
    assert file_res.status_code == 200
    assert file_res.headers["content-type"].startswith("image/")

    # 4. Get Image Annotations
    ann_res = client.get(f"/datasets/jobs/{job_id}/images/{image_id}", headers=headers)
    assert ann_res.status_code == 200
    ann_data = ann_res.json()
    assert "annotations" in ann_data

    # 5. Save Human-in-the-Loop Edited Annotations
    new_annotations = [
        {
            "class_id": 3,
            "class_name": "D40",
            "x_min": 10.0,
            "y_min": 15.0,
            "x_max": 80.0,
            "y_max": 95.0,
            "confidence": 0.88,
            "is_prediction": False,
            "is_modified": True,
        },
        {
            "class_id": 0,
            "class_name": "D00",
            "x_min": 25.0,
            "y_min": 30.0,
            "x_max": 120.0,
            "y_max": 150.0,
            "confidence": None,
            "is_prediction": False,
            "is_modified": True,
        },
    ]

    put_res = client.put(
        f"/datasets/jobs/{job_id}/images/{image_id}/annotations",
        json={"status": "reviewed", "annotations": new_annotations},
        headers=headers,
    )
    assert put_res.status_code == 200
    updated_image = put_res.json()
    assert updated_image["status"] == "reviewed"
    assert len(updated_image["annotations"]) == 2

    # Check updated job progress
    job_check = client.get(f"/datasets/jobs/{job_id}", headers=headers).json()
    assert job_check["reviewed_images"] == 1

    # 6. Export YOLO labels ZIP
    export_res = client.get(f"/datasets/jobs/{job_id}/export", headers=headers)
    assert export_res.status_code == 200
    assert export_res.headers["content-type"] == "application/zip"

    # Inspect exported ZIP content
    exported_zip = zipfile.ZipFile(io.BytesIO(export_res.content))
    namelist = exported_zip.namelist()
    assert "classes.txt" in namelist
    assert "data.yaml" in namelist
    assert "dataset_info.txt" in namelist
    # Check that labels folder contains txt for the image
    label_files = [n for n in namelist if n.startswith("labels/") and n.endswith(".txt")]
    assert len(label_files) == 2

    # Verify label coordinates format: class_id x_center y_center w h
    first_label_name = f"labels/{first_image['filename'].split('.')[0]}.txt"
    if first_label_name in namelist:
        lines = exported_zip.read(first_label_name).decode("utf-8").strip().splitlines()
        assert len(lines) == 2
        parts = lines[0].split()
        assert len(parts) == 5
        # Ensure class id is 3 or 0
        assert parts[0] in {"0", "3"}
        # Normalized coords are floats between 0 and 1
        for coord in parts[1:]:
            val = float(coord)
            assert 0.0 <= val <= 1.0


def test_create_dataset_job_from_single_image(client):
    img_bytes = _create_sample_image_bytes(250, 250)
    headers = {"X-API-Key": "valid-key-123"}

    response = client.post(
        "/datasets/jobs",
        files={"file": ("single_road.jpg", img_bytes, "image/jpeg")},
        data={"name": "single_road_test"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["total_images"] == 1
    assert data["status"] == "ready_for_review"

    # List jobs
    list_res = client.get("/datasets/jobs", headers=headers)
    assert list_res.status_code == 200
    jobs_list = list_res.json()
    assert any(j["id"] == data["job_id"] for j in jobs_list)

    # Delete job
    del_res = client.delete(f"/datasets/jobs/{data['job_id']}", headers=headers)
    assert del_res.status_code == 200


def test_job_not_found(client):
    headers = {"X-API-Key": "valid-key-123"}
    res = client.get("/datasets/jobs/nonexistent_id", headers=headers)
    assert res.status_code == 404
