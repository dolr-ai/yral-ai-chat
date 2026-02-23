use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Instant;

use axum::body::Body;
use axum::http::{Request, Response, StatusCode};
use axum::response::IntoResponse;
use dashmap::DashMap;
use tower::{Layer, Service};

/// Token bucket for rate limiting.
struct TokenBucket {
    tokens: f64,
    capacity: f64,
    refill_rate: f64, // tokens per second
    last_refill: Instant,
}

impl TokenBucket {
    fn new(capacity: f64, refill_rate: f64) -> Self {
        Self {
            tokens: capacity,
            capacity,
            refill_rate,
            last_refill: Instant::now(),
        }
    }

    fn consume(&mut self) -> bool {
        self.refill();
        if self.tokens >= 1.0 {
            self.tokens -= 1.0;
            true
        } else {
            false
        }
    }

    fn refill(&mut self) {
        let now = Instant::now();
        let elapsed = now.duration_since(self.last_refill).as_secs_f64();
        self.tokens = (self.tokens + elapsed * self.refill_rate).min(self.capacity);
        self.last_refill = now;
    }

    fn retry_after(&self) -> u64 {
        if self.tokens >= 1.0 {
            return 0;
        }
        let needed = 1.0 - self.tokens;
        (needed / self.refill_rate).ceil() as u64 + 1
    }

    fn remaining(&self) -> u64 {
        self.tokens.max(0.0) as u64
    }
}

struct Buckets {
    minute: TokenBucket,
    hour: TokenBucket,
}

/// Shared state for rate limiting.
#[derive(Clone)]
struct RateLimitState {
    buckets: Arc<DashMap<String, Buckets>>,
    per_minute: u32,
    per_hour: u32,
    last_cleanup: Arc<AtomicU64>,
}

impl RateLimitState {
    fn new(per_minute: u32, per_hour: u32) -> Self {
        Self {
            buckets: Arc::new(DashMap::new()),
            per_minute,
            per_hour,
            last_cleanup: Arc::new(AtomicU64::new(0)),
        }
    }

    fn get_or_create(&self, key: &str) -> dashmap::mapref::one::RefMut<'_, String, Buckets> {
        self.buckets.entry(key.to_string()).or_insert_with(|| Buckets {
            minute: TokenBucket::new(self.per_minute as f64, self.per_minute as f64 / 60.0),
            hour: TokenBucket::new(self.per_hour as f64, self.per_hour as f64 / 3600.0),
        })
    }

    fn cleanup(&self) {
        let now = Instant::now()
            .duration_since(Instant::now() - std::time::Duration::from_secs(1))
            .as_secs(); // approximation
        let last = self.last_cleanup.load(Ordering::Relaxed);
        if now.saturating_sub(last) < 300 {
            return;
        }
        self.last_cleanup.store(now, Ordering::Relaxed);

        let threshold = Instant::now() - std::time::Duration::from_secs(3600);
        self.buckets.retain(|_, v| {
            v.minute.last_refill > threshold || v.hour.last_refill > threshold
        });
    }
}

const EXCLUDED_PATHS: &[&str] = &["/", "/health", "/status"];

/// Tower Layer for rate limiting.
#[derive(Clone)]
pub struct RateLimitLayer {
    state: RateLimitState,
}

impl RateLimitLayer {
    pub fn new(per_minute: u32, per_hour: u32) -> Self {
        Self {
            state: RateLimitState::new(per_minute, per_hour),
        }
    }
}

impl<S> Layer<S> for RateLimitLayer {
    type Service = RateLimitService<S>;

    fn layer(&self, inner: S) -> Self::Service {
        RateLimitService {
            inner,
            state: self.state.clone(),
        }
    }
}

/// Tower Service for rate limiting.
#[derive(Clone)]
pub struct RateLimitService<S> {
    inner: S,
    state: RateLimitState,
}

impl<S> Service<Request<Body>> for RateLimitService<S>
where
    S: Service<Request<Body>, Response = Response<Body>> + Clone + Send + 'static,
    S::Future: Send + 'static,
{
    type Response = Response<Body>;
    type Error = S::Error;
    type Future = std::pin::Pin<
        Box<dyn std::future::Future<Output = Result<Self::Response, Self::Error>> + Send>,
    >;

    fn poll_ready(
        &mut self,
        cx: &mut std::task::Context<'_>,
    ) -> std::task::Poll<Result<(), Self::Error>> {
        self.inner.poll_ready(cx)
    }

    fn call(&mut self, req: Request<Body>) -> Self::Future {
        let path = req.uri().path().to_string();

        // Skip rate limiting for excluded paths
        if EXCLUDED_PATHS.contains(&path.as_str()) {
            let mut inner = self.inner.clone();
            return Box::pin(async move { inner.call(req).await });
        }

        // Determine identifier: X-Forwarded-For > client IP
        let identifier = req
            .headers()
            .get("X-Forwarded-For")
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.split(',').next())
            .map(|ip| format!("ip:{}", ip.trim()))
            .unwrap_or_else(|| "ip:unknown".to_string());

        let state = self.state.clone();
        let mut inner = self.inner.clone();

        Box::pin(async move {
            state.cleanup();

            let mut entry = state.get_or_create(&identifier);

            // Check per-minute bucket
            if !entry.minute.consume() {
                let retry_after = entry.minute.retry_after();
                drop(entry);
                return Ok(rate_limit_response(
                    retry_after,
                    "per_minute",
                    state.per_minute,
                ));
            }

            // Check per-hour bucket
            if !entry.hour.consume() {
                let retry_after = entry.hour.retry_after();
                // Refund minute token
                entry.minute.tokens += 1.0;
                drop(entry);
                return Ok(rate_limit_response(retry_after, "per_hour", state.per_hour));
            }

            let minute_remaining = entry.minute.remaining();
            let hour_remaining = entry.hour.remaining();
            let per_minute = state.per_minute;
            let per_hour = state.per_hour;
            drop(entry);

            let mut response = inner.call(req).await?;

            // Add rate limit headers
            let headers = response.headers_mut();
            headers.insert(
                "X-RateLimit-Limit-Minute",
                per_minute.to_string().parse().unwrap(),
            );
            headers.insert(
                "X-RateLimit-Limit-Hour",
                per_hour.to_string().parse().unwrap(),
            );
            headers.insert(
                "X-RateLimit-Remaining-Minute",
                minute_remaining.to_string().parse().unwrap(),
            );
            headers.insert(
                "X-RateLimit-Remaining-Hour",
                hour_remaining.to_string().parse().unwrap(),
            );

            Ok(response)
        })
    }
}

fn rate_limit_response(retry_after: u64, limit_type: &str, limit: u32) -> Response<Body> {
    let body = serde_json::json!({
        "error": "rate_limit_exceeded",
        "message": format!("Too many requests. Try again in {retry_after} seconds."),
        "retry_after": retry_after,
        "limit_type": limit_type,
        "limit": limit,
    });

    let mut resp = (
        StatusCode::TOO_MANY_REQUESTS,
        axum::Json(body),
    )
        .into_response();

    resp.headers_mut().insert(
        "Retry-After",
        retry_after.to_string().parse().unwrap(),
    );

    resp
}
