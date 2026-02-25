use std::collections::HashMap;
use std::time::Duration;

use aws_sdk_s3::Client;
use aws_sdk_s3::config::{Credentials, Region};
use aws_sdk_s3::presigning::PresigningConfig;
use aws_sdk_s3::primitives::ByteStream;

use crate::config::Settings;
use crate::error::AppError;

pub struct StorageService {
    client: Client,
    bucket: String,
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
        let creds = Credentials::new(
            &settings.aws_access_key_id,
            &settings.aws_secret_access_key,
            None,
            None,
            "yral_ai_chat",
        );

        let config = aws_sdk_s3::Config::builder()
            .behavior_version_latest()
            .region(Region::new(settings.aws_region.clone()))
            .endpoint_url(&settings.s3_endpoint_url)
            .credentials_provider(creds)
            .force_path_style(true)
            .build();

        let client = Client::from_conf(config);

        Ok(Self {
            client,
            bucket: settings.aws_s3_bucket.clone(),
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

        self.client
            .put_object()
            .bucket(&self.bucket)
            .key(&key)
            .body(ByteStream::from(file_bytes))
            .content_type(content_type)
            .content_length(size as i64)
            .send()
            .await
            .map_err(|e| AppError::service_unavailable(format!("S3 upload failed: {e}")))?;

        Ok((key, size))
    }

    pub async fn generate_presigned_url(&self, key: &str) -> String {
        if key.starts_with("http://") || key.starts_with("https://") {
            return key.to_string();
        }

        let expires =
            PresigningConfig::expires_in(Duration::from_secs(self.url_expires_seconds as u64))
                .expect("valid presigning config");

        match self
            .client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .presigned(expires)
            .await
        {
            Ok(presigned) => presigned.uri().to_string(),
            Err(e) => {
                tracing::error!(error = %e, key = key, "Failed to generate presigned URL");
                key.to_string()
            }
        }
    }

    pub async fn generate_presigned_urls_batch(&self, keys: &[String]) -> HashMap<String, String> {
        let mut map = HashMap::with_capacity(keys.len());
        for key in keys {
            let url = self.generate_presigned_url(key).await;
            map.insert(key.clone(), url);
        }
        map
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
