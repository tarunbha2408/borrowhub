# 🚀 BorrowHub SVNIT — Complete Production Deployment Guide

This guide walks you through deploying **BorrowHub** to the internet so students across all SVNIT departments can access it from their laptops and phones, receive real verification OTPs in their student email inboxes, and borrow/share campus resources securely.

---

## 📋 Table of Contents
1. [Architecture Overview](#1-architecture-overview)
2. [Setting Up Real Email Delivery (SMTP)](#2-setting-up-real-email-delivery-smtp)
   - [Option A: Personal Gmail + App Password (Fastest & Free)](#option-a-personal-gmail--app-password)
   - [Option B: Brevo (Recommended for Cloud Deployments)](#option-b-brevo-free-300-emailsday)
3. [Setting Up a Free Cloud MySQL Database](#3-setting-up-a-free-cloud-mysql-database)
4. [Deploying BorrowHub to the Web (Option 1: Render — Free & Easy)](#4-deploying-to-render-free--easiest)
5. [Deploying BorrowHub to Railway (Option 2)](#5-deploying-to-railway)
6. [Deploying to a Linux VPS (Ubuntu / AWS / DigitalOcean)](#6-deploying-to-a-linux-vps-aws--digitalocean)
7. [Environment Variables Cheat Sheet](#7-environment-variables-cheat-sheet)
8. [Post-Deployment Verification Checklist](#8-post-deployment-verification-checklist)

---

## 1. Architecture Overview

BorrowHub is a high-performance full-stack web application:
- **Backend:** FastAPI (Python 3.11+) with Uvicorn.
- **Frontend:** Responsive vanilla HTML5, CSS3, and JavaScript (served directly by FastAPI or a CDN).
- **Database:** MySQL 8.0+ with transaction safety, triggers, and indices.
- **Email Service:** Real SMTP dispatch for student verification codes, password resets, and damage dispute alerts.
- **Media Uploads:** Cloudinary (for cloud image storage) or local disk.

---

## 2. Setting Up Real Email Delivery (SMTP)

Because college/institutional Google Workspace accounts (`@coed.svnit.ac.in`) have App Passwords blocked by the university IT department, use one of the two solutions below to send verification emails from BorrowHub to students.

### Option A: Personal Gmail + App Password

You can use any personal Gmail account (or create a dedicated free account like `svnit.borrowhub@gmail.com`).

1. Log in to your personal Google account.
2. Ensure **2-Step Verification** is turned on in your [Google Security Settings](https://myaccount.google.com/security).
3. Open **[Google App Passwords](https://myaccount.google.com/apppasswords)**.
4. In the "App name" box, type **BorrowHub** and click **Create**.
5. Google will generate a **16-character code** (e.g. `abcd efgh ijkl mnop`).
6. Configure your environment variables:
   ```env
   SMTP_HOST="smtp.gmail.com"
   SMTP_PORT=587
   SMTP_USER="your.personal.email@gmail.com"
   SMTP_PASSWORD="abcdefghijklmnop"
   SMTP_FROM_EMAIL="your.personal.email@gmail.com"
   SMTP_FROM_NAME="BorrowHub SVNIT"
   SMTP_TLS=True
   ```
> **How students see it:** When any student registers with their SVNIT ID (e.g. `u22cs001@coed.svnit.ac.in` or `u25mc020@ahmd.svnit.ac.in`), the OTP arrives in their official SVNIT inbox from **"BorrowHub SVNIT"**.

---

### Option B: Brevo (Free 300 Emails/Day — Recommended for Cloud)

[Brevo](https://www.brevo.com/) (formerly Sendinblue) provides free transactional SMTP for websites without Google restrictions.

1. Create a free account at [brevo.com](https://www.brevo.com/).
2. In your dashboard, click your profile name at the top right and select **SMTP & API**.
3. Under the **SMTP** tab, click **Generate a new SMTP key**.
4. Copy your SMTP server, port, login, and generated master password.
5. Configure your environment variables:
   ```env
   SMTP_HOST="smtp-relay.brevo.com"
   SMTP_PORT=587
   SMTP_USER="your-brevo-login-email@example.com"
   SMTP_PASSWORD="your-generated-brevo-smtp-key"
   SMTP_FROM_EMAIL="your-verified-email@example.com"
   SMTP_FROM_NAME="BorrowHub SVNIT"
   SMTP_TLS=True
   ```

---

## 3. Setting Up a Free Cloud MySQL Database

When deploying to the web, you need a cloud-hosted MySQL database.

### Using Aiven (Free MySQL Cloud):
1. Sign up for free at [aiven.io](https://aiven.io/).
2. Create a new service: select **MySQL** (Free tier available).
3. Once provisioned, copy the **Service URI**. It looks like:
   `mysql://avnadmin:password@mysql-xyz.aivencloud.com:12345/defaultdb?ssl-mode=REQUIRED`
4. Convert it to Python SQLAlchemy format by prefixing `mysql+pymysql://`:
   ```env
   DATABASE_URL="mysql+pymysql://avnadmin:password@mysql-xyz.aivencloud.com:12345/defaultdb?ssl_verify_cert=false"
   ```

### Initialize Database Tables & Triggers:
From your local terminal, run the initial schema migration against the cloud database:
```bash
python -m backend.migrations.versions.001_initial_schema
```
Or connect via MySQL Workbench / phpMyAdmin and execute the SQL migration script from `backend/migrations/`.

---

## 4. Deploying to Render (Free & Easiest)

[Render](https://render.com/) is one of the easiest platforms for deploying FastAPI applications.

### Step 1: Push your code to GitHub
```bash
git init
git add .
git commit -m "Initial commit for BorrowHub deployment"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/borrowhub.git
git push -u origin main
```

### Step 2: Create a Web Service on Render
1. Log in to [render.com](https://render.com/) and click **New +** → **Web Service**.
2. Connect your GitHub repository.
3. Configure the settings:
   - **Name:** `borrowhub-svnit`
   - **Region:** Singapore / Frankfurt / Oregon (choose closest to India, e.g. Singapore)
   - **Branch:** `main`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan:** Free

### Step 3: Add Environment Variables in Render Dashboard
Go to the **Environment** tab of your Render service and add:

| Key | Example Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `DEBUG` | `False` |
| `DATABASE_URL` | `mysql+pymysql://user:pass@host:port/dbname` |
| `JWT_SECRET_KEY` | *(generate a long random 32+ character string)* |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | `your.personal.email@gmail.com` |
| `SMTP_PASSWORD` | `your-16-char-app-password` |
| `SMTP_FROM_EMAIL` | `your.personal.email@gmail.com` |
| `SMTP_FROM_NAME` | `BorrowHub SVNIT` |
| `SMTP_TLS` | `True` |
| `CORS_ORIGINS` | `["*"]` |

4. Click **Deploy**. Render will build and deploy your app. You will receive a live URL like `https://borrowhub-svnit.onrender.com`.

---

## 5. Deploying to Railway

1. Sign up on [railway.app](https://railway.app/).
2. Click **New Project** → **Provision MySQL** (Railway will create an instant cloud MySQL database).
3. In the same project, click **New** → **GitHub Repo** → Select `borrowhub`.
4. In Railway variables, link `DATABASE_URL` directly from the MySQL service.
5. Add the SMTP credentials and `ENVIRONMENT="production"`.
6. Click **Generate Domain**. Your site is instantly live with HTTPS.

---

## 6. Deploying to a Linux VPS (AWS / DigitalOcean)

If deploying to an Ubuntu 22.04 / 24.04 server:

```bash
# 1. Update system & install Python + MySQL + Nginx
sudo apt update && sudo apt install -y python3-pip python3-venv mysql-server nginx git

# 2. Clone repository
git clone https://github.com/YOUR_USERNAME/borrowhub.git /var/www/borrowhub
cd /var/www/borrowhub

# 3. Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Configure .env
cp backend/.env.example backend/.env
nano backend/.env  # fill in production DB and SMTP details

# 5. Create Systemd Service
sudo nano /etc/systemd/system/borrowhub.service
```

Paste the systemd configuration:
```ini
[Unit]
Description=BorrowHub FastAPI Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/var/www/borrowhub
ExecStart=/var/www/borrowhub/venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 3
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable borrowhub
sudo systemctl start borrowhub
```

Configure Nginx reverse proxy with SSL:
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

---

## 7. Environment Variables Cheat Sheet

Create a `.env` file on your production server:

```env
PROJECT_NAME="BorrowHub"
ENVIRONMENT="production"
DEBUG=False
PORT=8000
HOST="0.0.0.0"

# Cloud Database URL
DATABASE_URL="mysql+pymysql://<user>:<password>@<cloud-host>:3306/<database>?charset=utf8mb4"

# Secret Key (Keep Private)
JWT_SECRET_KEY="generate_a_random_secure_key_here_change_for_prod"
JWT_ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=1440
OTP_EXPIRY_MINUTES=15

# Real Email Delivery (Gmail SMTP or Brevo)
SMTP_HOST="smtp.gmail.com"
SMTP_PORT=587
SMTP_USER="your-email@gmail.com"
SMTP_PASSWORD="your-16-char-app-password"
SMTP_FROM_EMAIL="your-email@gmail.com"
SMTP_FROM_NAME="BorrowHub SVNIT"
SMTP_TLS=True

# Admin Emails (Campus Managers who can mediate disputes)
ADMIN_EMAILS=["u22cs001@coed.svnit.ac.in","admin@svnit.ac.in"]
```

---

## 8. Post-Deployment Verification Checklist

Once deployed, perform this quick 5-step test:

- [ ] **Homepage loads:** Open your deployed URL. Marketplace items load without delay.
- [ ] **Student Registration:** Register with a real `@svnit.ac.in` student email.
- [ ] **Real Inbox Delivery:** Confirm the 6-digit OTP code arrives in the student Gmail/webmail inbox (check Spam folder if testing for the first time).
- [ ] **Strict Identity Check:** Verify that the code is **not** displayed on the screen or pre-filled in the browser.
- [ ] **Item Listing & Borrowing:** List an item and test requesting it from another account to verify the campus handover OTP flow.
