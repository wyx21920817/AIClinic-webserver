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

# Also check if port 5000 is in use
pid=$(lsof -t -i:5000)
if [ ! -z "$pid" ]; then
    echo "Killing process on port 5000: $pid"
    kill -9 $pid
fi

echo "Starting server..."
python3 -m uvicorn main:app --host 0.0.0.0 --port 5000 &
echo $! > .pid

echo "Server started with PID: $(cat .pid)"
