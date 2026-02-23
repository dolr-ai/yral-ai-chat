mod common;

use common::{base_url, http_client};

#[tokio::test]
async fn test_root_endpoint() {
    let base = base_url();
    let client = http_client();

    let resp = client.get(format!("{base}/")).send().await.unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["service"], "Yral AI Chat API");
    assert_eq!(data["version"], "1.0.0");
    assert_eq!(data["docs"], "/docs");
}

#[tokio::test]
async fn test_health_endpoint() {
    let base = base_url();
    let client = http_client();

    let resp = client.get(format!("{base}/health")).send().await.unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert!(data["status"].is_string());
    let status = data["status"].as_str().unwrap();
    assert!(status == "healthy" || status == "unhealthy");
    assert!(data["timestamp"].is_string());
    assert!(data["services"]["database"]["status"].is_string());
    assert!(data["services"]["database"]["latency_ms"].is_number());
}

#[tokio::test]
async fn test_status_endpoint() {
    let base = base_url();
    let client = http_client();

    let resp = client.get(format!("{base}/status")).send().await.unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["service"], "Yral AI Chat API");
    assert_eq!(data["version"], "1.0.0");
    assert!(data["uptime_seconds"].is_number());
    assert!(data["timestamp"].is_string());

    // Database stats
    assert!(data["database"]["connected"].is_boolean());

    // Statistics
    assert!(data["statistics"]["total_conversations"].is_number());
    assert!(data["statistics"]["total_messages"].is_number());
    assert!(data["statistics"]["active_influencers"].is_number());
}

#[tokio::test]
async fn test_status_endpoint_environment() {
    let base = base_url();
    let client = http_client();

    let resp = client.get(format!("{base}/status")).send().await.unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    let env = data["environment"].as_str().unwrap();
    assert!(
        env == "development" || env == "staging" || env == "production",
        "Unexpected environment: {env}"
    );
}
