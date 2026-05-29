// pm2 process map for the dos-arch substrate — host-level services.
// Run from the repo root:  pm2 start ecosystem.config.cjs
//
// Four apps run here: the substrate API, the SvelteKit UI, the browser-chat
// dispatcher, and the Ollama model-sync watcher. The API moved off Docker to
// pm2 (was the `dos-api` container) so it shares the host kernel with the
// other DB writers (dispatch, modelsync): a WAL SQLite file opened directly
// from BOTH a container and the host produced incoherent -shm wal-index reads
// and intermittent "database disk image is malformed" (CC-095). Only the
// credential broker stays containerized (dos-broker, secrets isolation) — see
// install/broker-up.sh.

const fs   = require('fs');
const os   = require('os');
const path = require('path');

// Parse the operator's .env so pm2 can hand selected values to processes.
// As of Phase 1 the dispatcher routes provider calls through the broker
// (BROKER_BASE, set per-app below) and holds no provider key — but .env still
// supplies non-provider config, and the legacy ANTHROPIC_API_KEY path remains
// for a broker-less setup. A missing file yields an empty env.
function loadEnv() {
  const env = {};
  const file = path.join(os.homedir(), '.config', 'dos-arch', '.env');
  try {
    for (const line of fs.readFileSync(file, 'utf8').split('\n')) {
      const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
      if (m) env[m[1]] = m[2].replace(/^(['"])(.*)\1$/, '$2');
    }
  } catch (e) { /* .env absent — surfaced by the dispatcher at startup */ }
  return env;
}

module.exports = {
  apps: [
    {
      name: 'dosarch-api',
      summary: 'Substrate API (FastAPI/uvicorn) — memory + admin surface on 127.0.0.1:8001',
      cwd: path.join(__dirname, 'shell_core'),
      script: path.join(__dirname, '.venv/bin/uvicorn'),
      // Bind 0.0.0.0 (not just loopback) so terminal-shell containers on
      // dos-net can reach it via host.docker.internal:8001 (run.py adds
      // --add-host=host.docker.internal:host-gateway). The substrate posture
      // is single-operator + host firewall — keep 8001 off any public iface.
      args: 'api.main:app --host 0.0.0.0 --port 8001',
      interpreter: 'none',
      // BROKER_BASE: startup model-sync hooks egress through the broker, like
      // the dispatcher. PYTHONPATH so `api.main:app` imports from shell_core.
      env: {
        ...loadEnv(),
        PYTHONPATH: path.join(__dirname, 'shell_core'),
        PYTHONUNBUFFERED: '1',
        BROKER_BASE: 'http://127.0.0.1:8788',
      },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      kill_timeout: 5000,
    },
    {
      name: 'dosarch-ui',
      summary: 'SvelteKit substrate UI — /shells, /flags, /plans routes on 127.0.0.1:5174',
      cwd:  './shell_core/ui',
      script: 'node_modules/.bin/vite',
      args:   'dev --host 127.0.0.1 --port 5174',
      interpreter: 'none',
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      kill_timeout: 5000,
    },
    {
      name: 'dosarch-dispatch',
      summary: 'Browser-chat dispatcher — own-runtime agent loop serving chat-enabled shells',
      cwd: __dirname,
      script: path.join(__dirname, 'shell_core/services/dispatch_live.py'),
      interpreter: path.join(__dirname, '.venv/bin/python3'),
      // BROKER_BASE routes provider calls through the credential broker
      // (Phase 1) — published to localhost by broker-up.sh — so the dispatcher
      // holds no provider key; the broker injects auth on egress. The provider
      // adapters prefer BROKER_BASE over any ANTHROPIC_API_KEY still in .env.
      env: { ...loadEnv(), BROKER_BASE: 'http://127.0.0.1:8788' },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      kill_timeout: 5000,
    },
    {
      name: 'dosarch-modelsync',
      summary: 'Watches Ollama for installed-model changes — keeps the models registry synced',
      cwd: __dirname,
      script: path.join(__dirname, 'shell_core/scripts/model_sync.py'),
      args: '--watch',
      interpreter: path.join(__dirname, '.venv/bin/python3'),
      env: loadEnv(),
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
      kill_timeout: 5000,
    },
  ],
}
