#!/usr/bin/env bash
# ==============================================================================
# FLUXLINK — AWS EC2 (Amazon Linux 2023) Automated Deployment Script
# Domain: fluxlinkbackend.chennareddy.in
# ==============================================================================

set -euo pipefail

echo "===> [1/7] Updating system packages on Amazon Linux 2023..."
sudo dnf update -y

echo "===> [2/7] Installing system dependencies (Python 3.12, Nginx, Git, Certbot)..."
sudo dnf install -y python3.12 python3.12-pip git nginx certbot python3-certbot-nginx

echo "===> [3/7] Setting up application directory at /opt/fluxlink..."
sudo mkdir -p /opt/fluxlink
sudo chown -R ec2-user:ec2-user /opt/fluxlink

# If repository not cloned yet, clone it; otherwise fetch latest
if [ ! -d "/opt/fluxlink/.git" ]; then
    echo "Cloning FluxLink repository..."
    git clone https://github.com/ychennakesavareddy/FluxLink.git /opt/fluxlink
else
    echo "Updating existing FluxLink repository..."
    cd /opt/fluxlink
    git fetch origin main
    git reset --hard origin/main
fi

cd /opt/fluxlink

echo "===> [4/7] Setting up Python virtual environment..."
if [ ! -d "/opt/fluxlink/.venv" ]; then
    python3.12 -m venv /opt/fluxlink/.venv
fi

/opt/fluxlink/.venv/bin/pip install --upgrade pip setuptools wheel
/opt/fluxlink/.venv/bin/pip install -e .
/opt/fluxlink/.venv/bin/pip install uvicorn[standard] gunicorn python-dotenv

# Verify .env exists
if [ ! -f "/opt/fluxlink/.env" ]; then
    echo "WARNING: /opt/fluxlink/.env not found!"
    echo "Copying .env.example to /opt/fluxlink/.env. Please configure your production credentials."
    cp /opt/fluxlink/.env.example /opt/fluxlink/.env
    chmod 600 /opt/fluxlink/.env
fi

echo "===> [5/7] Configuring systemd service..."
sudo cp /opt/fluxlink/deploy/fluxlinkbackend.service /etc/systemd/system/fluxlinkbackend.service
sudo systemctl daemon-reload
sudo systemctl enable fluxlinkbackend.service
sudo systemctl restart fluxlinkbackend.service

echo "===> [6/7] Configuring Nginx reverse proxy..."
sudo cp /opt/fluxlink/deploy/nginx_fluxlinkbackend.conf /etc/nginx/conf.d/fluxlinkbackend.conf
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

echo "===> [7/7] Verifying backend service health..."
sleep 3
if curl -s http://127.0.0.1:8000/health | grep -q "healthy"; then
    echo "SUCCESS: FluxLink backend is running and healthy on 127.0.0.1:8000!"
else
    echo "Backend status check failed. Inspect logs using: sudo journalctl -u fluxlinkbackend -n 50"
fi

echo ""
echo "=============================================================================="
echo "DEPLOYMENT COMPLETE!"
echo "Next Steps:"
echo "1. Verify Cloudflare DNS: A record for fluxlinkbackend.chennareddy.in -> EC2 IP"
echo "2. Obtain SSL certificate using Certbot:"
echo "   sudo certbot --nginx -d fluxlinkbackend.chennareddy.in"
echo "3. Restart Nginx:"
echo "   sudo systemctl restart nginx"
echo "=============================================================================="
