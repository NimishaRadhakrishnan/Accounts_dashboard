FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --create-home --uid 10001 vbt && mkdir -p /data/uploads && chown -R vbt /data
USER vbt

EXPOSE 8100
# Apply migrations, then serve. Workers=2 is plenty for a small accounts team.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8100 --workers 2 --proxy-headers --forwarded-allow-ips='*'"]
