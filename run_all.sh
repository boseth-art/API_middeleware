#!/bin/bash
redis-server --daemonize yes
sleep 1
npm start > server.log 2>&1 &
PROXY_PID=$!
node src/worker.js > worker.log 2>&1 &
WORKER_PID=$!
sleep 2

echo "Running Unit Tests..."
npm test > test_results.txt 2>&1

echo "Running Benchmarks..."
node benchmark.js

kill $PROXY_PID
kill $WORKER_PID
redis-cli shutdown
