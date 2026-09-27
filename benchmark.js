import http from 'http';

const NUM_REQUESTS = 200; // More than 100
const CONCURRENCY = 20;
let completed = 0;
let successful = 0;
let rateLimited = 0;
let queued = 0;
let errors = 0;

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
      res.on('end', () => {
        if (res.statusCode === 200) successful++;
        else if (res.statusCode === 429) rateLimited++;
        else if (res.statusCode === 202) queued++;
        else errors++;
        completed++;
        resolve();
      });
    });

    req.on('error', (e) => {
      errors++;
      completed++;
      resolve();
    });

    req.write(postData);
    req.end();
  });
}

async function run() {
  console.log(`Starting benchmark: ${NUM_REQUESTS} requests with concurrency ${CONCURRENCY}`);
  const startTime = Date.now();
  
  for (let i = 0; i < NUM_REQUESTS; i += CONCURRENCY) {
    const batch = [];
    for (let j = 0; j < CONCURRENCY && i + j < NUM_REQUESTS; j++) {
      batch.push(makeRequest());
    }
    await Promise.all(batch);
  }

  const endTime = Date.now();
  const duration = endTime - startTime;
  
  const results = `
--- Benchmark Results ---
Total Requests: ${NUM_REQUESTS}
Duration: ${duration} ms
Successful (200): ${successful}
Rate Limited (429): ${rateLimited}
Queued (202): ${queued}
Errors: ${errors}
Requests/sec: ${((NUM_REQUESTS / duration) * 1000).toFixed(2)}
-------------------------
`;
  console.log(results);
  
  // Also save to a file
  import('fs').then(fs => {
    fs.writeFileSync('benchmark_results.txt', results);
    console.log('Saved to benchmark_results.txt');
  });
}

run();
