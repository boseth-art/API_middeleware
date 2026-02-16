# Gemini Analysis for API Rate Limiter and Request Queuing Middleware

## Project Overview

This project is a Node.js middleware/proxy designed to enhance the resilience and stability of backend services, particularly during high traffic events like simultaneous user logins. It implements three core patterns:

1.  **Rate Limiting**: Utilizes the **Token Bucket algorithm** to control the flow of incoming requests, preventing backend overload.
2.  **Request Queuing**: Employs **Redis lists** to queue requests that exceed the rate limit, ensuring no requests are lost and providing a smoother user experience during spikes.
3.  **Circuit Breaker**: Implements a **Circuit Breaker pattern** to protect the backend service from repeated failures by temporarily preventing requests from reaching an unhealthy service, allowing it time to recover.

The state for rate limiting and request queuing is managed in Redis, making the middleware horizontally scalable. A separate worker process is responsible for asynchronously processing queued requests.

## Building and Running

This project uses Node.js and relies on a Redis instance for its distributed state management.

### Prerequisites

*   **Node.js**: Ensure Node.js (v18 or higher recommended) is installed.
*   **Redis Server**: A running Redis instance is required. You can easily start one using Docker:
    ```bash
    docker run --name my-redis -p 6379:6379 -d redis
    ```
    (To stop and remove this Docker container later: `docker stop my-redis && docker rm my-redis`)

### Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/boseth-art/API_middeleware.git
    cd API_middeleware
    ```
2.  **Install project dependencies**:
    ```bash
    npm install
    ```

### Running the Application

The application consists of two main parts: the proxy server and a worker process.

1.  **Start the Proxy Server**:
    Open a terminal in the project root directory and run:
    ```bash
    npm start
    ```
    This starts the Express.js server on `http://localhost:3000`. It includes a mock backend service internally on `http://localhost:3001/db-login` to simulate the protected database.

2.  **Start the Worker Process**:
    Open a *new terminal* in the project root directory and run:
    ```bash
    node src/worker.js
    ```
    This worker continuously pulls requests from the Redis queue and attempts to process them.

### Manual Testing

Once both components are running, you can test the functionality:

*   **Send Login Requests**:
    Use `curl` or Postman to send POST requests to `http://localhost:3000/login`.
    ```bash
    curl -X POST -H "Content-Type: application/json" -d "{\"username\": \"testuser\", \"password\": \"testpass\"}" http://localhost:3000/login
    ```
    Observe the console output in both the server and worker terminals. You'll see requests being rate-limited, queued, and eventually processed. The mock backend introduces occasional failures to demonstrate the circuit breaker.

*   **Check Application Status**:
    Access this endpoint to view the current state of the rate limiter, request queue, and circuit breaker:
    ```bash
    curl http://localhost:3000/status
    ```

### Running Automated Tests

The project includes unit tests for its core components.

1.  **Ensure Redis is running** (as per "Prerequisites" above).
2.  In your project root directory, run:
    ```bash
    npm test
    ```

## Development Conventions

*   **Language**: JavaScript (ES Modules).
*   **Framework**: Express.js for the proxy server.
*   **State Management**: Redis for distributed rate limiting and queuing.
*   **Testing**: Mocha and Chai are used for unit testing. Babel is configured to transpile ES module syntax for tests.
*   **Code Structure**: Logical separation of concerns into `src/` directory for core logic and `index.js` for the main application entry point.
*   **Dependencies**: Managed via `package.json` and installed with `npm`.

This `GEMINI.md` should provide a solid foundation for understanding and interacting with the project.
