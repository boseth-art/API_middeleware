// test/tokenBucket.test.js
import { expect } from 'chai';
import TokenBucket from '../src/rateLimiter.js';
import Redis from 'ioredis'; // Import Redis to clean up after tests

const REDIS_TEST_BUCKET_KEY = 'test_token_bucket';

describe('TokenBucket', () => {
    let tokenBucket;
    let redisClient;

    beforeEach(async () => {
        // Clear Redis before each test to ensure a clean state
        redisClient = new Redis({
            host: process.env.REDIS_HOST || '127.0.0.1',
            port: process.env.REDIS_PORT || 6379
        });
        await redisClient.del(REDIS_TEST_BUCKET_KEY);

        tokenBucket = new TokenBucket(10, 1, REDIS_TEST_BUCKET_KEY); // Capacity 10, fill rate 1 token/sec
    });

    afterEach(async () => {
        await tokenBucket.disconnect();
        await redisClient.disconnect();
    });

    it('should initially have full capacity of tokens', async () => {
        const hasToken = await tokenBucket.tryConsume();
        expect(hasToken).to.be.true;
        const currentTokens = await tokenBucket.getTokens();
        // After one consumption, it should be capacity - 1
        expect(currentTokens).to.be.closeTo(9, 0.1);
    });

    it('should consume tokens up to capacity', async () => {
        let consumedCount = 0;
        for (let i = 0; i < 10; i++) {
            if (await tokenBucket.tryConsume()) {
                consumedCount++;
            }
        }
        expect(consumedCount).to.equal(10);
        expect(await tokenBucket.tryConsume()).to.be.false; // Should be empty now
    });

    it('should refill tokens over time', async () => {
        // Consume all tokens
        for (let i = 0; i < 10; i++) {
            await tokenBucket.tryConsume();
        }
        expect(await tokenBucket.tryConsume()).to.be.false;

        // Wait for some time to allow tokens to refill
        await new Promise(resolve => setTimeout(resolve, 1200)); // Wait 1.2 seconds, 1 token should refill

        const hasToken = await tokenBucket.tryConsume();
        expect(hasToken).to.be.true;
        const currentTokens = await tokenBucket.getTokens();
        expect(currentTokens).to.be.closeTo(0, 0.1); // 1 refilled, 1 consumed
    });

    it('should not exceed capacity when refilling', async function() { // Use function() for 'this' context
        this.timeout(10000); // Increase timeout for this specific test to 10 seconds
        // Wait for a long time, tokens should not exceed capacity
        await new Promise(resolve => setTimeout(resolve, 5000)); // 5 seconds, should refill 5 tokens
        const currentTokens = await tokenBucket.getTokens();
        expect(currentTokens).to.be.closeTo(10, 0.1); // Should still be at capacity

        // Consume one, wait for a refill, should still be at capacity
        await tokenBucket.tryConsume();
        await new Promise(resolve => setTimeout(resolve, 1200));
        expect(await tokenBucket.getTokens()).to.be.closeTo(10, 0.1);
    });
});
