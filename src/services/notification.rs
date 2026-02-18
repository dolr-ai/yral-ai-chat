/// Push notification service via Yral Metadata Server.
#[derive(Clone)]
pub struct PushNotificationService {
    http: reqwest::Client,
    metadata_url: String,
    auth_token: Option<String>,
    configured: bool,
}

impl PushNotificationService {
    pub fn new(http: reqwest::Client, metadata_url: &str, auth_token: Option<String>) -> Self {
        let configured = auth_token.as_ref().is_some_and(|t| !t.is_empty());
        Self {
            http,
            metadata_url: metadata_url.to_string(),
            auth_token,
            configured,
        }
    }

    pub async fn send_push_notification(
        &self,
        user_id: &str,
        title: &str,
        body: &str,
        data: Option<&serde_json::Value>,
    ) -> bool {
        if !self.configured {
            return false;
        }

        let url = format!("{}/notifications/{user_id}/send", self.metadata_url);

        let mut payload = serde_json::json!({
            "data": {
                "title": title,
                "body": body,
            }
        });

        if let Some(extra) = data {
            if let Some(obj) = extra.as_object() {
                if let Some(data_obj) = payload["data"].as_object_mut() {
                    for (k, v) in obj {
                        data_obj.insert(k.clone(), v.clone());
                    }
                }
            }
        }

        let mut req = self
            .http
            .post(&url)
            .json(&payload)
            .timeout(std::time::Duration::from_secs(10));

        if let Some(token) = &self.auth_token {
            req = req.header("Authorization", format!("Bearer {token}"));
        }

        match req.send().await {
            Ok(resp) if resp.status().is_success() => true,
            Ok(resp) => {
                tracing::error!(
                    status = %resp.status(),
                    user_id = %user_id,
                    "Push notification failed"
                );
                false
            }
            Err(e) => {
                tracing::error!(error = %e, user_id = %user_id, "Push notification error");
                false
            }
        }
    }
}
