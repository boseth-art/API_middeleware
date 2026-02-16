import Redis from 'ioredis';

const REDIS_HOST = process.env.REDIS_HOST || '127.0.0.1';
const REDIS_PORT = process.env.REDIS_PORT || 6379;

class TokenBucket {
    constructor(capacity, fillRate, bucketKey) {
        this.capacity = capacity; // Maximum tokens the bucket can hold
        this.fillRate = fillRate; // Tokens added per second
        this.bucketKey = bucketKey; // Key for Redis to store this bucket's state
        this.redis = new Redis({
            host: REDIS_HOST,
            port: REDIS_PORT
        });

        // Lua script for atomic token consumption
        this.consumeScript = `
            local key = KEYS[1]
            local capacity = tonumber(ARGV[1])
            local fillRate = tonumber(ARGV[2])
            local now = tonumber(ARGV[3])

            local bucket = redis.call('HGETALL', key)
            local tokens = tonumber(bucket[2]) or capacity -- current tokens, default to capacity if not set
            local lastRefillTime = tonumber(bucket[4]) or now -- last refill time, default to now

            local timePassed = now - lastRefillTime
            local tokensToAdd = math.floor(timePassed * fillRate)

            tokens = math.min(capacity, tokens + tokensToAdd)
            lastRefillTime = now

            if tokens >= 1 then
                tokens = tokens - 1
                redis.call('HSET', key, 'tokens', tokens, 'lastRefillTime', lastRefillTime)
                return 1 -- Token consumed
            else
                redis.call('HSET', key, 'tokens', tokens, 'lastRefillTime', lastRefillTime) -- Update refill time even if no token consumed
                return 0 -- No token available
            end
        `;
    }

    /**
     * Attempts to consume a token from the bucket.
     * @returns {Promise<boolean>} True if a token was consumed, false otherwise.
     */
    async tryConsume() {
        const now = Math.floor(Date.now() / 1000); // Current time in seconds
        try {
            const result = await this.redis.eval(
                this.consumeScript,
                1, // Number of keys
                this.bucketKey,
                this.capacity,
                this.fillRate,
                now
            );
            return result === 1;
        } catch (error) {
            console.error('Error consuming token:', error);
            // In case of Redis error, we might want to fail safe (allow access) or fail closed (deny access).
            // For a critical service, failing closed might be safer to prevent overload.
            // For now, let's deny access to prevent potential overload.
            return false;
        }
    }

    /**
     * Gets the current number of tokens in the bucket.
     * This is primarily for debugging/monitoring and not used in the core logic of tryConsume.
     * @returns {Promise<number>} The current token count.
     */
    async getTokens() {
        const key = this.bucketKey;
        const capacity = this.capacity;
        const fillRate = this.fillRate;
        const now = Math.floor(Date.now() / 1000); // Current time in seconds

        // Execute a Lua script to get the current tokens after a potential refill
        const script = `
            local key = KEYS[1]
            local capacity = tonumber(ARGV[1])
            local fillRate = tonumber(ARGV[2])
            local now = tonumber(ARGV[3])

            local bucket = redis.call('HGETALL', key)
            local tokens = tonumber(bucket[2]) or capacity -- current tokens, default to capacity if not set
            local lastRefillTime = tonumber(bucket[4]) or now -- last refill time, default to now

            local timePassed = now - lastRefillTime
            local tokensToAdd = math.floor(timePassed * fillRate)

            tokens = math.min(capacity, tokens + tokensToAdd)
            -- Note: We are not updating lastRefillTime here unless we explicitly consume a token
            -- This function just calculates and returns the current state.
            return tokens
        `;
        
        try {
            const result = await this.redis.eval(
                script,
                1, // Number of keys
                key,
                capacity,
                fillRate,
                now
            );
            return result;
        } catch (error) {
            console.error('Error getting tokens (with refill calculation):', error);
            return capacity; // Default to capacity on error
        }
    }

    async disconnect() {
        await this.redis.disconnect();
    }
}

export default TokenBucket;
