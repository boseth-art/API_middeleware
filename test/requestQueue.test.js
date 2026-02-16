// test/requestQueue.test.js
import { expect } from 'chai';
import RequestQueue from '../src/requestQueue.js';
import Redis from 'ioredis';

const REDIS_TEST_QUEUE_NAME = 'test_request_queue';

describe('RequestQueue', () => {
    let requestQueue;
    let redisClient;

    beforeEach(async () => {
        redisClient = new Redis({
            host: process.env.REDIS_HOST || '127.0.0.1',
            port: process.env.REDIS_PORT || 6379
        });
        await redisClient.del(REDIS_TEST_QUEUE_NAME); // Clear queue before each test

        requestQueue = new RequestQueue(REDIS_TEST_QUEUE_NAME);
    });

    afterEach(async () => {
        await requestQueue.disconnect();
        await redisClient.disconnect();
    });

    it('should enqueue and dequeue a request', async () => {
        const testRequest = { path: '/test', method: 'GET' };
        await requestQueue.enqueue(testRequest);
        const dequeuedRequest = await requestQueue.dequeue();

        expect(dequeuedRequest).to.have.property('id');
        expect(dequeuedRequest).to.have.property('timestamp');
        expect(dequeuedRequest.path).to.equal(testRequest.path);
        expect(dequeuedRequest.method).to.equal(testRequest.method);
    });

    it('should return null when dequeueing from an empty queue', async () => {
        const dequeuedRequest = await requestQueue.dequeue();
        expect(dequeuedRequest).to.be.null;
    });

    it('should maintain order (FIFO)', async () => {
        const request1 = { order: 1 };
        const request2 = { order: 2 };
        await requestQueue.enqueue(request1);
        await requestQueue.enqueue(request2);

        const dequeued1 = await requestQueue.dequeue();
        const dequeued2 = await requestQueue.dequeue();

        expect(dequeued1.order).to.equal(1);
        expect(dequeued2.order).to.equal(2);
    });

    it('should correctly report queue length', async () => {
        expect(await requestQueue.length()).to.equal(0);

        await requestQueue.enqueue({ order: 1 });
        expect(await requestQueue.length()).to.equal(1);

        await requestQueue.enqueue({ order: 2 });
        expect(await requestQueue.length()).to.equal(2);

        await requestQueue.dequeue();
        expect(await requestQueue.length()).to.equal(1);

        await requestQueue.dequeue();
        expect(await requestQueue.length()).to.equal(0);
    });

    it('should block and dequeue a request when available', async () => {
        const testRequest = { path: '/block', method: 'POST' };

        // Enqueue after a short delay
        setTimeout(() => requestQueue.enqueue(testRequest), 50);

        const dequeuedRequest = await requestQueue.blockDequeue(2); // Wait up to 2 seconds

        expect(dequeuedRequest).to.have.property('id');
        expect(dequeuedRequest.path).to.equal(testRequest.path);
    });

    it('should return null from blockDequeue after timeout', async () => {
        const dequeuedRequest = await requestQueue.blockDequeue(0.1); // Wait for 0.1 seconds
        expect(dequeuedRequest).to.be.null;
    });
});
