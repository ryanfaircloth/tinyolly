# Unified demo image - can run frontend or backend via CMD
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy both frontend and backend
COPY frontend.py .
COPY backend.py .

EXPOSE 5000 8000

# Default to frontend, can be overridden in deployment
CMD ["python", "-u", "frontend.py"]
