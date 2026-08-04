# surge-vless-bridge

Use VLESS, including Reality, from Surge for macOS without modifying Surge.

The tool keeps Surge as the rule and policy control plane. sing-box handles the VLESS data plane locally. Each VLESS node becomes one local SOCKS5 port, and Surge sees those ports as normal `socks5` proxies.

## Features

- Supports raw VLESS subscriptions from any provider.
- Accepts base64 subscriptions or plain text files/lists containing `vless://` links.
- Generates one sing-box inbound/outbound pair per node.
- Updates only marked blocks in a Surge profile.
- Keeps old working config on fetch, parse, sing-box check, or Surge profile check failure.
- Provides macOS LaunchAgent templates for sing-box keepalive and scheduled sync.
- Uses Python standard library only.

## Quick install

```bash
git clone https://github.com/Casper-Feehily/surge-vless-bridge.git
cd surge-vless-bridge
bash install.sh
```

Or from an existing checkout:

```bash
bash install.sh
```

## What the installer does

- checks that Surge for macOS is installed
- installs `sing-box` with Homebrew when it is missing
- asks for your Surge profile path
- creates `[Proxy]` or `[Proxy Group]` sections when missing
- adds the managed marker pairs to the Surge profile
- asks for your VLESS subscription URL
- asks how often to refresh the subscription, in hours
- writes `~/Library/Application Support/surge-vless-bridge/config.json`
- runs the first sync and loads the LaunchAgents

## Non-interactive install

```bash
SURGE_PROFILE_PATH="$HOME/Library/Application Support/Surge/Profiles/Main.conf" \
SUBSCRIPTION_URL="https://example.com/subscription" \
SYNC_INTERVAL_HOURS="6" \
bash install.sh
```

`SYNC_INTERVAL_HOURS` must be a positive integer. When omitted, the installer refreshes every 1 hour.

## Surge profile markers

Add these markers inside `[Proxy]`:

```ini
# BEGIN SURGE VLESS BRIDGE PROXIES
# END SURGE VLESS BRIDGE PROXIES
```

Add these markers inside `[Proxy Group]`:

```ini
# BEGIN SURGE VLESS BRIDGE GROUP
# END SURGE VLESS BRIDGE GROUP
```

Only content between those marker pairs is replaced.

## Node names

By default, node names come from the URI fragment:

```text
vless://uuid@example.com:443?...#My%20Node
```

You can normalize names in `config.json`. Strip patterns are applied to the original subscription name before prefix/suffix or template formatting.

```json
{
  "name_prefix": "VLESS ",
  "name_suffix": "",
  "name_template": "",
  "name_strip_patterns": ["^Provider-\\d+@"]
}
```

`name_template` overrides prefix/suffix when set. Available fields:

- `{index}`
- `{name}`
- `{server}`
- `{port}`

Example:

```json
{
  "name_template": "VLESS {index} {server}"
}
```

## Common commands

Validate without writing:

```bash
/usr/bin/python3 "$HOME/Library/Application Support/surge-vless-bridge/surge_vless_bridge.py" \
  -c "$HOME/Library/Application Support/surge-vless-bridge/config.json" \
  --dry-run
```

Sync once now:

```bash
surge-vless-sync
```

The installer adds `~/.local/bin` to the current shell startup file: `~/.zshrc` for zsh, `~/.bashrc` and `~/.bash_profile` for bash, or `~/.config/fish/config.fish` for fish. Restart the terminal after install to use the short command directly.

Reload LaunchAgents:

```bash
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.casper.surge-vless-bridge.sing-box.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.casper.surge-vless-bridge.sync.plist"
```

Trigger sync now:

```bash
surge-vless-sync
```

Check sing-box:

```bash
launchctl print gui/$(id -u)/com.casper.surge-vless-bridge.sing-box
curl --socks5-hostname 127.0.0.1:39000 https://www.gstatic.com/generate_204 -I
```

## Surge usage

The generated group defaults to:

```ini
VLESS = select, ...
```

Point normal Surge rules to `VLESS`:

```ini
DOMAIN-SUFFIX,example.com,VLESS
FINAL,DIRECT
```

Surge still owns rule matching, policy groups, Dashboard, and reload. sing-box owns the VLESS/Reality connection.

## Compatibility

The parser maps common VLESS URI parameters to sing-box:

- `security=none|tls|reality`
- `type=tcp|ws|grpc|http|h2|httpupgrade|quic`
- `flow=xtls-rprx-vision`
- `sni`, `fp`, `alpn`, `allowInsecure`
- Reality `pbk`/`publicKey` and `sid`/`shortId`
- WS `host` and `path`
- gRPC `serviceName`

## Development

```bash
/usr/bin/python3 tests/test_surge_vless_bridge.py
/usr/bin/python3 -m py_compile surge_vless_bridge.py tests/test_surge_vless_bridge.py
bash -n install.sh
```
