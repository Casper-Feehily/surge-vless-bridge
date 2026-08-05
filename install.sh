#!/usr/bin/env bash
set -euo pipefail

APP_NAME="surge-vless-bridge"
APP_DIR="${HOME}/Library/Application Support/${APP_NAME}"
AGENTS_DIR="${HOME}/Library/LaunchAgents"
BIN_DIR="${HOME}/.local/bin"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
SING_BOX=""
SURGE_CLI="${SURGE_CLI_PATH:-/Applications/Surge.app/Contents/Applications/surge-cli}"
INSTALL_LANG="${INSTALL_LANG:-}"
INSTALL_CONFIG=""

cleanup() {
  if [[ -n "${INSTALL_CONFIG}" ]]; then
    rm -f "${INSTALL_CONFIG}"
  fi
}
trap cleanup EXIT

expand_path() {
  case "$1" in
    "~") printf "%s\n" "${HOME}" ;;
    "~/"*) printf "%s\n" "${HOME}/${1#"~/"}" ;;
    *) printf "%s\n" "$1" ;;
  esac
}

choose_language() {
  while [[ "${INSTALL_LANG}" != "zh" && "${INSTALL_LANG}" != "en" ]]; do
    echo "Select language / 选择语言:"
    echo "1) 中文"
    echo "2) English"
    read -r -p "Language [1]: " choice
    case "${choice:-1}" in
      1|zh|ZH|cn|CN) INSTALL_LANG="zh" ;;
      2|en|EN) INSTALL_LANG="en" ;;
      *) echo "Please enter 1 or 2. / 请输入 1 或 2。" >&2 ;;
    esac
  done
}

msg() {
  local key="$1"
  case "${INSTALL_LANG}:${key}" in
    zh:surge_profile_path) printf "%s\n" "Surge profile 路径" ;;
    zh:subscription_url) printf "%s\n" "VLESS 节点订阅链接" ;;
    zh:refresh_interval) printf "%s\n" "订阅刷新间隔（小时）" ;;
    zh:positive_number) printf "%s\n" "请输入正数，例如 1 或 0.5。" ;;
    zh:surge_missing) printf "未找到 Surge: %s\n" "${SURGE_CLI}" ;;
    zh:surge_missing_hint) printf "%s\n" "请先安装 Surge for macOS，或用 SURGE_CLI_PATH=/path/to/surge-cli 指定路径。" ;;
    zh:sing_box_no_brew) printf "%s\n" "未找到 sing-box，且未安装 Homebrew。" ;;
    zh:sing_box_no_brew_hint) printf "%s\n" "请先安装 Homebrew 或 sing-box，然后重新运行安装脚本。" ;;
    zh:sing_box_installing) printf "%s\n" "未找到 sing-box，正在用 Homebrew 安装..." ;;
    zh:sing_box_missing_after_install) printf "%s\n" "sing-box 安装已结束，但仍不在 PATH 中。" ;;
    zh:profile_not_found) printf "未找到 Surge profile: %s\n" "${SURGE_PROFILE_PATH}" ;;
    zh:interval_invalid) printf "%s\n" "SYNC_INTERVAL_HOURS 必须是正数，例如 1 或 0.5。" ;;
    zh:path_unknown_shell) printf "无法自动为当前 shell 更新 PATH: %s\n" "${SHELL:-unknown}" ;;
    zh:path_manual_hint) printf "如需直接运行 surge-vless-sync，请手动把 %s 加入 PATH。\n" "${BIN_DIR}" ;;
    zh:installed) printf "已安装 %s。\n" "${APP_NAME}" ;;
    zh:first_sync) printf "%s\n" "正在执行首次同步..." ;;
    zh:loading_agents) printf "%s\n" "正在加载 LaunchAgents..." ;;
    zh:done) printf "%s\n" "完成。" ;;
    zh:config) printf "配置文件: %s\n" "${APP_DIR}/config.json" ;;
    zh:sync_command) printf "%s\n" "同步命令: surge-vless-sync" ;;
    zh:restart_terminal) printf "%s\n" "重启终端后即可使用这个短命令。" ;;
    zh:refresh_result) printf "刷新间隔: 每 %s 小时\n" "${SYNC_INTERVAL_HOURS}" ;;
    zh:markers_done) printf "Surge profile marker 已写入: %s\n" "${SURGE_PROFILE_PATH}" ;;
    *) case "${key}" in
      surge_profile_path) printf "%s\n" "Surge profile path" ;;
      subscription_url) printf "%s\n" "VLESS node subscription URL" ;;
      refresh_interval) printf "%s\n" "Refresh interval in hours" ;;
      positive_number) printf "%s\n" "Enter a positive number, for example 1 or 0.5." ;;
      surge_missing) printf "Surge not found: %s\n" "${SURGE_CLI}" ;;
      surge_missing_hint) printf "%s\n" "Install Surge for macOS first, or run with SURGE_CLI_PATH=/path/to/surge-cli." ;;
      sing_box_no_brew) printf "%s\n" "sing-box not found and Homebrew is not installed." ;;
      sing_box_no_brew_hint) printf "%s\n" "Install Homebrew or sing-box first, then rerun this script." ;;
      sing_box_installing) printf "%s\n" "sing-box not found; installing with Homebrew..." ;;
      sing_box_missing_after_install) printf "%s\n" "sing-box installation finished, but sing-box is still not on PATH." ;;
      profile_not_found) printf "Surge profile not found: %s\n" "${SURGE_PROFILE_PATH}" ;;
      interval_invalid) printf "%s\n" "SYNC_INTERVAL_HOURS must be a positive number, for example 1 or 0.5." ;;
      path_unknown_shell) printf "Could not update PATH automatically for shell: %s\n" "${SHELL:-unknown}" ;;
      path_manual_hint) printf "Add %s to PATH if you want to run surge-vless-sync without the full path.\n" "${BIN_DIR}" ;;
      installed) printf "Installed %s.\n" "${APP_NAME}" ;;
      first_sync) printf "%s\n" "Running first sync..." ;;
      loading_agents) printf "%s\n" "Loading LaunchAgents..." ;;
      done) printf "%s\n" "Done." ;;
      config) printf "Config: %s\n" "${APP_DIR}/config.json" ;;
      sync_command) printf "%s\n" "Sync command: surge-vless-sync" ;;
      restart_terminal) printf "%s\n" "Restart your terminal before using the short sync command." ;;
      refresh_result) printf "Refresh interval: every %s hour(s)\n" "${SYNC_INTERVAL_HOURS}" ;;
      markers_done) printf "Surge profile markers ensured in: %s\n" "${SURGE_PROFILE_PATH}" ;;
    esac ;;
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

prompt_positive_number() {
  local prompt="$1"
  local default="$2"
  local value=""
  while true; do
    value="$(prompt_required "${prompt}" "${default}")"
    if [[ "${value}" =~ ^([0-9]+([.][0-9]+)?|[.][0-9]+)$ ]] && /usr/bin/python3 -c 'import sys; raise SystemExit(not (float(sys.argv[1]) > 0))' "${value}"; then
      printf "%s\n" "${value}"
      return
    fi
    msg positive_number >&2
  done
}

detect_surge() {
  if [[ ! -x "${SURGE_CLI}" ]]; then
    msg surge_missing >&2
    msg surge_missing_hint >&2
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
      msg sing_box_no_brew >&2
      msg sing_box_no_brew_hint >&2
      exit 1
    fi
    msg sing_box_installing
    brew install sing-box
    SING_BOX="$(command -v sing-box || true)"
  fi

  if [[ -z "${SING_BOX}" ]]; then
    msg sing_box_missing_after_install >&2
    exit 1
  fi
}

ensure_path() {
  local shell_name
  local path_line='export PATH="$HOME/.local/bin:$PATH"'
  shell_name="$(basename "${SHELL:-}")"
  case "${shell_name}" in
    zsh)
      touch "${HOME}/.zshrc"
      grep -Fq "${path_line}" "${HOME}/.zshrc" || printf "\n# surge-vless-bridge\n%s\n" "${path_line}" >> "${HOME}/.zshrc"
      ;;
    bash)
      touch "${HOME}/.bashrc" "${HOME}/.bash_profile"
      grep -Fq "${path_line}" "${HOME}/.bashrc" || printf "\n# surge-vless-bridge\n%s\n" "${path_line}" >> "${HOME}/.bashrc"
      grep -Fq "${path_line}" "${HOME}/.bash_profile" || printf "\n# surge-vless-bridge\n%s\n" "${path_line}" >> "${HOME}/.bash_profile"
      ;;
    fish)
      mkdir -p "${HOME}/.config/fish"
      touch "${HOME}/.config/fish/config.fish"
      grep -Fq 'fish_add_path -g "$HOME/.local/bin"' "${HOME}/.config/fish/config.fish" || printf "\n# surge-vless-bridge\nfish_add_path -g \"\$HOME/.local/bin\"\n" >> "${HOME}/.config/fish/config.fish"
      ;;
    *)
      msg path_unknown_shell >&2
      msg path_manual_hint >&2
      ;;
  esac
}

choose_language
detect_surge
detect_or_install_sing_box

SURGE_PROFILE_PATH="$(expand_path "${SURGE_PROFILE_PATH:-$(prompt_required "$(msg surge_profile_path)")}")"
if [[ ! -f "${SURGE_PROFILE_PATH}" ]]; then
  msg profile_not_found >&2
  exit 1
fi

SUBSCRIPTION_URL="${SUBSCRIPTION_URL:-$(prompt_required "$(msg subscription_url)")}"
SYNC_INTERVAL_HOURS="${SYNC_INTERVAL_HOURS:-$(prompt_positive_number "$(msg refresh_interval)" "1")}"
if ! [[ "${SYNC_INTERVAL_HOURS}" =~ ^([0-9]+([.][0-9]+)?|[.][0-9]+)$ ]] || ! /usr/bin/python3 -c 'import sys; raise SystemExit(not (float(sys.argv[1]) > 0))' "${SYNC_INTERVAL_HOURS}"; then
  msg interval_invalid >&2
  exit 1
fi
SYNC_INTERVAL_SECONDS="$(/usr/bin/python3 -c 'import math, sys; print(max(1, math.ceil(float(sys.argv[1]) * 3600)))' "${SYNC_INTERVAL_HOURS}")"

mkdir -p "${APP_DIR}/logs" "${AGENTS_DIR}" "${BIN_DIR}"
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

INSTALL_CONFIG="${APP_DIR}/config.install.json"
/usr/bin/python3 - <<'PY'
import json
import os
from pathlib import Path

source = Path(os.environ["APP_DIR"]) / "config.json"
target = Path(os.environ["APP_DIR"]) / "config.install.json"
data = json.loads(source.read_text())
data["restart_sing_box"] = False
target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
PY

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

cat > "${BIN_DIR}/surge-vless-sync" <<SH
#!/usr/bin/env bash
set -euo pipefail
LABEL="com.casper.surge-vless-bridge.sync"
CONFIG="${APP_DIR}/config.json"
if launchctl kickstart -k "gui/\$(id -u)/\${LABEL}" >/dev/null 2>&1; then
  echo "Sync triggered through LaunchAgent."
else
  /usr/bin/python3 "${APP_DIR}/surge_vless_bridge.py" -c "\${CONFIG}"
fi
SH
chmod +x "${BIN_DIR}/surge-vless-sync"
ensure_path

msg installed
msg first_sync
/usr/bin/python3 "${APP_DIR}/surge_vless_bridge.py" -c "${INSTALL_CONFIG}"

msg loading_agents
launchctl bootout "gui/$(id -u)" "${AGENTS_DIR}/com.casper.surge-vless-bridge.sing-box.plist" >/dev/null 2>&1 || true
launchctl bootout "gui/$(id -u)" "${AGENTS_DIR}/com.casper.surge-vless-bridge.sync.plist" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${AGENTS_DIR}/com.casper.surge-vless-bridge.sing-box.plist"
launchctl bootstrap "gui/$(id -u)" "${AGENTS_DIR}/com.casper.surge-vless-bridge.sync.plist"

msg done
msg config
msg sync_command
msg restart_terminal
msg refresh_result
msg markers_done
