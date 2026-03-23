FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Create upload dir
RUN mkdir -p uploads

EXPOSE 5000

# Production server – Render injects $PORT (default 10000)
ENV PORT=10000
CMD gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300 --workers 1 --max-requests 200
