# API Rate Limiter and Request Queuing Middleware

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
*   `src/rateLimiter.js`: Implements the `TokenBucket` algorithm using Redis for distributed token management.
*   `src/requestQueue.js`: Manages a distributed request queue using Redis lists.
*   `src/circuitBreaker.js`: Implements an in-memory circuit breaker pattern (for a distributed system, this state would ideally also be in Redis).
*   `src/worker.js`: A separate process responsible for continuously pulling requests from the `RequestQueue` and dispatching them to the backend when allowed by the rate limiter and circuit breaker.
*   `test/`: Contains unit tests for `TokenBucket`, `RequestQueue`, and `CircuitBreaker`.

## Setup and Installation

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
    This worker will continuously process requests from the Redis queue.

## How to Test (Manual)

Once both the proxy server and the worker are running, you can interact with the `/login` endpoint.

*   **Send a login request**:
    Use `curl` or Postman to send a POST request to `http://localhost:3000/login` with a JSON body:
    ```bash
    curl -X POST -H "Content-Type: application/json" -d "{"username": "userX", "password": "password"}" http://localhost:3000/login
    ```
    Observe the server logs. If requests exceed the rate limit, they will be queued.
    The mock backend (`/db-login`) has a 20% chance of failure to simulate an unstable service, which will trigger the circuit breaker.

*   **Check status**:
    Access `http://localhost:3000/status` in your browser or with `curl` to see the current state of the Token Bucket, Request Queue, and Circuit Breaker.
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

This README provides a comprehensive overview and instructions for the project.
