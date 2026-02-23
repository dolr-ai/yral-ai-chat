mod common;

use common::*;
use serde_json::json;

#[tokio::test]
async fn test_valid_yral_token() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;

    let resp = client
        .post(format!("{base}/api/v1/chat/conversations"))
        .header("Authorization", auth_header("test_user_valid"))
        .json(&json!({"influencer_id": influencer_id}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 201);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["user_id"], "test_user_valid");
}

#[tokio::test]
async fn test_valid_dolr_token() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;

    let token = generate_token_with_issuer("test_user_dolr", "https://auth.dolr.ai");
    let resp = client
        .post(format!("{base}/api/v1/chat/conversations"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&json!({"influencer_id": influencer_id}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 201);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["user_id"], "test_user_dolr");
}

#[tokio::test]
async fn test_missing_authorization_header() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;

    let resp = client
        .post(format!("{base}/api/v1/chat/conversations"))
        .json(&json!({"influencer_id": influencer_id}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 401);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert!(data["detail"]
        .as_str()
        .unwrap()
        .contains("Missing authorization header"));
}

#[tokio::test]
async fn test_invalid_authorization_format() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;

    let resp = client
        .post(format!("{base}/api/v1/chat/conversations"))
        .header("Authorization", "invalid_format")
        .json(&json!({"influencer_id": influencer_id}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 401);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert!(data["detail"]
        .as_str()
        .unwrap()
        .contains("Invalid authorization header format"));
}

#[tokio::test]
async fn test_invalid_jwt_token() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;

    let resp = client
        .post(format!("{base}/api/v1/chat/conversations"))
        .header("Authorization", "Bearer invalid.token.value")
        .json(&json!({"influencer_id": influencer_id}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 401);
}

#[tokio::test]
async fn test_expired_token() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;

    let token = generate_expired_token("test_user");
    let resp = client
        .post(format!("{base}/api/v1/chat/conversations"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&json!({"influencer_id": influencer_id}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 401);
}

#[tokio::test]
async fn test_wrong_issuer() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;

    let token = generate_token_with_issuer("test_user", "wrong_issuer");
    let resp = client
        .post(format!("{base}/api/v1/chat/conversations"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&json!({"influencer_id": influencer_id}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 401);
}

#[tokio::test]
async fn test_missing_sub_claim() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;

    let token = generate_token_without_sub();
    let resp = client
        .post(format!("{base}/api/v1/chat/conversations"))
        .header("Authorization", format!("Bearer {token}"))
        .json(&json!({"influencer_id": influencer_id}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 401);
}

#[tokio::test]
async fn test_list_conversations_without_auth() {
    let base = base_url();
    let client = http_client();

    let resp = client
        .get(format!("{base}/api/v1/chat/conversations"))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 401);
}

#[tokio::test]
async fn test_send_message_without_auth() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let conv_id = create_test_conversation(&client, &base, &user, &influencer_id).await;

    // Try to send without auth
    let resp = client
        .post(format!(
            "{base}/api/v1/chat/conversations/{conv_id}/messages"
        ))
        .json(&json!({"content": "Hello!", "message_type": "text"}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 401);
}
