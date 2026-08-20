#!/usr/bin/env python3
import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_manage_subscriptions_adds_deletes_and_syncs():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        app_dir = root / "app"
        first = root / "first.txt"
        second = root / "second.txt"
        profile = root / "surge.conf"
        app_dir.mkdir()
        first.write_text("vless://u1@first.example.com:443?security=none&type=tcp#First", encoding="utf-8")
        second.write_text("vless://u2@second.example.com:443?security=none&type=tcp#Second", encoding="utf-8")
        profile.write_text("[Proxy]\n[Proxy Group]\n", encoding="utf-8")
        config_path = app_dir / "config.json"
        config_path.write_text(json.dumps({
            "subscription_urls": [str(first)],
            "surge_profile_path": str(profile),
            "sing_box_config_path": str(app_dir / "sing-box.json"),
            "sing_box_path": str(root / "missing-sing-box"),
            "surge_cli_path": str(root / "missing-surge-cli"),
            "restart_sing_box": False,
            "reload_surge": False,
        }), encoding="utf-8")
        result = subprocess.run(
            ["/usr/bin/python3", "manage_subscriptions.py", "--config", str(config_path), "--bridge", str(ROOT / "surge_vless_bridge.py")],
            cwd=ROOT,
            input=f"a\nSecond provider\n{second}\nd\n1\ns\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert result.returncode == 0, result.stdout
        assert json.loads(config_path.read_text(encoding="utf-8"))["subscription_urls"] == [{"name": "Second provider", "url": str(second)}]
        assert "Second = socks5, 127.0.0.1, 39000" in profile.read_text(encoding="utf-8")
        assert list(app_dir.glob("config.json.bak.*"))


if __name__ == "__main__":
    tests = [name for name in globals() if name.startswith("test_")]
    for name in tests:
        globals()[name]()
    print(f"{len(tests)} tests passed")
