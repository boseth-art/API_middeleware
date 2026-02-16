import TokenBucket from './rateLimiter.js';
import RequestQueue from './requestQueue.js';
import CircuitBreaker from './circuitBreaker.js';
import fetch from 'node-fetch'; // For making HTTP requests

// --- Configuration ---
const RATE_LIMIT_CAPACITY = 1000;
const RATE_LIMIT_FILL_RATE = 100;
const QUEUE_NAME = 'login_queue';
const TARGET_SERVICE_URL = 'http://localhost:3001/db-login';

const CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3;
const CIRCUIT_BREAKER_RESET_TIMEOUT = 15000; // 15 seconds
const CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 2;

const WORKER_DELAY_MS = 50; // Delay between queue processing attempts

// --- Instantiation ---
const tokenBucket = new TokenBucket(RATE_LIMIT_CAPACITY, RATE_LIMIT_FILL_RATE, 'login_rate_limit');
const requestQueue = new RequestQueue(QUEUE_NAME);
const circuitBreaker = new CircuitBreaker(
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_RESET_TIMEOUT,
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD
);

console.log('Request processing worker started.');

async function processQueue() {
    while (true) {
        try {
            // Block and wait for a request
            const queuedRequest = await requestQueue.blockDequeue(1); // Wait for 1 second

            if (queuedRequest) {
                const { requestId, method, url, headers, body } = queuedRequest;
                console.log(`[Worker] Processing request ${requestId} from queue.`);

                // 1. Try to consume a token
                const tokenConsumed = await tokenBucket.tryConsume();

                if (!tokenConsumed) {
                    console.log(`[Worker] No token available for ${requestId}. Re-enqueueing.`);
                    // Re-enqueue the request if no token is available
                    // Using RPUSH to add to the end of the queue, LIFO
                    await requestQueue.enqueue({ requestId, method, url, headers, body });
                    // Add a small delay to prevent tight-loop re-enqueuing
                    await new Promise(resolve => setTimeout(resolve, WORKER_DELAY_MS));
                    continue; // Skip to next iteration
                }

                // 2. Dispatch request to backend via Circuit Breaker
                try {
                    const backendResponse = await circuitBreaker.fire(async () => {
                        const response = await fetch(TARGET_SERVICE_URL, {
                            method: method,
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(body),
                        });

                        if (!response.ok) {
                            const errorBody = await response.json();
                            throw new Error(`Backend service responded with ${response.status}: ${errorBody.message}`);
                        }

                        return response.json();
                    });

                    console.log(`[Worker] Successfully processed and dispatched ${requestId}. Backend response:`, backendResponse);
                    // Here, you would typically send the response back to the original client
                    // This is a complex problem in a queued system as the original HTTP connection is long gone.
                    // Possible solutions: WebSockets, long polling, or client-side polling for results by requestId.
                    // For this exercise, we'll just log success.

                } catch (error) {
                    console.error(`[Worker] Error dispatching request ${requestId} to backend:`, error.message);
                    if (error.message.includes('Circuit is OPEN')) {
                        console.warn(`[Worker] Circuit is OPEN. Request ${requestId} not dispatched.`);
                        // If circuit is open, we can't dispatch.
                        // Re-enqueue or move to a dead-letter queue. Re-enqueueing for simplicity.
                        await requestQueue.enqueue({ requestId, method, url, headers, body });
                    }
                    // Other errors (e.g., backend actual failure): potentially re-enqueue with retry count, or dead-letter.
                }
            }
        } catch (error) {
            console.error('[Worker] Uncaught error in processQueue:', error);
        }
        await new Promise(resolve => setTimeout(resolve, WORKER_DELAY_MS)); // Prevent busy-waiting
    }
}

// Start the worker
processQueue();

// --- Graceful Shutdown ---
process.on('SIGTERM', async () => {
    console.log('SIGTERM signal received by worker: disconnecting Redis clients.');
    await tokenBucket.disconnect();
    await requestQueue.disconnect();
    console.log('Worker Redis clients disconnected. Exiting.');
    process.exit(0);
});
