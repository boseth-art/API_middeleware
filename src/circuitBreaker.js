class CircuitBreaker {
    constructor(failureThreshold = 3, resetTimeout = 5000, successThreshold = 2) {
        this.failureThreshold = failureThreshold;
        this.resetTimeout = resetTimeout; // ms
        this.successThreshold = successThreshold;

        this.state = 'CLOSED';
        this.failures = 0;
        this.successes = 0; // for HALF_OPEN state
        this.lastFailureTime = 0;
    }

    /**
     * Wraps an asynchronous operation with circuit breaker logic.
     * @param {Function} operation - An async function that returns a Promise.
     * @returns {Promise<any>} The result of the operation, or a rejected Promise if the circuit is open.
     */
    async fire(operation) {
        if (this.state === 'OPEN') {
            if (Date.now() - this.lastFailureTime > this.resetTimeout) {
                this.state = 'HALF_OPEN';
                this.successes = 0; // Reset success count for HALF_OPEN
                console.log('CircuitBreaker: State changed to HALF_OPEN');
            } else {
                return Promise.reject(new Error('CircuitBreaker: Circuit is OPEN'));
            }
        }

        try {
            const result = await operation();
            this.success(this.state);
            return result;
        } catch (error) {
            this.fail(this.state);
            throw error;
        }
    }

    success(state) {
        if (state === 'CLOSED') {
            this.failures = 0; // Reset failures on success in CLOSED state
        } else if (state === 'HALF_OPEN') {
            this.successes++;
            if (this.successes >= this.successThreshold) {
                this.state = 'CLOSED';
                this.failures = 0;
                this.successes = 0;
                console.log('CircuitBreaker: State changed to CLOSED');
            }
        }
    }

    fail(state) {
        if (state === 'HALF_OPEN') {
            this.state = 'OPEN';
            this.failures = 0; // Reset failures for next HALF_OPEN cycle
            this.lastFailureTime = Date.now();
            console.log('CircuitBreaker: State changed back to OPEN (failed in HALF_OPEN)');
        } else { // CLOSED state
            this.failures++;
            if (this.failures >= this.failureThreshold) {
                this.state = 'OPEN';
                this.lastFailureTime = Date.now();
                console.log('CircuitBreaker: State changed to OPEN');
            }
        }
    }

    // For debugging/monitoring
    getState() {
        return this.state;
    }
}

export default CircuitBreaker;