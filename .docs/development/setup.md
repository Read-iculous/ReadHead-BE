# Local Development Setup Guide

## 1. Prerequisites
- **Python**: Version 3.10, 3.11, or 3.12 installed.
- **PostgreSQL**: Version 15+ running locally (e.g., standard PostgreSQL service or Docker container).
- **Git**: Installed and configured.

---

## 2. Step-by-Step Environment Setup

### Step 2.1: Clone & Create Virtual Environment
```bash
# In the project root
python -m venv venv

# Activate virtual environment
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On Linux/macOS:
source venv/bin/activate
```

### Step 2.2: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Step 2.3: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Generate an AES-256-GCM master key for `ENCRYPTION_MASTER_KEY`:
```bash
python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```
Paste the generated string into your `.env` file along with your local PostgreSQL and Redis credentials.

### Step 2.4: Prepare Database & Redis Services
1. **PostgreSQL**: Create the database (e.g. `readhead_db`):
```sql
CREATE DATABASE readhead_db;
```
Apply migrations via Alembic:
```bash
alembic upgrade head
```

2. **Redis**: Ensure a Redis instance is running locally on port 6379:
```bash
# Using Docker:
docker run -d --name readhead-redis -p 6379:6379 redis:7-alpine

# Or using local system service (Ubuntu/Debian):
sudo systemctl start redis-server
```

### Step 2.5: Bootstrap Initial Super Admin (Optional for Admin Portal)
Create the initial administrator account:
```bash
python -m app.cli.create_admin --email admin@readhead.io --password "SecureAdminPassword123!"
```

### Step 2.6: Start the Development Server
```bash
uvicorn app.main:app --reload --port 8000
```
Open interactive API docs in your browser:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
