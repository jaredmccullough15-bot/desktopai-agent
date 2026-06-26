import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_upload_worker_release_success():
    with open("small_test_package.zip", "rb") as file:
        response = client.post(
            "/api/worker/releases",
            data={"version": "1.0.0", "release_notes": "Initial release", "channel": "stable"},
            files={"package": ("small_test_package.zip", file, "application/zip")},
        )
    assert response.status_code == 200
    assert "release_id" in response.json()

def test_upload_worker_release_missing_package():
    response = client.post(
        "/api/worker/releases",
        data={"version": "1.0.0", "release_notes": "Initial release", "channel": "stable"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid file field: package"

def test_upload_worker_release_invalid_field():
    with open("small_test_package.zip", "rb") as file:
        response = client.post(
            "/api/worker/releases",
            data={"version": "1.0.0", "release_notes": "Initial release", "channel": "stable"},
            files={"wrong_field": ("small_test_package.zip", file, "application/zip")},
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid file field: package"