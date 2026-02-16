import express from 'express';
import TokenBucket from './src/rateLimiter.js';
import RequestQueue from './src/requestQueue.js';
import CircuitBreaker from './src/circuitBreaker.js';
import { v4 as uuidv4 } from 'uuid'; // For request IDs

const app = express();
const PORT = process.env.PORT || 3000;
const TARGET_SERVICE_URL = 'http://localhost:3001/db-login'; // Mock database service

// --- Configuration ---
const RATE_LIMIT_CAPACITY = 1000;   // Max 1000 tokens in the bucket
const RATE_LIMIT_FILL_RATE = 100;   // 100 tokens per second (allowing 100 RPS)
const QUEUE_NAME = 'login_queue';

const CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3;
const CIRCUIT_BREAKER_RESET_TIMEOUT = 15000; // 15 seconds
const CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 2;

// --- Instantiation ---
const tokenBucket = new TokenBucket(RATE_LIMIT_CAPACITY, RATE_LIMIT_FILL_RATE, 'login_rate_limit');
const requestQueue = new RequestQueue(QUEUE_NAME);
const circuitBreaker = new CircuitBreaker(
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_RESET_TIMEOUT,
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD
);

// Middleware to parse JSON bodies
app.use(express.json());

// Mock backend service (for demonstration)
// In a real scenario, this would be a separate microservice
app.all('/db-login', async (req, res) => {
    // Simulate database latency and occasional failures
    const latency = Math.floor(Math.random() * 500) + 50; // 50ms to 550ms
    await new Promise(resolve => setTimeout(resolve, latency));

    if (Math.random() < 0.2) { // 20% chance of failure
        console.log('Mock DB: Login failed for', req.body.username);
        return res.status(500).json({ message: 'Internal Server Error (Mock DB)' });
    }

    console.log('Mock DB: Login successful for', req.body.username);
    res.status(200).json({ message: 'Login successful', user: req.body.username });
});


// --- Main Proxy Endpoint ---
app.post('/login', async (req, res) => {
    const requestId = uuidv4();
    const { username, password } = req.body;
    console.log(`[${requestId}] Received login request for ${username}`);

    // 1. Rate Limiting
    const tokenConsumed = await tokenBucket.tryConsume();

    if (!tokenConsumed) {
        // 2. Request Queuing
        console.log(`[${requestId}] Rate limit exceeded for ${username}. Enqueuing request.`);
        await requestQueue.enqueue({
            requestId,
            method: req.method,
            url: req.originalUrl,
            headers: req.headers,
            body: req.body,
            // You might need to store more context if the client needs to be notified directly
            // For now, we'll assume the client just gets a 'queued' response.
        });
        return res.status(202).json({ message: 'Request queued. Please wait.', requestId });
    }

    // If token consumed, proceed with circuit breaker
    try {
        console.log(`[${requestId}] Token consumed for ${username}. Attempting backend call.`);
        const backendResponse = await circuitBreaker.fire(async () => {
            // Simulate calling the actual backend service
            // In a real app, you'd use a library like 'axios' or 'node-fetch'
            const response = await fetch(TARGET_SERVICE_URL, {
                method: req.method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });

            if (!response.ok) {
                const errorBody = await response.json();
                throw new Error(`Backend service responded with ${response.status}: ${errorBody.message}`);
            }

            return response.json();
        });
        
        console.log(`[${requestId}] Backend call successful for ${username}.`);
        res.status(200).json(backendResponse);

    } catch (error) {
        console.error(`[${requestId}] Error processing request for ${username}:`, error.message);
        if (error.message.includes('Circuit is OPEN')) {
            return res.status(503).json({ message: 'Service temporarily unavailable. Circuit is OPEN.' });
        } else if (error.message.includes('Service temporarily unavailable')) {
            // This would be from the HALF_OPEN state or general backend unhealthiness
            return res.status(503).json({ message: 'Service temporarily unavailable. Try again later.' });
        }
        res.status(500).json({ message: 'Internal Server Error' });
    }
});

// --- Health Check / Status Endpoint ---
app.get('/status', async (req, res) => {
    const currentTokens = await tokenBucket.getTokens();
    const queueLength = await requestQueue.length();
    res.json({
        service: 'Rate Limiter Proxy',
        status: 'running',
        tokenBucket: {
            capacity: RATE_LIMIT_CAPACITY,
            fillRate: RATE_LIMIT_FILL_RATE,
            currentTokens: currentTokens,
        },
        requestQueue: {
            name: QUEUE_NAME,
            length: queueLength,
        },
        circuitBreaker: {
            state: circuitBreaker.getState(),
            failureThreshold: CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            resetTimeout: CIRCUIT_BREAKER_RESET_TIMEOUT,
            successThreshold: CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
        }
    });
});


// --- Start Server ---
const server = app.listen(PORT, () => {
    console.log(`Proxy server listening on port ${PORT}`);
    console.log(`Mock DB service running on port 3001 (internal)`);
    console.log('To test:');
    console.log(`  POST http://localhost:${PORT}/login with JSON body { "username": "userX", "password": "password" }`);
});

// --- Graceful Shutdown ---
process.on('SIGTERM', async () => {
    console.log('SIGTERM signal received: closing HTTP server');
    server.close(async () => {
        console.log('HTTP server closed.');
        await tokenBucket.disconnect();
        await requestQueue.disconnect();
        // circuitBreaker doesn't have explicit connections to disconnect
        console.log('Redis clients disconnected.');
        process.exit(0);
    });
});
