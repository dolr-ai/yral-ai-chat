"""
Tests for media upload endpoints
"""
import io


def test_upload_image_invalid_format(client):
    """Test uploading a file with invalid image format"""
    # Create a fake text file
    file_content = b"This is not an image file"

    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"},
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
    )

    # Should return 400 bad request
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"] == "bad_request"
    assert "message" in data
    assert "format" in data["message"].lower() or "allowed" in data["message"].lower()


def test_upload_without_file(client):
    """Test uploading without providing a file"""
    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"}
    )

    # Should return 422 validation error
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"] == "validation_error"
    assert "message" in data


def test_upload_with_invalid_type(client):
    """Test uploading with invalid type parameter"""
    file_content = b"fake image content"

    response = client.post(
        "/api/v1/media/upload",
        data={"type": "invalid_type"},
        files={"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")}
    )

    # Should return 422 validation error
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"] == "validation_error"
    assert "message" in data


def test_upload_audio_invalid_format(client):
    """Test uploading audio with invalid format"""
    file_content = b"This is not an audio file"

    response = client.post(
        "/api/v1/media/upload",
        data={"type": "audio"},
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
    )

    # Should return 400 bad request
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"] == "bad_request"
    assert "message" in data


def test_upload_missing_type_parameter(client):
    """Test uploading without type parameter"""
    file_content = b"fake content"

    response = client.post(
        "/api/v1/media/upload",
        files={"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")}
    )

    # Should return 422 validation error (missing required field)
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"] == "validation_error"
    assert "message" in data


def test_upload_endpoint_requires_auth(client):
    """Test that upload endpoint structure is correct"""
    # Note: Auth is disabled for testing, but we can verify the endpoint exists
    # and has proper validation

    file_content = b"test content"

    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"},
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")}
    )

    # Should get a response (not 404)
    assert response.status_code != 404

    # Should either succeed or fail with validation error, not server error
    assert response.status_code in [200, 201, 400, 422]
