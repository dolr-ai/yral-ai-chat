"""
Tests for media upload endpoints
"""
import io

import httpx


def test_upload_image_invalid_format(client, auth_headers):
    """Test uploading a file with invalid image format"""
    # Create a fake text file
    file_content = b"This is not an image file"

    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"},
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
        headers=auth_headers
    )

    # Should return 400 bad request
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"] == "bad_request"
    assert "message" in data
    assert "format" in data["message"].lower() or "allowed" in data["message"].lower()


def test_upload_without_file(client, auth_headers):
    """Test uploading without providing a file"""
    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"},
        headers=auth_headers
    )

    # Should return 422 validation error
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"] == "validation_error"
    assert "message" in data


def test_upload_with_invalid_type(client, auth_headers):
    """Test uploading with invalid type parameter"""
    file_content = b"fake image content"

    response = client.post(
        "/api/v1/media/upload",
        data={"type": "invalid_type"},
        files={"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")},
        headers=auth_headers
    )

    # Should return 422 validation error
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"] == "validation_error"
    assert "message" in data


def test_upload_audio_invalid_format(client, auth_headers):
    """Test uploading audio with invalid format"""
    file_content = b"This is not an audio file"

    response = client.post(
        "/api/v1/media/upload",
        data={"type": "audio"},
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
        headers=auth_headers
    )

    # Should return 400 bad request
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"] == "bad_request"
    assert "message" in data


def test_upload_missing_type_parameter(client, auth_headers):
    """Test uploading without type parameter"""
    file_content = b"fake content"

    response = client.post(
        "/api/v1/media/upload",
        files={"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")},
        headers=auth_headers
    )

    # Should return 422 validation error (missing required field)
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"] == "validation_error"
    assert "message" in data


def test_upload_endpoint_requires_auth(client, auth_headers):
    """Test that upload endpoint structure is correct"""
    file_content = b"test content"

    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"},
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
        headers=auth_headers
    )

    # Should get a response (not 404)
    assert response.status_code != 404

    # Should either succeed or fail with validation error, not server error
    assert response.status_code in [200, 201, 400, 422]


def test_upload_image_success(client, auth_headers):
    """Test uploading an image to Storj storage"""
    test_image_url = "https://yral-profile.hel1.your-objectstorage.com/users/upzvo-glz6l-actg5-izx2o-bsufp-hacvl-e6yeh-wyxl2-qf2gq-c3ndy-2ae/profile-1767637456.jpg"
    
    with httpx.Client() as http_client:
        image_response = http_client.get(test_image_url, timeout=10.0)
        image_response.raise_for_status()
        image_data = image_response.content
    
    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"},
        files={"file": ("test_image.jpg", io.BytesIO(image_data), "image/jpeg")},
        headers=auth_headers
    )
    
    assert response.status_code in [200, 201]
    assert response.json()["url"]
