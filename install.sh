#!/usr/bin/env bash
set -euo pipefail

APP_NAME="surge-vless-bridge"
APP_DIR="${HOME}/Library/Application Support/${APP_NAME}"
AGENTS_DIR="${HOME}/Library/LaunchAgents"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
SING_BOX="$(command -v sing-box || true)"

if [[ -z "${SING_BOX}" ]]; then
  if [[ -x /opt/homebrew/bin/sing-box ]]; then
    SING_BOX=/opt/homebrew/bin/sing-box
  elif [[ -x /usr/local/bin/sing-box ]]; then
    SING_BOX=/usr/local/bin/sing-box
  else
    echo "sing-box not found. Install it first: brew install sing-box" >&2
    exit 1
  fi
fi

mkdir -p "${APP_DIR}/logs" "${AGENTS_DIR}"
cp "${SRC_DIR}/surge_vless_bridge.py" "${APP_DIR}/surge_vless_bridge.py"
chmod +x "${APP_DIR}/surge_vless_bridge.py"

if [[ ! -f "${APP_DIR}/config.json" ]]; then
  cp "${SRC_DIR}/config.example.json" "${APP_DIR}/config.json"
  /usr/bin/python3 - <<PY
import json
from pathlib import Path
path = Path("${APP_DIR}/config.json")
data = json.loads(path.read_text())
data["sing_box_path"] = "${SING_BOX}"
data["sing_box_config_path"] = "${APP_DIR}/sing-box.generated.json"
path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
PY
  echo "Created ${APP_DIR}/config.json; edit subscription_url and surge_profile_path before loading launchd jobs."
fi

cat > "${AGENTS_DIR}/com.casper.surge-vless-bridge.sing-box.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.casper.surge-vless-bridge.sing-box</string>
  <key>ProgramArguments</key>
  <array>
    <string>${SING_BOX}</string>
    <string>run</string>
    <string>-c</string>
    <string>${APP_DIR}/sing-box.generated.json</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${APP_DIR}/logs/sing-box.log</string>
  <key>StandardErrorPath</key>
  <string>${APP_DIR}/logs/sing-box.log</string>
</dict>
</plist>
PLIST

cat > "${AGENTS_DIR}/com.casper.surge-vless-bridge.sync.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.casper.surge-vless-bridge.sync</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>${APP_DIR}/surge_vless_bridge.py</string>
    <string>-c</string>
    <string>${APP_DIR}/config.json</string>
  </array>
  <key>StartInterval</key>
  <integer>3600</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${APP_DIR}/logs/sync.launchd.log</string>
  <key>StandardErrorPath</key>
  <string>${APP_DIR}/logs/sync.launchd.log</string>
</dict>
</plist>
PLIST

echo "Installed ${APP_NAME}."
echo "Next:"
echo "1. Edit ${APP_DIR}/config.json"
echo "2. Add marker pairs to your Surge profile"
echo "3. Dry run: /usr/bin/python3 '${APP_DIR}/surge_vless_bridge.py' -c '${APP_DIR}/config.json' --dry-run"
echo "4. Sync once: /usr/bin/python3 '${APP_DIR}/surge_vless_bridge.py' -c '${APP_DIR}/config.json'"
echo "5. Load agents:"
echo "   launchctl bootstrap gui/$(id -u) '${AGENTS_DIR}/com.casper.surge-vless-bridge.sing-box.plist'"
echo "   launchctl bootstrap gui/$(id -u) '${AGENTS_DIR}/com.casper.surge-vless-bridge.sync.plist'"
