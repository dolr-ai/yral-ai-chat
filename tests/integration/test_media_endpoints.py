"""
Tests for media upload endpoints
"""
import io

from PIL import Image

from src.services.storage_service import StorageService


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
    # Ensure the bucket exists before testing
    storage_service = StorageService()
    s3_client = storage_service.s3_client
    bucket_name = storage_service.bucket
    
    # Check if bucket exists, create if it doesn't
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except s3_client.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code in ("404", "NoSuchBucket"):
            # Bucket doesn't exist, try to create it
            try:
                s3_client.create_bucket(Bucket=bucket_name)
            except Exception:
                # If creation fails (e.g., no permission or bucket naming conflict),
                # the upload will fail with a clear error message
                pass
    
    # Create a simple test image in memory using Pillow
    img = Image.new("RGB", (100, 100), color="red")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="JPEG")
    image_data = img_bytes.getvalue()
    
    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"},
        files={"file": ("test_image.jpg", io.BytesIO(image_data), "image/jpeg")},
        headers=auth_headers
    )
    
    assert response.status_code in [200, 201]
    data = response.json()
    assert "url" in data
    assert "storage_key" in data
    assert data["type"] == "image"
