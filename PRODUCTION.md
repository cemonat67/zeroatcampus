# Zero@Campus Production Deployment Guide

## 1. Server Setup (Ubuntu 22.04 LTS)

### Prerequisites
- SSH access to `18.218.142.167`
- Domain `campus.zeroatecosystem.com` pointing to server IP (Cloudflare Proxied)

### Install Dependencies
```bash
sudo apt update && sudo apt install -y nginx python3-venv git certbot python3-certbot-nginx
```

## 2. Application Deployment

### Clone Repository
```bash
sudo mkdir -p /var/www/zeroatcampus
sudo chown -R ubuntu:ubuntu /var/www/zeroatcampus
git clone https://github.com/cemonat67/zeroatcampus.git /var/www/zeroatcampus
cd /var/www/zeroatcampus
```

### Setup Backend Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn reportlab
```

### Configure Systemd Service
```bash
sudo cp deploy/service/zero-campus.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable zero-campus
sudo systemctl start zero-campus
```

## 3. Web Server Configuration (Nginx)

### Configure Nginx
```bash
sudo cp deploy/nginx_campus.conf /etc/nginx/sites-available/campus.zeroatecosystem.com
sudo ln -s /etc/nginx/sites-available/campus.zeroatecosystem.com /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### SSL Setup (Cloudflare Full Strict)
If using Cloudflare Full Strict, you need a valid Origin Certificate on the server.
Alternatively, use Certbot to get a Let's Encrypt certificate (Cloudflare SSL mode must be Full, not Strict, or allow Let's Encrypt validation).

**Easiest: Cloudflare Origin CA**
1. Generate Origin Certificate in Cloudflare Dashboard.
2. Save to `/etc/ssl/certs/cf_origin.pem` and `/etc/ssl/private/cf_key.pem`.
3. Update Nginx config to listen 443 ssl and point to these files.

**Certbot (Let's Encrypt)**
```bash
sudo certbot --nginx -d campus.zeroatecosystem.com
```

## 4. Verification
- Visit: `https://campus.zeroatecosystem.com`
- Check API: `https://campus.zeroatecosystem.com/api/system/status`
