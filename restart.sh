#!/bin/bash

# Check and kill existing server process
echo "Checking for running server..."
if [ -f ".pid" ]; then
    pid=$(cat .pid)
    if ps -p $pid > /dev/null; then
        echo "Killing process $pid"
        kill $pid
    fi
    rm .pid
fi

# Check if port 8000 is in use
pid=$(lsof -t -i:8000)
if [ ! -z "$pid" ]; then
    echo "Killing process on port 8000: $pid"
    kill -9 $pid
fi

# Detect OS and set virtual environment paths
if [ -d "venv/Scripts" ]; then
    # Windows paths
    VENV_ACTIVATE="venv/Scripts/activate"
    VENV_PYTHON="venv/Scripts/python"
else
    # Unix paths
    VENV_ACTIVATE="venv/bin/activate"
    VENV_PYTHON="venv/bin/python3"
fi

# Create or activate virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    # Ensure python3-venv is installed on Ubuntu
    if command -v apt-get &> /dev/null; then
        echo "Installing python3-venv..."
        sudo apt-get update && sudo apt-get install -y python3-venv python3-pip python3-full
    fi
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source $VENV_ACTIVATE

# Upgrade pip first
echo "Upgrading pip..."
$VENV_PYTHON -m pip install --upgrade pip setuptools wheel

# Always ensure requirements are installed
echo "Installing/updating requirements..."
$VENV_PYTHON -m pip install -r requirements.txt --no-cache-dir

# Start the server using venv python
echo "Starting server..."
$VENV_PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8000 &
echo $! > .pid

echo "Server started with PID: $(cat .pid)"
