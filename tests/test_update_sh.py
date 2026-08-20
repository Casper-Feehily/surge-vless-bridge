#!/usr/bin/env python3
import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_update_preserves_config_and_migrates_single_subscription():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        home = root / "home"
        app_dir = home / "Library/Application Support/surge-vless-bridge"
        sub = root / "sub.txt"
        profile = root / "surge.conf"
        home.mkdir()
        app_dir.mkdir(parents=True)
        sub.write_text("vless://u@example.com:443?security=none&type=tcp#Node", encoding="utf-8")
        profile.write_text("[Proxy]\n[Proxy Group]\n", encoding="utf-8")
        config = {
            "subscription_url": str(sub),
            "surge_profile_path": str(profile),
            "sing_box_config_path": str(app_dir / "sing-box.generated.json"),
            "sing_box_path": str(root / "missing-sing-box"),
            "surge_cli_path": str(root / "missing-surge-cli"),
            "restart_sing_box": False,
            "reload_surge": False,
        }
        (app_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")
        (app_dir / "surge_vless_bridge.py").write_text("old version", encoding="utf-8")

        result = subprocess.run(
            ["bash", "update.sh"],
            cwd=ROOT,
            env={**os.environ, "HOME": str(home), "SKIP_GIT_PULL": "1"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert result.returncode == 0, result.stdout
        updated = json.loads((app_dir / "config.json").read_text(encoding="utf-8"))
        assert updated["subscription_urls"] == [str(sub)]
        assert "subscription_url" not in updated
        assert list(app_dir.glob("config.json.bak.*"))
        assert (app_dir / "surge_vless_bridge.py").read_text(encoding="utf-8") == (ROOT / "surge_vless_bridge.py").read_text(encoding="utf-8")
        assert (app_dir / "sing-box.generated.json").exists()


if __name__ == "__main__":
    tests = [name for name in globals() if name.startswith("test_")]
    for name in tests:
        globals()[name]()
    print(f"{len(tests)} tests passed")
