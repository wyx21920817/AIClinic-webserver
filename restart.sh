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

# Also check if port 8000 is in use
pid=$(lsof -t -i:8001)
if [ ! -z "$pid" ]; then
    echo "Killing process on port 8001: $pid"
    kill -9 $pid
fi

echo "Starting server..."
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
echo $! > .pid

echo "Server started with PID: $(cat .pid)"
