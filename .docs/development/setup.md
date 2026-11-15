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
Generate an AES-256 master key for `ENCRYPTION_MASTER_KEY`:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Paste the generated string into your `.env` file along with your local PostgreSQL credentials.

### Step 2.4: Prepare Database & Run Migrations
Create the PostgreSQL database (e.g. `readhead_db`):
```sql
CREATE DATABASE readhead_db;
```
Apply migrations via Alembic:
```bash
alembic upgrade head
```

### Step 2.5: Start the Development Server
```bash
uvicorn app.main:app --reload --port 8000
```
Open interactive API docs in your browser:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
