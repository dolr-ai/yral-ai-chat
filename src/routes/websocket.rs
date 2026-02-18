use std::sync::Arc;

use axum::extract::ws::{Message, WebSocket};
use axum::extract::{Path, State, WebSocketUpgrade};
use axum::response::IntoResponse;

use crate::AppState;

pub async fn ws_inbox(
    State(state): State<Arc<AppState>>,
    Path(user_id): Path<String>,
    ws: WebSocketUpgrade,
) -> impl IntoResponse {
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
