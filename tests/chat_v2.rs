mod common;

use common::*;

#[tokio::test]
async fn test_list_conversations_v2() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let auth = auth_header(&user);

    // Create a conversation so there's data
    let _ = create_test_conversation(&client, &base, &user, &influencer_id).await;

    let resp = client
        .get(format!("{base}/api/v2/chat/conversations"))
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
async fn test_list_conversations_v2_with_pagination() {
    let base = base_url();
    let client = http_client();
    let auth = auth_header("test_user_default");

    let resp = client
        .get(format!(
            "{base}/api/v2/chat/conversations?limit=5&offset=0"
        ))
        .header("Authorization", &auth)
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert!(data["conversations"].as_array().unwrap().len() <= 5);
}

#[tokio::test]
async fn test_list_conversations_v2_response_structure() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let auth = auth_header(&user);

    let _ = create_test_conversation(&client, &base, &user, &influencer_id).await;

    let resp = client
        .get(format!("{base}/api/v2/chat/conversations"))
        .header("Authorization", &auth)
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    let conv = &data["conversations"][0];

    // V2-specific fields
    assert!(conv["id"].is_string());
    assert!(conv["user_id"].is_string());
    assert!(conv["influencer_id"].is_string());
    assert!(conv["influencer"].is_object());
    assert!(conv["created_at"].is_string());
    assert!(conv["updated_at"].is_string());
    assert!(conv["unread_count"].is_number());

    let influencer = &conv["influencer"];
    assert!(influencer["id"].is_string());
    assert!(influencer["display_name"].is_string());
    assert!(influencer["avatar_url"].is_string());
    assert!(influencer["is_online"].is_boolean());
}

#[tokio::test]
async fn test_list_conversations_v2_filtered_by_influencer() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;
    let user = unique_user();
    let auth = auth_header(&user);

    let _ = create_test_conversation(&client, &base, &user, &influencer_id).await;

    let resp = client
        .get(format!(
            "{base}/api/v2/chat/conversations?influencer_id={influencer_id}"
        ))
        .header("Authorization", &auth)
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    for conv in data["conversations"].as_array().unwrap() {
        assert_eq!(conv["influencer"]["id"].as_str().unwrap(), influencer_id);
    }
}
