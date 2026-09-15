# DeskTrack — VPS deploy (Docker)

DeskTrack needs a normal VPS (not Vercel): live camera frames, YOLO, and SQLite stay on the server.

## Disk size (what to expect)

| Item | Approx size |
|------|-------------|
| Docker image (built) | **~1.0–1.4 GB** |
| YOLO models volume | **~4 MB** (auto-downloaded on first start) |
| SQLite DB volume | grows with use (**tens of MB** for a small office) |
| Docker Engine + OS free space buffer | keep **≥ 5–8 GB free** |

**Recommendation:** VPS with **≥ 20 GB disk** and **≥ 2 GB RAM** (YOLO + OpenCV). Prefer **1–2 GB free RAM** after the OS.

Source footprint on your machine (for reference): YOLO ~4 MB, built UI ~0.2 MB, `node_modules` only needed at build time (~40 MB).

## 1. Install Docker on the VPS

```bash
sudo apt update
sudo apt install -y ca-certificates curl
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# log out/in, then:
docker --version
docker compose version
```

## 2. Copy the project

```bash
# example
sudo mkdir -p /opt/desktrack
sudo chown $USER:$USER /opt/desktrack
# scp / rsync / git clone into /opt/desktrack
cd /opt/desktrack
```

## 3. Create `.env`

```bash
cp .env.example .env
nano .env
```

Production values:

```env
DESKTRACK_ENV=production
SECRET_KEY=<openssl rand -hex 32>
AGENT_TOKEN=<openssl rand -hex 16>
PUBLIC_URL=http://YOUR_VPS_IP:8000
HTTPS_ONLY=false
SEED_DEMO=false
RELOAD=false
CORS_ORIGINS=http://YOUR_VPS_IP:8000
DATABASE_URL=sqlite:////app/data/office.db
HOST=0.0.0.0
PORT=8000
```

When you put **HTTPS + domain** in front (Nginx/Caddy):

- `PUBLIC_URL=https://desktrack.yourdomain.com`
- `HTTPS_ONLY=true`
- `CORS_ORIGINS=https://desktrack.yourdomain.com`

## 4. Build and run

```bash
cd /opt/desktrack
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100
```

Health: `curl http://127.0.0.1:8000/health`  
App: `http://YOUR_VPS_IP:8000`

First boot downloads YOLO models into the `desktrack_models` volume (~4 MB).

## 5. First login

Fresh production DB creates only:

- **HR** `hr` / `hr123`

Change that password ASAP. Employees use **Create account** on the login page (or HR → People).

## 6. HTTPS (recommended — camera needs it)

Chrome blocks camera on plain `http://IP`. Use a domain + reverse proxy.

Example Nginx (TLS via Certbot) → proxy to `127.0.0.1:8000`. See `deploy/nginx.conf`.

Then set `HTTPS_ONLY=true` and restart:

```bash
docker compose up -d
```

Optional: change compose to bind only localhost (`127.0.0.1:8000:8000`) when Nginx is the public entry.

## 7. Updates

```bash
cd /opt/desktrack
# pull / copy new code
docker compose up -d --build
```

## 8. Backup

```bash
docker compose exec desktrack ls -la /app/data
# copy volume or file:
docker run --rm -v desktrack_desktrack_data:/data -v $(pwd):/backup alpine \
  tar czf /backup/office-backup.tgz -C /data .
```

## Feature check (from your laptop against a running server)

```bash
python scripts/feature_check.py
```

(edit `BASE` in the script if the server is remote)

## Notes

- Do **not** use Vercel/serverless for this app.
- RAM matters more than disk for YOLO.
- `SEED_DEMO=false` in production (no fake employees).
