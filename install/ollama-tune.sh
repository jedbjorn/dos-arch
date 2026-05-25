#!/usr/bin/env bash
# ollama-tune.sh — systemd drop-in for ollama.service with dos-arch defaults.
#
# Sets two env vars on the Ollama daemon:
#
#   OLLAMA_FLASH_ATTENTION=1    Flash-attention kernels — typically 10–30%
#                               faster prefill+decode on supported GPUs,
#                               lower KV-cache memory pressure. Required
#                               for the q8_0 KV path below.
#   OLLAMA_KV_CACHE_TYPE=q8_0   Quantize the KV cache to 8-bit. Halves KV
#                               memory at near-zero quality cost, so num_ctx
#                               can go higher for the same VRAM budget. Needs
#                               flash attention enabled.
#
# Both are free wins on any modern CUDA/ROCm/Metal Ollama install. The
# adapter (shell_core/services/providers/ollama_adapter.py) tunes per-request
# options (num_ctx, keep_alive); these are daemon-level and Ollama only
# reads them at service start, so they belong in a systemd drop-in, not in
# request bodies.
#
# Run AS ROOT — writes /etc/systemd/system/ollama.service.d/dos-arch.conf,
# daemon-reload, try-restart ollama.service. Idempotent; safe to re-run.
#
#   sudo ./install/ollama-tune.sh
#
# host-setup.sh invokes this automatically when ollama.service is already
# present. If you install Ollama after first setup, run this script
# directly (or re-run host-setup.sh — it's idempotent too).
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "ERROR: run with sudo — writes a systemd drop-in." >&2
  exit 1
fi

if ! systemctl cat ollama.service >/dev/null 2>&1; then
  echo "ollama.service not found — install Ollama first, then re-run this script."
  exit 0   # not-an-error: install ordering, not failure
fi

DROPIN_DIR="/etc/systemd/system/ollama.service.d"
DROPIN_FILE="${DROPIN_DIR}/dos-arch.conf"

mkdir -p "${DROPIN_DIR}"
cat >"${DROPIN_FILE}" <<'EOF'
# dos-arch defaults — flash attention + q8_0 KV cache.
# Flash attention: faster prefill+decode, lower KV memory on supported GPUs.
# q8_0 KV: halves KV memory at near-zero quality cost (requires flash attn).
[Service]
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
EOF
echo "    wrote ${DROPIN_FILE}"

systemctl daemon-reload
systemctl try-restart ollama.service || true

# Smoke-check: systemd should now report the merged env on the unit. This
# verifies the drop-in was picked up; it does not verify Ollama itself
# loaded with the flags (check `journalctl -u ollama --since '1 min ago'`
# for the "flash attention" line at next model load if you want full proof).
if systemctl show ollama.service -p Environment \
     | grep -q 'OLLAMA_FLASH_ATTENTION=1'; then
  echo "    ollama.service env updated; flash attention + q8_0 KV cache active on next model load"
else
  echo "    WARNING: drop-in written but systemctl show does not report the new env — investigate" >&2
fi
