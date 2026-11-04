# Recovery — Lightweight OCI Deployment Guide (Phase 1)

**Target Stack:** Oracle Cloud Infrastructure (Always Free Ubuntu 22.04/24.04 LTS), Caddy (Automated TLS/HTTPS reverse proxy), Python 3.11+, Uvicorn (1 worker), SQLite (WAL mode).

> **Critical Stability Notice:** Always Free instances with 1 OCPU and 1 GB RAM will trigger Out-Of-Memory (OOM) kernel panics if Node.js is compiled directly on the server or if multiple Uvicorn workers run concurrently. Follow this specification verbatim.

---

## 1. OCI Console Network Configuration

Before connecting via SSH, configure the virtual network in the Oracle Cloud Console:
1. Navigate to **Virtual Cloud Network (VCN)** → **Security Lists** (Public Subnet).
2. Add the following **Ingress Rules** (Stateless: No, Source CIDR: `0.0.0.0/0`):
   - **Port 80** (HTTP) - Protocol: TCP
   - **Port 443** (HTTPS) - Protocol: TCP

---

## 2. Operating System Preparation (SSH)

Establish an SSH session to the instance's public IP:
```bash
ssh ubuntu@<PUBLIC_IP>
```

### A. OS-Level Firewall Rules (Oracle Ubuntu iptables)
*Oracle Cloud platform images block inbound HTTP/HTTPS traffic at the OS level by default.*
```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo apt install -y iptables-persistent
sudo netfilter-persistent save
```

### B. Mandatory 2 GB Swapfile (OOM Prevention)
```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
sudo sysctl vm.swappiness=10
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
```
*Verify with `free -h` that Swap displays `2.0Gi`.*

---

## 3. Package Installation

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip git debian-keyring debian-archive-keyring apt-transport-https curl
```

### Install Caddy (Lightweight web server with automatic TLS management):
```bash
curl -1sLF 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLF 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install -y caddy
```

---

## 4. Repository & Python Environment Setup

```bash
sudo mkdir -p /var/www
sudo chown -R ubuntu:ubuntu /var/www
cd /var/www
git clone https://github.com/beyond-sprint-labs/recovery.git
cd recovery

# Setup virtual environment and dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .

# Initialize production environment configuration
cp .env.example .env
nano .env
```

**Production environment variables (`/var/www/recovery/.env`):**
```dotenv
APP_ENV=production
DEMO_MODE=false
PAYPAL_MODE=real
AGENT_MODE=llm
ALLOW_SCENARIO_ID=true
DATABASE_URL=sqlite:///./recovery.db
PUBLIC_BASE_URL=https://<YOUR_DOMAIN_OR_NIP_IO>
CORS_ORIGINS=https://<YOUR_DOMAIN_OR_NIP_IO>
UVICORN_WORKERS=1
PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com
PAYPAL_CLIENT_ID=<SANDBOX_CLIENT_ID>
PAYPAL_CLIENT_SECRET=<SANDBOX_CLIENT_SECRET>
PAYPAL_WEBHOOK_ID=<REGISTERED_WEBHOOK_ID>
PAYPAL_MERCHANT_EMAIL=<SANDBOX_BUSINESS_EMAIL>
```

---

## 5. Systemd Service Configuration (`recovery.service`)

Create the systemd service file:
```bash
sudo nano /etc/systemd/system/recovery.service
```

Insert the following configuration:
```ini
[Unit]
Description=Recovery FastAPI Application Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/var/www/recovery
EnvironmentFile=/var/www/recovery/.env
ExecStart=/var/www/recovery/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5
MemoryMax=600M

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable recovery
sudo systemctl start recovery
sudo systemctl status recovery
```

---

## 6. Caddy Configuration (Reverse Proxy & Static Asset Serving)

> **Golden Rule:** Compiling Node.js directly on this instance is strictly prohibited. Compile the frontend build artifacts locally (`npm run build`) and upload the resulting `dist/` directory to `/var/www/recovery/ui/dist`.

Edit `/etc/caddy/Caddyfile`:
```bash
sudo nano /etc/caddy/Caddyfile
```

Replace its contents with:
```caddy
<YOUR_DOMAIN_OR_IP.nip.io> {
    # 1. FastAPI API endpoints
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }

    # 2. Health check route
    handle /health {
        reverse_proxy 127.0.0.1:8000
    }

    # 3. Static frontend single-page application
    handle {
        root * /var/www/recovery/ui/dist
        try_files {path} /index.html
        file_server
    }
}
```

Restart Caddy:
```bash
sudo systemctl restart caddy
```

---

## 7. Deployment Health Verification

1. Query the health check endpoint from a browser:
   `https://<YOUR_DOMAIN_OR_IP.nip.io>/health`
   
   **Expected Response (`200 OK`):**
   ```json
   {
     "status": "ok",
     "demo_mode": false,
     "engine_version": "1.0.0",
     "paypal_mode": "real",
     "agent_mode": "llm"
   }
   ```

2. Register the public HTTPS webhook URL in the PayPal Developer Dashboard:
   `https://<YOUR_DOMAIN_OR_IP.nip.io>/api/v1/webhooks/paypal`
