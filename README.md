# FluxLink ⚡

FluxLink is a high-speed developer tool and real-time collaboration bridge designed for instant, byte-exact, lossless source-code and file transfers across devices (Web and Terminal/CLI).

---

## 1. System Architecture & Domains

```
                      ┌─────────────────────────────────┐
                      │    Cloudflare DNS (GoDaddy)     │
                      └────────────────┬────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼                                                     ▼
┌───────────────────────────────┐             ┌───────────────────────────────────────┐
│     Frontend Web UI           │             │      Backend ASGI & WebSockets        │
│ https://fluxlink.chennareddy.in│             │ https://fluxlinkbackend.chennareddy.in│
│   (Cloudflare Pages / Edge)   │             │   (AWS EC2 — Amazon Linux 2023)       │
└───────────────┬───────────────┘             └───────────────────┬───────────────────┘
                │                                                 │
                │        REST API & WebSockets (WSS)              │
                └─────────────────────────┬───────────────────────┘
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
┌───────────────────────────────────┐           ┌───────────────────────────────────┐
│      Terminal CLI Client          │           │       Authoritative Cloud         │
│  (Kali Linux / Windows / macOS)   │           │      Supabase Infrastructure      │
│      fluxlink / chennalink        │           │  PostgreSQL (Sessions & History)  │
│       Python + Textual TUI        │           │  Private Storage (chennalink-files│
└───────────────────────────────────┘           └───────────────────────────────────┘
```

- **Frontend Domain:** `https://fluxlink.chennareddy.in`
- **Backend Domain:** `https://fluxlinkbackend.chennareddy.in`
- **WebSocket Gateway:** `wss://fluxlinkbackend.chennareddy.in/ws/{session_code}/{device_id}`
- **Health Endpoints:** `https://fluxlinkbackend.chennareddy.in/health` and `/api/health`

---

## 2. Technologies Used

- **Backend:** Python 3.12, FastAPI, Uvicorn, Gunicorn, WebSockets, Pydantic v2.
- **Database & Storage:** Supabase PostgreSQL (`psycopg 3` connection pooling) + Supabase Private Storage (`chennalink-files`).
- **Terminal CLI:** Python Textual, Rich, Pyperclip.
- **Frontend:** Vanilla HTML5, modern CSS3, native WebSockets, responsive mobile & desktop layout.
- **Infrastructure & Proxy:** AWS EC2 (Amazon Linux 2023), Nginx (Reverse Proxy & WebSocket upgrade), Let's Encrypt (Certbot SSL), Cloudflare DNS.

---

## 3. Local Development Setup

### 3.1 Prerequisites
- Python 3.12+
- Git

### 3.2 Installation
```bash
# Clone the repository
git clone https://github.com/ychennakesavareddy/FluxLink.git
cd FluxLink

# Create and activate virtual environment
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Install in editable mode
pip install -e .
pip install uvicorn[standard] pytest pytest-asyncio
```

### 3.3 Configuration
Copy the configuration template:
```bash
cp .env.example .env
```
Fill in your Supabase project credentials in `.env`:
- `DATABASE_URL`: Your Supabase PostgreSQL connection URI.
- `SUPABASE_URL`: Your Supabase API URL.
- `SUPABASE_SERVICE_ROLE_KEY`: Your Supabase Service Role Key.
- `SUPABASE_STORAGE_BUCKET`: `chennalink-files`

### 3.4 Running Locally

**Start Backend:**
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

**Start Terminal CLI:**
```bash
# Launch interactive TUI connected to local server
FLUXLINK_ENV=development fluxlink
# Or using the backend flag
fluxlink --backend http://127.0.0.1:8000
```

**Open Web Interface:**
Navigate to `http://127.0.0.1:8000/web` in your browser.

---

## 4. FluxLink CLI Guide (Kali Linux / Terminal)

The CLI provides a full keyboard-driven terminal UI (TUI) for sending and receiving code without breaking indentation or file fidelity.

### Commands

| Command | Action |
| :--- | :--- |
| `fluxlink` | Launch interactive TUI connected to production backend |
| `fluxlink send <path>` | Launch TUI and automatically preload `<path>` for sending |
| `fluxlink receive` | Jump directly into incoming transfer queue |
| `fluxlink history` | Jump directly into transfer history and inspector |
| `fluxlink session` | View active session code, connected devices, and status |
| `fluxlink --backend <url>` | Override backend URL (e.g. `http://127.0.0.1:8000`) |
| `fluxlink help` | Print command line cheatsheet |

### Keyboard Shortcuts in TUI

- `Ctrl + T`: WhatsApp-style Real-Time Chat Timeline
- `Ctrl + 1`: Send File (open file by path or paste code)
- `Ctrl + 2`: Receive Queue (browse incoming files & download)
- `Ctrl + 3`: History Screen (inspect past transfers & exact bytes)
- `Ctrl + 4`: Session Screen (view session code & participant roster)
- `Ctrl + H`: Help & Shortcuts Screen
- `Ctrl + Q`: Quit Application

---

## 5. AWS EC2 Backend Deployment (Amazon Linux 2023)

### 5.1 EC2 Security Group Configuration

In AWS Console > EC2 > Security Groups, configure:

| Protocol | Port | Source | Purpose |
| :--- | :--- | :--- | :--- |
| **SSH** | 22 | `YOUR_IP/32` | Administrative access (restricted to your IP) |
| **HTTP** | 80 | `0.0.0.0/0` | Public HTTP-to-HTTPS redirect & Certbot challenges |
| **HTTPS** | 443 | `0.0.0.0/0` | Secure public API and WebSocket connections |

> **Note:** Port 8000 should **not** be open to the internet. It binds only to `127.0.0.1` and is proxied through Nginx on port 443.

### 5.2 Elastic IP Allocation
Allocate an AWS Elastic IP and associate it with your EC2 instance. This prevents the public IP from changing upon instance reboot.

### 5.3 Automated Server Setup
SSH into your EC2 instance from Kali Linux:
```bash
ssh -i /path/to/key.pem ec2-user@<YOUR_ELASTIC_IP>
```

Run the automated deployment script located in `deploy/deploy_ec2.sh`:
```bash
# Clone repository
sudo mkdir -p /opt/fluxlink
sudo chown -R ec2-user:ec2-user /opt/fluxlink
git clone https://github.com/ychennakesavareddy/FluxLink.git /opt/fluxlink
cd /opt/fluxlink

# Run automated deployment
chmod +x deploy/deploy_ec2.sh
./deploy/deploy_ec2.sh
```

### 5.4 Configure Production `.env`
Edit `/opt/fluxlink/.env` on the server and add your Supabase credentials:
```bash
nano /opt/fluxlink/.env
```
Restart the service:
```bash
sudo systemctl restart fluxlinkbackend
```

### 5.5 Obtain SSL Certificate with Certbot
Once DNS is pointed:
```bash
sudo certbot --nginx -d fluxlinkbackend.chennareddy.in
sudo systemctl restart nginx
```

---

## 6. Frontend Deployment (Cloudflare Pages)

Because your domain `chennareddy.in` is already managed through Cloudflare DNS, **Cloudflare Pages** is the recommended zero-maintenance hosting solution for the frontend:

1. In the **Cloudflare Dashboard**, navigate to **Workers & Pages** > **Create application** > **Pages** > **Connect to Git**.
2. Select repository: `ychennakesavareddy/FluxLink`.
3. Build configuration:
   - Framework preset: `None`
   - Build command: *(leave empty)*
   - Build output directory: `web`
4. Deploy site.
5. In your Pages project settings, go to **Custom Domains** > **Set up a custom domain**:
   - Enter: `fluxlink.chennareddy.in`
   - Cloudflare will automatically route the CNAME and provision universal SSL.

---

## 7. Cloudflare DNS Configuration

In your Cloudflare DNS management for `chennareddy.in`, configure:

| Type | Name | Content / Target | Proxy status |
| :--- | :--- | :--- | :--- |
| **A** | `fluxlinkbackend` | `<YOUR_EC2_ELASTIC_IP>` | DNS only (Grey Cloud) during Certbot, then Proxied (Orange Cloud) |
| **CNAME** | `fluxlink` | `<YOUR_CLOUDFLARE_PAGES_DOMAIN>` (e.g. `fluxlink.pages.dev`) | Proxied (Orange Cloud) |

---

## 8. Testing & Verification

Run the test suite:
```bash
# Run all unit, UI, and production enforcement tests
pytest -k "not live" -v

# Run live Supabase integration tests (requires live .env)
pytest tests/test_live_supabase_integration.py -v
```

### Health Check Verification
```bash
curl https://fluxlinkbackend.chennareddy.in/health
```
Expected response:
```json
{
  "status": "healthy",
  "service": "fluxlink",
  "database": "PostgresRepository",
  "database_backend": "postgres",
  "storage_backend": "supabase",
  "storage_bucket": "chennalink-files"
}
```
