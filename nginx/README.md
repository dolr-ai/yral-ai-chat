# Nginx Reverse Proxy Setup for Yral AI Chat API

This directory contains the nginx configuration for setting up a reverse proxy that routes HTTPS traffic (port 443) to the FastAPI application running on port 8000.

## Prerequisites

1. Nginx installed on your server
2. Domain name pointing to your server's IP address
3. Ports 80 and 443 open in your firewall

## Setup Instructions

### 1. Install Nginx (if not already installed)

```bash
sudo apt-get update
sudo apt-get install nginx -y
```

### 2. Install Certbot for SSL Certificates

```bash
sudo apt-get install certbot python3-certbot-nginx -y
```

### 3. Configure the Nginx File

1. Copy the configuration file to nginx sites-available:
```bash
sudo cp nginx/yral-ai-chat.conf /etc/nginx/sites-available/yral-ai-chat.conf
```

2. Edit the configuration file to replace `chat.yral.com` with your actual domain:
```bash
sudo nano /etc/nginx/sites-available/yral-ai-chat.conf
```

Replace all instances of:
- `chat.yral.com` with your actual domain (e.g., `api.yral.com`)
- Update SSL certificate paths if using a different certificate provider

3. Create a symlink to enable the site:
```bash
sudo ln -s /etc/nginx/sites-available/yral-ai-chat.conf /etc/nginx/sites-enabled/
```

4. Remove the default nginx site (optional):
```bash
sudo rm /etc/nginx/sites-enabled/default
```

### 4. Obtain SSL Certificate with Let's Encrypt

Run certbot to automatically obtain and configure SSL certificates:

```bash
sudo certbot --nginx -d chat.yral.com -d www.chat.yral.com
```

Certbot will:
- Automatically obtain SSL certificates from Let's Encrypt
- Update the nginx configuration with the correct certificate paths
- Set up automatic renewal

### 5. Test Nginx Configuration

```bash
sudo nginx -t
```

If the test is successful, you should see:
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### 6. Start/Restart Nginx

```bash
sudo systemctl restart nginx
sudo systemctl enable nginx  # Enable nginx to start on boot
```

### 7. Verify the Setup

1. Check nginx status:
```bash
sudo systemctl status nginx
```

2. Test HTTPS access:
```bash
curl https://chat.yral.com/health
```

3. Check nginx logs if there are issues:
```bash
sudo tail -f /var/log/nginx/yral-ai-chat-access.log
sudo tail -f /var/log/nginx/yral-ai-chat-error.log
```

## Firewall Configuration

Make sure ports 80 and 443 are open:

```bash
# For UFW (Ubuntu Firewall)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload

# For firewalld (CentOS/RHEL)
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

## SSL Certificate Auto-Renewal

Let's Encrypt certificates expire after 90 days. Certbot sets up automatic renewal, but you can test it:

```bash
sudo certbot renew --dry-run
```

## Manual SSL Certificate Setup (Alternative)

If you're not using Let's Encrypt, you can manually configure SSL certificates:

1. Place your SSL certificate and private key in appropriate locations
2. Update the `ssl_certificate` and `ssl_certificate_key` paths in the nginx config
3. Restart nginx

## Troubleshooting

### Nginx won't start
- Check configuration: `sudo nginx -t`
- Check error logs: `sudo tail -f /var/log/nginx/error.log`
- Ensure port 443 is not already in use: `sudo netstat -tulpn | grep 443`

### SSL certificate errors
- Verify certificate paths are correct
- Check certificate permissions: `sudo ls -la /etc/letsencrypt/live/chat.yral.com/`
- Ensure certificate is valid: `sudo openssl x509 -in /etc/letsencrypt/live/chat.yral.com/fullchain.pem -text -noout`

### 502 Bad Gateway
- Ensure FastAPI app is running on port 8000: `curl http://localhost:8000/health`
- Check if the app is listening on the correct interface (should be 0.0.0.0:8000)
- Review nginx error logs for more details

### Connection refused
- Verify firewall rules allow traffic
- Check that the FastAPI app is running: `ps aux | grep uvicorn`
- Ensure the app is bound to 0.0.0.0, not just localhost

## Staging Environment Setup

The nginx configuration supports both production and staging environments on the same domain using path-based routing:

- **Production**: `https://chat.yral.com/*` → routes to container on port 8000
- **Staging**: `https://chat.yral.com/staging/*` → routes to container on port 8001

### Deploying Updated Nginx Config for Staging

After updating the nginx configuration file in the repository, deploy it to your server:

1. **Copy the updated configuration**:
   ```bash
   sudo cp nginx/yral-ai-chat.conf /etc/nginx/sites-available/yral-ai-chat.conf
   ```

2. **Test the configuration**:
   ```bash
   sudo nginx -t
   ```

3. **If test passes, reload nginx** (no downtime):
   ```bash
   sudo systemctl reload nginx
   ```

4. **Verify staging routing works**:
   ```bash
   # Test production endpoint
   curl https://chat.yral.com/health
   
   # Test staging endpoint
   curl https://chat.yral.com/staging/health
   ```

### CI/CD Deployment

For automated deployment via GitHub Actions:

1. **SSH into server with sudo access** (requires passwordless sudo for nginx commands)
2. **Copy updated config**: `sudo cp nginx/yral-ai-chat.conf /etc/nginx/sites-available/yral-ai-chat.conf`
3. **Test and reload**: `sudo nginx -t && sudo systemctl reload nginx`

Alternatively, configure passwordless sudo for specific nginx commands:
```bash
# Add to /etc/sudoers.d/nginx-deploy (via visudo)
deploy_user ALL=(ALL) NOPASSWD: /usr/bin/cp /path/to/nginx/yral-ai-chat.conf /etc/nginx/sites-available/yral-ai-chat.conf
deploy_user ALL=(ALL) NOPASSWD: /usr/sbin/nginx -t
deploy_user ALL=(ALL) NOPASSWD: /bin/systemctl reload nginx
```

## Production Recommendations

1. **Update CORS settings**: Update `CORS_ORIGINS` in your `.env` file to include your domain:
   ```
   CORS_ORIGINS=https://chat.yral.com,https://www.chat.yral.com
   ```

2. **Update MEDIA_BASE_URL**: Update the media base URL in your `.env` file:
   ```
   MEDIA_BASE_URL=https://chat.yral.com/media
   ```

3. **Run FastAPI with multiple workers**:
   ```bash
   uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
   ```

4. **Set up process management**: Consider using systemd or supervisor to manage the FastAPI process

5. **Monitor logs**: Set up log rotation and monitoring for both nginx and FastAPI logs

