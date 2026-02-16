import Redis from 'ioredis';
import { v4 as uuidv4 } from 'uuid'; // To generate unique IDs for queued requests

const REDIS_HOST = process.env.REDIS_HOST || '127.0.0.1';
const REDIS_PORT = process.env.REDIS_PORT || 6379;

class RequestQueue {
    constructor(queueName) {
        this.queueName = queueName;
        this.redis = new Redis({
            host: REDIS_HOST,
            port: REDIS_PORT
        });
        this.subRedis = new Redis({ // Separate client for blocking operations
            host: REDIS_HOST,
            port: REDIS_PORT
        });
        console.log(`RequestQueue '${queueName}' initialized with Redis at ${REDIS_HOST}:${REDIS_PORT}`);
    }

    /**
     * Adds a request to the end of the queue.
     * @param {object} requestData - The data of the request to enqueue.
     * @returns {Promise<string>} The ID of the enqueued request.
     */
    async enqueue(requestData) {
        const requestId = uuidv4();
        const queuedRequest = { id: requestId, timestamp: Date.now(), ...requestData };
        try {
            await this.redis.rpush(this.queueName, JSON.stringify(queuedRequest));
            console.log(`Enqueued request ${requestId} to queue '${this.queueName}'`);
            return requestId;
        } catch (error) {
            console.error('Error enqueuing request:', error);
            throw error;
        }
    }

    /**
     * Removes and returns a request from the beginning of the queue.
     * @returns {Promise<object|null>} The dequeued request data, or null if the queue is empty.
     */
    async dequeue() {
        try {
            const result = await this.redis.lpop(this.queueName);
            if (result) {
                const request = JSON.parse(result);
                console.log(`Dequeued request ${request.id} from queue '${this.queueName}'`);
                return request;
            }
            return null;
        } catch (error) {
            console.error('Error dequeuing request:', error);
            throw error;
        }
    }

    /**
     * Blocks until a request is available in the queue, or the timeout is reached.
     * @param {number} timeout - The maximum time in seconds to wait for a request. 0 means block indefinitely.
     * @returns {Promise<object|null>} The dequeued request data, or null if a timeout occurred.
     */
    async blockDequeue(timeout = 0) {
        try {
            // BLPOP returns an array: [queueName, element]
            const result = await this.subRedis.blpop(this.queueName, timeout);
            if (result && result[1]) {
                const request = JSON.parse(result[1]);
                console.log(`Blocked dequeued request ${request.id} from queue '${this.queueName}'`);
                return request;
            }
            return null;
        } catch (error) {
            console.error('Error in blocked dequeue:', error);
            throw error;
        }
    }

    /**
     * Gets the current length of the queue.
     * @returns {Promise<number>} The number of requests in the queue.
     */
    async length() {
        try {
            return await this.redis.llen(this.queueName);
        } catch (error) {
            console.error('Error getting queue length:', error);
            throw error;
        }
    }

    async disconnect() {
        await this.redis.disconnect();
        await this.subRedis.disconnect();
    }
}

export default RequestQueue;
