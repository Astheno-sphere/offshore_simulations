#!/usr/bin/env bash
# Runs once when the machine (Codespace / devcontainer) is created. Idempotent. No secrets are printed.
set -uo pipefail
npm ci --prefix offsim/render_deck >/dev/null 2>&1 || true
npm ci --prefix offsim/motion >/dev/null 2>&1 || npm install --prefix offsim/motion >/dev/null 2>&1 || true
# AMPL: here the binary download is allowed (unlike the Claude cloud workspace). Licence from a Codespaces secret.
if [ -n "${AMPL_LICENSE_UUID:-}" ]; then
  python -m amplpy.modules install highs cbc >/dev/null 2>&1 && python -m amplpy.modules activate "$AMPL_LICENSE_UUID" >/dev/null 2>&1 \
    && echo "AMPL: activated" || echo "AMPL: activation failed (check the secret)"
else
  echo "AMPL: no AMPL_LICENSE_UUID Codespaces secret; solver ampl stays unavailable (pyomo twin works)"
fi
python -m offsim tools || true
python -m offsim live --only runner || true
echo "Machine ready. Read AGENTS.md, then: python -m offsim status"
