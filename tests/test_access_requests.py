ADMIN_KEY = "supersecretkey"


def test_submit_access_request_valid(client):
    payload = {
        "name": "Jane Recruiter",
        "email": "jane@techcorp.com",
        "organization": "TechCorp",
        "intended_use": "Evaluating automated road damage dataset labeling for CV benchmarking.",
    }
    response = client.post("/auth/access-requests", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert "detail" in data
    assert "id" in data


def test_submit_access_request_without_organization(client):
    payload = {
        "name": "Alex Independent",
        "email": "alex@example.org",
        "intended_use": "Testing YOLO road crack inference model locally.",
    }
    response = client.post("/auth/access-requests", json=payload)
    assert response.status_code == 201
    assert response.json()["status"] == "success"


def test_submit_access_request_invalid_email(client):
    payload = {
        "name": "Bad Email",
        "email": "not-an-email",
        "intended_use": "Testing validation rules.",
    }
    response = client.post("/auth/access-requests", json=payload)
    assert response.status_code == 422


def test_submit_access_request_too_short_intended_use(client):
    payload = {
        "name": "Short Use",
        "email": "short@example.com",
        "intended_use": "Hi",
    }
    response = client.post("/auth/access-requests", json=payload)
    assert response.status_code == 422


def test_list_access_requests_as_admin(client):
    # First submit a request
    payload = {
        "name": "Admin Review Test",
        "email": "review@infra.gov",
        "organization": "DOT",
        "intended_use": "Municipal highway damage assessment test.",
    }
    submit_res = client.post("/auth/access-requests", json=payload)
    assert submit_res.status_code == 201

    # Admin retrieves requests
    response = client.get(
        "/auth/access-requests",
        headers={"X-API-Key": ADMIN_KEY},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    emails = [item["email"] for item in data]
    assert "review@infra.gov" in emails


def test_list_access_requests_forbidden_without_admin(client):
    # Anonymous request
    response_anon = client.get("/auth/access-requests")
    assert response_anon.status_code == 403

    # Client key request (not admin)
    response_client = client.get(
        "/auth/access-requests",
        headers={"X-API-Key": "valid-key-123"},
    )
    assert response_client.status_code == 403
