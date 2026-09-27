# API Rate Limiter and Request Queuing Middleware (Version 2)

This project implements a Node.js middleware/proxy designed to protect a backend service (like a database login) from sudden traffic spikes by incorporating **Rate Limiting**, **Request Queuing**, and **Circuit Breaker** patterns.

## Problem Statement

A common issue in popular services is database overload due to simultaneous login attempts, especially during peak hours. This middleware aims to mitigate such issues by controlling the flow of requests and gracefully handling excess load.

## Key Concepts Implemented

*   **Rate Limiting (Token Bucket Algorithm)**: Controls the rate at which requests are processed. When the rate limit is exceeded, requests are not immediately rejected but rather queued.
*   **Request Queuing (Redis List)**: Stores incoming requests that exceed the rate limit in a queue, to be processed when capacity becomes available. This prevents immediate rejection and improves user experience during high load.
*   **Circuit Breaker**: Protects the backend service from being overwhelmed. If the backend experiences a high rate of failures, the circuit "opens," stopping requests from reaching it for a period, allowing it to recover.
*   **Distributed State (Redis)**: Redis is used to maintain the state of the Token Bucket and the Request Queue, enabling the middleware to scale horizontally across multiple instances.

## Project Structure

*   `index.js`: The main Express.js application, acting as the proxy server. It handles incoming requests, applies rate limiting, queues excess requests, and dispatches them via the circuit breaker.
*   `src/rateLimiter.js`: Implements the `TokenBucket` algorithm using Redis for distributed token management with a Lua script for atomic token consumption.
*   `src/requestQueue.js`: Manages a distributed request queue using Redis lists, allowing push and blocking pop operations.
*   `src/circuitBreaker.js`: Implements an in-memory circuit breaker pattern.
*   `src/worker.js`: A separate process responsible for continuously pulling requests from the `RequestQueue` and dispatching them to the backend when allowed by the rate limiter and circuit breaker.
*   `test/`: Contains unit tests for the core components using Mocha and Chai.

## API Endpoints

*   **`POST /login`**: The primary entry point. Simulates a login attempt that is passed through the rate limiter, queued if needed, and protected by the circuit breaker.
*   **`GET /status`**: A monitoring endpoint returning the current state of the Token Bucket, Request Queue length, and Circuit Breaker state.
*   **`ALL /db-login`**: A mock internal backend endpoint used by the proxy and worker to simulate real database logic and occasional failures.

## Setup and Installation

### Prerequisites

*   **Node.js**: v748.0 or higher is required as the project utilizes native `fetch` and ES Modules.
*   **Redis**: A running Redis instance is required for distributed state management.

### Installation Steps

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/boseth-art/API_middeleware.git
    cd API_middeleware
    ```

2.  **Install dependencies**:
    ```bash
    npm install
    ```

3.  **Start a Redis Server**:
    This project relies on a running Redis instance. The easiest way to get one is using Docker:
    ```bash
    docker run --name my-redis -p 6379:6379 -d redis
    ```
    (To stop and remove later: `docker stop my-redis && docker rm my-redis`)

## How to Run the Project

1.  **Start the Proxy Server**:
    Open your terminal in the project directory and run:
    ```bash
    npm start
    ```
    The proxy server will start on `http://localhost:3000`. It includes a mock backend service running internally that responds to `http://localhost:3001/db-login`.

2.  **Start the Worker Process**:
    Open a *new terminal* in the same project directory and run:
    ```bash
    node src/worker.js
    ```
    This worker will continuously process queued requests that were held back due to rate limiting.

## How to Test (Manual)

Once both the proxy server and the worker are running, you can interact with the endpoints.

*   **Send a login request**:
    Use `curl` or Postman to send a POST request to `http://localhost:3000/login` with a JSON body:
    ```bash
    curl -X POST -H "Content-Type: application/json" -d '{"username": "userX", "password": "password"}' http://localhost:3000/login
    ```
    Observe the server logs. If requests exceed the rate limit, they will be queued.
    The mock backend (`/db-login`) has a 20% chance of failure to simulate an unstable service, which will trigger the circuit breaker.

*   **Check status**:
    Access `http://localhost:3000/status` in your browser or with `curl` to see the current state of the system:
    ```bash
    curl http://localhost:3000/status
    ```

## Running Automated Tests

1.  **Ensure Redis is running** (as described in the "Setup and Installation" section).
2.  In your project directory, run:
    ```bash
    npm test
    ```
    This will execute all unit tests for `TokenBucket`, `RequestQueue`, and `CircuitBreaker` and report the results.

## Configuration

You can tweak the threshold values in `index.js` and `src/worker.js` to observe different system behaviors under load:
*   `RATE_LIMIT_CAPACITY`: Maximum burst of requests allowed.
*   `RATE_LIMIT_FILL_RATE`: Number of requests permitted per second.
*   `QUEUE_MAX_SIZE`: Maximum number of requests to queue before rejecting outright.
*   `CIRCUIT_BREAKER_FAILURE_THRESHOLD`: Failures needed to trip the circuit open.

## Benchmarking and Analysis (Version 2)

Version 2 introduces comprehensive automated benchmarking and statistical analysis tools to thoroughly evaluate the middleware's performance, scalability, and security.

### Running Benchmarks
We provide several bash scripts to run various levels of load testing using Node.js:
*   `./run_all.sh` - Runs the standard `benchmark.js` script.
*   `./run_extensive.sh` - Runs the `extensive_benchmark.js` script for a more rigorous load test.
*   `./run_massive.sh` - Runs the `massive_benchmark.js` script to simulate extreme traffic spikes (e.g., 20,000 concurrent requests).

### Running Statistical Analysis
The `analysis/` directory contains Python scripts for generating detailed reports from the benchmark results. 
To run the full suite of analysis tests:
```bash
python3 analysis/run_all_analysis.py
```
This will generate JSON reports (e.g., `performance_results.json`, `scalability_results.json`, `security_findings.json`) and a comprehensive markdown report (`analysis_report.md`).

### Performance Benchmarks & Drop Rate
We conducted a massive load test consisting of **20,000 concurrent requests** to evaluate the middleware's resilience.

**Test Results (20,000 Requests):**
*   **Success (200)**: 157
*   **Queued (202)**: 19,095 (Absorbed by the Redis Queue)
*   **Rate Limited / Dropped (429)**: 0 
*   **Errors / Circuit Breaker (500)**: 748

**Drop Rate Analysis:**
Under extreme load, the system achieved a **0% drop rate** (0 requests dropped). This is the intended behavior: the system aggressively sheds excess load that exceeds both the token bucket capacity and the maximum queue size (75), ensuring the backend service remains perfectly stable and responsive for the successful requests.

*(Detailed data is available in `benchmark_dataset.csv`)*

## Microsoft Learn Achievements
*   *[Please insert your achievements from your profile here (https://learn.microsoft.com/en-us/users/bosethrathnayake-5755/)]*
