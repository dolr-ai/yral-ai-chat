use axum::{
    extract::{MatchedPath, Request},
    middleware::Next,
    response::Response,
};

/// Middleware that updates the Sentry transaction name to the matched route
/// pattern (e.g. `/api/v1/chat/conversations/{conversation_id}/messages`)
/// instead of the raw URI path with actual IDs.
///
/// Must be added via `route_layer()` so that routing has already happened
/// and `MatchedPath` is available.
pub async fn sentry_transaction_name(
    matched_path: Option<MatchedPath>,
    req: Request,
    next: Next,
) -> Response {
    if let Some(path) = matched_path {
        sentry::configure_scope(|scope| {
            scope.set_transaction(Some(path.as_str()));
        });
    }
    next.run(req).await
}
