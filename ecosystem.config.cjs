// pm2 process map for shell-infra — the host-level UI service.
// Run from this directory:  pm2 start ecosystem.config.cjs
//
// Neither the credential broker nor the substrate API runs here — both run
// as their own containers on the dos-net network (dos-broker, dos-api); see
// install/broker-up.sh and install/api-up.sh. pm2 hosts only the UI.

module.exports = {
  apps: [
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
  ],
}
