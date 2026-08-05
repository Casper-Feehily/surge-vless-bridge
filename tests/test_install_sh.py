#!/usr/bin/env python3
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_noninteractive_install_creates_expected_files():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        home = root / "home"
        bin_dir = root / "bin"
        sub = root / "sub.txt"
        profile = root / "surge.conf"
        home.mkdir()
        bin_dir.mkdir()
        sub.write_text("vless://u@example.com:443?security=none&type=tcp#Node", encoding="utf-8")
        profile.write_text("[General]\nloglevel = notify\n", encoding="utf-8")
        write_executable(bin_dir / "sing-box", "#!/usr/bin/env bash\nexit 0\n")
        write_executable(bin_dir / "surge-cli", "#!/usr/bin/env bash\nexit 0\n")
        write_executable(bin_dir / "launchctl", "#!/usr/bin/env bash\nexit 0\n")

        env = {
            **os.environ,
            "HOME": str(home),
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "SHELL": "/bin/zsh",
            "INSTALL_LANG": "en",
            "SURGE_CLI_PATH": str(bin_dir / "surge-cli"),
            "SURGE_PROFILE_PATH": str(profile),
            "SUBSCRIPTION_URL": str(sub),
            "SYNC_INTERVAL_HOURS": "0.5",
        }
        result = subprocess.run(["bash", "install.sh"], cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        assert result.returncode == 0, result.stdout

        app_dir = home / "Library/Application Support/surge-vless-bridge"
        config = json.loads((app_dir / "config.json").read_text(encoding="utf-8"))
        assert config["subscription_url"] == str(sub)
        assert config["surge_profile_path"] == str(profile)
        assert config["sing_box_launchd_label"] == "com.casper.surge-vless-bridge.sing-box"
        assert not (app_dir / "config.install.json").exists()
        assert (app_dir / "sing-box.generated.json").exists()
        assert (app_dir / "state.json").exists()

        profile_text = profile.read_text(encoding="utf-8")
        assert "[Proxy]" in profile_text
        assert "[Proxy Group]" in profile_text
        assert "Node = socks5, 127.0.0.1, 39000, udp-relay=true" in profile_text
        assert "VLESS = select, Node" in profile_text

        sync_plist = home / "Library/LaunchAgents/com.casper.surge-vless-bridge.sync.plist"
        assert "<integer>1800</integer>" in sync_plist.read_text(encoding="utf-8")
        shortcut = home / ".local/bin/surge-vless-sync"
        assert shortcut.exists()
        assert os.access(shortcut, os.X_OK)
        assert 'export PATH="$HOME/.local/bin:$PATH"' in (home / ".zshrc").read_text(encoding="utf-8")
        assert "Sync command: surge-vless-sync" in result.stdout


def test_failed_install_removes_temporary_install_config():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        home = root / "home"
        bin_dir = root / "bin"
        sub = root / "sub.txt"
        profile = root / "surge.conf"
        home.mkdir()
        bin_dir.mkdir()
        sub.write_text("not a subscription", encoding="utf-8")
        profile.write_text("[General]\nloglevel = notify\n", encoding="utf-8")
        write_executable(bin_dir / "sing-box", "#!/usr/bin/env bash\nexit 0\n")
        write_executable(bin_dir / "surge-cli", "#!/usr/bin/env bash\nexit 0\n")
        write_executable(bin_dir / "launchctl", "#!/usr/bin/env bash\nexit 0\n")

        env = {
            **os.environ,
            "HOME": str(home),
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "SHELL": "/bin/zsh",
            "INSTALL_LANG": "en",
            "SURGE_CLI_PATH": str(bin_dir / "surge-cli"),
            "SURGE_PROFILE_PATH": str(profile),
            "SUBSCRIPTION_URL": str(sub),
            "SYNC_INTERVAL_HOURS": "1",
        }
        result = subprocess.run(["bash", "install.sh"], cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        assert result.returncode == 1, result.stdout
        assert not (home / "Library/Application Support/surge-vless-bridge/config.install.json").exists()


def test_uninstall_removes_installed_files():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        home = root / "home"
        bin_dir = root / "bin"
        app_dir = home / "Library/Application Support/surge-vless-bridge"
        agents_dir = home / "Library/LaunchAgents"
        shortcut = home / ".local/bin/surge-vless-sync"
        home.mkdir()
        bin_dir.mkdir()
        app_dir.mkdir(parents=True)
        agents_dir.mkdir(parents=True)
        shortcut.parent.mkdir(parents=True)
        write_executable(bin_dir / "launchctl", "#!/usr/bin/env bash\nexit 0\n")
        (app_dir / "config.json").write_text("{}", encoding="utf-8")
        (agents_dir / "com.casper.surge-vless-bridge.sing-box.plist").write_text("plist", encoding="utf-8")
        (agents_dir / "com.casper.surge-vless-bridge.sync.plist").write_text("plist", encoding="utf-8")
        write_executable(shortcut, "#!/usr/bin/env bash\nexit 0\n")

        env = {**os.environ, "HOME": str(home), "PATH": f"{bin_dir}:/usr/bin:/bin"}
        result = subprocess.run(["bash", "uninstall.sh"], cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        assert result.returncode == 0, result.stdout
        assert not app_dir.exists()
        assert not shortcut.exists()
        assert not (agents_dir / "com.casper.surge-vless-bridge.sing-box.plist").exists()
        assert not (agents_dir / "com.casper.surge-vless-bridge.sync.plist").exists()


def test_uninstall_can_keep_config():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        home = root / "home"
        bin_dir = root / "bin"
        app_dir = home / "Library/Application Support/surge-vless-bridge"
        home.mkdir()
        bin_dir.mkdir()
        app_dir.mkdir(parents=True)
        write_executable(bin_dir / "launchctl", "#!/usr/bin/env bash\nexit 0\n")
        (app_dir / "config.json").write_text("{}", encoding="utf-8")

        env = {**os.environ, "HOME": str(home), "PATH": f"{bin_dir}:/usr/bin:/bin", "KEEP_CONFIG": "1"}
        result = subprocess.run(["bash", "uninstall.sh"], cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        assert result.returncode == 0, result.stdout
        assert app_dir.exists()
        assert (app_dir / "config.json").exists()


if __name__ == "__main__":
    tests = [name for name in globals() if name.startswith("test_")]
    for name in tests:
        globals()[name]()
    print(f"{len(tests)} tests passed")
