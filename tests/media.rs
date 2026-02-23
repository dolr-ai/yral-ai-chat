mod common;

use common::*;
use reqwest::multipart;

#[tokio::test]
async fn test_upload_endpoint_requires_auth() {
    let base = base_url();
    let client = http_client();

    let form = multipart::Form::new().text("type", "image").part(
        "file",
        multipart::Part::bytes(b"test content".to_vec())
            .file_name("test.jpg")
            .mime_str("image/jpeg")
            .unwrap(),
    );

    let resp = client
        .post(format!("{base}/api/v1/media/upload"))
        .multipart(form)
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 401);
}

#[tokio::test]
async fn test_upload_image_invalid_format() {
    let base = base_url();
    let client = http_client();

    let form = multipart::Form::new().text("type", "image").part(
        "file",
        multipart::Part::bytes(b"This is not an image".to_vec())
            .file_name("test.txt")
            .mime_str("text/plain")
            .unwrap(),
    );

    let resp = client
        .post(format!("{base}/api/v1/media/upload"))
        .header("Authorization", auth_header("test_user"))
        .multipart(form)
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 400);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["error"], "bad_request");
}

#[tokio::test]
async fn test_upload_with_invalid_type() {
    let base = base_url();
    let client = http_client();

    let form = multipart::Form::new().text("type", "invalid_type").part(
        "file",
        multipart::Part::bytes(b"fake image content".to_vec())
            .file_name("test.jpg")
            .mime_str("image/jpeg")
            .unwrap(),
    );

    let resp = client
        .post(format!("{base}/api/v1/media/upload"))
        .header("Authorization", auth_header("test_user"))
        .multipart(form)
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 422);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["error"], "validation_error");
}
