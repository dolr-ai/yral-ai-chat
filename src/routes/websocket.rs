use std::collections::HashMap;
use std::sync::Arc;

use axum::extract::ws::{CloseFrame, Message, WebSocket};
use axum::extract::{Path, Query, State, WebSocketUpgrade};
use axum::http::StatusCode;
use axum::response::IntoResponse;

use crate::AppState;
use crate::middleware;

pub async fn ws_inbox(
    State(state): State<Arc<AppState>>,
    Path(user_id): Path<String>,
    Query(params): Query<HashMap<String, String>>,
    ws: WebSocketUpgrade,
) -> impl IntoResponse {
    // Validate JWT from ?token= query param
    let token = match params.get("token") {
        Some(t) if !t.is_empty() => t.clone(),
        _ => {
            return ws.on_upgrade(|mut socket| async move {
                let _ = socket
                    .send(Message::Close(Some(CloseFrame {
                        code: 4001,
                        reason: "Missing authentication token".into(),
                    })))
                    .await;
            });
        }
    };

    let claims = match middleware::decode_jwt(&token) {
        Ok(c) => c,
        Err(_) => {
            return ws.on_upgrade(|mut socket| async move {
                let _ = socket
                    .send(Message::Close(Some(CloseFrame {
                        code: 4001,
                        reason: "Invalid or expired token".into(),
                    })))
                    .await;
            });
        }
    };

    // Verify path user_id matches JWT subject
    if claims.sub != user_id {
        return ws.on_upgrade(|mut socket| async move {
            let _ = socket
                .send(Message::Close(Some(CloseFrame {
                    code: 4003,
                    reason: "Forbidden".into(),
                })))
                .await;
        });
    }

    ws.on_upgrade(move |socket| handle_socket(state, user_id, socket))
}

async fn handle_socket(state: Arc<AppState>, user_id: String, mut socket: WebSocket) {
    let (conn_id, mut rx) = state.ws_manager.connect(&user_id);

    tracing::info!(user_id = %user_id, conn_id = conn_id, "WebSocket connected");

    loop {
        tokio::select! {
            // Forward events from WsManager to the WebSocket client
            msg = rx.recv() => {
                match msg {
                    Some(text) => {
                        if socket.send(Message::Text(text.into())).await.is_err() {
                            break;
                        }
                    }
                    None => break, // channel closed
                }
            }
            // Handle incoming messages from the client (or detect disconnect)
            incoming = socket.recv() => {
                match incoming {
                    Some(Ok(Message::Close(_))) | None => break,
                    Some(Ok(Message::Ping(data))) => {
                        if socket.send(Message::Pong(data)).await.is_err() {
                            break;
                        }
                    }
                    Some(Err(_)) => break,
                    _ => {} // ignore text/binary from client
                }
            }
        }
    }

    state.ws_manager.disconnect(&user_id, conn_id);
    tracing::info!(user_id = %user_id, conn_id = conn_id, "WebSocket disconnected");
}

/// Dummy endpoint that returns 418 to expose WebSocket event schemas (matches Python).
pub async fn ws_docs() -> (StatusCode, &'static str) {
    (StatusCode::IM_A_TEAPOT, "WebSocket documentation endpoint")
}
