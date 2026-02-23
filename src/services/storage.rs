use std::collections::HashMap;
use std::time::Duration;

use rusty_s3::{Bucket as S3Bucket, Credentials as S3Credentials, S3Action, UrlStyle};
use url::Url;

use crate::config::Settings;
use crate::error::AppError;

pub struct StorageService {
    bucket: S3Bucket,
    credentials: S3Credentials,
    http_client: reqwest::Client,
    public_url_base: String,
    url_expires_seconds: u32,
    max_image_size_bytes: u64,
    max_audio_size_bytes: u64,
}

const IMAGE_EXTENSIONS: &[&str] = &[".jpg", ".jpeg", ".png", ".gif", ".webp"];
const AUDIO_EXTENSIONS: &[&str] = &[".mp3", ".m4a", ".wav", ".ogg"];

impl StorageService {
    pub fn new(settings: &Settings, http_client: reqwest::Client) -> Result<Self, anyhow::Error> {
        let endpoint = Url::parse(&settings.s3_endpoint_url)?;
        let bucket = S3Bucket::new(
            endpoint,
            UrlStyle::Path,
            settings.aws_s3_bucket.clone(),
            settings.aws_region.clone(),
        )?;
        let credentials =
            S3Credentials::new(&settings.aws_access_key_id, &settings.aws_secret_access_key);

        Ok(Self {
            bucket,
            credentials,
            http_client,
            public_url_base: settings.s3_public_url_base.clone(),
            url_expires_seconds: settings.s3_url_expires_seconds,
            max_image_size_bytes: settings.max_image_size_bytes(),
            max_audio_size_bytes: settings.max_audio_size_bytes(),
        })
    }

    pub async fn upload(
        &self,
        user_id: &str,
        file_bytes: Vec<u8>,
        file_extension: &str,
        content_type: &str,
    ) -> Result<(String, u64), AppError> {
        let filename = format!("{}{}", uuid::Uuid::new_v4(), file_extension);
        let key = format!("{user_id}/{filename}");
        let size = file_bytes.len() as u64;

        let mut action = self.bucket.put_object(Some(&self.credentials), &key);
        action.headers_mut().insert("Content-Type", content_type);
        let url = action.sign(Duration::from_secs(300));

        self.http_client
            .put(url.as_str())
            .header("Content-Type", content_type)
            .body(file_bytes)
            .send()
            .await
            .map_err(|e| AppError::service_unavailable(format!("S3 upload failed: {e}")))?
            .error_for_status()
            .map_err(|e| AppError::service_unavailable(format!("S3 upload rejected: {e}")))?;

        Ok((key, size))
    }

    pub fn generate_presigned_url(&self, key: &str) -> String {
        if key.starts_with("http://") || key.starts_with("https://") {
            return key.to_string();
        }

        let action = self.bucket.get_object(Some(&self.credentials), key);
        action
            .sign(Duration::from_secs(self.url_expires_seconds as u64))
            .to_string()
    }

    pub fn generate_presigned_urls_batch(&self, keys: &[String]) -> HashMap<String, String> {
        keys.iter()
            .map(|key| (key.clone(), self.generate_presigned_url(key)))
            .collect()
    }

    pub fn extract_key_from_url(&self, url_or_key: &str) -> String {
        if !url_or_key.starts_with("http://") && !url_or_key.starts_with("https://") {
            return url_or_key.to_string();
        }
        if !self.public_url_base.is_empty() && url_or_key.starts_with(&self.public_url_base) {
            return url_or_key[self.public_url_base.len()..]
                .trim_start_matches('/')
                .to_string();
        }
        url_or_key.to_string()
    }

    pub fn validate_image(&self, filename: &str, size: u64) -> Result<(), AppError> {
        let ext = file_extension(filename).to_lowercase();
        if !IMAGE_EXTENSIONS.contains(&ext.as_str()) {
            return Err(AppError::bad_request(format!(
                "Unsupported image format. Allowed: {}",
                IMAGE_EXTENSIONS.join(", ")
            )));
        }
        if size > self.max_image_size_bytes {
            return Err(AppError::bad_request(format!(
                "Image too large. Max: {}MB",
                self.max_image_size_bytes / (1024 * 1024)
            )));
        }
        Ok(())
    }

    pub fn validate_audio(&self, filename: &str, size: u64) -> Result<(), AppError> {
        let ext = file_extension(filename).to_lowercase();
        if !AUDIO_EXTENSIONS.contains(&ext.as_str()) {
            return Err(AppError::bad_request(format!(
                "Unsupported audio format. Allowed: {}",
                AUDIO_EXTENSIONS.join(", ")
            )));
        }
        if size > self.max_audio_size_bytes {
            return Err(AppError::bad_request(format!(
                "Audio too large. Max: {}MB",
                self.max_audio_size_bytes / (1024 * 1024)
            )));
        }
        Ok(())
    }

    pub async fn download_file(&self, url: &str) -> Result<(Vec<u8>, String), AppError> {
        let resp = self
            .http_client
            .get(url)
            .timeout(Duration::from_secs(15))
            .send()
            .await
            .map_err(|e| AppError::service_unavailable(format!("Failed to download file: {e}")))?
            .error_for_status()
            .map_err(|e| AppError::service_unavailable(format!("Download failed: {e}")))?;

        let content_type = resp
            .headers()
            .get("content-type")
            .and_then(|v| v.to_str().ok())
            .unwrap_or("application/octet-stream")
            .to_string();

        let bytes = resp
            .bytes()
            .await
            .map_err(|e| AppError::service_unavailable(format!("Failed to read file: {e}")))?;

        Ok((bytes.to_vec(), content_type))
    }
}

pub fn file_extension(filename: &str) -> String {
    filename
        .rfind('.')
        .map(|i| filename[i..].to_string())
        .unwrap_or_default()
}

pub fn mime_from_extension(ext: &str) -> &'static str {
    match ext.to_lowercase().as_str() {
        ".jpg" | ".jpeg" => "image/jpeg",
        ".png" => "image/png",
        ".gif" => "image/gif",
        ".webp" => "image/webp",
        ".mp3" => "audio/mpeg",
        ".m4a" => "audio/mp4",
        ".wav" => "audio/wav",
        ".ogg" => "audio/ogg",
        _ => "application/octet-stream",
    }
}
