# surge-vless-bridge

[English](README.en.md)

在 Surge for macOS 中使用 VLESS（包括 Reality），不需要改造 Surge 本身。

这个工具让 Surge 继续负责规则和策略组，`sing-box` 在本机处理 VLESS 数据面。每个 VLESS 节点会变成一个本地 SOCKS5 端口，Surge 只需要把它们当成普通 `socks5` 代理使用。

## 功能

- 支持任意服务商的原始 VLESS 订阅。
- 支持 base64 订阅，也支持包含 `vless://` 链接的纯文本文件或列表。
- 为每个节点生成一组 sing-box inbound/outbound。
- 只更新 Surge profile 中被 marker 包住的托管区块。
- 订阅获取、解析、sing-box 检查或 Surge profile 检查失败时，会保留旧的可用配置。
- 提供 macOS LaunchAgent，用于 sing-box keepalive 和定时同步。
- 创建surge-vless-status和surge-vless-sync命令用于查看订阅状态和更新订阅。

## 快速安装

```bash
git clone https://github.com/Casper-Feehily/surge-vless-bridge.git
cd surge-vless-bridge
bash install.sh
```

## 安装脚本会做什么

- 首先选择安装语言：中文或 English。
- 检查是否已安装 Surge for macOS。
- 缺少 `sing-box` 时用 Homebrew 安装。
- 询问 Surge profile 路径。
- 缺少 `[Proxy]` 或 `[Proxy Group]` 时自动创建。
- 在 Surge profile 中补齐托管 marker。
- 询问 VLESS 节点订阅链接。
- 询问订阅刷新间隔，单位是小时，支持小数。
- 安装 `surge-vless-sync` 和 `surge-vless-status` 快捷命令。zsh、bash、fish 会自动配置；其他 shell 会询问 home 路径和启动配置文件路径后直接写入。
- 写入 `~/Library/Application Support/surge-vless-bridge/config.json`。
- 执行首次同步并加载 LaunchAgents。

## 非交互式安装

```bash
SURGE_PROFILE_PATH="$HOME/Library/Application Support/Surge/Profiles/Main.conf" \
SUBSCRIPTION_URL="https://example.com/subscription" \
SYNC_INTERVAL_HOURS="6" \
INSTALL_LANG="zh" \
bash install.sh
```

`SYNC_INTERVAL_HOURS` 必须是正数，支持小数，例如 `0.5` 表示 30 分钟。未设置时，安装脚本默认每 1 小时刷新一次订阅。`INSTALL_LANG` 可设为 `zh` 或 `en`，用于跳过语言选择。

如果你的 shell 不是 zsh、bash 或 fish，可以额外设置 `COMMAND_HOME=/Users/yourname` 和 `COMMAND_RC_PATH=/Users/yourname/.profile` 来跳过快捷命令安装路径提问。

## 安全提醒

VLESS 订阅链接通常包含账号凭据。不要把真实的 `subscription_url` 提交到 GitHub。安装脚本会把真实配置写到 `~/Library/Application Support/surge-vless-bridge/config.json`，仓库里的 `.gitignore` 也会忽略本地 `config.json`，避免误提交。

## Surge profile marker

同步程序会自动把下面的 marker 补到 `[Proxy]`：

```ini
# BEGIN SURGE VLESS BRIDGE PROXIES
# END SURGE VLESS BRIDGE PROXIES
```

并把下面的 marker 补到 `[Proxy Group]`：

```ini
# BEGIN SURGE VLESS BRIDGE GROUP
# END SURGE VLESS BRIDGE GROUP
```

工具只会替换 marker 中间的内容，不会改动你手写的其他 Surge 配置。

## 节点命名

默认节点名来自 URI fragment：

```text
vless://uuid@example.com:443?...#My%20Node
```

可以在 `config.json` 里规范化节点名。`name_strip_patterns` 会先作用于订阅里的原始名称，然后再应用 prefix/suffix 或 template。

```json
{
  "name_prefix": "VLESS ",
  "name_suffix": "",
  "name_template": "",
  "name_strip_patterns": ["^Provider-\\d+@"]
}
```

设置 `name_template` 后会覆盖 prefix/suffix。可用字段：

- `{index}`
- `{name}`
- `{server}`
- `{port}`

示例：

```json
{
  "name_template": "VLESS {index} {server}"
}
```

## 常用命令

验证配置但不写入：

```bash
/usr/bin/python3 "$HOME/Library/Application Support/surge-vless-bridge/surge_vless_bridge.py" \
  -c "$HOME/Library/Application Support/surge-vless-bridge/config.json" \
  --dry-run
```

立即同步一次：

```bash
surge-vless-sync
```

安装脚本会按当前 shell 把 `~/.local/bin` 加到启动配置：zsh 写入 `~/.zshrc`，bash 写入 `~/.bashrc` 和 `~/.bash_profile`，fish 写入 `~/.config/fish/config.fish`。安装后重开终端即可直接使用短命令。

如果当前 shell 不是 zsh、bash 或 fish，安装脚本会询问 home 路径和启动配置文件路径，然后直接写入 PATH。安装后重开终端即可使用 `surge-vless-sync`。

查看状态：

```bash
surge-vless-status
```

重新加载 LaunchAgents：

```bash
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/io.github.surge-vless-bridge.sing-box.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/io.github.surge-vless-bridge.sync.plist"
```

检查 sing-box：

```bash
launchctl print gui/$(id -u)/io.github.surge-vless-bridge.sing-box
curl --socks5-hostname 127.0.0.1:39000 https://www.gstatic.com/generate_204 -I
```

卸载会停止并移除两个 LaunchAgent，删除 `surge-vless-sync` / `surge-vless-status`，并删除 `~/Library/Application Support/surge-vless-bridge` 里的配置、日志、状态和生成文件：

```bash
bash uninstall.sh
```

如果只想移除 LaunchAgent 和快捷命令，但保留配置、日志、状态和生成文件：

```bash
KEEP_CONFIG=1 bash uninstall.sh
```

## Surge 使用方式

生成的策略组默认是：

```ini
VLESS = select, ...
```

把常规 Surge 规则指向 `VLESS`：

```ini
DOMAIN-SUFFIX,example.com,VLESS
FINAL,DIRECT
```

Surge 仍然负责规则匹配、策略组、Dashboard 和 reload。`sing-box` 负责 VLESS/Reality 连接。

## 兼容性

解析器会把常见 VLESS URI 参数映射到 sing-box：

- `security=none|tls|reality`
- `type=tcp|ws|grpc|http|h2|httpupgrade|quic`
- `flow=xtls-rprx-vision`
- `sni`, `fp`, `alpn`, `allowInsecure`
- Reality `pbk`/`publicKey` 和 `sid`/`shortId`
- WS `host` 和 `path`
- gRPC `serviceName`

## 开发

```bash
/usr/bin/python3 tests/test_surge_vless_bridge.py
/usr/bin/python3 tests/test_install_sh.py
/usr/bin/python3 -m py_compile surge_vless_bridge.py tests/test_surge_vless_bridge.py
bash -n install.sh
bash -n uninstall.sh
```
