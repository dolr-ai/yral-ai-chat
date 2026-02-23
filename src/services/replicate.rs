use serde::{Deserialize, Serialize};

use crate::error::AppError;

#[derive(Clone)]
pub struct ReplicateClient {
    http: reqwest::Client,
    api_token: String,
    model: String,
    configured: bool,
}

#[derive(Serialize)]
struct PredictionRequest {
    input: serde_json::Value,
}

#[derive(Deserialize)]
struct PredictionResponse {
    id: String,
    status: String,
    output: Option<serde_json::Value>,
    urls: Option<PredictionUrls>,
}

#[derive(Deserialize)]
struct PredictionUrls {
    get: Option<String>,
}

impl ReplicateClient {
    pub fn new(http: reqwest::Client, api_token: &str, model: &str) -> Self {
        Self {
            http,
            configured: !api_token.is_empty(),
            api_token: api_token.to_string(),
            model: model.to_string(),
        }
    }

    pub fn is_configured(&self) -> bool {
        self.configured
    }

    pub async fn generate_image(
        &self,
        prompt: &str,
        aspect_ratio: &str,
    ) -> Result<Option<String>, AppError> {
        self.run_prediction(
            &self.model,
            serde_json::json!({
                "prompt": prompt,
                "go_fast": true,
                "megapixels": "1",
                "aspect_ratio": aspect_ratio,
                "output_format": "jpg",
                "output_quality": 80
            }),
        )
        .await
    }

    pub async fn generate_image_via_image(
        &self,
        prompt: &str,
        input_image: &str,
        aspect_ratio: &str,
    ) -> Result<Option<String>, AppError> {
        self.run_prediction(
            "black-forest-labs/flux-kontext-dev",
            serde_json::json!({
                "prompt": prompt,
                "go_fast": true,
                "guidance": 2.5,
                "megapixels": "1",
                "num_inference_steps": 30,
                "aspect_ratio": aspect_ratio,
                "output_format": "jpg",
                "output_quality": 80,
                "input_image": input_image
            }),
        )
        .await
    }

    async fn run_prediction(
        &self,
        model: &str,
        input: serde_json::Value,
    ) -> Result<Option<String>, AppError> {
        if !self.configured {
            return Ok(None);
        }

        let url = format!("https://api.replicate.com/v1/models/{model}/predictions");

        let resp = self
            .http
            .post(&url)
            .header("Authorization", format!("Bearer {}", self.api_token))
            .header("Prefer", "wait")
            .json(&PredictionRequest { input })
            .timeout(std::time::Duration::from_secs(120))
            .send()
            .await
            .map_err(|e| AppError::service_unavailable(format!("Replicate API error: {e}")))?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            tracing::error!(status = %status, body = %body, "Replicate API error");
            return Err(AppError::service_unavailable(format!(
                "Replicate API returned {status}"
            )));
        }

        let prediction: PredictionResponse = resp.json().await.map_err(|e| {
            AppError::service_unavailable(format!("Failed to parse Replicate response: {e}"))
        })?;

        // If "Prefer: wait" didn't resolve, poll
        if prediction.status == "starting" || prediction.status == "processing" {
            if let Some(urls) = &prediction.urls
                && let Some(get_url) = &urls.get
            {
                return self.poll_prediction(get_url).await;
            }
            return self
                .poll_prediction(&format!(
                    "https://api.replicate.com/v1/predictions/{}",
                    prediction.id
                ))
                .await;
        }

        Ok(extract_output_url(&prediction.output))
    }

    async fn poll_prediction(&self, url: &str) -> Result<Option<String>, AppError> {
        for _ in 0..30 {
            tokio::time::sleep(std::time::Duration::from_secs(2)).await;

            let resp = self
                .http
                .get(url)
                .header("Authorization", format!("Bearer {}", self.api_token))
                .timeout(std::time::Duration::from_secs(10))
                .send()
                .await
                .map_err(|e| AppError::service_unavailable(format!("Replicate poll error: {e}")))?;

            let prediction: PredictionResponse = resp.json().await.map_err(|e| {
                AppError::service_unavailable(format!("Replicate poll parse error: {e}"))
            })?;

            match prediction.status.as_str() {
                "succeeded" => return Ok(extract_output_url(&prediction.output)),
                "failed" | "canceled" => {
                    return Err(AppError::service_unavailable("Image generation failed"));
                }
                _ => continue,
            }
        }

        Err(AppError::service_unavailable("Image generation timed out"))
    }
}

fn extract_output_url(output: &Option<serde_json::Value>) -> Option<String> {
    match output {
        Some(serde_json::Value::Array(arr)) => {
            arr.first().and_then(|v| v.as_str().map(String::from))
        }
        Some(serde_json::Value::String(s)) => Some(s.clone()),
        _ => None,
    }
}
