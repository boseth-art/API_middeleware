#!/bin/bash
redis-server --daemonize yes
sleep 1
redis-cli flushall
npm start > server.log 2>&1 &
PROXY_PID=$!
node src/worker.js > worker.log 2>&1 &
WORKER_PID=$!
sleep 2

echo "Running Extensive Benchmarks..."
node extensive_benchmark.js

kill $PROXY_PID
kill $WORKER_PID
redis-cli shutdown
