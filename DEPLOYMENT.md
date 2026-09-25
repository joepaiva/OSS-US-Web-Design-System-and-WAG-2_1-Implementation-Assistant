# DEPLOYMENT.md

```markdown
# Deployment Guide

> Production deployment guide for the application.
> Last updated: 2025

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Database Setup](#database-setup)
- [Docker Deployment](#docker-deployment)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| RAM | 2 GB | 8 GB |
| Disk | 20 GB | 50 GB |
| OS | Ubuntu 20.04 | Ubuntu 22.04 LTS |

### Required Software

Ensure the following tools are installed before proceeding:

- **Docker** `>= 24.0.0`
  ```bash
  docker --version
  # Docker version 24.0.0, build abcdef
  ```

- **Docker Compose** `>= 2.20.0`
  ```bash
  docker compose version
  # Docker Compose version v2.20.0
  ```

- **Git** `>= 2.40.0`
  ```bash
  git --version
  ```

- **Make** *(optional but recommended)*
  ```bash
  make --version
  ```

### Install Docker (Ubuntu)

```bash
# Remove old versions
sudo apt-get remove docker docker-engine docker.io containerd runc

# Install dependencies
sudo apt-get update
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up the repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add current user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

### Network Requirements

- Inbound: `80` (HTTP), `443` (HTTPS), `22` (SSH)
- Outbound: `443` (package registries, external APIs)
- Internal: `5432` (PostgreSQL), `6379` (Redis), `8080` (App)

---

## Environment Variables

### Setup

Copy the example environment file and configure it for your environment:

```bash
cp .env.example .env
```

> ⚠️ **Never commit `.env` to version control.**
> Ensure `.env` is listed in `.gitignore`.

### Variable Reference

#### Application

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NODE_ENV` | ✅ | `production` | Runtime environment |
| `APP_PORT` | ✅ | `8080` | Port the app listens on |
| `APP_HOST` | ✅ | `0.0.0.0` | Host binding |
| `APP_URL` | ✅ | — | Public-facing base URL |
| `LOG_LEVEL` | ❌ | `info` | Logging verbosity (`debug`, `info`, `warn`, `error`) |
| `SECRET_KEY` | ✅ | — | Application secret key (min 32 chars) |
| `ALLOWED_HOSTS` | ✅ | — | Comma-separated list of allowed hostnames |

#### Database

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DB_HOST` | ✅ | `localhost` | PostgreSQL host |
| `DB_PORT` | ✅ | `5432` | PostgreSQL port |
| `DB_NAME` | ✅ | — | Database name |
| `DB_USER` | ✅ | — | Database user |
| `DB_PASSWORD` | ✅ | — | Database password |
| `DB_SSL` | ❌ | `true` | Enable SSL connection |
| `DB_POOL_MIN` | ❌ | `2` | Minimum connection pool size |
| `DB_POOL_MAX` | ❌ | `10` | Maximum connection pool size |

#### Cache / Redis

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_HOST` | ✅ | `localhost` | Redis host |
| `REDIS_PORT` | ✅ | `6379` | Redis port |
| `REDIS_PASSWORD` | ✅ | — | Redis auth password |
| `REDIS_DB` | ❌ | `0` | Redis database index |
| `CACHE_TTL` | ❌ | `3600` | Default cache TTL in seconds |

#### Authentication

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `JWT_SECRET` | ✅ | — | JWT signing secret (min 64 chars) |
| `JWT_EXPIRES_IN` | ❌ | `7d` | JWT token expiry |
| `REFRESH_TOKEN_SECRET` | ✅ | — | Refresh token signing secret |
| `REFRESH_TOKEN_EXPIRES_IN` | ❌ | `30d` | Refresh token expiry |

#### Email

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SMTP_HOST` | ✅ | — | SMTP server host |
| `SMTP_PORT` | ✅ | `587` | SMTP server port |
| `SMTP_USER` | ✅ | — | SMTP username |
| `SMTP_PASSWORD` | ✅ | — | SMTP password |
| `EMAIL_FROM` | ✅ | — | Default sender address |

#### Storage

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STORAGE_DRIVER` | ❌ | `local` | Storage driver (`local`, `s3`) |
| `AWS_ACCESS_KEY_ID` | ⚠️ | — | Required if `STORAGE_DRIVER=s3` |
| `AWS_SECRET_ACCESS_KEY` | ⚠️ | — | Required if `STORAGE_DRIVER=s3` |
| `AWS_REGION` | ⚠️ | — | AWS region |
| `AWS_S3_BUCKET` | ⚠️ | — | S3 bucket name |

### Example `.env` File

```dotenv
# ── Application ──────────────────────────────────────────
NODE_ENV=production
APP_PORT=8080
APP_HOST=0.0.0.0
APP_URL=https://yourdomain.com
LOG_LEVEL=info
SECRET_KEY=your-super-secret-key-minimum-32-characters-long
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# ── Database ─────────────────────────────────────────────
DB_HOST=postgres
DB_PORT=5432
DB_NAME=appdb
DB_USER=appuser
DB_PASSWORD=strongpassword123
DB_SSL=true
DB_POOL_MIN=2
DB_POOL_MAX=10

# ── Redis ─────────────────────────────────────────────────
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=redispassword123
REDIS_DB=0
CACHE_TTL=3600

# ── Authentication ────────────────────────────────────────
JWT_SECRET=your-jwt-secret-minimum-64-characters-long-for-security
JWT_EXPIRES_IN=7d
REFRESH_TOKEN_SECRET=your-refresh-token-secret-also-minimum-64-chars
REFRESH_TOKEN_EXPIRES_IN=30d

# ── Email ─────────────────────────────────────────────────
SMTP_HOST=smtp.mailprovider.com
SMTP_PORT=587
SMTP_USER=noreply@yourdomain.com
SMTP_PASSWORD=smtppassword123
EMAIL_FROM="App Name <noreply@yourdomain.com>"

# ── Storage ───────────────────────────────────────────────
STORAGE_DRIVER=s3
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_REGION=us-east-1
AWS_S3_BUCKET=your-app-bucket
```

### Generating Secure Secrets

```bash
# Generate a 64-character secret key
openssl rand -base64 48

# Generate a UUID-based secret
cat /proc/sys/kernel/random/uuid | tr -d '-' | head -c 32

# Using Node.js
node -e "console.log(require('crypto').randomBytes(64).toString('hex'))"
```

---

## Database Setup

### PostgreSQL Initialization

#### 1. Connect to PostgreSQL

```bash
# Via Docker
docker exec -it postgres psql -U postgres

# Via psql client
psql -h localhost -U postgres
```

#### 2. Create Database and User

```sql
-- Create application user
CREATE USER appuser WITH PASSWORD 'strongpassword123';

-- Create database
CREATE DATABASE appdb
    WITH
    OWNER = appuser
    ENCODING = 'UTF8'
    LC_COLLATE = 'en_US.UTF-8'
    LC_CTYPE = 'en_US.UTF-8'
    TEMPLATE = template0;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE appdb TO appuser;

-- Connect to the new database
\c appdb

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO appuser;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO appuser;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO appuser;

-- Ensure future tables are accessible
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON TABLES TO appuser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON SEQUENCES TO appuser;
```

#### 3. Enable Required Extensions

```sql
-- Connect to the application database
\c appdb

-- UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Cryptographic functions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Full-text search improvements
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Verify extensions
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE installed_version IS NOT NULL;
```

### Running Migrations

```bash
# Run all pending migrations
docker compose exec app npm run migrate

# Run migrations with verbose output
docker compose exec app npm run migrate -- --verbose

# Check migration status
docker compose exec app npm run migrate:status

# Rollback last migration (use with caution in production)
docker compose exec app npm run migrate:rollback
```

### Seeding Initial Data

```bash
# Seed required lookup data (roles, permissions, etc.)
docker compose exec app npm run seed

# Seed specific module
docker compose exec app npm run seed -- --module=roles
```

### Database Backup

#### Manual Backup

```bash
# Full database backup
docker exec postgres pg_dump \
    -U appuser \
    -d appdb \
    -F c \
    -f /tmp/backup_$(date +%Y%m%d_%H%M%S).dump

# Copy backup from container
docker cp postgres:/tmp/backup_*.dump ./backups/
```

#### Automated Backup Script

```bash
#!/bin/bash
# /opt/scripts/db-backup.sh

set -euo pipefail

BACKUP_DIR="/opt/backups/postgres"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/appdb_${TIMESTAMP}.dump"
RETENTION_DAYS=30

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting database backup..."

docker exec postgres pg_dump \
    -U appuser \
    -d appdb \
    -F c \
    -f "/tmp/backup_${TIMESTAMP}.dump"

docker cp "postgres:/tmp/backup_${TIMESTAMP}.dump" "$BACKUP_FILE"
docker exec postgres rm "/tmp/backup_${TIMESTAMP}.dump"

# Compress backup
gzip "$BACKUP_FILE"

echo "[$(date)] Backup saved to ${BACKUP_FILE}.gz"

# Remove old backups
find "$BACKUP_DIR" -name "*.dump.gz" -mtime +${RETENTION_DAYS} -delete
echo "[$(date)] Removed backups older than ${RETENTION_DAYS} days"
```

```bash
# Make executable and schedule
chmod +x /opt/scripts/db-backup.sh

# Add to crontab (daily at 2:00 AM)
echo "0 2 * * * /opt/scripts/db-backup.sh >> /var/log/db-backup.log 2>&1" | crontab -
```

#### Restore from Backup

```bash
# Restore from dump file
docker exec -i postgres pg_restore \
    -U appuser \
    -d appdb \
    --clean \
    --if-exists \
    < ./backups/appdb_20250101_020000.dump.gz
```

### Database Health Check

```sql
-- Check active connections
SELECT count(*), state
FROM pg_stat_activity
WHERE datname = 'appdb'
GROUP BY state;

-- Check table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Check for long-running queries
SELECT pid, now() - query_start AS duration, query, state
FROM pg_stat_activity
WHERE state != 'idle'
  AND query_start < now() - interval '5 minutes';
```

---

## Docker Deployment

### Project Structure

```
.
├── docker-compose.yml          # Production compose file
├── docker-compose.override.yml # Local overrides (not committed)
├── Dockerfile                  # Application image
├── .dockerignore               # Docker build exclusions
├── nginx/
│   ├── nginx.conf              # Nginx configuration
│   └── ssl/                    # SSL certificates
├── .env                        # Environment variables
└── scripts/
    ├── entrypoint.sh           # Container entrypoint
    └── healthcheck.sh          # Health check script
```

### Dockerfile

```dockerfile
# ── Build Stage ───────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (layer caching)
COPY package*.json ./
RUN npm ci --only=production && npm cache clean --force

# Copy source and build
COPY . .
RUN npm run build

# ── Production Stage ──────────────────────────────────────
FROM node:20-alpine AS production

# Security: run as non-root user
RUN addgroup -g 1001 -S appgroup && \
    adduser -u 1001 -S appuser -G appgroup

WORKDIR /app

# Copy built artifacts
COPY --from=builder --chown=appuser:appgroup /app/dist ./dist
COPY --from=builder --chown=appuser:appgroup /app/node_modules ./node_modules
COPY --from=builder --chown=appuser:appgroup /app/package.json ./

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD wget -qO- http://localhost:8080/health || exit 1

USER appuser

EXPOSE 8080

CMD ["node", "dist/main.js"]
```

### Docker Compose Configuration

```yaml
# docker-compose.yml
version: "3.9"

services:

  # ── Application ─────────────────────────────────────────
  app:
    build:
      context: .
      dockerfile: Dockerfile
      target: production
    image: myapp:${APP_VERSION:-latest}
    container_name: app
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file:
      - .env
    ports:
      - "8080:8080"
    volumes:
      - app_uploads:/app/uploads
      - app_logs:/app/logs
    networks:
      - app_network
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 512M
        reservations:
          cpus: "0.25"
          memory: 128M
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "5"

  # ── PostgreSQL ───────────────────────────────────────────
  postgres:
    image: postgres:16-alpine
    container_name: postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/init.sql:ro
    networks:
      - app_network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 1G
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  # ── Redis ────────────────────────────────────────────────
  redis:
    image: redis:7-alpine
    container_name: redis
    restart: unless-stopped
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD}
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
      --save 900 1
      --save 300 10
      --save 60 10000
    volumes:
      - redis_data:/data
    networks:
      - app_network
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 256M
    logging:
      driver: "json-file"
      options:
        max-size: "5m"
        max-file: "3"

  # ── Nginx Reverse Proxy ──────────────────────────────────
  nginx:
    image: nginx:1.25-alpine
    container_name: nginx
    restart: unless-stopped
    depends_on:
      - app
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - nginx_logs:/var/log/nginx
    networks:
      - app_network
    healthcheck:
      test: ["CMD", "nginx", "-t"]
      interval: 30s
      timeout: 10s
      retries: 3
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "5"

# ── Volumes ──────────────────────────────────────────────
volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
  app_uploads:
    driver: local
  app_logs:
    driver: local
  nginx_logs:
    driver: local

# ── Networks ─────────────────────────────────────────────
networks:
  app_network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

### Nginx Configuration

```nginx
# nginx/nginx.conf

user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for" '
                    'rt=$request_time uct=$upstream_connect_time '
                    'uht=$upstream_header_time urt=$upstream_response_time';

    access_log /var/log/nginx/access.log main;

    # Performance
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 50M;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    # Hide Nginx version
    server_tokens off;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css application/json application/javascript
               text/xml application/xml application/xml+rss text/javascript;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=auth:10m rate=5r/m;

    # Upstream
    upstream app_backend {
        server app:8080;
        keepalive 32;
    }

    # HTTP → HTTPS redirect
    server {
        listen 80;
        server_name yourdomain.com www.yourdomain.com;

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        location / {
            return 301 https://$host$request_uri;
        }
    }

    # HTTPS server
    server {
        listen 443 ssl http2;
        server_name yourdomain.com www.yourdomain.com;

        # SSL configuration
        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;
        ssl_session_timeout 1d;
        ssl_session_cache shared:SSL:50m;
        ssl_session_tickets off;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
        ssl_prefer_server_ciphers off;

        # API routes
        location /api/ {
            limit_req zone=api burst=20 nodelay;

            proxy_pass http://app_backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_cache_bypass $http_upgrade;
            proxy_read_timeout 60s;
            proxy_connect_timeout 10s;
        }

        # Auth routes (stricter rate limiting)
        location /api/auth/ {
            limit_req zone=auth burst=5 nodelay;

            proxy_pass http://app_backend;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Health check (no rate limiting)
        location /health {
            proxy_pass http://app_backend;
            access_log off;
        }

        # Static files
        location /static/ {
            alias /app/static/;
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }
}
```

### Deployment Steps

#### 1. Clone and Configure

```bash
# Clone repository
git clone https://github.com/your-org/your-app.git
cd your-app

# Checkout production tag
git checkout v1.0.0

# Configure environment
cp .env.example .env
nano .env  # Edit with your production values
```

#### 2. SSL Certificate Setup

```bash
# Option A: Let's Encrypt (recommended)
sudo apt-get install -y certbot

certbot certonly \
    --standalone \
    --preferred-challenges http \
    -d yourdomain.com \
    -d www.yourdomain.com \
    --email admin@yourdomain.com \
    --agree-tos \
    --non-interactive

# Copy certificates
mkdir -p ./nginx/ssl
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ./nginx/ssl/
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ./nginx/ssl/

# Option B: Self-signed (development/staging only)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout ./nginx/ssl/privkey.pem \
    -out ./nginx/ssl/fullchain.pem \
    -subj "/C=US/ST=State/L=City/O=Org/CN=yourdomain.com"
```

#### 3. Build and Start Services

```bash
# Pull latest base images
docker compose pull postgres redis nginx

# Build application image
docker compose build --no-cache app

# Start all services in detached mode
docker compose up -d

# Verify all containers are running
docker compose ps
```

#### 4. Initialize Database

```bash
# Wait for PostgreSQL to be ready
docker compose exec postgres pg_isready -U appuser -d appdb

# Run migrations
docker compose exec app npm run migrate

# Seed initial data
docker compose exec app npm run seed

# Verify
docker compose exec postgres psql -U appuser -d appdb -c "\dt"
```

#### 5. Verify Deployment

```bash
# Check all services are healthy
docker compose ps

# Check application logs
docker compose logs --tail=50 app

# Test health endpoint
curl -f https://yourdomain.com/health

# Test API
curl -X GET https://yourdomain.com/api/v1/status
```

### Zero-Downtime Updates

```bash
#!/bin/bash
# scripts/deploy.sh

set -euo pipefail

APP_VERSION=${1:-latest}
echo "🚀 Deploying version: $APP_VERSION"

# Pull latest code
git fetch origin
git checkout "v${APP_VERSION}"

# Build new image
echo "🔨 Building new image..."
docker compose build --no-cache app

# Run migrations before switching traffic
echo "📦 Running migrations..."
docker compose run --rm app npm run migrate

# Rolling restart (zero downtime)
echo "🔄 Restarting application..."
docker compose up -d --no-deps --scale app=2 app
sleep 15
docker compose up -d --no-deps --scale app=1 app

echo "✅ Deployment complete!"

# Verify
docker compose ps
curl -sf https://yourdomain.com/health && echo "Health check passed ✓"
```

```bash
chmod +x scripts/deploy.sh
./scripts/deploy.sh 1.2.0
```

### Rollback Procedure

```bash
# Rollback to previous version
git checkout v1.1.0
docker compose build app
docker compose up -d --no-deps app

# Rollback database migration (if needed)
docker compose exec app npm run migrate:rollback

# Verify rollback
curl -f https://yourdomain.com/health
```

### Useful Docker Commands

```bash
# View real-time logs
docker compose logs -f app
docker compose logs -f --tail=100 nginx

# Execute commands in running container
docker compose exec app sh
docker compose exec postgres psql -U appuser -d appdb

# Inspect container resource usage
docker stats

# View container details
docker compose inspect app

# Clean up unused resources
docker system prune -f
docker volume prune -f  # ⚠️ Only if you want to remove unused volumes

# Force recreate containers
docker compose up -d --force-recreate

# Scale application (if load balanced)
docker compose up -d --scale app=3
```

---

## Monitoring

### Health Check Endpoints

The application exposes the following health endpoints:

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Overall application health |
| `GET /health/live` | Liveness probe (is the app running?) |
| `GET /health/ready` | Readiness probe (is the app ready to serve?) |
| `GET /metrics` | Prometheus metrics (if enabled) |

#### Example Health Response

```json
{
  "status": "healthy",
  "timestamp": "2025-01-01T00:00:00.000Z",
  "uptime": 86400,
  "version": "1.0.0",
  "checks": {
    "database": {
      "status": "healthy",
      "responseTime": "2ms"
    },
    "redis": {
      "status": "healthy",
      "responseTime": "1ms"
    },
    "memory": {
      "status": "healthy",
      "used": "128MB",
      "total": "512MB",
      "percentage": 25
    }
  }
}
```

### Prometheus + Grafana Stack

#### Docker Compose Addition

```yaml
# Add to docker-compose.yml

  # ── Prometheus ───────────────────────────────────────────
  prometheus:
    image: prom/prometheus:v2.48.0
    container_name: prometheus
    restart: unless-stopped
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
      - '--web.console.libraries=/usr