FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/readhead
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home readhead
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
USER readhead
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
