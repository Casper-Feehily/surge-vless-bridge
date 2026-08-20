#!/usr/bin/env bash
set -euo pipefail

APP_NAME="surge-vless-bridge"
APP_DIR="${HOME}/Library/Application Support/${APP_NAME}"
CONFIG="${APP_DIR}/config.json"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMP_BRIDGE=""

cleanup() {
  [[ -z "${TEMP_BRIDGE}" ]] || rm -f "${TEMP_BRIDGE}"
}
trap cleanup EXIT

if [[ ! -f "${CONFIG}" ]]; then
  echo "No installed config found: ${CONFIG}" >&2
  echo "Run bash install.sh first." >&2
  exit 1
fi

if [[ "${SKIP_GIT_PULL:-0}" != "1" ]]; then
  git -C "${SRC_DIR}" pull --ff-only
fi

TEMP_BRIDGE="$(mktemp "${APP_DIR}/surge_vless_bridge.py.XXXXXX")"
cp "${SRC_DIR}/surge_vless_bridge.py" "${TEMP_BRIDGE}"
chmod +x "${TEMP_BRIDGE}"
/usr/bin/python3 "${TEMP_BRIDGE}" -c "${CONFIG}" --dry-run

CONFIG_BACKUP="$(mktemp "${APP_DIR}/config.json.bak.XXXXXX")"
cp "${CONFIG}" "${CONFIG_BACKUP}"
/usr/bin/python3 - "${CONFIG}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
if "subscription_urls" not in data and data.get("subscription_url"):
    data["subscription_urls"] = [data.pop("subscription_url")]
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

mv "${TEMP_BRIDGE}" "${APP_DIR}/surge_vless_bridge.py"
TEMP_BRIDGE=""
/usr/bin/python3 "${APP_DIR}/surge_vless_bridge.py" -c "${CONFIG}"
echo "Updated ${APP_NAME}. Config backup: ${CONFIG_BACKUP}"
