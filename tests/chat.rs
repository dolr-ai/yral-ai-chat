mod common;

use common::*;
use serde_json::json;

#[tokio::test]
async fn test_create_conversation() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();

    let resp = client
        .post(format!("{base}/api/v1/chat/conversations"))
        .header("Authorization", auth_header(&user))
        .json(&json!({"influencer_id": influencer_id}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 201);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert!(data["id"].is_string());
    assert_eq!(data["user_id"].as_str().unwrap(), user);
    assert!(data["created_at"].is_string());
    assert!(data["updated_at"].is_string());

    let influencer = &data["influencer"];
    assert_eq!(influencer["id"].as_str().unwrap(), influencer_id);
    assert!(influencer["display_name"].is_string());
    assert!(influencer["avatar_url"].is_string());
    assert!(influencer["name"].is_string());
}

#[tokio::test]
async fn test_create_conversation_returns_existing() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let auth = auth_header(&user);

    let resp1 = client
        .post(format!("{base}/api/v1/chat/conversations"))
        .header("Authorization", &auth)
        .json(&json!({"influencer_id": influencer_id}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp1.status(), 201);
    let id1 = resp1.json::<serde_json::Value>().await.unwrap()["id"]
        .as_str()
        .unwrap()
        .to_string();

    let resp2 = client
        .post(format!("{base}/api/v1/chat/conversations"))
        .header("Authorization", &auth)
        .json(&json!({"influencer_id": influencer_id}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp2.status(), 201);
    let id2 = resp2.json::<serde_json::Value>().await.unwrap()["id"]
        .as_str()
        .unwrap()
        .to_string();

    assert_eq!(id1, id2);
}

#[tokio::test]
async fn test_list_conversations() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let auth = auth_header(&user);

    // Create a conversation first
    let _ = create_test_conversation(&client, &base, &user, &influencer_id).await;

    let resp = client
        .get(format!("{base}/api/v1/chat/conversations"))
        .header("Authorization", &auth)
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert!(data["conversations"].is_array());
    assert!(data["total"].is_number());
    assert!(!data["conversations"].as_array().unwrap().is_empty());
}

#[tokio::test]
async fn test_list_conversations_with_pagination() {
    let base = base_url();
    let client = http_client();
    let auth = auth_header("test_user_default");

    let resp = client
        .get(format!("{base}/api/v1/chat/conversations?limit=5&offset=0"))
        .header("Authorization", &auth)
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert!(data["conversations"].as_array().unwrap().len() <= 5);
}

#[tokio::test]
async fn test_list_conversations_response_structure() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let auth = auth_header(&user);

    let _ = create_test_conversation(&client, &base, &user, &influencer_id).await;

    let resp = client
        .get(format!("{base}/api/v1/chat/conversations"))
        .header("Authorization", &auth)
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    let conv = &data["conversations"][0];

    assert!(conv["id"].is_string());
    assert!(conv["user_id"].is_string());
    assert!(conv["influencer"].is_object());
    assert!(conv["created_at"].is_string());
    assert!(conv["updated_at"].is_string());
    assert!(conv["message_count"].is_number());
    assert!(conv["recent_messages"].is_array());

    let influencer = &conv["influencer"];
    assert!(influencer["id"].is_string());
    assert!(influencer["display_name"].is_string());
    assert!(influencer["avatar_url"].is_string());
    assert!(influencer["name"].is_string());
}

#[tokio::test]
async fn test_list_messages() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let auth = auth_header(&user);
    let conv_id = create_test_conversation(&client, &base, &user, &influencer_id).await;

    let resp = client
        .get(format!(
            "{base}/api/v1/chat/conversations/{conv_id}/messages"
        ))
        .header("Authorization", &auth)
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["conversation_id"].as_str().unwrap(), conv_id);
    assert!(data["messages"].is_array());
    assert!(data["total"].is_number());
    assert_eq!(data["limit"], 50);
    assert_eq!(data["offset"], 0);
}

#[tokio::test]
async fn test_list_messages_with_pagination() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let auth = auth_header(&user);
    let conv_id = create_test_conversation(&client, &base, &user, &influencer_id).await;

    let resp = client
        .get(format!(
            "{base}/api/v1/chat/conversations/{conv_id}/messages?limit=10&offset=0"
        ))
        .header("Authorization", &auth)
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["limit"], 10);
    assert_eq!(data["offset"], 0);
    assert!(data["messages"].as_array().unwrap().len() <= 10);
}

#[tokio::test]
async fn test_send_text_message() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let auth = auth_header(&user);
    let conv_id = create_test_conversation(&client, &base, &user, &influencer_id).await;

    let resp = client
        .post(format!(
            "{base}/api/v1/chat/conversations/{conv_id}/messages"
        ))
        .header("Authorization", &auth)
        .json(&json!({"content": "Hello, this is a test message!", "message_type": "text"}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();

    let user_msg = &data["user_message"];
    assert_eq!(user_msg["role"], "user");
    assert_eq!(user_msg["content"], "Hello, this is a test message!");
    assert_eq!(user_msg["message_type"], "text");
    assert!(user_msg["id"].is_string());
    assert!(user_msg["created_at"].is_string());

    let assistant_msg = &data["assistant_message"];
    assert_eq!(assistant_msg["role"], "assistant");
    assert_eq!(assistant_msg["message_type"], "text");
    assert!(assistant_msg["content"].as_str().unwrap().len() > 0);
    assert!(assistant_msg["id"].is_string());
    assert!(assistant_msg["created_at"].is_string());
}

#[tokio::test]
async fn test_send_message_response_structure() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let auth = auth_header(&user);
    let conv_id = create_test_conversation(&client, &base, &user, &influencer_id).await;

    let resp = client
        .post(format!(
            "{base}/api/v1/chat/conversations/{conv_id}/messages"
        ))
        .header("Authorization", &auth)
        .json(&json!({"content": "Test structure", "message_type": "text"}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    let msg = &data["user_message"];

    assert!(msg["id"].is_string());
    assert!(msg["role"].is_string());
    assert!(msg["content"].is_string());
    assert!(msg["message_type"].is_string());
    assert!(msg["media_urls"].is_array());
    assert!(msg["created_at"].is_string());
    // audio_url and audio_duration_seconds may be null
    assert!(msg.get("audio_url").is_some());
    assert!(msg.get("audio_duration_seconds").is_some());
    assert!(msg.get("token_count").is_some());
}

#[tokio::test]
async fn test_send_message_validation_error_empty_content() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let auth = auth_header(&user);
    let conv_id = create_test_conversation(&client, &base, &user, &influencer_id).await;

    let resp = client
        .post(format!(
            "{base}/api/v1/chat/conversations/{conv_id}/messages"
        ))
        .header("Authorization", &auth)
        .json(&json!({"content": "", "message_type": "text"}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 422);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["error"], "validation_error");
}

#[tokio::test]
async fn test_send_message_validation_error_invalid_type() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let auth = auth_header(&user);
    let conv_id = create_test_conversation(&client, &base, &user, &influencer_id).await;

    let resp = client
        .post(format!(
            "{base}/api/v1/chat/conversations/{conv_id}/messages"
        ))
        .header("Authorization", &auth)
        .json(&json!({"content": "Test", "message_type": "invalid_type"}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 422);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["error"], "validation_error");
}

#[tokio::test]
async fn test_send_message_to_nonexistent_conversation() {
    let base = base_url();
    let client = http_client();
    let auth = auth_header("someone");
    let fake = "00000000-0000-0000-0000-000000000000";

    let resp = client
        .post(format!("{base}/api/v1/chat/conversations/{fake}/messages"))
        .header("Authorization", &auth)
        .json(&json!({"content": "Test", "message_type": "text"}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 404);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["error"], "not_found");
}

#[tokio::test]
async fn test_delete_conversation() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let auth = auth_header(&user);
    let conv_id = create_test_conversation(&client, &base, &user, &influencer_id).await;

    let resp = client
        .delete(format!("{base}/api/v1/chat/conversations/{conv_id}"))
        .header("Authorization", &auth)
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert!(data["success"].as_bool().unwrap());
    assert_eq!(data["deleted_conversation_id"].as_str().unwrap(), conv_id);
    assert!(data["deleted_messages_count"].is_number());
}

#[tokio::test]
async fn test_delete_nonexistent_conversation() {
    let base = base_url();
    let client = http_client();
    let auth = auth_header("someone");
    let fake = "00000000-0000-0000-0000-000000000000";

    let resp = client
        .delete(format!("{base}/api/v1/chat/conversations/{fake}"))
        .header("Authorization", &auth)
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 404);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["error"], "not_found");
}

#[tokio::test]
async fn test_message_content_not_duplicated() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let auth = auth_header(&user);
    let conv_id = create_test_conversation(&client, &base, &user, &influencer_id).await;

    let resp = client
        .post(format!(
            "{base}/api/v1/chat/conversations/{conv_id}/messages"
        ))
        .header("Authorization", &auth)
        .json(&json!({"content": "80", "message_type": "text"}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["user_message"]["content"], "80");
    assert!(
        !data["user_message"]["content"]
            .as_str()
            .unwrap()
            .contains("8080")
    );
}

#[tokio::test]
async fn test_send_message_accepts_uppercase_text_type() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let auth = auth_header(&user);
    let conv_id = create_test_conversation(&client, &base, &user, &influencer_id).await;

    for input_type in ["TEXT", "Text", "text"] {
        let resp = client
            .post(format!(
                "{base}/api/v1/chat/conversations/{conv_id}/messages"
            ))
            .header("Authorization", &auth)
            .json(&json!({"content": "Test", "message_type": input_type}))
            .send()
            .await
            .unwrap();
        assert_eq!(
            resp.status(),
            200,
            "Message type '{input_type}' should be accepted"
        );

        let data: serde_json::Value = resp.json().await.unwrap();
        assert_eq!(data["user_message"]["message_type"], "text");
    }
}
