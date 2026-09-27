#!/bin/bash
echo "Flushing Redis..."
redis-cli flushall

echo "Starting Proxy Server..."
npm start > server_massive.log 2>&1 &
PROXY_PID=$!

echo "Starting 50 Workers..."
for i in {1..50}; do
  node src/worker.js >> worker_massive.log 2>&1 &
  WORKER_PIDS+=($!)
done

sleep 2

echo "Running Massive Benchmark..."
node massive_benchmark.js

echo "Cleaning up..."
kill $PROXY_PID
for pid in "${WORKER_PIDS[@]}"; do
  kill $pid
done
