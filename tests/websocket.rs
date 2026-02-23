mod common;

use common::*;
use futures_util::{SinkExt, StreamExt};
use tokio_tungstenite::{
    connect_async,
    tungstenite::protocol::{Message, frame::coding::CloseCode},
};

/// Convert HTTP base URL to WebSocket URL.
fn ws_url(base: &str, path: &str) -> String {
    base.replace("https://", "wss://")
        .replace("http://", "ws://")
        + path
}

fn close_code_u16(code: CloseCode) -> u16 {
    u16::from(code)
}

#[tokio::test]
async fn test_websocket_missing_token() {
    let base = base_url();
    let url = ws_url(&base, "/api/v1/chat/ws/inbox/user123");

    match connect_async(&url).await {
        Ok((mut ws, _)) => {
            if let Some(Ok(msg)) = ws.next().await {
                if let Message::Close(Some(frame)) = msg {
                    assert_eq!(close_code_u16(frame.code), 4001, "Expected close code 4001");
                }
            }
        }
        Err(_) => {
            // Connection rejected at HTTP level - also acceptable
        }
    }
}

#[tokio::test]
async fn test_websocket_invalid_token() {
    let base = base_url();
    let url = ws_url(&base, "/api/v1/chat/ws/inbox/user123?token=invalid-token");

    match connect_async(&url).await {
        Ok((mut ws, _)) => {
            if let Some(Ok(msg)) = ws.next().await {
                if let Message::Close(Some(frame)) = msg {
                    assert_eq!(close_code_u16(frame.code), 4001, "Expected close code 4001");
                }
            }
        }
        Err(_) => {}
    }
}

#[tokio::test]
async fn test_websocket_wrong_user() {
    let base = base_url();
    let token = generate_test_token("user456");
    let url = ws_url(
        &base,
        &format!("/api/v1/chat/ws/inbox/user123?token={token}"),
    );

    match connect_async(&url).await {
        Ok((mut ws, _)) => {
            if let Some(Ok(msg)) = ws.next().await {
                if let Message::Close(Some(frame)) = msg {
                    assert_eq!(close_code_u16(frame.code), 4003, "Expected close code 4003");
                }
            }
        }
        Err(_) => {}
    }
}

#[tokio::test]
async fn test_websocket_authorized_success() {
    let base = base_url();
    let user_id = "ws_test_user_123";
    let token = generate_test_token(user_id);
    let url = ws_url(
        &base,
        &format!("/api/v1/chat/ws/inbox/{user_id}?token={token}"),
    );

    let (mut ws, _) = connect_async(&url)
        .await
        .expect("WebSocket connection should succeed with valid token");

    // Send a ping to verify the connection is alive
    ws.send(Message::Ping(vec![1, 2, 3].into()))
        .await
        .expect("Should be able to send ping");

    // Wait for pong (with timeout)
    let msg = tokio::time::timeout(std::time::Duration::from_secs(5), ws.next())
        .await
        .expect("Should get a response within 5s");

    if let Some(Ok(Message::Pong(_))) = msg {
        // Got pong - connection is alive
    } else if let Some(Ok(Message::Close(Some(frame)))) = msg {
        let code = close_code_u16(frame.code);
        if code == 4001 || code == 4003 {
            panic!(
                "WebSocket auth rejected: code={}, reason={}",
                code, frame.reason
            );
        }
    }

    let _ = ws.close(None).await;
}
