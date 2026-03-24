/// Google Chat webhook notification service.
#[derive(Clone)]
pub struct GoogleChatService {
    http: reqwest::Client,
    webhook_url: Option<String>,
}

impl GoogleChatService {
    pub fn new(http: reqwest::Client, webhook_url: Option<String>) -> Self {
        Self { http, webhook_url }
    }

    pub async fn send_message(&self, text: &str) {
        let Some(url) = &self.webhook_url else {
            return;
        };

        let payload = serde_json::json!({ "text": text });

        match self
            .http
            .post(url)
            .json(&payload)
            .timeout(std::time::Duration::from_secs(10))
            .send()
            .await
        {
            Ok(resp) if resp.status().is_success() => {}
            Ok(resp) => {
                tracing::error!(status = %resp.status(), "Google Chat webhook failed");
            }
            Err(e) => {
                tracing::error!(error = %e, "Google Chat webhook error");
            }
        }
    }

    pub async fn notify_influencer_banned(&self, influencer_id: &str, influencer_name: &str) {
        self.send_message(&format!(
            "🚫 AI Influencer banned\nID: {influencer_id}\nName: {influencer_name}"
        ))
        .await;
    }

    pub async fn notify_influencer_ban_failed(&self, influencer_id: &str, error: &str) {
        self.send_message(&format!(
            "❌ Failed to ban AI Influencer\nID: {influencer_id}\nError: {error}"
        ))
        .await;
    }

    pub async fn notify_influencer_unbanned(&self, influencer_id: &str, influencer_name: &str) {
        self.send_message(&format!(
            "✅ AI Influencer unbanned\nID: {influencer_id}\nName: {influencer_name}"
        ))
        .await;
    }

    pub async fn notify_influencer_unban_failed(&self, influencer_id: &str, error: &str) {
        self.send_message(&format!(
            "❌ Failed to unban AI Influencer\nID: {influencer_id}\nError: {error}"
        ))
        .await;
    }
}
