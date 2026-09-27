import http from 'http';
import fs from 'fs';

const TOTAL_REQUESTS = 20000;
const CONCURRENCY = 200;
const CSV_FILENAME = 'benchmark_dataset.csv';

const postData = JSON.stringify({ username: 'testuser', password: 'testpass' });
const options = {
  hostname: 'localhost',
  port: 4000,
  path: '/login',
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(postData)
  }
};

// Initialize CSV with headers
fs.writeFileSync(CSV_FILENAME, 'request_id,timestamp,latency_ms,status_code\n');
const writeStream = fs.createWriteStream(CSV_FILENAME, { flags: 'a' });

function makeRequest(id) {
  return new Promise((resolve) => {
    const start = Date.now();
    const req = http.request(options, (res) => {
      res.resume(); // Consume response data to free up memory
      res.on('end', () => {
        const latency = Date.now() - start;
        writeStream.write(`${id},${start},${latency},${res.statusCode}\n`);
        resolve();
      });
    });
    
    req.on('error', (e) => {
      const latency = Date.now() - start;
      writeStream.write(`${id},${start},${latency},ERROR\n`);
      resolve();
    });
    
    req.write(postData);
    req.end();
  });
}

async function run() {
  console.log(`Starting massive benchmark: ${TOTAL_REQUESTS} requests, concurrency ${CONCURRENCY}`);
  const startTime = Date.now();

  for (let i = 0; i < TOTAL_REQUESTS; i += CONCURRENCY) {
    const batch = [];
    for (let j = 0; j < CONCURRENCY && i + j < TOTAL_REQUESTS; j++) {
      batch.push(makeRequest(i + j + 1));
    }
    await Promise.all(batch);
    
    if ((i + CONCURRENCY) % 2000 === 0) {
        console.log(`Processed ${i + CONCURRENCY} requests...`);
    }
  }

  writeStream.end();
  const duration = Date.now() - startTime;
  console.log(`\nFinished in ${duration}ms (${(TOTAL_REQUESTS / duration * 1000).toFixed(2)} req/sec)`);
  console.log(`Dataset saved to ${CSV_FILENAME}`);
}

run();
