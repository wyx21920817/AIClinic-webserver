FROM python:3.10-slim-bullseye

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Install only necessary system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    lsof \
    curl \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy the rest of the application
COPY . .

# Create a new restart.sh script that properly uses environment variables
RUN rm -f restart.sh && \
    echo '#!/bin/bash' > restart.sh && \
    echo '' >> restart.sh && \
    echo 'echo "Starting server on port $PORT..."' >> restart.sh && \
    echo 'python3 -m uvicorn main:app --host 0.0.0.0 --port $PORT' >> restart.sh && \
    chmod +x restart.sh

# Create necessary directories
RUN mkdir -p docs

# Default port (can be overridden at build time)
ENV PORT=${PORT}

# Expose the port the app runs on
EXPOSE ${PORT}

# Command to run the application
# Using shell form to ensure environment variables are expanded
CMD ./restart.sh
