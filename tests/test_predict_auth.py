def test_predict_missing_key_rejected(client):
    response = client.post(
        "/predict",
        files={"file": ("test.jpg", b"fake-data", "image/jpeg")},
    )
    assert response.status_code == 401


def test_predict_invalid_key_rejected(client):
    response = client.post(
        "/predict",
        files={"file": ("test.jpg", b"fake-data", "image/jpeg")},
        headers={"X-API-Key": "invalid-key-xyz"},
    )
    assert response.status_code == 403


def test_predict_inactive_key_rejected(client):
    response = client.post(
        "/predict",
        files={"file": ("test.jpg", b"fake-data", "image/jpeg")},
        headers={"X-API-Key": "inactive-key-123"},
    )
    assert response.status_code == 403


def test_images_missing_key_rejected(client):
    response = client.post(
        "/images",
        files={"file": ("test.jpg", b"fake-data", "image/jpeg")},
    )
    assert response.status_code == 401


def test_images_invalid_key_rejected(client):
    response = client.post(
        "/images",
        files={"file": ("test.jpg", b"fake-data", "image/jpeg")},
        headers={"X-API-Key": "invalid-key-xyz"},
    )
    assert response.status_code == 403
