# BorrowHub — Deployment Guide

This guide covers both local development setup and production deployment for BorrowHub.

---

## 1. Local Development Setup (Quickstart)

### Prerequisites
* Python 3.10+ (Tested on Python 3.13)
* MySQL 8.0.16+ (Local instance or Docker container)
* Node.js / Modern Web Browser (Chrome, Firefox, Edge, Safari)

### Step 1: Database Initialization
1. Ensure your local MySQL server is running (e.g. on port 3306).
2. Connect to MySQL and apply the master production schema:
   ```bash
   mysql -u root -p < database/schema.sql
   ```
3. Load the pre-configured SVNIT seed data (categories, locations, test users, sample items):
   ```bash
   mysql -u root -p borrowhub < database/seed.sql
   ```

### Step 2: Backend Configuration
1. Navigate to the project root:
   ```bash
   cd /path/to/BorrowHub
   ```
2. Create or verify your environment configuration in `backend/.env`:
   ```env
   PROJECT_NAME=BorrowHub
   ENVIRONMENT=development
   DEBUG=True
   PORT=8000
   HOST=0.0.0.0

   # Database Connection String
   DATABASE_URL=mysql+pymysql://root:12345@localhost:3306/borrowhub?charset=utf8mb4

   # Security
   JWT_SECRET_KEY=borrowhub_super_secret_jwt_key_svnit_campus_2026_change_in_production
   JWT_ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=1440

   # Payment Gateway (Razorpay Test Mode)
   RAZORPAY_KEY_ID=rzp_test_borrowhub_dummy
   RAZORPAY_KEY_SECRET=rzp_secret_borrowhub_dummy
   RAZORPAY_WEBHOOK_SECRET=rzp_webhook_secret_borrowhub

   # Cloudinary (Optional - uses local upload fallback if empty)
   CLOUDINARY_CLOUD_NAME=
   CLOUDINARY_API_KEY=
   CLOUDINARY_API_SECRET=
   ```
3. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```

### Step 3: Run the Application
Start the unified FastAPI server (serves both API and frontend static files):
```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser to:
* **Web Application:** `http://localhost:8000`
* **Interactive API Documentation:** `http://localhost:8000/api/docs`
* **ReDoc Specifications:** `http://localhost:8000/api/redoc`

### Step 4: Run Automated Tests
Execute the comprehensive pytest test suite:
```bash
python -m pytest backend/tests -v
```

---

## 2. Production Deployment

### 2.1 Docker Deployment
Create a `Dockerfile` in the project root:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend and frontend source files
COPY backend ./backend
COPY frontend ./frontend
COPY database ./database

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### 2.2 Cloud Platform Hosting (Render, Railway, or AWS)
1. **Managed Database:** Provision a MySQL 8.0 managed database instance (e.g. AWS RDS, PlanetScale, or Railway MySQL).
2. **Apply Migrations:** Run Alembic migrations:
   ```bash
   alembic upgrade head
   ```
3. **Environment Secrets:** Configure environment variables in your hosting dashboard:
   - `DATABASE_URL`: `mysql+pymysql://<user>:<password>@<host>:<port>/borrowhub?ssl_ca=/path/to/ca`
   - `JWT_SECRET_KEY`: Generate a high-entropy 256-bit key via `openssl rand -hex 32`.
   - `ENVIRONMENT`: `production`
   - `DEBUG`: `False`
   - `RAZORPAY_KEY_ID` & `RAZORPAY_KEY_SECRET`: Live credentials from Razorpay Dashboard.
   - `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`: Production Cloudinary account.

### 2.3 Nginx Reverse Proxy Configuration
```nginx
server {
    listen 80;
    server_name borrowhub.svnit.ac.in;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name borrowhub.svnit.ac.in;

    ssl_certificate /etc/letsencrypt/live/borrowhub.svnit.ac.in/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/borrowhub.svnit.ac.in/privkey.pem;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
