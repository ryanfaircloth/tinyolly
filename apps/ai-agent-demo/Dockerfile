FROM python:3.14-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py .

# Run directly - instrumentation is initialized in code
# Works with both manual setup and OTel operator injection
CMD ["python", "-u", "agent.py"]
