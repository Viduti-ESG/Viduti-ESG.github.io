# Oracle Cloud: AMD Micro → ARM A1.Flex Upgrade

## Current setup
- Shape: VM.Standard.E2.1.Micro (AMD, Always Free)
- OCPU: 1 / RAM: 1 GB
- Limitation: 1 GB RAM causes uvicorn to OOM-kill on large esg_quotient.json loads or
  concurrent AI requests (Anthropic API responses can hold ~300 MB of context in memory).

## Target setup
- Shape: VM.Standard.A1.Flex (ARM Ampere A1, Always Free quota)
- OCPU: 4 / RAM: 24 GB (combined across Always Free A1 quota)
- Cost: ₹0/month (4 OCPU + 24 GB RAM is the Always Free limit for A1)

---

## Step-by-step migration

### 1. Back up DB and .env
```bash
# On the current AMD instance:
sqlite3 /opt/greencurve/greencurve.db ".backup '/tmp/greencurve_backup.db'"
scp -i ~/.ssh/gc_key ubuntu@161.118.174.87:/tmp/greencurve_backup.db ./greencurve_backup_$(date +%Y%m%d).db
scp -i ~/.ssh/gc_key ubuntu@161.118.174.87:/opt/greencurve/.env ./env_backup_$(date +%Y%m%d).txt
```

### 2. Create A1.Flex instance in OCI Console
1. Compute → Instances → Create Instance
2. Shape: VM.Standard.A1.Flex → 4 OCPU / 24 GB RAM
3. Image: **Canonical Ubuntu 22.04 (aarch64)**  ← critical: ARM image, not x86
4. VCN: same as current instance (or new with same security list rules)
5. Public IP: Reserve a new static public IP (you'll point DNS here)
6. Boot volume: 100 GB (free tier allows up to 200 GB total)
7. SSH key: upload same key as current instance

### 3. Provision the new instance
```bash
ssh -i ~/.ssh/gc_key ubuntu@<new_arm_ip>

# System packages
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3-pip sqlite3 nginx certbot python3-certbot-nginx

# App directory
sudo mkdir -p /opt/greencurve /var/log/greencurve
sudo chown ubuntu:ubuntu /opt/greencurve /var/log/greencurve
```

### 4. Transfer files
```bash
# From your local machine:
rsync -avz --exclude='__pycache__' --exclude='*.pyc' \
  -e "ssh -i ~/.ssh/gc_key" \
  ./esg-site/ ubuntu@<new_arm_ip>:/opt/greencurve/

# Transfer DB backup
scp -i ~/.ssh/gc_key ./greencurve_backup_$(date +%Y%m%d).db \
  ubuntu@<new_arm_ip>:/opt/greencurve/greencurve.db
```

### 5. Python environment
```bash
cd /opt/greencurve
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 6. .env file
```bash
cp /opt/greencurve/.env.example /opt/greencurve/.env
# Edit .env and fill in JWT_SECRET, GC_ENV=production, GC_SMTP_*, ANTHROPIC_API_KEY
```

### 7. systemd service
```bash
# /etc/systemd/system/greencurve.service is already in deploy/greencurve.service
sudo cp /opt/greencurve/deploy/greencurve.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable greencurve
sudo systemctl start greencurve
sudo systemctl status greencurve
```

### 8. Nginx + TLS
```bash
# Copy nginx config from current instance or create fresh:
sudo cp /opt/greencurve/deploy/nginx.conf /etc/nginx/sites-available/greencurve
sudo ln -s /etc/nginx/sites-available/greencurve /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# TLS cert (update DNS first — see step 9):
sudo certbot --nginx -d greencurve.solutions -d www.greencurve.solutions
```

### 9. DNS cutover (Cloudflare)
1. Note new ARM instance public IP.
2. In Cloudflare DNS → change A record from `161.118.174.87` → `<new_arm_ip>`.
3. Set TTL to 60 seconds before cutover; restore to Auto after.
4. Verify: `curl -I https://greencurve.solutions/health`

### 10. Decommission AMD instance
- Wait 24 hours after DNS cutover to confirm no traffic to old IP.
- OCI Console → Terminate the AMD instance (release boot volume to keep storage free).

---

## ARM-specific gotchas

| Issue | Fix |
|-------|-----|
| pip packages with C extensions (bcrypt, cryptography) need ARM wheels | Modern PyPI has arm64 wheels for all Green Curve deps — no action needed |
| Anthropic SDK on ARM | Fully supported since v0.18 |
| sqlite3 WAL mode | Works identically on ARM |
| certbot | `python3-certbot-nginx` package works on aarch64 |

## Memory headroom after upgrade
| Service | AMD Micro (1 GB) | A1.Flex (24 GB) |
|---------|-----------------|-----------------|
| uvicorn (4 workers) | OOM risk | ~800 MB, safe |
| AI API context | ~300 MB/request | No issue |
| SQLite WAL cache | ~100 MB | No issue |
| Nginx | ~50 MB | No issue |
| **Total** | **> 1 GB → OOM** | **~1.2 GB → 22 GB headroom** |
