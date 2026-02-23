use std::sync::Arc;

use axum::extract::{Multipart, State};
use axum::Json;
use chrono::Utc;

use crate::middleware::AuthenticatedUser;
use crate::error::AppError;
use crate::models::responses::MediaUploadResponse;
use crate::services::storage::{file_extension, mime_from_extension};
use crate::AppState;

// POST /api/v1/media/upload
pub async fn upload_media(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    mut multipart: Multipart,
) -> Result<Json<MediaUploadResponse>, AppError> {
    let mut file_bytes: Option<Vec<u8>> = None;
    let mut file_name: Option<String> = None;
    let mut content_type: Option<String> = None;
    let mut media_type: Option<String> = None;

    while let Some(field) = multipart
        .next_field()
        .await
        .map_err(|e| AppError::bad_request(format!("Invalid multipart data: {e}")))?
    {
        let name = field.name().unwrap_or("").to_string();
        match name.as_str() {
            "file" => {
                file_name = field.file_name().map(|s| s.to_string());
                content_type = field.content_type().map(|s| s.to_string());
                file_bytes = Some(
                    field
                        .bytes()
                        .await
                        .map_err(|e| AppError::bad_request(format!("Failed to read file: {e}")))?
                        .to_vec(),
                );
            }
            "type" => {
                media_type = Some(
                    field
                        .text()
                        .await
                        .map_err(|e| AppError::bad_request(format!("Failed to read type: {e}")))?,
                );
            }
            _ => {}
        }
    }

    let file_bytes =
        file_bytes.ok_or_else(|| AppError::bad_request("Missing 'file' field in upload"))?;
    let media_type =
        media_type.ok_or_else(|| AppError::bad_request("Missing 'type' field in upload"))?;
    let file_name = file_name.unwrap_or_else(|| "upload".to_string());

    if media_type != "image" && media_type != "audio" {
        return Err(AppError::bad_request(
            "Invalid type. Must be 'image' or 'audio'",
        ));
    }

    let ext = file_extension(&file_name);
    let size = file_bytes.len() as u64;

    // Validate
    if media_type == "image" {
        state.storage.validate_image(&file_name, size)?;
    } else {
        state.storage.validate_audio(&file_name, size)?;
    }

    // Determine content type
    let ct = content_type.unwrap_or_else(|| mime_from_extension(&ext).to_string());

    // Upload to S3
    let (storage_key, _) = state
        .storage
        .upload(&user.user_id, file_bytes, &ext, &ct)
        .await?;

    // Generate presigned URL for immediate access
    let presigned_url = state.storage.generate_presigned_url(&storage_key);

    Ok(Json(MediaUploadResponse {
        url: presigned_url,
        storage_key,
        media_type,
        size,
        mime_type: ct,
        duration_seconds: None,
        uploaded_at: Utc::now().naive_utc(),
    }))
}
