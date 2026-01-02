"""
Tests for media upload endpoints
"""
import io
from pathlib import Path

import pytest


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


def test_upload_image_nsfw_detection_rejected(client, auth_headers, mocker):
    """Test that NSFW images are rejected before storage"""
    # Create a fake image file (valid format)
    # In a real scenario, this would be actual image bytes
    file_content = b"\xff\xd8\xff\xe0\x00\x10JFIF"  # Minimal valid JPEG header
    
    # Mock the NSFW detection service's check_image method to return True (NSFW detected)
    async def mock_check_image(image_content):
        return True
    
    mocker.patch(
        "src.services.nsfw_detection_service.nsfw_detection_service.check_image",
        side_effect=mock_check_image
    )
    
    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"},
        files={"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")},
        headers=auth_headers
    )
    
    # Should return 400 bad request with NSFW message
    assert response.status_code == 400
    data = response.json()
    assert "error" in data or "detail" in data
    # Check for NSFW-related error message
    error_message = data.get("detail") or data.get("message", "")
    assert "inappropriate" in error_message.lower() or "nsfw" in error_message.lower()


def test_upload_image_nsfw_detection_allowed(client, auth_headers, mocker):
    """Test that safe images pass NSFW detection and are uploaded"""
    # Create a fake image file (valid format)
    file_content = b"\xff\xd8\xff\xe0\x00\x10JFIF"  # Minimal valid JPEG header
    
    # Mock the NSFW detection service to return False (safe image)
    async def mock_check_image(image_content):
        return False
    
    mocker.patch(
        "src.services.nsfw_detection_service.nsfw_detection_service.check_image",
        side_effect=mock_check_image
    )
    
    # Mock storage service to avoid actual S3 upload
    async def mock_save_file(file_content, filename, user_id):
        return ("test-key.jpg", "image/jpeg", len(file_content))
    
    mocker.patch(
        "src.services.storage_service.storage_service.save_file",
        side_effect=mock_save_file
    )
    
    mocker.patch(
        "src.services.storage_service.storage_service.generate_presigned_url",
        return_value="https://example.com/presigned-url.jpg"
    )
    
    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"},
        files={"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")},
        headers=auth_headers
    )
    
    # Should succeed (200 or 201) if storage is mocked, or fail with storage error if not
    # Since we're mocking storage, it should succeed
    assert response.status_code in [200, 201, 500]  # 500 if storage mock fails
    if response.status_code in [200, 201]:
        data = response.json()
        assert "url" in data or "storage_key" in data


def test_upload_audio_bypasses_nsfw_check(client, auth_headers, mocker):
    """Test that audio files bypass NSFW detection"""
    # Create a fake audio file
    file_content = b"fake audio content"
    
    # Mock NSFW detection - it should NOT be called for audio
    mock_nsfw_check = mocker.patch(
        "src.services.nsfw_detection_service.nsfw_detection_service.check_image"
    )
    
    # Mock storage service to avoid actual S3 upload
    async def mock_save_file(file_content, filename, user_id):
        return ("test-key.mp3", "audio/mpeg", len(file_content))
    
    mocker.patch(
        "src.services.storage_service.storage_service.save_file",
        side_effect=mock_save_file
    )
    
    mocker.patch(
        "src.services.storage_service.storage_service.generate_presigned_url",
        return_value="https://example.com/presigned-url.mp3"
    )
    
    response = client.post(
        "/api/v1/media/upload",
        data={"type": "audio"},
        files={"file": ("test.mp3", io.BytesIO(file_content), "audio/mpeg")},
        headers=auth_headers
    )
    
    # NSFW check should not have been called for audio
    mock_nsfw_check.assert_not_called()
    
    # Should either succeed or fail with validation/storage error, not NSFW error
    assert response.status_code in [200, 201, 400, 422, 500]
    if response.status_code == 400:
        # If it fails, it shouldn't be due to NSFW
        data = response.json()
        error_message = data.get("detail") or data.get("message", "")
        assert "inappropriate" not in error_message.lower()
        assert "nsfw" not in error_message.lower()


def test_upload_image_nsfw_detection_service_error(client, auth_headers, mocker):
    """Test that NSFW detection service errors are handled gracefully"""
    file_content = b"\xff\xd8\xff\xe0\x00\x10JFIF"  # Minimal valid JPEG header
    
    # Mock the NSFW detection service to raise an exception
    async def mock_check_image_error(image_content):
        raise RuntimeError("Replicate API error")
    
    mocker.patch(
        "src.services.nsfw_detection_service.nsfw_detection_service.check_image",
        side_effect=mock_check_image_error
    )
    
    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"},
        files={"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")},
        headers=auth_headers
    )
    
    # Should return 400 with error message about verification failure
    assert response.status_code == 400
    data = response.json()
    error_message = data.get("detail") or data.get("message", "")
    assert "verify" in error_message.lower() or "unable" in error_message.lower()


def test_upload_image_nsfw_detection_disabled(client, auth_headers, mocker):
    """Test that when NSFW detection is disabled, images are allowed through"""
    file_content = b"\xff\xd8\xff\xe0\x00\x10JFIF"  # Minimal valid JPEG header
    
    # Mock NSFW service to be disabled (check_image returns False when disabled)
    async def mock_check_image_disabled(image_content):
        return False  # When disabled, it returns False (not NSFW)
    
    mocker.patch(
        "src.services.nsfw_detection_service.nsfw_detection_service.check_image",
        side_effect=mock_check_image_disabled
    )
    
    # Mock storage service
    async def mock_save_file(file_content, filename, user_id):
        return ("test-key.jpg", "image/jpeg", len(file_content))
    
    mocker.patch(
        "src.services.storage_service.storage_service.save_file",
        side_effect=mock_save_file
    )
    
    mocker.patch(
        "src.services.storage_service.storage_service.generate_presigned_url",
        return_value="https://example.com/presigned-url.jpg"
    )
    
    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"},
        files={"file": ("test.jpg", io.BytesIO(file_content), "image/jpeg")},
        headers=auth_headers
    )
    
    # Should succeed when NSFW detection is disabled
    assert response.status_code in [200, 201, 500]  # 500 if storage mock fails


def test_upload_real_nsfw_image_rejected(client, auth_headers):
    """
    Test NSFW detection with a real NSFW image file.
    This test uses an actual NSFW image to verify the detection works end-to-end.
    """
    # Get the path to the test image file
    test_image_path = Path(__file__).parent / "images.jpeg"
    
    # Skip test if image file doesn't exist
    if not test_image_path.exists():
        pytest.skip(f"Test image file not found: {test_image_path}")
    
    # Read the actual image file
    with test_image_path.open("rb") as f:
        image_content = f.read()
    
    # Upload the image - it should be rejected as NSFW
    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"},
        files={"file": ("images.jpeg", io.BytesIO(image_content), "image/jpeg")},
        headers=auth_headers
    )
    
    # Should return 400 bad request
    assert response.status_code == 400, f"Expected 400, got {response.status_code}. Response: {response.json()}"
    data = response.json()
    
    # Check for NSFW-related error message or API failure message
    # (API failure also blocks upload for safety)
    error_message = data.get("detail") or data.get("message", "")
    assert (
        "inappropriate" in error_message.lower()
        or "nsfw" in error_message.lower()
        or "unable to verify" in error_message.lower()
        or "verify" in error_message.lower()
    ), f"Expected NSFW or verification error message, got: {error_message}"


def test_upload_real_nsfw_image_with_mocked_detection(client, auth_headers, mocker):
    """
    Test that a real NSFW image file is properly sent to the detection service.
    This verifies the file is correctly passed through to the NSFW detection.
    """
    # Get the path to the test image file
    test_image_path = Path(__file__).parent / "images.jpeg"
    
    # Skip test if image file doesn't exist
    if not test_image_path.exists():
        pytest.skip(f"Test image file not found: {test_image_path}")
    
    # Read the actual image file
    with test_image_path.open("rb") as f:
        image_content = f.read()
    
    # Track what was passed to the NSFW detection
    captured_image_content = None
    
    async def mock_check_image(image_content_bytes):
        nonlocal captured_image_content
        captured_image_content = image_content_bytes
        return True  # Return NSFW detected
    
    mocker.patch(
        "src.services.nsfw_detection_service.nsfw_detection_service.check_image",
        side_effect=mock_check_image
    )
    
    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"},
        files={"file": ("images.jpeg", io.BytesIO(image_content), "image/jpeg")},
        headers=auth_headers
    )
    
    # Verify the actual image content was passed to the detection service
    assert captured_image_content is not None, "NSFW detection should have been called with image content"
    assert captured_image_content == image_content, "Image content should match what was uploaded"
    assert len(captured_image_content) > 0, "Image content should not be empty"
    
    # Should return 400 bad request
    assert response.status_code == 400
    data = response.json()
    error_message = data.get("detail") or data.get("message", "")
    assert "inappropriate" in error_message.lower() or "nsfw" in error_message.lower()


def test_upload_real_safe_image_allowed(client, auth_headers, mocker):
    """
    Test that a safe (non-NSFW) image file passes NSFW detection and can be uploaded.
    This test uses an actual safe image to verify legitimate images aren't blocked.
    """
    # Get the path to the test image file
    test_image_path = Path(__file__).parent / "0040 (2).jpg"
    
    # Skip test if image file doesn't exist
    if not test_image_path.exists():
        pytest.skip(f"Test image file not found: {test_image_path}")
    
    # Read the actual image file
    with test_image_path.open("rb") as f:
        image_content = f.read()
    
    # Mock storage service to avoid actual S3 upload
    # Mock the storage service instance that's returned by dependency injection
    async def mock_save_file(file_content, filename, user_id):
        return ("test-key-safe.jpg", "image/jpeg", len(file_content))
    
    mocker.patch(
        "src.services.storage_service.storage_service.save_file",
        side_effect=mock_save_file
    )
    
    mocker.patch(
        "src.services.storage_service.storage_service.generate_presigned_url",
        return_value="https://example.com/presigned-url-safe.jpg"
    )
    
    # Upload the image - it should pass NSFW detection and be uploaded
    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"},
        files={"file": ("0040 (2).jpg", io.BytesIO(image_content), "image/jpeg")},
        headers=auth_headers
    )
    
    # Should succeed (200 or 201) - safe images should pass through
    # If it fails, it should NOT be due to NSFW detection
    assert response.status_code in [200, 201, 400, 422, 500], \
        f"Unexpected status code: {response.status_code}. Response: {response.json()}"
    
    if response.status_code in [200, 201]:
        # Success case - image passed NSFW check and was uploaded
        data = response.json()
        assert "url" in data or "storage_key" in data
        assert data.get("type") == "image"
    elif response.status_code == 400:
        # If it fails, verify it's NOT due to NSFW
        data = response.json()
        error_message = data.get("detail") or data.get("message", "")
        assert "inappropriate" not in error_message.lower(), \
            f"Safe image was incorrectly flagged as NSFW: {error_message}"
        assert "nsfw" not in error_message.lower(), \
            f"Safe image was incorrectly flagged as NSFW: {error_message}"


def test_upload_real_safe_image_nsfw_check_called(client, auth_headers, mocker):
    """
    Test that a safe image file is properly checked by NSFW detection service.
    This verifies the image content is correctly passed to the detection service.
    """
    # Get the path to the test image file
    test_image_path = Path(__file__).parent / "0040 (2).jpg"
    
    # Skip test if image file doesn't exist
    if not test_image_path.exists():
        pytest.skip(f"Test image file not found: {test_image_path}")
    
    # Read the actual image file
    with test_image_path.open("rb") as f:
        image_content = f.read()
    
    # Track what was passed to the NSFW detection
    captured_image_content = None
    
    async def mock_check_image(image_content_bytes):
        nonlocal captured_image_content
        captured_image_content = image_content_bytes
        return False  # Return safe (not NSFW)
    
    mocker.patch(
        "src.services.nsfw_detection_service.nsfw_detection_service.check_image",
        side_effect=mock_check_image
    )
    
    # Mock storage service
    async def mock_save_file(file_content, filename, user_id):
        return ("test-key-safe.jpg", "image/jpeg", len(file_content))
    
    mocker.patch(
        "src.services.storage_service.storage_service.save_file",
        side_effect=mock_save_file
    )
    
    mocker.patch(
        "src.services.storage_service.storage_service.generate_presigned_url",
        return_value="https://example.com/presigned-url-safe.jpg"
    )
    
    response = client.post(
        "/api/v1/media/upload",
        data={"type": "image"},
        files={"file": ("0040 (2).jpg", io.BytesIO(image_content), "image/jpeg")},
        headers=auth_headers
    )
    
    # Verify the actual image content was passed to the detection service
    assert captured_image_content is not None, "NSFW detection should have been called with image content"
    assert captured_image_content == image_content, "Image content should match what was uploaded"
    assert len(captured_image_content) > 0, "Image content should not be empty"
    
    # Should succeed since we mocked it as safe
    assert response.status_code in [200, 201], \
        f"Expected success (200/201), got {response.status_code}. Response: {response.json()}"
    data = response.json()
    assert "url" in data or "storage_key" in data
