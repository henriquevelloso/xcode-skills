#!/usr/bin/env python3
"""Deploy the reviewed maintainer and an empty, disabled Preview scaffold.

This never edits the stable plugin or its installed cache. Default: dry-run.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

import maintain as m


def payload_files(root):
    return {rel: p for rel, p in m.safe_files(root).items()
            if not rel.startswith(("staging/", ".state/setup-receipts/")) and rel != ".gitignore"}


def write_private(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
        temp = Path(f.name)
        f.write(text)
    os.chmod(str(temp), mode)
    os.replace(str(temp), str(path))


def plan(root, destination, home):
    root, destination, home = Path(root).resolve(), m.safe_target(destination), Path(home).resolve()
    manager = m.Manager(root / "maintain.json")
    stable, preview = manager.source("stable"), manager.source("preview")
    m.require(stable.is_dir(), "Existing stable plugin missing")
    m.require(preview.parent == stable.parent and preview.name == "xcode-apple-skills-preview", "Unexpected Preview target")
    m.require(destination.parent == stable.parent and destination.name == "xcode-skills-maintenance", "Unexpected maintenance target")
    registry = home / ".agents/plugins/marketplace.json"
    config = home / ".codex/config.toml"
    catalog = m.read_json(registry)
    m.require(catalog["name"] == manager.config["marketplace"], "Marketplace identity mismatch")
    text = config.read_text()
    stable_id = manager.channel("stable")["plugin_id"] + "@" + manager.config["marketplace"]
    preview_id = manager.channel("preview")["plugin_id"] + "@" + manager.config["marketplace"]
    m.require(m.enabled_setting(text, stable_id) is True, "Stable must remain enabled; review current selection first")
    m.require(m.enabled_setting(text, preview_id) is not True, "Preview was explicitly enabled; review current selection before rerunning setup")
    existing = [p for p in catalog["plugins"] if p["name"] == "xcode-apple-skills-preview"]
    m.require(len(existing) <= 1, "Duplicate Preview marketplace entry")
    entry = {"name": "xcode-apple-skills-preview", "source": {"source": "local", "path": "./" + str(preview.relative_to(home))},
             "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Productivity"}
    m.require(not existing or existing[0] == entry, "Existing Preview registration differs; review before overwriting")
    if preview.exists():
        current = m.read_json(preview / ".codex-plugin/plugin.json")
        m.require(current["name"] == "xcode-apple-skills-preview" and current["interface"]["displayName"] == "Xcode Apple Skills Preview", "Preview source identity mismatch")
    payload = payload_files(root)
    if destination.exists():
        for rel, p in payload.items():
            if rel.startswith(".state/"):
                continue
            target = destination / rel
            m.require(target.is_file() and target.read_bytes() == p.read_bytes(), "Maintainer already exists with different files: " + rel)
    new_text = m.set_enabled(text, preview_id, False)
    return {"root": root, "destination": destination, "stable": stable, "preview": preview,
            "registry": registry, "config": config, "catalog": catalog, "entry": entry,
            "existing": existing, "text": text, "new_text": new_text, "payload": payload,
            "stable_sha256": m.tree_digest(stable), "config_sha256": m.sha(text.encode()),
            "registry_sha256": m.sha(registry.read_bytes()), "preview_setting_before": m.enabled_setting(text, preview_id)}


def deploy(root, destination, home, execute=False):
    p = plan(root, destination, home)
    result = {"dry_run": not execute, "maintenance_path": str(p["destination"]), "preview_path": str(p["preview"]),
              "stable_source_sha256": p["stable_sha256"], "stable_source_will_change": False,
              "preview_enabled": False, "registry_will_change": not bool(p["existing"]),
              "config_will_change": p["new_text"] != p["text"], "preview_skills": m.skills(p["preview"] / "skills") if p["preview"].exists() else []}
    if not execute:
        return result
    # Recheck source/config immediately before mutation. No entire config backup:
    # the receipt records only the one plugin setting and file hashes.
    m.require(m.tree_digest(p["stable"]) == p["stable_sha256"], "Stable changed during setup")
    m.require(m.sha(p["config"].read_bytes()) == p["config_sha256"], "Config changed during setup")
    m.require(m.sha(p["registry"].read_bytes()) == p["registry_sha256"], "Marketplace changed during setup")
    if not p["destination"].exists():
        temporary = Path(tempfile.mkdtemp(prefix=".xcode-skills-maintenance-", dir=p["destination"].parent))
        try:
            for rel, original in p["payload"].items():
                target = temporary / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(original), str(target))
            temporary.rename(p["destination"])
        except Exception:
            shutil.rmtree(temporary)
            raise
    if not p["preview"].exists():
        m.copy_tree(Path(root) / "scaffold/xcode-apple-skills-preview", p["preview"])
        (p["preview"] / "skills").mkdir(exist_ok=True)
    if p["new_text"] != p["text"]:
        write_private(p["config"], p["new_text"])
    if not p["existing"]:
        p["catalog"]["plugins"].append(p["entry"])
        m.write_json(p["registry"], p["catalog"])
    m.require(m.tree_digest(p["stable"]) == p["stable_sha256"], "Stable changed unexpectedly")
    m.require(m.enabled_setting(p["config"].read_text(), "xcode-apple-skills-preview@personal") is False, "Preview unexpectedly enabled")
    receipt = {"at": m.now(), "stable_source_sha256": p["stable_sha256"],
               "preview_setting_before": p["preview_setting_before"], "preview_setting_after": False,
               "registry_entry_before": p["existing"], "registry_entry_after": p["entry"],
               "config_sha256_before": p["config_sha256"], "config_sha256_after": m.sha(p["config"].read_bytes()),
               "registry_sha256_before": p["registry_sha256"], "registry_sha256_after": m.sha(p["registry"].read_bytes()),
               "installed_cache_changed": False}
    receipt_path = p["destination"] / ".state/setup-receipts" / (m.digest(receipt)[:16] + ".json")
    m.write_json(receipt_path, receipt)
    return dict(result, receipt=str(receipt_path), stable_verified_unchanged=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", default="~/plugins/xcode-skills-maintenance")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = deploy(Path(__file__).resolve().parent, Path(args.destination).expanduser(), Path.home(), args.execute)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (m.MaintenanceError, OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
