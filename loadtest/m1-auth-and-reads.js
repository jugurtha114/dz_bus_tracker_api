// M1 baseline: authenticated reads, conditional reads, token refresh and logins through the
// complete middleware stack (auth, revocation check, rate limiting, ETag, compression).
//
//   k6 run -e BASE_URL=http://127.0.0.1:8080 loadtest/m1-auth-and-reads.js
//
// Run it against the load-test overlay (loadtest/compose.loadtest.yaml): per-user and
// per-IP quotas are raised there, otherwise the limiter (correctly) answers 429.
import http from 'k6/http';
import { check, fail } from 'k6';
import exec from 'k6/execution';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8080';
const USERS = Number(__ENV.USERS || 200);
const PASSWORD = 'load test passphrase 2026';
const JSON_HEADERS = { 'content-type': 'application/json' };

export const options = {
  scenarios: {
    reads: {
      executor: 'constant-arrival-rate',
      exec: 'readMe',
      rate: Number(__ENV.READ_RPS || 500),
      timeUnit: '1s',
      duration: __ENV.DURATION || '2m',
      preAllocatedVUs: 50,
      maxVUs: 300,
    },
    conditional_reads: {
      executor: 'constant-arrival-rate',
      exec: 'readMeConditional',
      rate: Number(__ENV.CONDITIONAL_RPS || 200),
      timeUnit: '1s',
      duration: __ENV.DURATION || '2m',
      preAllocatedVUs: 20,
      maxVUs: 200,
    },
    logins: {
      executor: 'constant-arrival-rate',
      exec: 'login',
      rate: Number(__ENV.LOGIN_RPS || 10),
      timeUnit: '1s',
      duration: __ENV.DURATION || '2m',
      preAllocatedVUs: 10,
      maxVUs: 50,
    },
  },
  // M1 SLOs (2 vCPU / 512 MiB API container, see loadtest/README.md).
  thresholds: {
    http_req_failed: ['rate<0.001'],
    'http_req_duration{scenario:reads}': ['p(95)<25', 'p(99)<75'],
    'http_req_duration{scenario:conditional_reads}': ['p(95)<20', 'p(99)<60'],
    // Dominated by Argon2id (19 MiB, t=2) by design.
    'http_req_duration{scenario:logins}': ['p(95)<250', 'p(99)<500'],
  },
};

export function setup() {
  const accounts = [];
  for (let i = 0; i < USERS; i++) {
    const email = `load-${Date.now()}-${i}@example.test`;
    const res = http.post(
      `${BASE_URL}/api/v1/auth/register`,
      JSON.stringify({ email, password: PASSWORD }),
      { headers: JSON_HEADERS },
    );
    if (res.status !== 201) fail(`registration failed: ${res.status} ${res.body}`);
    const body = res.json();
    accounts.push({ email, token: body.tokens.access_token });
  }
  return { accounts };
}

function pick(data) {
  return data.accounts[exec.scenario.iterationInTest % data.accounts.length];
}

export function readMe(data) {
  const res = http.get(`${BASE_URL}/api/v1/me`, {
    headers: { authorization: `Bearer ${pick(data).token}`, 'accept-encoding': 'br, gzip' },
  });
  check(res, { 'me 200': (r) => r.status === 200 });
}

export function readMeConditional(data) {
  const account = pick(data);
  const first = http.get(`${BASE_URL}/api/v1/me`, {
    headers: { authorization: `Bearer ${account.token}` },
  });
  const etag = first.headers.Etag || first.headers.ETag;
  const res = http.get(`${BASE_URL}/api/v1/me`, {
    headers: { authorization: `Bearer ${account.token}`, 'if-none-match': etag },
  });
  check(res, { 'me 304': (r) => r.status === 304 });
}

export function login(data) {
  const res = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ email: pick(data).email, password: PASSWORD }),
    { headers: JSON_HEADERS },
  );
  check(res, { 'login 200': (r) => r.status === 200 });
}
