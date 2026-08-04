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
- 只使用 Python standard library。

## 安装

```bash
git clone https://github.com/Casper-Feehily/surge-vless-bridge.git
cd surge-vless-bridge
bash install.sh
```

已有 checkout 时直接运行：

```bash
bash install.sh
```

安装脚本会：

- 检查是否已安装 Surge for macOS。
- 缺少 `sing-box` 时用 Homebrew 安装。
- 询问 Surge profile 路径。
- 缺少 `[Proxy]` 或 `[Proxy Group]` 时自动创建。
- 在 Surge profile 中写入托管 marker。
- 询问 VLESS 节点订阅链接。
- 写入 `~/Library/Application Support/surge-vless-bridge/config.json`。
- 执行首次同步并加载 LaunchAgents。

非交互式安装：

```bash
SURGE_PROFILE_PATH="$HOME/Library/Application Support/Surge/Profiles/Main.conf" \
SUBSCRIPTION_URL="https://example.com/subscription" \
bash install.sh
```

## Surge profile marker

安装脚本会自动把下面的 marker 写入 `[Proxy]`：

```ini
# BEGIN SURGE VLESS BRIDGE PROXIES
# END SURGE VLESS BRIDGE PROXIES
```

并把下面的 marker 写入 `[Proxy Group]`：

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

## 运行

Dry run：

```bash
/usr/bin/python3 "$HOME/Library/Application Support/surge-vless-bridge/surge_vless_bridge.py" \
  -c "$HOME/Library/Application Support/surge-vless-bridge/config.json" \
  --dry-run
```

同步一次：

```bash
/usr/bin/python3 "$HOME/Library/Application Support/surge-vless-bridge/surge_vless_bridge.py" \
  -c "$HOME/Library/Application Support/surge-vless-bridge/config.json"
```

加载 LaunchAgents：

```bash
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.casper.surge-vless-bridge.sing-box.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.casper.surge-vless-bridge.sync.plist"
```

立即触发同步：

```bash
launchctl kickstart -k gui/$(id -u)/com.casper.surge-vless-bridge.sync
```

检查 sing-box：

```bash
launchctl print gui/$(id -u)/com.casper.surge-vless-bridge.sing-box
curl --socks5-hostname 127.0.0.1:39000 https://www.gstatic.com/generate_204 -I
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
/usr/bin/python3 -m py_compile surge_vless_bridge.py tests/test_surge_vless_bridge.py
bash -n install.sh
```
