#!/usr/bin/env bash
# Deploy latest changes: pull, install, restart services
set -euo pipefail

JOBHUNT_DIR="${JOBHUNT_DIR:-$HOME/jobhunt}"
VENV="$JOBHUNT_DIR/.venv"
PRO_DIR="$JOBHUNT_DIR/src/pro"

SERVICES=(jobhunt-telegram jobhunt-whatsapp)

# Detect which services are actually installed
active_services=()
for svc in "${SERVICES[@]}"; do
  if systemctl list-unit-files "$svc.service" &>/dev/null && systemctl list-unit-files "$svc.service" | grep -q "$svc"; then
    active_services+=("$svc")
  fi
done

echo "=== Jobhunt Deploy ==="
echo "Dir:      $JOBHUNT_DIR"
echo "Services: ${active_services[*]:-none}"
echo ""

# Pull latest code
echo "--- Pulling core repo ---"
git -C "$JOBHUNT_DIR" pull origin main

echo "--- Pulling pro repo ---"
git -C "$PRO_DIR" pull origin main

# Install / upgrade packages
echo "--- Installing packages ---"
source "$VENV/bin/activate"
pip install -q -e "$JOBHUNT_DIR" -e "$PRO_DIR"

# Restart services
if [ ${#active_services[@]} -eq 0 ]; then
  echo "--- No services to restart ---"
else
  echo "--- Restarting services ---"
  sudo systemctl restart "${active_services[@]}"

  echo ""
  echo "--- Status ---"
  for svc in "${active_services[@]}"; do
    status=$(systemctl is-active "$svc" 2>/dev/null || echo "unknown")
    echo "  $svc: $status"
  done
fi

echo ""
echo "=== Done ==="
