FROM python:3.11-slim

WORKDIR /app

# Install system dependency for PDF rendering (optional, used by some PDF libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY digest.py .

ENTRYPOINT ["python", "digest.py"]
