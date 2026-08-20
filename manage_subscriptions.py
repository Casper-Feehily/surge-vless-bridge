#!/usr/bin/env python3
"""Interactively add or remove VLESS subscription URLs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def subscriptions(config: dict) -> list[dict[str, str]]:
    urls = config.get("subscription_urls")
    if urls is None and config.get("subscription_url"):
        urls = [config["subscription_url"]]
    if not isinstance(urls, list):
        raise ValueError("config has no valid subscription URLs")
    result = []
    for item in urls:
        url = item if isinstance(item, str) else item.get("url") if isinstance(item, dict) else None
        name = url if isinstance(item, str) else item.get("name") if isinstance(item, dict) else None
        if not isinstance(url, str) or not url.strip() or not isinstance(name, str) or not name.strip():
            raise ValueError("config has no valid subscription URLs")
        result.append({"name": name.strip(), "url": url.strip()})
    if not result:
        raise ValueError("config has no valid subscription URLs")
    return result


def write_json(path: Path, data: dict) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
        temporary = Path(fh.name)
    os.replace(temporary, path)


def apply(config_path: Path, bridge_path: Path, config: dict, entries: list[dict[str, str]]) -> bool:
    updated = {**config, "subscription_urls": entries}
    updated.pop("subscription_url", None)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=config_path.parent, suffix=".json", delete=False) as fh:
        json.dump(updated, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
        temporary = Path(fh.name)
    try:
        if subprocess.run([sys.executable, str(bridge_path), "-c", str(temporary), "--dry-run"], check=False).returncode:
            return False
    finally:
        temporary.unlink(missing_ok=True)

    original = config_path.read_text(encoding="utf-8")
    backup = Path(tempfile.mkstemp(prefix="config.json.bak.", dir=config_path.parent)[1])
    backup.write_text(original, encoding="utf-8")
    write_json(config_path, updated)
    if subprocess.run([sys.executable, str(bridge_path), "-c", str(config_path)], check=False).returncode:
        config_path.write_text(original, encoding="utf-8")
        print("Sync failed; restored the previous config.", file=sys.stderr)
        return False
    print(f"Saved and synced. Config backup: {backup}")
    return True


def main() -> int:
    app_dir = Path.home() / "Library/Application Support/surge-vless-bridge"
    parser = argparse.ArgumentParser(description="Add or remove VLESS subscription URLs.")
    parser.add_argument("--config", type=Path, default=app_dir / "config.json")
    parser.add_argument("--bridge", type=Path, default=app_dir / "surge_vless_bridge.py")
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        urls = subscriptions(config)
    except Exception as exc:
        print(f"Could not read subscriptions: {exc}", file=sys.stderr)
        return 1

    while True:
        print("\nCurrent subscriptions:")
        print(*[f"{index}. {entry['name']}: {entry['url']}" for index, entry in enumerate(urls, start=1)], sep="\n")
        action = input("[a]dd, [d]elete, [s]ave and sync, [q]uit: ").strip().lower()
        if action == "a":
            name = input("Subscription name: ").strip()
            url = input("Subscription URL: ").strip()
            if not name or not url:
                print("Name and URL cannot be empty.")
            elif any(entry["url"] == url for entry in urls):
                print("That URL is already present.")
            else:
                urls.append({"name": name, "url": url})
        elif action == "d":
            try:
                index = int(input("Subscription number to delete: ")) - 1
                if len(urls) == 1:
                    raise ValueError("Keep at least one subscription.")
                removed = urls.pop(index)
                print(f"Removed: {removed['name']}")
            except (ValueError, IndexError) as exc:
                print(f"Nothing removed: {exc}")
        elif action == "s":
            return 0 if apply(args.config, args.bridge, config, urls) else 1
        elif action == "q":
            return 0
        else:
            print("Choose a, d, s, or q.")


if __name__ == "__main__":
    raise SystemExit(main())
