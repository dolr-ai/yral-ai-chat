use std::sync::atomic::{AtomicU64, Ordering};

use dashmap::DashMap;
use tokio::sync::mpsc;

static CONN_COUNTER: AtomicU64 = AtomicU64::new(0);

pub type WsSender = mpsc::UnboundedSender<String>;

struct Connection {
    id: u64,
    sender: WsSender,
}

pub struct WsManager {
    connections: DashMap<String, Vec<Connection>>,
}

impl WsManager {
    pub fn new() -> Self {
        Self {
            connections: DashMap::new(),
        }
    }

    /// Register a new WebSocket connection for a user.
    /// Returns (connection_id, receiver) — the receiver streams JSON messages to the WS client.
    pub fn connect(&self, user_id: &str) -> (u64, mpsc::UnboundedReceiver<String>) {
        let id = CONN_COUNTER.fetch_add(1, Ordering::Relaxed);
        let (tx, rx) = mpsc::unbounded_channel();

        self.connections
            .entry(user_id.to_string())
            .or_default()
            .push(Connection { id, sender: tx });

        (id, rx)
    }

    /// Remove a connection by user_id and connection id.
    pub fn disconnect(&self, user_id: &str, conn_id: u64) {
        if let Some(mut conns) = self.connections.get_mut(user_id) {
            conns.retain(|c| c.id != conn_id);
            if conns.is_empty() {
                drop(conns);
                self.connections.remove(user_id);
            }
        }
    }

    /// Send a JSON message to all connections for a user.
    fn send_to_user(&self, user_id: &str, message: &str) {
        if let Some(mut conns) = self.connections.get_mut(user_id) {
            conns.retain(|c| c.sender.send(message.to_string()).is_ok());
            if conns.is_empty() {
                drop(conns);
                self.connections.remove(user_id);
            }
        }
    }

    pub fn broadcast_new_message(
        &self,
        user_id: &str,
        conversation_id: &str,
        message: &serde_json::Value,
        influencer: &serde_json::Value,
        unread_count: i64,
    ) {
        let event = serde_json::json!({
            "event": "new_message",
            "data": {
                "conversation_id": conversation_id,
                "message": message,
                "influencer": influencer,
                "unread_count": unread_count,
            }
        });
        self.send_to_user(user_id, &event.to_string());
    }

    pub fn broadcast_conversation_read(
        &self,
        user_id: &str,
        conversation_id: &str,
        read_at: &str,
    ) {
        let event = serde_json::json!({
            "event": "conversation_read",
            "data": {
                "conversation_id": conversation_id,
                "unread_count": 0,
                "read_at": read_at,
            }
        });
        self.send_to_user(user_id, &event.to_string());
    }

    pub fn broadcast_typing_status(
        &self,
        user_id: &str,
        conversation_id: &str,
        influencer_id: &str,
        is_typing: bool,
    ) {
        let event = serde_json::json!({
            "event": "typing_status",
            "data": {
                "conversation_id": conversation_id,
                "influencer_id": influencer_id,
                "is_typing": is_typing,
            }
        });
        self.send_to_user(user_id, &event.to_string());
    }
}
