#!/usr/bin/env bash
set -euo pipefail

APP_NAME="surge-vless-bridge"
APP_DIR="${HOME}/Library/Application Support/${APP_NAME}"
AGENTS_DIR="${HOME}/Library/LaunchAgents"
BIN_DIR="${HOME}/.local/bin"
UID_VALUE="$(id -u)"

launchctl bootout "gui/${UID_VALUE}" "${AGENTS_DIR}/com.casper.surge-vless-bridge.sing-box.plist" >/dev/null 2>&1 || true
launchctl bootout "gui/${UID_VALUE}" "${AGENTS_DIR}/com.casper.surge-vless-bridge.sync.plist" >/dev/null 2>&1 || true

rm -f "${AGENTS_DIR}/com.casper.surge-vless-bridge.sing-box.plist"
rm -f "${AGENTS_DIR}/com.casper.surge-vless-bridge.sync.plist"
rm -f "${BIN_DIR}/surge-vless-sync"
rm -f "${BIN_DIR}/surge-vless-status"

if [[ "${KEEP_CONFIG:-0}" == "1" ]]; then
  echo "Kept config and app data: ${APP_DIR}"
else
  rm -rf "${APP_DIR}"
  echo "Removed config and app data: ${APP_DIR}"
fi

echo "Uninstalled ${APP_NAME}."
