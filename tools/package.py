#!/usr/bin/env python3
"""Generate, validate and deterministically package the two instruction libraries.

Python 3.9+, standard library only. No exported helper is imported or executed.
Source Xcode version/build and package version are deliberately separate fields.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
import urllib.parse
import zipfile

CHANNELS = ("stable", "preview")
PLUGINS = {"stable": "xcode-apple-skills", "preview": "xcode-apple-skills-preview"}
CATALOG_START = "<!-- GENERATED CATALOG START -->"
CATALOG_END = "<!-- GENERATED CATALOG END -->"
VERSION_RX = re.compile(r"\d+\.\d+\.\d+")
PRIVATE_RX = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)[A-Za-z0-9._-]+|~/(?:plugins|Downloads)/")
SECRET_RX = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
PERSONAL_RX = re.compile(r"TrueTapp|SwiftUI/MV|Preserve MV without ViewModels|For this environment, use|\bAxiom\b", re.I)
BANNED_PARTS = {".state", ".local", "__pycache__", "node_modules", ".git", "hooks", "sessions", "backups"}
ALLOWED_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".py"}


def contains_private(value):
    """Inspect decoded strings so JSON escaping cannot hide a private path."""
    if isinstance(value, str):
        return bool(PRIVATE_RX.search(value) or SECRET_RX.search(value))
    if isinstance(value, dict):
        return any(contains_private(key) or contains_private(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(contains_private(item) for item in value)
    return False


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def json_text(value):
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def files(root):
    """No symlink traversal; reject links even if their targets are in the package."""
    root = Path(root)
    if root.is_symlink():
        raise ValueError("Symlink package root")
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlink is not distributable: " + path.relative_to(root).as_posix())
        if path.is_file():
            result[path.relative_to(root).as_posix()] = path
    return result


def skill_names(plugin):
    return sorted(path.parent.name for path in (Path(plugin) / "skills").glob("*/SKILL.md"))


def frontmatter(text):
    match = re.match(r"^\ufeff?---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.S)
    if not match:
        raise ValueError("Missing skill frontmatter")
    fields = {}
    for key in ("name", "description"):
        row = re.search(r"^" + key + r":\s*(.+)$", match.group(1), re.M)
        if not row:
            raise ValueError("Missing frontmatter " + key)
        value = row.group(1).strip()
        if value[:1] == '"':
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = value.strip('"')
        elif value[:1] == "'":
            value = value[1:-1].replace("''", "'")
        fields[key] = value
    return fields


def release(root):
    data = read_json(Path(root) / "release.json")
    if contains_private(data):
        raise ValueError("Private path or credential-shaped content in release metadata")
    if data.get("schema_version") != 1 or not VERSION_RX.fullmatch(data.get("version", "")):
        raise ValueError("Unsupported release schema or package version")
    if data.get("repository") != "henriquevelloso/xcode-skills" or data.get("author") != "Henrique Velloso":
        raise ValueError("Unexpected repository or maintainer identity")
    if set(data.get("channels", {})) != set(CHANNELS):
        raise ValueError("Release must contain stable and preview sources")
    for channel in CHANNELS:
        source = data["channels"][channel]
        xcode = source["xcode"]
        if source.get("plugin") != PLUGINS[channel] or xcode.get("channel") != channel:
            raise ValueError("Plugin/channel identity mismatch")
        if not re.fullmatch(r"\d+(?:\.\d+)*", xcode.get("version", "")) or not re.fullmatch(r"[A-Za-z0-9]+", xcode.get("build", "")):
            raise ValueError("Invalid Xcode version/build")
        if not re.fullmatch(r"[a-f0-9]{64}", source.get("export_sha256", "")):
            raise ValueError("Missing export digest")
        if source.get("source_url") != "https://developer.apple.com/news/releases/":
            raise ValueError("Source evidence must reference Apple's release catalog")
    stable = data["channels"]["stable"]["xcode"]["version"].split(".")
    prefix = stable[:2] if len(stable) > 1 else stable + ["0"]
    if data["version"].split(".")[:2] != prefix:
        raise ValueError("Package prefix must follow the included stable Xcode")
    return data


def label(source):
    xcode = source["xcode"]
    # Keep full beta/RC wording; a build is shown separately in the catalog.
    return re.sub(r"\s*\(" + re.escape(xcode["build"]) + r"\)\s*$", "", xcode["label"]).strip()


def manifests(data, channel):
    source = data["channels"][channel]
    name = source["plugin"]
    title = "Xcode Skills" + (" Preview" if channel == "preview" else "") + " — " + label(source)
    description = ("Preview (beta/RC)" if channel == "preview" else "Release") + " Xcode instruction skills and references. " + label(source) + "; community adaptation maintained by Henrique Velloso."
    common = {"name": name, "version": data["version"], "description": description,
              "author": {"name": data["author"], "url": "https://github.com/henriquevelloso"},
              "homepage": "https://github.com/" + data["repository"],
              "repository": "https://github.com/" + data["repository"]}
    codex = dict(common, skills="./skills/", interface={
        "displayName": title, "developerName": data["author"], "category": "Developer Tools",
        "shortDescription": ("Preview" if channel == "preview" else "Release") + " instructions from " + label(source),
        "longDescription": description + " Not an official Apple or OpenAI plugin. Uses your project's existing architecture, toolchain and instructions. No bundled hooks or servers. Source and licensing limitations are recorded in THIRD_PARTY_NOTICES.md.",
        "capabilities": ["Read", "Write"],
        "defaultPrompt": ["Review the relevant SwiftUI code without modifying files."]})
    claude = dict(common, displayName=title)
    return codex, claude


def provenance(root, data, channel):
    source = data["channels"][channel]
    plugin = Path(root) / "plugins" / source["plugin"]
    inventory = {name: sha(path.read_bytes()) for name, path in files(plugin / "skills").items()}
    return {"schema_version": 1, "package_version": data["version"], "channel": channel,
            "project_maintainer": data["author"], "upstream": source,
            "skills": skill_names(plugin), "skill_file_sha256": inventory,
            "adaptation": "Community-maintained entrypoints; references are derived from the stated Xcode export. Upstream content is not authored by the project maintainer.",
            "validation_limits": ["Structural and packaging checks do not prove all SDK examples compile.", "No app, Siri, device or distribution journey is asserted by this package.", "No newly exported executable code is run by packaging."]}


def catalogs(data):
    entries = [{"name": PLUGINS[c], "source": {"source": "local", "path": "./plugins/" + PLUGINS[c]},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Developer Tools"} for c in CHANNELS]
    codex = {"name": "xcode-skills", "interface": {"displayName": "Xcode Skills by Henrique Velloso"}, "plugins": entries}
    claude = {"name": "xcode-skills", "owner": {"name": data["author"], "url": "https://github.com/henriquevelloso"},
              "description": "Release and preview Xcode instruction skills maintained by Henrique Velloso.",
              "plugins": [{"name": PLUGINS[c], "source": "./plugins/" + PLUGINS[c]} for c in CHANNELS]}
    return codex, claude


def release_notes(root, data):
    lines = ["# Xcode Skills " + data["version"], "", "Both plugins use this package version. Xcode source versions below are independent of the package revision.", ""]
    for channel in CHANNELS:
        source = data["channels"][channel]
        lines += ["## " + channel.title(), "", "- Plugin: `" + source["plugin"] + "`",
                  "- Source: " + source["xcode"]["label"], "- Export SHA-256: `" + source["export_sha256"] + "`",
                  "- Included skills: " + str(len(skill_names(Path(root) / "plugins" / source["plugin"]))) + ".", ""]
        changes = data.get("changes", {}).get(channel, {})
        for key in ("added", "updated", "removed", "unchanged"):
            values = changes.get(key, [])
            lines.append("- " + key.title() + ": " + (", ".join("`" + x + "`" for x in values) if values else "none") + ".")
        lines += ["- " + note for note in changes.get("notes", [])]
        lines += [""]
    lines += ["## Validation limits", "", "The release validates metadata, source containment, references, allowed helper hashes and deterministic artifacts. It does not establish compilation or runtime correctness of all exported examples. See THIRD_PARTY_NOTICES.md for provenance and licensing boundaries.", ""]
    return "\n".join(lines)


def inventory_table(root, data):
    lines = ["**Package version: `" + data["version"] + "`**", "", "| Channel | Xcode source | Build | Skills |", "| --- | --- | --- | ---: |"]
    for channel in CHANNELS:
        source = data["channels"][channel]
        lines.append("| " + channel + " | " + label(source) + " | `" + source["xcode"]["build"] + "` | " + str(len(skill_names(Path(root) / "plugins" / source["plugin"]))) + " |")
    lines += ["", "| Release skill | Preview counterpart |", "| --- | --- |"]
    stable = set(skill_names(Path(root) / "plugins" / PLUGINS["stable"]))
    preview = set(skill_names(Path(root) / "plugins" / PLUGINS["preview"]))
    for name in sorted(stable | {name[:-8] for name in preview if name.endswith("-preview")}):
        lines.append("| " + ("`" + name + "`" if name in stable else "—") + " | " + ("`" + name + "-preview`" if name + "-preview" in preview else "—") + " |")
    return "\n".join(lines)


def generate(root):
    root = Path(root).resolve()
    data = release(root)
    write(root / "VERSION", data["version"] + "\n")
    for channel in CHANNELS:
        plugin = root / "plugins" / PLUGINS[channel]
        codex, claude = manifests(data, channel)
        write(plugin / ".codex-plugin/plugin.json", json_text(codex))
        write(plugin / ".claude-plugin/plugin.json", json_text(claude))
        write(plugin / "provenance.json", json_text(provenance(root, data, channel)))
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            if (root / name).is_file():
                write(plugin / name, (root / name).read_text(encoding="utf-8"))
        readme = "# " + codex["interface"]["displayName"] + "\n\nPackage version: `" + data["version"] + "`. Source build: `" + data["channels"][channel]["xcode"]["build"] + "`.\n\nInstall from the `henriquevelloso/xcode-skills` marketplace, then select `" + PLUGINS[channel] + "@xcode-skills`. The repository README contains Codex and Claude Code commands.\n\nThis package shares the same `skills/` directory across clients. It has no hooks, bundled server, credentials, or automatic code execution. Consuming tools and platform APIs must exist in your environment.\n\nSee `provenance.json` and `THIRD_PARTY_NOTICES.md` for source evidence and limitations.\n"
        write(plugin / "README.md", readme)
    codex, claude = catalogs(data)
    write(root / ".agents/plugins/marketplace.json", json_text(codex))
    write(root / ".claude-plugin/marketplace.json", json_text(claude))
    notes = release_notes(root, data)
    history = root / "releases" / ("v" + data["version"] + ".md")
    # The current candidate may evolve before publication; previously released
    # note files are not touched because only the current version is selected.
    write(history, notes)
    write(root / "CHANGELOG.md", "# Changelog\n\n" + "\n".join("- [" + p.stem + "](" + p.relative_to(root).as_posix() + ")" for p in sorted((root / "releases").glob("v*.md"), key=lambda p: tuple(int(v) for v in p.stem[1:].split(".")), reverse=True)) + "\n")
    readme = root / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        if CATALOG_START not in text or CATALOG_END not in text:
            raise ValueError("README is missing generated catalog markers")
        before, rest = text.split(CATALOG_START, 1)
        _, after = rest.split(CATALOG_END, 1)
        write(readme, before + CATALOG_START + "\n" + inventory_table(root, data) + "\n" + CATALOG_END + after)
    return {"version": data["version"], "generated": True, "plugins": [PLUGINS[c] for c in CHANNELS]}


def public_text_errors(root):
    """Check public documents/metadata, not code or intentionally hostile fixtures."""
    root = Path(root)
    candidates = set(root.glob("*.md"))
    candidates.update(root.glob("*.json"))
    for folder in ("docs", "releases"):
        candidates.update((root / folder).rglob("*.md"))
    candidates.update(root / name for name in ("LICENSE", "VERSION", ".agents/plugins/marketplace.json", ".claude-plugin/marketplace.json"))
    errors = []
    for path in sorted(candidates):
        if path.is_symlink():
            errors.append("Symlink public document: " + path.relative_to(root).as_posix())
            continue
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        decoded_private = path.suffix == ".json" and contains_private(json.loads(text))
        if PRIVATE_RX.search(text) or SECRET_RX.search(text) or decoded_private:
            errors.append("Private path or credential-shaped content in public document: " + path.relative_to(root).as_posix())
    return errors


def validate(root):
    root = Path(root).resolve()
    errors = []
    try:
        errors.extend(public_text_errors(root))
        data = release(root)
        policy = read_json(root / "package-policy.json")
        if policy.get("schema_version") != 1:
            raise ValueError("Unsupported package policy")
        if (root / "VERSION").read_text().strip() != data["version"]:
            errors.append("VERSION does not match release metadata")
        for channel in CHANNELS:
            plugin = root / "plugins" / PLUGINS[channel]
            codex, claude = manifests(data, channel)
            for rel, expected in ((".codex-plugin/plugin.json", codex), (".claude-plugin/plugin.json", claude), ("provenance.json", provenance(root, data, channel))):
                if read_json(plugin / rel) != expected:
                    errors.append("Generated metadata drift: " + PLUGINS[channel] + "/" + rel)
            names = skill_names(plugin)
            if not names:
                errors.append("Empty plugin: " + PLUGINS[channel])
            for name in names:
                entry = plugin / "skills" / name / "SKILL.md"
                fields = frontmatter(entry.read_text(encoding="utf-8"))
                if fields["name"] != name or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
                    errors.append("Invalid skill name/directory: " + name)
                if len(fields["description"]) > 1024 or not fields["description"].strip():
                    errors.append("Invalid skill description: " + name)
                if channel == "preview" and not name.endswith("-preview"):
                    errors.append("Preview skill missing suffix: " + name)
                canonical = name[:-8] if channel == "preview" and name.endswith("-preview") else name
                if canonical in policy["excluded_skills"]:
                    errors.append("Excluded skill included: " + name)
            for rel, path in files(plugin).items():
                parts = Path(rel).parts
                root_files = {"README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "provenance.json", ".codex-plugin/plugin.json", ".claude-plugin/plugin.json"}
                if rel not in root_files and not (len(parts) >= 3 and parts[0] == "skills" and parts[1] in names):
                    errors.append("File outside the declared skill library: " + PLUGINS[channel] + "/" + rel)
                if set(parts) & BANNED_PARTS or path.suffix not in ALLOWED_SUFFIXES and rel != "LICENSE":
                    errors.append("Unsupported/private package file: " + PLUGINS[channel] + "/" + rel)
                if path.name.startswith((".mcp", "hooks.")) or rel in {"mcp.json", ".app.json", "plugin.json"}:
                    errors.append("Unexpected executable integration: " + rel)
                if path.stat().st_size > 5 * 1024 * 1024:
                    errors.append("Oversize package file: " + rel)
                content = path.read_bytes()
                text = content.decode("utf-8")
                if PRIVATE_RX.search(text) or SECRET_RX.search(text):
                    errors.append("Private path or credential-shaped content: " + PLUGINS[channel] + "/" + rel)
                if rel.startswith("skills/") and PERSONAL_RX.search(text):
                    errors.append("Personal architecture/tool preference: " + PLUGINS[channel] + "/" + rel)
                if path.suffix == ".py" or content.startswith(b"#!"):
                    identity = path.relative_to(root).as_posix()
                    if policy.get("allowed_executables", {}).get(identity) != sha(content):
                        errors.append("Unreviewed executable bytes: " + identity)
                if path.suffix == ".md":
                    # Ignore fenced code; links inside examples are not actual references.
                    prose = re.sub(r"```.*?```", "", text, flags=re.S)
                    for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", prose):
                        target = target.strip().split(' "', 1)[0].strip("<>")
                        url = urllib.parse.urlsplit(target)
                        if url.scheme or not url.path:
                            continue
                        resolved = (path.parent / urllib.parse.unquote(url.path)).resolve()
                        if plugin not in resolved.parents or not resolved.is_file():
                            errors.append("Broken/escaping reference: " + rel + " -> " + target)
            for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
                if (plugin / name).read_bytes() != (root / name).read_bytes():
                    errors.append("Licensing notice drift: " + PLUGINS[channel] + "/" + name)
        expected_codex, expected_claude = catalogs(data)
        for rel, expected in ((".agents/plugins/marketplace.json", expected_codex), (".claude-plugin/marketplace.json", expected_claude)):
            if read_json(root / rel) != expected:
                errors.append("Marketplace metadata drift: " + rel)
        if (root / "releases" / ("v" + data["version"] + ".md")).read_text() != release_notes(root, data):
            errors.append("Current release notes drift")
        readme = (root / "README.md").read_text()
        if CATALOG_START + "\n" + inventory_table(root, data) + "\n" + CATALOG_END not in readme:
            errors.append("README inventory drift")
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        errors.append(str(error))
    return {"valid": not errors, "errors": errors, "version": data.get("version") if "data" in locals() else None}


def build(root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    result = validate(root)
    if not result["valid"]:
        raise ValueError("Package validation failed: " + "; ".join(result["errors"]))
    if out == root or (root / "plugins") == out or (root / "plugins") in out.parents:
        raise ValueError("Artifact output must not be inside a plugin")
    data = release(root)
    expected_names = {PLUGINS[c] + "-" + data["version"] + ".zip" for c in CHANNELS} | {"SHA256SUMS", "provenance.json", "RELEASE_NOTES.md"}
    if out.exists():
        unexpected = {path.name for path in out.iterdir()} - expected_names
        if unexpected:
            raise ValueError("Output contains unrelated or previous-version files; choose a fresh output directory: " + ", ".join(sorted(unexpected)))
    out.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for channel in CHANNELS:
        plugin = root / "plugins" / PLUGINS[channel]
        archive = out / (PLUGINS[channel] + "-" + data["version"] + ".zip")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as stream:
            for rel, path in files(plugin).items():
                info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                stream.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_STORED)
        artifacts.append(archive)
    # Aggregate provenance has no local paths and does not include mutable CI timestamps.
    write(out / "provenance.json", json_text({"schema_version": 1, "version": data["version"], "repository": data["repository"], "channels": {c: provenance(root, data, c) for c in CHANNELS}}))
    write(out / "RELEASE_NOTES.md", release_notes(root, data))
    artifacts += [out / "provenance.json", out / "RELEASE_NOTES.md"]
    write(out / "SHA256SUMS", "".join(sha(path.read_bytes()) + "  " + path.name + "\n" for path in sorted(artifacts)))
    return {"version": data["version"], "artifacts": [str(path) for path in artifacts] + [str(out / "SHA256SUMS")], "valid": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["generate", "validate", "build"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            result = generate(args.root)
        elif args.command == "validate":
            result = validate(args.root)
        else:
            result = build(args.root, args.out or args.root / "dist")
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"valid": False, "errors": [str(error)]}
    print(json_text(result), end="")
    return 0 if result.get("valid", True) else 1


if __name__ == "__main__":
    sys.exit(main())
