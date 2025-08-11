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

# Fix line endings and make restart.sh executable
RUN sed -i 's/\r$//' restart.sh && chmod +x restart.sh

# Create a modified restart script that runs in foreground instead of background
RUN sed -i 's/nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 > server.log 2>\&1 \&/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000/' restart.sh && \
    sed -i '/echo $! > .pid/d' restart.sh && \
    sed -i '/echo "Server started with PID: $(cat .pid)"/d' restart.sh

# Create necessary directories
RUN mkdir -p docs

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD ["/bin/bash", "-c", "./restart.sh && tail -f server.log"]
