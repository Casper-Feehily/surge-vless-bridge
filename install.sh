#!/usr/bin/env bash
set -euo pipefail

APP_NAME="surge-vless-bridge"
APP_DIR="${HOME}/Library/Application Support/${APP_NAME}"
AGENTS_DIR="${HOME}/Library/LaunchAgents"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
SING_BOX=""
SURGE_CLI="${SURGE_CLI_PATH:-/Applications/Surge.app/Contents/Applications/surge-cli}"

expand_path() {
  case "$1" in
    "~") printf "%s\n" "${HOME}" ;;
    "~/"*) printf "%s\n" "${HOME}/${1#"~/"}" ;;
    *) printf "%s\n" "$1" ;;
  esac
}

prompt_required() {
  local prompt="$1"
  local default="${2:-}"
  local value=""
  while [[ -z "${value}" ]]; do
    if [[ -n "${default}" ]]; then
      read -r -p "${prompt} [${default}]: " value
      value="${value:-${default}}"
    else
      read -r -p "${prompt}: " value
    fi
  done
  printf "%s\n" "${value}"
}

prompt_positive_integer() {
  local prompt="$1"
  local default="$2"
  local value=""
  while true; do
    value="$(prompt_required "${prompt}" "${default}")"
    if [[ "${value}" =~ ^[1-9][0-9]*$ ]]; then
      printf "%s\n" "${value}"
      return
    fi
    echo "Enter a positive integer." >&2
  done
}

detect_surge() {
  if [[ ! -x "${SURGE_CLI}" ]]; then
    echo "Surge not found: ${SURGE_CLI}" >&2
    echo "Install Surge for macOS first, or run with SURGE_CLI_PATH=/path/to/surge-cli." >&2
    exit 1
  fi
}

detect_or_install_sing_box() {
  SING_BOX="$(command -v sing-box || true)"
  if [[ -z "${SING_BOX}" && -x /opt/homebrew/bin/sing-box ]]; then
    SING_BOX=/opt/homebrew/bin/sing-box
  fi
  if [[ -z "${SING_BOX}" && -x /usr/local/bin/sing-box ]]; then
    SING_BOX=/usr/local/bin/sing-box
  fi

  if [[ -z "${SING_BOX}" ]]; then
    if ! command -v brew >/dev/null 2>&1; then
      echo "sing-box not found and Homebrew is not installed." >&2
      echo "Install Homebrew or sing-box first, then rerun this script." >&2
      exit 1
    fi
    echo "sing-box not found; installing with Homebrew..."
    brew install sing-box
    SING_BOX="$(command -v sing-box || true)"
  fi

  if [[ -z "${SING_BOX}" ]]; then
    echo "sing-box installation finished, but sing-box is still not on PATH." >&2
    exit 1
  fi
}

write_profile_markers() {
  export SURGE_PROFILE_PATH="$1"
  /usr/bin/python3 - <<'PY'
import os
import re
import shutil
import time
from pathlib import Path

path = Path(os.environ["SURGE_PROFILE_PATH"]).expanduser()
proxy_begin = "# BEGIN SURGE VLESS BRIDGE PROXIES"
proxy_end = "# END SURGE VLESS BRIDGE PROXIES"
group_begin = "# BEGIN SURGE VLESS BRIDGE GROUP"
group_end = "# END SURGE VLESS BRIDGE GROUP"

def ensure_section(text, section):
    if re.search(rf"(?m)^\[{re.escape(section)}\]\s*$", text):
        return text
    if text and not text.endswith("\n"):
        text += "\n"
    return text + f"\n[{section}]\n"

def ensure_markers(text, section, begin, end):
    if begin in text and end in text:
        return text
    if begin in text or end in text:
        raise SystemExit(f"incomplete marker pair in {section}: {begin} / {end}")
    lines = text.splitlines()
    header = next(i for i, line in enumerate(lines) if line.strip() == f"[{section}]")
    insert_at = len(lines)
    for i in range(header + 1, len(lines)):
        if re.match(r"^\[[^\]]+\]\s*$", lines[i].strip()):
            insert_at = i
            break
    if insert_at > header + 1 and lines[insert_at - 1].strip():
        markers = ["", begin, end, ""]
    else:
        markers = [begin, end, ""]
    lines[insert_at:insert_at] = markers
    return "\n".join(lines).rstrip() + "\n"

text = path.read_text(encoding="utf-8")
updated = ensure_section(text, "Proxy")
updated = ensure_section(updated, "Proxy Group")
updated = ensure_markers(updated, "Proxy", proxy_begin, proxy_end)
updated = ensure_markers(updated, "Proxy Group", group_begin, group_end)
if updated != text:
    shutil.copy2(path, path.with_suffix(path.suffix + f".bak.{int(time.time())}"))
    path.write_text(updated, encoding="utf-8")
PY
}

detect_surge
detect_or_install_sing_box

SURGE_PROFILE_PATH="$(expand_path "${SURGE_PROFILE_PATH:-$(prompt_required "Surge profile path")}")"
if [[ ! -f "${SURGE_PROFILE_PATH}" ]]; then
  echo "Surge profile not found: ${SURGE_PROFILE_PATH}" >&2
  exit 1
fi

SUBSCRIPTION_URL="${SUBSCRIPTION_URL:-$(prompt_required "VLESS node subscription URL")}"
SYNC_INTERVAL_HOURS="${SYNC_INTERVAL_HOURS:-$(prompt_positive_integer "Refresh interval in hours" "1")}"
if [[ ! "${SYNC_INTERVAL_HOURS}" =~ ^[1-9][0-9]*$ ]]; then
  echo "SYNC_INTERVAL_HOURS must be a positive integer." >&2
  exit 1
fi
SYNC_INTERVAL_SECONDS=$((SYNC_INTERVAL_HOURS * 3600))

mkdir -p "${APP_DIR}/logs" "${AGENTS_DIR}"
cp "${SRC_DIR}/surge_vless_bridge.py" "${APP_DIR}/surge_vless_bridge.py"
chmod +x "${APP_DIR}/surge_vless_bridge.py"

if [[ -f "${APP_DIR}/config.json" ]]; then
  cp "${APP_DIR}/config.json" "${APP_DIR}/config.json.bak.$(date +%s)"
fi
cp "${SRC_DIR}/config.example.json" "${APP_DIR}/config.json"
export APP_DIR SING_BOX SURGE_CLI SURGE_PROFILE_PATH SUBSCRIPTION_URL
/usr/bin/python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["APP_DIR"]) / "config.json"
data = json.loads(path.read_text())
data["subscription_url"] = os.environ["SUBSCRIPTION_URL"]
data["surge_profile_path"] = os.environ["SURGE_PROFILE_PATH"]
data["sing_box_path"] = os.environ["SING_BOX"]
data["sing_box_config_path"] = str(Path(os.environ["APP_DIR"]) / "sing-box.generated.json")
data["surge_cli_path"] = os.environ["SURGE_CLI"]
data["sing_box_launchd_label"] = "com.casper.surge-vless-bridge.sing-box"
path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
PY

write_profile_markers "${SURGE_PROFILE_PATH}"

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
  <integer>${SYNC_INTERVAL_SECONDS}</integer>
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
echo "Running first sync..."
/usr/bin/python3 "${APP_DIR}/surge_vless_bridge.py" -c "${APP_DIR}/config.json"

echo "Loading LaunchAgents..."
launchctl bootout "gui/$(id -u)" "${AGENTS_DIR}/com.casper.surge-vless-bridge.sing-box.plist" >/dev/null 2>&1 || true
launchctl bootout "gui/$(id -u)" "${AGENTS_DIR}/com.casper.surge-vless-bridge.sync.plist" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${AGENTS_DIR}/com.casper.surge-vless-bridge.sing-box.plist"
launchctl bootstrap "gui/$(id -u)" "${AGENTS_DIR}/com.casper.surge-vless-bridge.sync.plist"

echo "Done."
echo "Config: ${APP_DIR}/config.json"
echo "Refresh interval: every ${SYNC_INTERVAL_HOURS} hour(s)"
echo "Surge profile markers ensured in: ${SURGE_PROFILE_PATH}"
