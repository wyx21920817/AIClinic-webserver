#!/bin/bash

echo "Checking for running server..."
if [ -f ".pid" ]; then
    pid=$(cat .pid)
    if ps -p $pid > /dev/null; then
        echo "Killing process $pid"
        kill $pid
    fi
    rm .pid
fi

# Get port from environment variable or default to 8000
PORT=${PORT}

# Also check if the port is in use
pid=$(lsof -t -i:$PORT)
if [ ! -z "$pid" ]; then
    echo "Killing process on port $PORT: $pid"
    kill -9 $pid
fi

echo "Starting server on port $PORT..."
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port $PORT > server.log 2>&1 &
echo $! > .pid

echo "Server started with PID: $(cat .pid)"
