# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install system dependencies if needed (e.g., for certain libraries)
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# We copy individual directories needed by the services
COPY webapp /app/webapp
COPY bot /app/bot
COPY uploader /app/uploader

# Note: .env file is NOT copied into the image for security.
# It will be mounted via docker-compose.

# Expose the port the Flask app runs on (if running Flask directly, or Gunicorn)
EXPOSE 5000

# Default command can be overridden in docker-compose.yml
# CMD ["python", "webapp/app.py"]