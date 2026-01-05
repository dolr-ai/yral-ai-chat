# Nginx Configuration Validation Fix

## Problem

The CI/CD validation fails because `limit_req_zone` directives must be in the `http` context, not in a `server` block. The validation command tests the config file in isolation without the `http` context.

## Solution

The rate limiting zones have been moved to a separate file (`rate-limit-zones.conf`) that should be included in the main `nginx.conf` `http` block.

## For CI/CD Validation

Update the validation command in your CI/CD workflow to use a wrapper nginx.conf:

**Current (failing):**
```bash
docker run --rm \
  -v "$(pwd)/nginx/yral-ai-chat.conf:/etc/nginx/conf.d/default.conf:ro" \
  -v /etc/letsencrypt:/etc/letsencrypt:ro \
  nginx:alpine nginx -t
```

**Updated (working):**
```bash
docker run --rm \
  -v "$(pwd)/nginx/rate-limit-zones.conf:/etc/nginx/conf.d/rate-limit-zones.conf:ro" \
  -v "$(pwd)/nginx/yral-ai-chat.conf:/etc/nginx/conf.d/default.conf:ro" \
  -v "$(pwd)/nginx/nginx.conf.wrapper:/etc/nginx/nginx.conf:ro" \
  -v /etc/letsencrypt:/etc/letsencrypt:ro \
  nginx:alpine nginx -t
```

## For Production Deployment

On the server, ensure the main `/etc/nginx/nginx.conf` includes the rate limiting zones in the `http` block:

```nginx
http {
    # ... other http-level directives ...
    
    # Include rate limiting zones
    include /etc/nginx/rate-limit-zones.conf;
    
    # Include site configurations
    include /etc/nginx/sites-enabled/*;
}
```

And copy the zones file:
```bash
sudo cp nginx/rate-limit-zones.conf /etc/nginx/rate-limit-zones.conf
```

