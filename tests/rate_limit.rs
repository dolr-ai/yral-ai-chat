mod common;

use common::*;

#[tokio::test]
async fn test_rate_limit_headers_present() {
    let base = base_url();
    let client = http_client();

    let resp = client
        .get(format!("{base}/api/v1/influencers"))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let headers = resp.headers();
    assert!(headers.contains_key("x-ratelimit-limit-minute"));
    assert!(headers.contains_key("x-ratelimit-limit-hour"));
    assert!(headers.contains_key("x-ratelimit-remaining-minute"));
    assert!(headers.contains_key("x-ratelimit-remaining-hour"));

    let limit_min: u32 = headers["x-ratelimit-limit-minute"]
        .to_str()
        .unwrap()
        .parse()
        .unwrap();
    assert!(limit_min > 0);
}

#[tokio::test]
async fn test_rate_limit_excluded_paths() {
    let base = base_url();
    let client = http_client();

    let resp = client.get(format!("{base}/health")).send().await.unwrap();
    assert_eq!(resp.status(), 200);

    // Health endpoints should not have rate limit headers
    assert!(!resp.headers().contains_key("x-ratelimit-limit-minute"));
}

#[tokio::test]
async fn test_rate_limit_remaining_decreases() {
    let base = base_url();
    let client = http_client();

    let resp1 = client
        .get(format!("{base}/api/v1/influencers"))
        .send()
        .await
        .unwrap();
    assert_eq!(resp1.status(), 200);
    let remaining1: u32 = resp1.headers()["x-ratelimit-remaining-minute"]
        .to_str()
        .unwrap()
        .parse()
        .unwrap();

    let resp2 = client
        .get(format!("{base}/api/v1/influencers"))
        .send()
        .await
        .unwrap();
    assert_eq!(resp2.status(), 200);
    let remaining2: u32 = resp2.headers()["x-ratelimit-remaining-minute"]
        .to_str()
        .unwrap()
        .parse()
        .unwrap();

    assert!(remaining2 <= remaining1);
}
