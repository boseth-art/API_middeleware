import http from 'http';
import fs from 'fs';

const scenarios = [
  { requests: 150, concurrency: 10 },
  { requests: 300, concurrency: 50 },
  { requests: 500, concurrency: 100 },
  { requests: 1000, concurrency: 200 }
];

const postData = JSON.stringify({ username: 'testuser', password: 'testpass' });

const options = {
  hostname: 'localhost',
  port: 3000,
  path: '/login',
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(postData)
  }
};

function makeRequest() {
  return new Promise((resolve) => {
    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(res.statusCode));
    });
    req.on('error', (e) => resolve('error'));
    req.write(postData);
    req.end();
  });
}

async function runScenario(scenario) {
  const { requests, concurrency } = scenario;
  console.log(`Running scenario: ${requests} requests, concurrency ${concurrency}`);
  const startTime = Date.now();
  
  let successful = 0;
  let rateLimited = 0;
  let queued = 0;
  let errors = 0;
  
  for (let i = 0; i < requests; i += concurrency) {
    const batch = [];
    for (let j = 0; j < concurrency && i + j < requests; j++) {
      batch.push(makeRequest());
    }
    const results = await Promise.all(batch);
    for (const res of results) {
      if (res === 200) successful++;
      else if (res === 429) rateLimited++;
      else if (res === 202) queued++;
      else errors++;
    }
  }

  const duration = Date.now() - startTime;
  return {
    requests,
    concurrency,
    duration,
    rps: (requests / duration) * 1000,
    successful,
    rateLimited,
    queued,
    errors
  };
}

async function main() {
  const allResults = [];
  
  for (const scenario of scenarios) {
    const res = await runScenario(scenario);
    allResults.push(res);
    // Give some time for queue to drain between scenarios
    await new Promise(r => setTimeout(r, 2000));
  }
  
  const report = allResults.map(r => `
Scenario: ${r.requests} reqs (c=${r.concurrency})
-----------------------------------------
Duration:     ${r.duration}ms
Requests/sec: ${r.rps.toFixed(2)}
Success:      ${r.successful}
Rate Limited: ${r.rateLimited}
Queued:       ${r.queued}
Errors:       ${r.errors}
`).join('\n');
  
  fs.writeFileSync('extensive_benchmark_results.txt', report);
  console.log(report);
  console.log('Saved to extensive_benchmark_results.txt');
}

main();
