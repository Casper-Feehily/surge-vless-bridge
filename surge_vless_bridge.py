#!/usr/bin/env python3
"""Bridge VLESS subscriptions into Surge through local sing-box SOCKS ports."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PROXY_BEGIN = "# BEGIN SURGE VLESS BRIDGE PROXIES"
DEFAULT_PROXY_END = "# END SURGE VLESS BRIDGE PROXIES"
DEFAULT_GROUP_BEGIN = "# BEGIN SURGE VLESS BRIDGE GROUP"
DEFAULT_GROUP_END = "# END SURGE VLESS BRIDGE GROUP"

@dataclass(frozen=True)
class Node:
    name: str
    uuid: str
    server: str
    port: int
    flow: str
    security: str
    network: str
    params: dict[str, str]


def log(message: str, log_path: Path | None = None) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line)
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        config = json.load(fh)
    base = path.parent
    defaults = {
        "listen_host": "127.0.0.1",
        "start_port": 39000,
        "group_name": "VLESS",
        "group_type": "select",
        "proxy_marker_begin": DEFAULT_PROXY_BEGIN,
        "proxy_marker_end": DEFAULT_PROXY_END,
        "group_marker_begin": DEFAULT_GROUP_BEGIN,
        "group_marker_end": DEFAULT_GROUP_END,
        "name_prefix": "",
        "name_suffix": "",
        "name_template": "",
        "name_strip_patterns": [],
        "surge_cli_path": "/Applications/Surge.app/Contents/Applications/surge-cli",
        "sing_box_path": shutil.which("sing-box") or "/opt/homebrew/bin/sing-box",
        "reload_surge": True,
        "restart_sing_box": True,
        "check_port_conflicts": False,
        "log_path": str(base / "logs" / "sync.log"),
        "state_path": str(base / "state.json"),
    }
    merged = {**defaults, **config}
    required = ["subscription_url", "surge_profile_path", "sing_box_config_path"]
    missing = [key for key in required if not merged.get(key)]
    if missing:
        raise ValueError(f"missing required config keys: {', '.join(missing)}")
    for key in ("surge_profile_path", "sing_box_config_path", "log_path", "state_path"):
        merged[key] = str(Path(merged[key]).expanduser())
    return merged


def fetch_subscription(url: str, timeout: int = 30) -> str:
    if url.startswith("file://"):
        return Path(urllib.parse.urlparse(url).path).read_text(encoding="utf-8")
    if "://" not in url:
        return Path(url).expanduser().read_text(encoding="utf-8")
    req = urllib.request.Request(url, headers={"User-Agent": "surge-vless-bridge/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def maybe_decode_base64(raw: str) -> str:
    if "vless://" in raw:
        return raw
    stripped = "".join(raw.strip().split())
    if not stripped:
        return raw
    padded = stripped + "=" * (-len(stripped) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            decoded = decoder(padded, validate=False).decode("utf-8", errors="replace")
        except Exception:
            continue
        if "vless://" in decoded:
            return decoded
    return raw


def extract_vless_uris(text: str) -> list[str]:
    decoded = maybe_decode_base64(text)
    uris: list[str] = []
    for line in decoded.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "vless://" not in line:
            continue
        match = re.search(r"vless://\S+", line)
        if match:
            uris.append(match.group(0))
    if not uris and decoded.strip().startswith("vless://"):
        uris.append(decoded.strip())
    return uris


def first(params: dict[str, list[str]], *names: str, default: str = "") -> str:
    for name in names:
        values = params.get(name)
        if values and values[0] != "":
            return values[0]
    return default


def parse_vless_uri(uri: str, index: int, config: dict) -> Node:
    parsed = urllib.parse.urlparse(uri.strip())
    if parsed.scheme.lower() != "vless":
        raise ValueError("not a vless uri")
    if not parsed.username or not parsed.hostname or not parsed.port:
        raise ValueError("vless uri missing uuid/server/port")
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    params = {k: v[-1] for k, v in query.items() if v}
    raw_name = urllib.parse.unquote(parsed.fragment or "").strip()
    security = first(query, "security", default="none").lower()
    network = first(query, "type", "network", default="tcp").lower()
    name = build_node_name(raw_name, parsed.hostname, int(parsed.port), index, config)
    return Node(
        name=name,
        uuid=urllib.parse.unquote(parsed.username),
        server=parsed.hostname,
        port=int(parsed.port),
        flow=first(query, "flow"),
        security=security,
        network=network,
        params=params,
    )


def build_node_name(raw_name: str, server: str, port: int, index: int, config: dict) -> str:
    source_name = raw_name or server
    for pattern in config.get("name_strip_patterns", []):
        source_name = re.sub(pattern, "", source_name)
    template = config.get("name_template") or ""
    if template:
        name = template.format(index=index, name=source_name, server=server, port=port)
    else:
        name = f"{config.get('name_prefix', '')}{source_name}{config.get('name_suffix', '')}"
    return sanitize_name(name) or f"vless-{index:03d}"


def parse_nodes(text: str, config: dict | None = None) -> list[Node]:
    config = config or {}
    uris = extract_vless_uris(text)
    if not uris:
        raise ValueError("subscription contains no vless:// nodes")
    nodes = []
    for index, uri in enumerate(uris, start=1):
        try:
            nodes.append(parse_vless_uri(uri, index, config))
        except Exception as exc:
            raise ValueError(f"failed to parse node {index}: {exc}") from exc
    return dedupe_names(nodes)


def dedupe_names(nodes: list[Node]) -> list[Node]:
    seen: dict[str, int] = {}
    result: list[Node] = []
    for node in nodes:
        safe = sanitize_name(node.name)
        count = seen.get(safe, 0) + 1
        seen[safe] = count
        name = safe if count == 1 else f"{safe} {count}"
        result.append(Node(name, node.uuid, node.server, node.port, node.flow, node.security, node.network, node.params))
    return result


def sanitize_name(name: str) -> str:
    cleaned = re.sub(r"[\r\n,=]", " ", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def bool_param(value: str) -> bool:
    return value.lower() in {"1", "true", "yes"}


def build_tls(node: Node) -> dict | None:
    if node.security not in {"tls", "reality"}:
        return None
    p = node.params
    tls: dict = {"enabled": True}
    server_name = p.get("sni") or p.get("servername") or p.get("serverName")
    if server_name:
        tls["server_name"] = server_name
    if bool_param(p.get("allowInsecure", p.get("insecure", "false"))):
        tls["insecure"] = True
    alpn = p.get("alpn")
    if alpn:
        tls["alpn"] = [item for item in alpn.split(",") if item]
    fingerprint = p.get("fp") or p.get("fingerprint")
    if fingerprint:
        tls["utls"] = {"enabled": True, "fingerprint": fingerprint}
    if node.security == "reality":
        public_key = p.get("pbk") or p.get("publicKey") or p.get("public_key")
        short_id = p.get("sid") or p.get("shortId") or p.get("short_id")
        if not public_key:
            raise ValueError(f"{node.name}: reality node missing public key")
        tls["reality"] = {"enabled": True, "public_key": public_key}
        if short_id:
            tls["reality"]["short_id"] = short_id
    return tls


def build_transport(node: Node) -> dict | None:
    p = node.params
    network = node.network
    if network == "tcp":
        return None
    if network == "ws":
        transport: dict = {"type": "ws"}
        if p.get("path"):
            transport["path"] = p["path"]
        if p.get("host"):
            transport["headers"] = {"Host": p["host"]}
        return transport
    if network == "grpc":
        service_name = p.get("serviceName") or p.get("service_name") or p.get("grpc-service-name")
        transport = {"type": "grpc"}
        if service_name:
            transport["service_name"] = service_name
        return transport
    if network in {"http", "h2"}:
        transport = {"type": "http"}
        if p.get("path"):
            transport["path"] = p["path"]
        if p.get("host"):
            transport["host"] = [item for item in p["host"].split(",") if item]
        return transport
    if network == "httpupgrade":
        transport = {"type": "httpupgrade"}
        if p.get("path"):
            transport["path"] = p["path"]
        if p.get("host"):
            transport["host"] = p["host"]
        return transport
    if network == "quic":
        return {"type": "quic"}
    raise ValueError(f"{node.name}: unsupported transport type {network}")


def tag_for(prefix: str, node: Node, index: int) -> str:
    digest = hashlib.sha1(f"{node.name}|{node.server}|{node.port}|{index}".encode()).hexdigest()[:8]
    return f"{prefix}-{index:03d}-{digest}"


def build_sing_box(nodes: list[Node], config: dict) -> dict:
    inbounds = []
    outbounds = [{"type": "direct", "tag": "direct"}]
    rules = []
    for index, node in enumerate(nodes, start=1):
        inbound_tag = tag_for("socks", node, index)
        outbound_tag = tag_for("vless", node, index)
        inbounds.append({
            "type": "socks",
            "tag": inbound_tag,
            "listen": config["listen_host"],
            "listen_port": int(config["start_port"]) + index - 1,
        })
        outbound: dict = {
            "type": "vless",
            "tag": outbound_tag,
            "server": node.server,
            "server_port": node.port,
            "uuid": node.uuid,
        }
        if node.flow:
            outbound["flow"] = node.flow
        tls = build_tls(node)
        if tls:
            outbound["tls"] = tls
        transport = build_transport(node)
        if transport:
            outbound["transport"] = transport
        outbounds.append(outbound)
        rules.append({"inbound": [inbound_tag], "outbound": outbound_tag})
    return {
        "log": {"level": "info", "timestamp": True},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "route": {"rules": rules, "final": "direct"},
    }


def build_surge_blocks(nodes: list[Node], config: dict) -> tuple[str, str]:
    proxy_lines = [
        f"{node.name} = socks5, {config['listen_host']}, {int(config['start_port']) + index}, udp-relay=true"
        for index, node in enumerate(nodes)
    ]
    names = ", ".join(node.name for node in nodes)
    group_line = f"{config['group_name']} = {config['group_type']}, {names}"
    return "\n".join(proxy_lines), group_line


def marker_pair(config: dict, kind: str, profile_text: str) -> tuple[str, str]:
    if kind == "proxy":
        return config["proxy_marker_begin"], config["proxy_marker_end"]
    return config["group_marker_begin"], config["group_marker_end"]


def ensure_section(text: str, section: str) -> str:
    if re.search(rf"(?m)^\[{re.escape(section)}\]\s*$", text):
        return text
    if text and not text.endswith("\n"):
        text += "\n"
    return text + f"\n[{section}]\n"


def ensure_markers(text: str, section: str, begin: str, end: str) -> str:
    if begin in text and end in text:
        return text
    if begin in text or end in text:
        raise ValueError(f"incomplete marker pair in {section}: {begin} / {end}")
    lines = text.splitlines()
    header = next(i for i, line in enumerate(lines) if line.strip() == f"[{section}]")
    insert_at = len(lines)
    for i in range(header + 1, len(lines)):
        if re.match(r"^\[[^\]]+\]\s*$", lines[i].strip()):
            insert_at = i
            break
    markers = [begin, end, ""]
    if insert_at > header + 1 and lines[insert_at - 1].strip():
        markers.insert(0, "")
    lines[insert_at:insert_at] = markers
    return "\n".join(lines).rstrip() + "\n"


def ensure_profile_markers(text: str, config: dict) -> str:
    text = ensure_section(text, "Proxy")
    text = ensure_section(text, "Proxy Group")
    text = ensure_markers(text, "Proxy", config["proxy_marker_begin"], config["proxy_marker_end"])
    return ensure_markers(text, "Proxy Group", config["group_marker_begin"], config["group_marker_end"])


def replace_between(text: str, begin: str, end: str, body: str) -> str:
    pattern = re.compile(rf"({re.escape(begin)})(.*?)(\n{re.escape(end)})", re.S)
    if not pattern.search(text):
        raise ValueError(f"missing marker pair: {begin} / {end}")
    return pattern.sub(lambda m: f"{m.group(1)}\n{body}{m.group(3)}", text, count=1)


def check_ports_free(host: str, start_port: int, count: int) -> None:
    for port in range(start_port, start_port + count):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((host, port)) == 0:
                raise RuntimeError(f"port already in use: {host}:{port}")


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
        temp = Path(fh.name)
    os.replace(temp, path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as fh:
        fh.write(text)
        temp = Path(fh.name)
    os.replace(temp, path)


def run_command(argv: list[str], required: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if required and result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(argv)}\n{result.stdout}")
    return result


def validate_sing_box(config_data: dict, config: dict) -> None:
    sing_box = config.get("sing_box_path")
    if not sing_box or not Path(sing_box).exists():
        log("sing-box binary not found; skipped sing-box check")
        return
    target = Path(config["sing_box_config_path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, suffix=".json", delete=False) as fh:
        json.dump(config_data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
        temp = Path(fh.name)
    try:
        run_command([sing_box, "check", "-c", str(temp)])
    finally:
        temp.unlink(missing_ok=True)


def validate_surge_profile(profile_text: str, config: dict) -> None:
    cli = Path(config["surge_cli_path"])
    if not cli.exists():
        log(f"surge-cli not found; skipped Surge profile check: {cli}")
        return
    profile_path = Path(config["surge_profile_path"])
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=profile_path.parent, suffix=".conf", delete=False) as fh:
        fh.write(profile_text)
        temp = Path(fh.name)
    try:
        run_command([str(cli), "--check", str(temp)])
    finally:
        temp.unlink(missing_ok=True)


def restart_sing_box(config: dict, log_path: Path | None = None) -> None:
    if not config.get("restart_sing_box", True):
        return
    label = config.get("sing_box_launchd_label", "io.github.surge-vless-bridge.sing-box")
    result = run_command(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{label}"], required=False)
    if result.returncode != 0:
        log(f"sing-box launchd kickstart skipped or failed: {result.stdout.strip()}", log_path)


def reload_surge(config: dict, log_path: Path | None = None) -> None:
    if not config.get("reload_surge", True):
        return
    cli = Path(config["surge_cli_path"])
    if not cli.exists():
        log(f"surge-cli not found: {cli}", log_path)
        return
    result = run_command([str(cli), "reload"], required=False)
    if result.returncode != 0:
        log(f"Surge reload failed: {result.stdout.strip()}", log_path)


def save_state(config: dict, nodes: list[Node]) -> None:
    state = {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "count": len(nodes),
        "nodes": [{"name": n.name, "server": n.server, "port": n.port, "network": n.network, "security": n.security} for n in nodes],
    }
    atomic_write_json(Path(config["state_path"]), state)


def sync(config_path: Path, dry_run: bool = False) -> int:
    config = load_config(config_path)
    log_path = Path(config["log_path"])
    try:
        nodes = parse_nodes(fetch_subscription(config["subscription_url"]), config)
        if config.get("check_port_conflicts", False):
            check_ports_free(config["listen_host"], int(config["start_port"]), len(nodes))
        sing_box_config = build_sing_box(nodes, config)
        validate_sing_box(sing_box_config, config)
        proxy_block, group_block = build_surge_blocks(nodes, config)
        profile_path = Path(config["surge_profile_path"])
        profile_text = profile_path.read_text(encoding="utf-8")
        profile_text = ensure_profile_markers(profile_text, config)
        profile_text = replace_between(profile_text, *marker_pair(config, "proxy", profile_text), proxy_block)
        profile_text = replace_between(profile_text, *marker_pair(config, "group", profile_text), group_block)
        validate_surge_profile(profile_text, config)
        if dry_run:
            log(f"dry run OK: {len(nodes)} nodes", log_path)
            return 0
        atomic_write_json(Path(config["sing_box_config_path"]), sing_box_config)
        atomic_write_text(profile_path, profile_text)
        save_state(config, nodes)
        restart_sing_box(config, log_path)
        reload_surge(config, log_path)
        log(f"sync OK: {len(nodes)} nodes", log_path)
        return 0
    except Exception as exc:
        log(f"sync failed, kept previous config: {exc}", log_path)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync VLESS subscriptions into Surge via sing-box.")
    parser.add_argument("-c", "--config", default="config.json", help="path to config.json")
    parser.add_argument("--dry-run", action="store_true", help="validate without writing generated files or reloading services")
    args = parser.parse_args()
    return sync(Path(args.config).expanduser(), dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
