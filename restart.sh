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

# Activate virtual environment
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/Scripts/activate
else
    echo "Creating virtual environment..."
    python -m venv venv
    source venv/Scripts/activate
    echo "Installing requirements..."
    pip install -r requirements.txt
fi

# Start the server using venv python
echo "Starting server..."
venv/Scripts/python -m uvicorn main:app --host 0.0.0.0 --port 8000 &
echo $! > .pid

echo "Server started with PID: $(cat .pid)"
