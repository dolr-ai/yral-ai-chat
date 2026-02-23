mod common;

use common::*;
use serde_json::json;

#[tokio::test]
async fn test_list_influencers_default_pagination() {
    let base = base_url();
    let client = http_client();

    let resp = client
        .get(format!("{base}/api/v1/influencers"))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["limit"], 50);
    assert_eq!(data["offset"], 0);
    assert!(data["total"].as_i64().unwrap() > 0);
    assert!(data["influencers"].as_array().unwrap().len() > 0);
}

#[tokio::test]
async fn test_list_influencers_custom_pagination() {
    let base = base_url();
    let client = http_client();

    let resp = client
        .get(format!("{base}/api/v1/influencers?limit=2&offset=1"))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["limit"], 2);
    assert_eq!(data["offset"], 1);
    assert!(data["influencers"].as_array().unwrap().len() <= 2);
}

#[tokio::test]
async fn test_list_influencers_response_structure() {
    let base = base_url();
    let client = http_client();

    let resp = client
        .get(format!("{base}/api/v1/influencers?limit=1"))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    let influencer = &data["influencers"][0];

    assert!(influencer["id"].is_string());
    assert!(influencer["name"].is_string());
    assert!(influencer["display_name"].is_string());
    assert!(influencer["avatar_url"].is_string());
    assert!(influencer["description"].is_string());
    assert!(influencer["category"].is_string());
    assert!(influencer["is_active"].is_string());
    assert!(influencer["created_at"].is_string());

    let status = influencer["is_active"].as_str().unwrap();
    assert!(
        status == "active" || status == "coming_soon" || status == "discontinued",
        "Unexpected status: {status}"
    );
}

#[tokio::test]
async fn test_get_single_influencer() {
    let base = base_url();
    let client = http_client();
    let influencer_id = get_test_influencer_id(&client, &base).await;

    let resp = client
        .get(format!("{base}/api/v1/influencers/{influencer_id}"))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["id"].as_str().unwrap(), influencer_id);
    assert!(data["name"].is_string());
    assert!(data["display_name"].is_string());
}

#[tokio::test]
async fn test_get_nonexistent_influencer() {
    let base = base_url();
    let client = http_client();

    let resp = client
        .get(format!(
            "{base}/api/v1/influencers/00000000-0000-0000-0000-000000000000"
        ))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 404);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["error"], "not_found");
}

#[tokio::test]
async fn test_list_trending_influencers() {
    let base = base_url();
    let client = http_client();

    let resp = client
        .get(format!("{base}/api/v1/influencers/trending"))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert!(data["influencers"].is_array());
}

#[tokio::test]
async fn test_list_influencers_pagination_consistency() {
    let base = base_url();
    let client = http_client();

    let resp1 = client
        .get(format!("{base}/api/v1/influencers?limit=2&offset=0"))
        .send()
        .await
        .unwrap();
    let data1: serde_json::Value = resp1.json().await.unwrap();

    let resp2 = client
        .get(format!("{base}/api/v1/influencers?limit=2&offset=2"))
        .send()
        .await
        .unwrap();
    let data2: serde_json::Value = resp2.json().await.unwrap();

    assert_eq!(data1["total"], data2["total"]);

    if data1["total"].as_i64().unwrap() > 2 && !data2["influencers"].as_array().unwrap().is_empty()
    {
        assert_ne!(data1["influencers"][0]["id"], data2["influencers"][0]["id"]);
    }
}

// --- Auth-required endpoints ---

#[tokio::test]
async fn test_generate_prompt_unauthorized() {
    let base = base_url();
    let client = http_client();

    let resp = client
        .post(format!("{base}/api/v1/influencers/generate-prompt"))
        .json(&json!({"prompt": "A character concept"}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 401);
}

#[tokio::test]
async fn test_validate_metadata_unauthorized() {
    let base = base_url();
    let client = http_client();

    let resp = client
        .post(format!(
            "{base}/api/v1/influencers/validate-and-generate-metadata"
        ))
        .json(&json!({"system_instructions": "Some instructions"}))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 401);
}

#[tokio::test]
async fn test_create_influencer_unauthorized() {
    let base = base_url();
    let client = http_client();

    let resp = client
        .post(format!("{base}/api/v1/influencers/create"))
        .json(&json!({
            "bot_principal_id": "unauth-bot",
            "name": "unauthbot",
            "display_name": "Unauth Bot",
            "system_instructions": "You are unauthorized.",
            "category": "test",
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 401);
}

#[tokio::test]
async fn test_create_influencer_success() {
    let base = base_url();
    let client = http_client();
    let owner = unique_user();
    let bot_id = unique_bot_id();

    let resp = client
        .post(format!("{base}/api/v1/influencers/create"))
        .header("Authorization", auth_header(&owner))
        .json(&json!({
            "bot_principal_id": bot_id,
            "parent_principal_id": owner,
            "name": format!("bot{}", &bot_id[9..]),
            "display_name": "Test Bot",
            "description": "A test bot",
            "system_instructions": "You are a helpful assistant.",
            "category": "general",
            "avatar_url": "https://example.com/avatar.jpg",
            "initial_greeting": "Hello!",
            "suggested_messages": ["Tell me a joke"],
            "personality_traits": {"friendly": true},
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert!(data["id"].is_string());
    assert!(data["name"].is_string());
    assert!(data["display_name"].is_string());
}

#[tokio::test]
async fn test_create_influencer_parent_id_override() {
    let base = base_url();
    let client = http_client();
    let user_id = unique_user();
    let bot_id = unique_bot_id();

    let resp = client
        .post(format!("{base}/api/v1/influencers/create"))
        .header("Authorization", auth_header(&user_id))
        .json(&json!({
            "bot_principal_id": bot_id,
            "parent_principal_id": "fake_parent_id",
            "name": format!("ovr{}", &bot_id[9..]),
            "display_name": "Override Bot",
            "description": "Bot to test parent_id override",
            "system_instructions": "You are a test bot.",
            "category": "test",
            "avatar_url": "https://example.com/avatar.jpg",
            "initial_greeting": "Hello",
            "suggested_messages": ["Hi"],
            "personality_traits": {},
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["parent_principal_id"].as_str().unwrap(), user_id);
}

#[tokio::test]
async fn test_delete_influencer_unauthorized() {
    let base = base_url();
    let client = http_client();

    let resp = client
        .delete(format!("{base}/api/v1/influencers/some-id"))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 401);
}

#[tokio::test]
async fn test_delete_influencer_not_found() {
    let base = base_url();
    let client = http_client();

    let resp = client
        .delete(format!("{base}/api/v1/influencers/non-existent-id"))
        .header("Authorization", auth_header("someone"))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 404);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["error"], "not_found");
}

#[tokio::test]
async fn test_delete_influencer_success() {
    let base = base_url();
    let client = http_client();
    let owner = unique_user();
    let bot_id = unique_bot_id();

    // Create
    let resp = client
        .post(format!("{base}/api/v1/influencers/create"))
        .header("Authorization", auth_header(&owner))
        .json(&json!({
            "bot_principal_id": bot_id,
            "parent_principal_id": owner,
            "name": format!("del{}", &bot_id[9..]),
            "display_name": "Bot to Delete",
            "description": "A test bot for deletion",
            "system_instructions": "You are a helpful assistant.",
            "category": "general",
            "avatar_url": "https://example.com/avatar.jpg",
            "initial_greeting": "Hello!",
            "suggested_messages": ["Tell me a joke"],
            "personality_traits": {"friendly": true},
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);
    let influencer_id = resp.json::<serde_json::Value>().await.unwrap()["id"]
        .as_str()
        .unwrap()
        .to_string();

    // Delete
    let resp = client
        .delete(format!("{base}/api/v1/influencers/{influencer_id}"))
        .header("Authorization", auth_header(&owner))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);

    let data: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(data["id"].as_str().unwrap(), influencer_id);
    assert_eq!(data["display_name"], "Deleted Bot");
    assert_eq!(data["is_active"], "discontinued");
}

#[tokio::test]
async fn test_delete_influencer_forbidden() {
    let base = base_url();
    let client = http_client();
    let owner = unique_user();
    let bot_id = unique_bot_id();

    // Create as owner
    let resp = client
        .post(format!("{base}/api/v1/influencers/create"))
        .header("Authorization", auth_header(&owner))
        .json(&json!({
            "bot_principal_id": bot_id,
            "parent_principal_id": owner,
            "name": format!("frb{}", &bot_id[9..]),
            "display_name": "Bot for Forbidden Test",
            "description": "A test bot",
            "system_instructions": "You are a helpful assistant.",
            "category": "general",
            "avatar_url": "https://example.com/avatar.jpg",
            "initial_greeting": "Hello!",
            "suggested_messages": ["Tell me a joke"],
            "personality_traits": {},
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200);
    let influencer_id = resp.json::<serde_json::Value>().await.unwrap()["id"]
        .as_str()
        .unwrap()
        .to_string();

    // Try to delete as different user
    let resp = client
        .delete(format!("{base}/api/v1/influencers/{influencer_id}"))
        .header("Authorization", auth_header("different_user"))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 403);
}
