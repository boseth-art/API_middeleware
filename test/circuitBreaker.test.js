// test/circuitBreaker.test.js
import { expect } from 'chai';
import CircuitBreaker from '../src/circuitBreaker.js';

describe('CircuitBreaker', () => {
    let circuitBreaker;

    beforeEach(() => {
        circuitBreaker = new CircuitBreaker(3, 100, 2); // failureThreshold=3, resetTimeout=100ms, successThreshold=2
    });

    it('should initially be in a CLOSED state', () => {
        expect(circuitBreaker.getState()).to.equal('CLOSED');
    });

    it('should remain CLOSED on successful operations', async () => {
        const successfulOperation = async () => 'success';
        await circuitBreaker.fire(successfulOperation);
        expect(circuitBreaker.getState()).to.equal('CLOSED');
    });

    it('should open the circuit after exceeding the failure threshold', async () => {
        const failingOperation = async () => { throw new Error('fail'); };

        for (let i = 0; i < circuitBreaker.failureThreshold; i++) {
            try {
                await circuitBreaker.fire(failingOperation);
            } catch (e) {
                // Expected to fail
            }
        }
        expect(circuitBreaker.getState()).to.equal('OPEN');
    });

    it('should reject requests immediately when in OPEN state', async () => {
        const failingOperation = async () => { throw new Error('fail'); };

        // Open the circuit
        for (let i = 0; i < circuitBreaker.failureThreshold; i++) {
            try {
                await circuitBreaker.fire(failingOperation);
            } catch (e) {}
        }
        expect(circuitBreaker.getState()).to.equal('OPEN');

        // Try to fire another request
        let error;
        try {
            await circuitBreaker.fire(async () => 'should not run');
        } catch (e) {
            error = e;
        }
        expect(error).to.be.an('error');
        expect(error.message).to.equal('CircuitBreaker: Circuit is OPEN');
    });

    it('should transition to HALF_OPEN after resetTimeout', async () => {
        const failingOperation = async () => { throw new Error('fail'); };

        // Open the circuit
        for (let i = 0; i < circuitBreaker.failureThreshold; i++) {
            try {
                await circuitBreaker.fire(failingOperation);
            } catch (e) {}
        }
        expect(circuitBreaker.getState()).to.equal('OPEN');

        // Wait for resetTimeout
        await new Promise(resolve => setTimeout(resolve, circuitBreaker.resetTimeout + 10));
        
        // A request should now be allowed through to test, transitioning to HALF_OPEN
        let error;
        try {
            await circuitBreaker.fire(async () => 'test'); // This will attempt to transition to HALF_OPEN
        } catch (e) {
            error = e;
        }
        // It might immediately fail again if the test operation fails, but the state should be HALF_OPEN
        expect(circuitBreaker.getState()).to.equal('HALF_OPEN');
    });

    it('should close the circuit after successThreshold in HALF_OPEN', async () => {
        const failingOperation = async () => { throw new Error('fail'); };
        const successfulOperation = async () => 'success';

        // Open the circuit
        for (let i = 0; i < circuitBreaker.failureThreshold; i++) {
            try {
                await circuitBreaker.fire(failingOperation);
            } catch (e) {}
        }

        // Wait for resetTimeout and transition to HALF_OPEN
        await new Promise(resolve => setTimeout(resolve, circuitBreaker.resetTimeout + 10));
        await circuitBreaker.fire(successfulOperation); // First success in HALF_OPEN
        expect(circuitBreaker.getState()).to.equal('HALF_OPEN');

        await circuitBreaker.fire(successfulOperation); // Second success, should close
        expect(circuitBreaker.getState()).to.equal('CLOSED');
    });

    it('should re-open circuit if failure occurs in HALF_OPEN state', async () => {
        const failingOperation = async () => { throw new Error('fail'); };
        const successfulOperation = async () => 'success';

        // Open the circuit
        for (let i = 0; i < circuitBreaker.failureThreshold; i++) {
            try {
                await circuitBreaker.fire(failingOperation);
            } catch (e) {}
        }

        // Wait for resetTimeout and transition to HALF_OPEN
        await new Promise(resolve => setTimeout(resolve, circuitBreaker.resetTimeout + 10));
        await circuitBreaker.fire(successfulOperation); // First success in HALF_OPEN
        expect(circuitBreaker.getState()).to.equal('HALF_OPEN');

        try {
            await circuitBreaker.fire(failingOperation); // Failure in HALF_OPEN
        } catch (e) {}
        expect(circuitBreaker.getState()).to.equal('OPEN');
    });
});
