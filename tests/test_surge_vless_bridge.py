#!/usr/bin/env python3
import base64
import importlib.util
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("surge_vless_bridge", ROOT / "surge_vless_bridge.py")
bridge = importlib.util.module_from_spec(spec)
sys.modules["surge_vless_bridge"] = bridge
spec.loader.exec_module(bridge)


BASE_CONFIG = {
    "listen_host": "127.0.0.1",
    "start_port": 39000,
    "group_name": "VLESS",
    "group_type": "select",
    "proxy_marker_begin": bridge.DEFAULT_PROXY_BEGIN,
    "proxy_marker_end": bridge.DEFAULT_PROXY_END,
    "group_marker_begin": bridge.DEFAULT_GROUP_BEGIN,
    "group_marker_end": bridge.DEFAULT_GROUP_END,
}


def make_sub(lines):
    return base64.b64encode("\n".join(lines).encode()).decode()


def test_parse_base64_reality_tcp():
    raw = make_sub([
        "vless://uuid@example.com:443?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.apple.com&fp=chrome&pbk=abc&sid=0123&type=tcp#Reality%20Node"
    ])
    nodes = bridge.parse_nodes(raw, BASE_CONFIG)
    cfg = bridge.build_sing_box(nodes, BASE_CONFIG)
    out = cfg["outbounds"][1]
    assert nodes[0].name == "Reality Node"
    assert out["flow"] == "xtls-rprx-vision"
    assert out["tls"]["reality"]["public_key"] == "abc"
    assert out["tls"]["utls"]["fingerprint"] == "chrome"


def test_parse_plain_vless_list():
    raw = "\n".join([
        "vless://u1@ws.example.com:443?security=tls&type=ws&sni=ws.example.com&host=cdn.example.com&path=%2Fws#WS",
        "vless://u2@grpc.example.com:443?security=tls&type=grpc&serviceName=mygrpc#GRPC",
    ])
    nodes = bridge.parse_nodes(raw, BASE_CONFIG)
    cfg = bridge.build_sing_box(nodes, BASE_CONFIG)
    assert len(nodes) == 2
    assert cfg["outbounds"][1]["transport"]["type"] == "ws"
    assert cfg["outbounds"][2]["transport"]["service_name"] == "mygrpc"


def test_parse_httpupgrade_and_quic_transports():
    raw = "\n".join([
        "vless://u1@hu.example.com:443?security=tls&type=httpupgrade&host=cdn.example.com&path=%2Fup#HTTPUpgrade",
        "vless://u2@quic.example.com:443?security=tls&type=quic#QUIC",
    ])
    nodes = bridge.parse_nodes(raw, BASE_CONFIG)
    cfg = bridge.build_sing_box(nodes, BASE_CONFIG)
    assert cfg["outbounds"][1]["transport"] == {"type": "httpupgrade", "path": "/up", "host": "cdn.example.com"}
    assert cfg["outbounds"][2]["transport"] == {"type": "quic"}


def test_name_cleanup_and_template():
    cfg = {**BASE_CONFIG, "name_strip_patterns": [r"^Provider-\d+@"], "name_template": "Node {index} {name}"}
    nodes = bridge.parse_nodes("vless://u@example.com:443?security=none&type=tcp#Provider-123@example.com:443", cfg)
    assert nodes[0].name == "Node 1 example.com:443"


def test_duplicate_and_invalid_node_names_are_sanitized():
    raw = "\n".join([
        "vless://u1@example.com:443?security=none&type=tcp#Bad,Name=One",
        "vless://u2@example.com:443?security=none&type=tcp#Bad%2CName%3DOne",
        "vless://u3@example.com:443?security=none&type=tcp#%0A",
    ])
    nodes = bridge.parse_nodes(raw, BASE_CONFIG)
    assert [node.name for node in nodes] == ["Bad Name One", "Bad Name One 2", "example.com"]


def test_reality_requires_public_key():
    try:
        nodes = bridge.parse_nodes("vless://u@example.com:443?security=reality&type=tcp#Reality", BASE_CONFIG)
        bridge.build_sing_box(nodes, BASE_CONFIG)
    except ValueError as exc:
        assert "reality node missing public key" in str(exc)
    else:
        raise AssertionError("expected missing Reality public key to fail")


def test_replace_generic_markers_and_preserve_manual_lines():
    profile = f"""[Proxy]
Manual = ss, 1.1.1.1, 443
{bridge.DEFAULT_PROXY_BEGIN}
old
{bridge.DEFAULT_PROXY_END}

[Proxy Group]
Old = select, Manual
{bridge.DEFAULT_GROUP_BEGIN}
old
{bridge.DEFAULT_GROUP_END}
"""
    nodes = bridge.parse_nodes("vless://u@example.com:443?security=none&type=tcp#Node", BASE_CONFIG)
    proxy, group = bridge.build_surge_blocks(nodes, BASE_CONFIG)
    updated = bridge.replace_between(profile, bridge.DEFAULT_PROXY_BEGIN, bridge.DEFAULT_PROXY_END, proxy)
    updated = bridge.replace_between(updated, bridge.DEFAULT_GROUP_BEGIN, bridge.DEFAULT_GROUP_END, group)
    assert "Manual = ss" in updated
    assert "Old = select, Manual" in updated
    assert "Node = socks5, 127.0.0.1, 39000, udp-relay=true" in updated
    assert "VLESS = select, Node" in updated


def test_sync_creates_missing_surge_sections_and_markers():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sub = root / "sub.txt"
        profile = root / "surge.conf"
        sb = root / "sing-box.json"
        sub.write_text("vless://u@example.com:443?security=none&type=tcp#Node", encoding="utf-8")
        profile.write_text("[General]\nloglevel = notify\n", encoding="utf-8")
        cfg = {
            **BASE_CONFIG,
            "subscription_url": str(sub),
            "surge_profile_path": str(profile),
            "sing_box_config_path": str(sb),
            "sing_box_path": str(root / "missing-sing-box"),
            "surge_cli_path": str(root / "missing-surge-cli"),
            "restart_sing_box": False,
            "reload_surge": False,
            "log_path": str(root / "sync.log"),
            "state_path": str(root / "state.json"),
            "check_port_conflicts": False,
        }
        cfg_path = root / "config.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        assert bridge.sync(cfg_path) == 0
        updated = profile.read_text(encoding="utf-8")
        assert "[Proxy]" in updated
        assert "[Proxy Group]" in updated
        assert bridge.DEFAULT_PROXY_BEGIN in updated
        assert bridge.DEFAULT_GROUP_BEGIN in updated
        assert "Node = socks5, 127.0.0.1, 39000, udp-relay=true" in updated
        assert "VLESS = select, Node" in updated


def test_dry_run_full_flow_file_subscription():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        sub = root / "sub.txt"
        profile = root / "surge.conf"
        sb = root / "sing-box.json"
        sub.write_text("vless://u@example.com:443?security=none&type=tcp#Node", encoding="utf-8")
        profile.write_text(f"[Proxy]\n{bridge.DEFAULT_PROXY_BEGIN}\n{bridge.DEFAULT_PROXY_END}\n[Proxy Group]\n{bridge.DEFAULT_GROUP_BEGIN}\n{bridge.DEFAULT_GROUP_END}\n", encoding="utf-8")
        cfg = {
            **BASE_CONFIG,
            "subscription_url": str(sub),
            "surge_profile_path": str(profile),
            "sing_box_config_path": str(sb),
            "sing_box_path": str(root / "missing-sing-box"),
            "surge_cli_path": str(root / "missing-surge-cli"),
            "restart_sing_box": False,
            "reload_surge": False,
            "log_path": str(root / "sync.log"),
            "state_path": str(root / "state.json"),
            "check_port_conflicts": False,
        }
        cfg_path = root / "config.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        assert bridge.sync(cfg_path, dry_run=True) == 0
        assert not sb.exists()


if __name__ == "__main__":
    tests = [name for name in globals() if name.startswith("test_")]
    for name in tests:
        globals()[name]()
    print(f"{len(tests)} tests passed")
