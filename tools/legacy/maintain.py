#!/usr/bin/env python3
"""Personal Xcode skill maintenance. Python 3.9+, standard library only.

check is read-only. prepare writes staging, never the active plugin. apply and
rollback default to dry-run and require a matching reviewed digest to execute.
No exported helper, hook, or third-party script is ever executed by this tool.
"""
import argparse
import contextlib
import datetime
import difflib
import hashlib
import html.parser
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request


class MaintenanceError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise MaintenanceError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, data):
    write_content(path, (json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode())


def write_content(path, data):
    """Atomic replacement also works for read-only files copied from Apple."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, delete=False) as f:
        temporary = Path(f.name)
        f.write(data)
    os.chmod(str(temporary), mode)
    os.replace(str(temporary), str(path))


def safe_files(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "Expected a real directory: %s" % root)
    result, folded = {}, set()
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in {".git", "__pycache__", ".DS_Store"} for part in rel.parts):
            continue
        require(not p.is_symlink(), "Symlink refused: %s" % p)
        if not p.is_file():
            continue
        name = rel.as_posix()
        require(name.casefold() not in folded, "Case-insensitive path collision: %s" % name)
        folded.add(name.casefold())
        result[name] = p
    return result


def inventory(root):
    return {rel: {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size,
                  "executable": bool(p.stat().st_mode & 0o111)}
            for rel, p in safe_files(root).items()}


def tree_digest(root):
    return digest(inventory(root))


def copy_tree(source, destination):
    files = safe_files(source)
    destination = Path(destination)
    require(not destination.exists(), "Destination already exists: %s" % destination)
    destination.mkdir(parents=True)
    for rel, p in files.items():
        q = destination / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(p), str(q))


def safe_target(path):
    path = Path(path).expanduser().absolute()
    require(not path.is_symlink(), "Plugin source must not be a symlink")
    require("cache" not in path.parts, "Refusing to write an installed plugin cache")
    require(len(path.parts) > 3, "Unsafe source directory")
    return path


def safe_relative(name):
    path = Path(name)
    require(not path.is_absolute() and name and ".." not in path.parts and "\\" not in name,
            "Unsafe relative path: " + name)
    return path


def skill_header(text):
    text = text.replace("\r\n", "\n")
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    require(m is not None, "SKILL.md needs YAML frontmatter")
    name = re.search(r"^name:\s*['\"]?([a-z0-9-]+)['\"]?\s*$", m.group(1), re.M)
    description = re.search(r"^description:\s*(.+)", m.group(1), re.M)
    require(name is not None and description is not None, "Skill name/description missing")
    require(len(name.group(1)) < 64, "Skill name is too long")
    return name.group(1), text[:m.end()], text[m.end():]


def skills(root):
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(p.parent.name for p in root.glob("*/SKILL.md"))


PREVIEW_NOTE = ("<!-- xcode-preview-channel -->\n"
    "This is the Preview edition. Select it when the user calls its `-preview` name or requests beta/RC guidance. "
    "Use the release edition for unspecified release work. References to other skills in this edition use their "
    "`-preview` equivalents from the same plugin; compare channels only when requested. "
    "Keep the selected app/toolchain and the task's existing authorization unchanged.\n\n")


def local_skill_path(rel, suffix):
    parts = safe_relative(rel).parts
    return Path(parts[0] + suffix, *parts[1:])


def logical_skill_files(plugin):
    """Map local aliases back to Apple's names for three-way comparison."""
    plugin = Path(plugin)
    provenance = read_json(plugin / "source-snapshot.json") if (plugin / "source-snapshot.json").is_file() else {}
    suffix = provenance.get("skill_name_suffix", "")
    result = {}
    for rel, path in safe_files(plugin / "skills").items():
        parts = Path(rel).parts
        name = parts[0]
        if suffix:
            require(name.endswith(suffix), "Local skill is missing its recorded suffix: " + name)
            name = name[:-len(suffix)]
        canonical = Path(name, *parts[1:]).as_posix()
        require(canonical not in result, "Logical skill collision: " + canonical)
        result[canonical] = path
    return result


def normalize_preview_names(plugin, suffix):
    """Only naming, routing and links in staging; never rename Apple CLI APIs."""
    if not suffix:
        return {}
    require(suffix == "-preview", "Only the reviewed Preview suffix is supported")
    plugin = Path(plugin)
    provenance_path = plugin / "source-snapshot.json"
    provenance = read_json(provenance_path) if provenance_path.is_file() else {}
    recorded = provenance.get("skill_name_suffix", "")
    require(recorded in {"", suffix}, "Local suffix scheme changed unexpectedly")
    if not recorded:
        for name in skills(plugin / "skills"):
            target = plugin / "skills" / (name + suffix)
            require(not target.exists(), "Preview naming collision: " + str(target))
        for name in skills(plugin / "skills"):
            (plugin / "skills" / name).rename(plugin / "skills" / (name + suffix))
    aliases = {}
    for name in skills(plugin / "skills"):
        require(name.endswith(suffix), "Preview name missing suffix")
        aliases[name[:-len(suffix)]] = name
    for original, name in aliases.items():
        entry = plugin / "skills" / name / "SKILL.md"
        _, header, body = skill_header(entry.read_text())
        header = re.sub(r"(?m)^name:.*$", "name: " + name, header)
        match = re.search(r"(?m)^description:\s*(.+)$", header)
        raw = match.group(1).strip()
        if raw.startswith('"'):
            try:
                description = json.loads(raw)
            except ValueError:
                raise MaintenanceError("Preview description needs manual YAML review: " + name)
        elif raw.startswith("'") and raw.endswith("'"):
            description = raw[1:-1].replace("''", "'")
        else:
            description = raw
        if not description.startswith("Preview (beta/RC). "):
            description = "Preview (beta/RC). " + description
        header = header[:match.start(1)] + json.dumps(description, ensure_ascii=False) + header[match.end(1):]
        if "<!-- xcode-preview-channel -->" not in body:
            body = "\n" + PREVIEW_NOTE + body.lstrip("\n")
        write_content(entry, (header + body).encode())
        ui = entry.parent / "agents/openai.yaml"
        if ui.is_file():
            text = ui.read_text()
            display = re.search(r'(?m)^([ \t]*display_name:[ \t]*)(.+)$', text)
            require(display is not None, "Preview UI metadata needs a display name: " + name)
            raw_name = display.group(2).strip()
            title = json.loads(raw_name) if raw_name.startswith('"') else raw_name.strip("'")
            if not title.lower().endswith(" preview"):
                title += " Preview"
            text = text[:display.start(2)] + json.dumps(title, ensure_ascii=False) + text[display.end(2):]
        else:
            title = {"xctrace": "Xcode Trace Analysis", "siri-app-integration": "Siri App Integration",
                     "siri-evaluations": "Siri Evaluations", "macos-touch-gestures": "macOS Touch Gestures"}.get(original, original.replace("-", " ").title())
            text = 'interface:\n  display_name: ' + json.dumps(title + " Preview") + '\n'
        for old, new in aliases.items():
            text = re.sub(r"\$(xcode-apple-skills-preview:)?" + re.escape(old) + r"(?=[^a-z0-9-]|$)",
                          lambda match: "$" + (match.group(1) or "") + new, text)
        write_content(ui, text.encode())
    # Only relative Markdown targets change. xctrace commands and code stay intact.
    for path in (plugin / "skills").rglob("*.md"):
        text = path.read_text()
        def rewrite(match):
            target = match.group(1)
            if urllib.parse.urlsplit(target).scheme:
                return match.group(0)
            parts = target.split("/")
            for index in range(len(parts) - 1):
                parts[index] = aliases.get(parts[index], parts[index])
            return match.group(0).replace(target, "/".join(parts), 1)
        text = re.sub(r"\[[^\]]*\]\(([^)]+)\)", rewrite, text)
        for old, new in aliases.items():
            text = text.replace("xcode-apple-skills-preview:" + old + "`", "xcode-apple-skills-preview:" + new + "`")
        write_content(path, text.encode())
    provenance.update(skill_name_suffix=suffix, skill_aliases=aliases, included_skills=skills(plugin / "skills"))
    write_json(provenance_path, provenance)
    return aliases


def code_file(name, data=None):
    return Path(name).suffix.lower() in {".py", ".sh", ".zsh", ".bash", ".js", ".ts", ".rb", ".pl", ".swift"} or (data or b"").startswith(b"#!")


def validate_plugin(root, expected_id=None, expected_name=None, excluded=(), skill_suffix=""):
    root = Path(root)
    errors, names = [], []
    files = safe_files(root)
    manifest = root / ".codex-plugin/plugin.json"
    require(manifest.is_file(), "Compatibility manifest missing: %s" % manifest)
    doc = read_json(manifest)
    if expected_id and doc.get("name") != expected_id:
        errors.append("Plugin identity mismatch")
    if expected_name and doc.get("interface", {}).get("displayName") != expected_name:
        errors.append("Plugin display name mismatch")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9.-]+)?", doc.get("version", "")):
        errors.append("Plugin version must be semver")
    if doc.get("skills") != "./skills/":
        errors.append("Expected skills path ./skills/")
    if any(x.startswith(("hooks/", ".mcp", "mcp.json", ".app.json")) for x in files):
        errors.append("Unexpected executable integration; review separately")
    for entry in (root / "skills").glob("*/SKILL.md"):
        try:
            name, _, _ = skill_header(entry.read_text())
            if name != entry.parent.name:
                errors.append("Skill directory/name mismatch: " + entry.parent.name)
            if name in names:
                errors.append("Duplicate skill name: " + name)
            canonical_name = name[:-len(skill_suffix)] if skill_suffix and name.endswith(skill_suffix) else name
            if name in excluded or canonical_name in excluded:
                errors.append("Excluded skill present: " + name)
            if skill_suffix and not name.endswith(skill_suffix):
                errors.append("Missing skill suffix: " + name)
            names.append(name)
        except MaintenanceError as e:
            errors.append(str(e) + ": " + str(entry))
    for rel, p in files.items():
        if not rel.startswith("skills/") or p.suffix != ".md":
            continue
        text = re.sub(r"```.*?```", "", p.read_text(), flags=re.S)
        for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            link = link.strip().split(' "', 1)[0].strip("<>")
            parsed = urllib.parse.urlsplit(link)
            if parsed.scheme or not parsed.path:
                continue
            target = (p.parent / urllib.parse.unquote(parsed.path)).resolve()
            if root.resolve() not in target.parents or not target.is_file():
                errors.append("Broken/escaping local link: %s -> %s" % (rel, link))
    return {"valid": not errors, "errors": errors, "skills": sorted(names), "files": len(files)}


def merge_lines(base, local, upstream):
    """Merge disjoint line edits. Overlaps preserve local and require review."""
    if local == upstream or upstream == base:
        return local, False
    if local == base:
        return upstream, False
    a, edits = base.splitlines(keepends=True), []
    for side, value in [("local", local), ("upstream", upstream)]:
        b = value.splitlines(keepends=True)
        for tag, i, j, x, y in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
            if tag != "equal":
                edits.append((i, j, b[x:y], side))
    unique = []
    for edit in edits:
        duplicate = False
        for prior in unique:
            i, j, replacement, side = edit
            x, y, other, other_side = prior
            if side == other_side:
                continue
            if i == x and j == y and replacement == other:
                duplicate = True
                break
            overlap = max(i, x) < min(j, y) or (i == j and x <= i <= y) or (x == y and i <= x <= j)
            if overlap:
                return local, True
        if not duplicate:
            unique.append(edit)
    for i, j, replacement, _ in sorted(unique, key=lambda e: (e[0], e[1]), reverse=True):
        a[i:j] = replacement
    return "".join(a), False


def merge_file(name, base, local, upstream):
    if upstream is None:
        return local, "retained_missing_upstream", False
    if local is None:
        if base is not None:
            return None, "retained_local_deletion", False
        return upstream, "added", code_file(name, upstream)
    if upstream == base or local == upstream:
        return local, "kept_local", False
    if base is None:
        return local, "local_upstream_collision", True
    if name.endswith("/SKILL.md"):
        try:
            _, _, old_body = skill_header(base.decode())
            _, local_head, local_body = skill_header(local.decode())
            _, _, new_body = skill_header(upstream.decode())
            if old_body.strip() == new_body.strip():
                return local, "kept_adapted_metadata", False
            body, conflict = merge_lines(old_body, local_body, new_body)
            return (local_head + body).encode(), "content_conflict" if conflict else "merged_body_kept_adapted_metadata", conflict
        except (UnicodeError, MaintenanceError):
            return local, "format_conflict", True
    if local == base:
        return upstream, "updated", code_file(name, upstream)
    try:
        merged, conflict = merge_lines(base.decode(), local.decode(), upstream.decode())
        return merged.encode(), "content_conflict" if conflict else "merged", conflict or code_file(name, upstream)
    except UnicodeError:
        return local, "binary_conflict", True


def enabled_setting(text, identity):
    pattern = r"(?m)^\[plugins\.([\"'])" + re.escape(identity) + r"\1\]\s*(?:\n|$)"
    matches = list(re.finditer(pattern, text))
    require(len(matches) <= 1, "Duplicate TOML plugin section: " + identity)
    if not matches:
        return None
    start = matches[0].end()
    end = re.search(r"(?m)^\[", text[start:])
    section = text[start:start + end.start()] if end else text[start:]
    values = re.findall(r"(?m)^\s*enabled\s*=\s*(true|false)\s*(?:#.*)?$", section)
    require(len(values) <= 1, "Duplicate enabled key: " + identity)
    return values[0] == "true" if values else None


def set_enabled(text, identity, value):
    enabled_setting(text, identity)
    pattern = r"(?m)^\[plugins\.([\"'])" + re.escape(identity) + r"\1\]\s*(?:\n|$)"
    match = re.search(pattern, text)
    line = "enabled = " + ("true" if value else "false") + "\n"
    if match is None:
        return text.rstrip() + '\n\n[plugins."' + identity + '"]\n' + line
    start = match.end()
    end_match = re.search(r"(?m)^\[", text[start:])
    end = start + end_match.start() if end_match else len(text)
    section = text[start:end]
    enabled = re.search(r"(?m)^[ \t]*enabled[ \t]*=[ \t]*(true|false)[ \t]*(?:#[^\n]*)?$", section)
    if enabled:
        section = section[:enabled.start(1)] + ("true" if value else "false") + section[enabled.end(1):]
    else:
        section = line + section
    return text[:start] + section + text[end:]


class ReleaseText(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip, self.text = 0, []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.text.append(data)


def fetch_release_evidence():
    url = "https://developer.apple.com/news/releases/"
    request = urllib.request.Request(url, headers={"User-Agent": "Personal-Xcode-Skills-Maintenance/1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        final_url = urllib.parse.urlsplit(response.url)
        require(final_url.hostname == "developer.apple.com" and final_url.scheme == "https", "Unexpected release source redirect")
        data = response.read(2 * 1024 * 1024 + 1)
        require(len(data) <= 2 * 1024 * 1024, "Release page exceeds limit")
    parser = ReleaseText()
    parser.feed(data.decode())
    text = " ".join(parser.text)
    pattern = r"\bXcode\s+(\d+(?:\.\d+)*)(\s+(?:beta|RC|Release Candidate)(?:\s+\d+)?)?\s*\(([A-Za-z0-9]+)\)"
    records = {}
    for m in re.finditer(pattern, text, re.I):
        version, suffix, build = m.groups()
        channel = "preview" if suffix else "stable"
        key = (version, build, channel)
        records[key] = {"version": version, "build": build, "channel": channel, "label": m.group(0)}
    require(records, "No exact Xcode version/build release records found; channels remain unknown")
    return {"schema_version": 1, "source": url, "checked_at": now(),
            "page_sha256": sha(data), "releases": list(records.values())}


class Manager:
    def __init__(self, config):
        self.config_path = Path(config).resolve()
        self.root = self.config_path.parent
        self.config = read_json(self.config_path)
        require(self.config.get("schema_version") == 1, "Unsupported maintenance config")
        self.state = (self.root / self.config.get("state_dir", ".state")).resolve()
        self.evidence_path = self.root / self.config["release_evidence"]
        self.evidence = read_json(self.evidence_path)
        require(self.evidence.get("source") == "https://developer.apple.com/news/releases/", "Release evidence must come from Apple's official releases page")

    def channel(self, name):
        require(name in {"stable", "preview"}, "Unknown channel")
        return self.config["channels"][name]

    def source(self, name):
        return safe_target(self.channel(name)["source"])

    def identify(self, app):
        app = Path(app).expanduser().resolve()
        require(app.suffix == ".app", "Expected an installed .app bundle")
        info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
        require(info.get("CFBundleIdentifier") == "com.apple.dt.Xcode", "Not an Xcode application")
        version = plistlib.loads((app / "Contents/version.plist").read_bytes())
        short, build = version["CFBundleShortVersionString"], version["ProductBuildVersion"]
        facts = [r for r in self.evidence["releases"] if r["version"] == short and r["build"] == build]
        fact = next((r for r in facts if r["channel"] == "stable"), facts[0] if facts else None)
        resources = {}
        for rel in ["Contents/PlugIns/IDEIntelligenceChat.framework/Versions/A/Resources",
                    "Contents/PlugIns/IDEXCStringsSupport.framework/Versions/A/Resources/Skills"]:
            folder = app / rel
            if folder.is_dir():
                for name, p in safe_files(folder).items():
                    if name.endswith((".idechatprompttemplate", ".md.packaged")):
                        resources[rel + "/" + name] = sha(p.read_bytes())
        exporter = app / "Contents/Developer/usr/bin/agent"
        bridge = app / "Contents/Developer/usr/bin/mcpbridge"
        require(exporter.is_file(), "Official agent exporter not found")
        identity = {"version": short, "build": build, "bundle_version": version["CFBundleVersion"],
                    "channel": fact["channel"] if fact else "unknown", "resources_sha256": digest(resources),
                    "exporter_sha256": sha(exporter.read_bytes()),
                    "mcpbridge_sha256": sha(bridge.read_bytes()) if bridge.is_file() else None}
        return dict(identity, path=str(app), fingerprint=digest(identity),
                    channel_evidence={"source": self.evidence["source"], "checked_at": self.evidence["checked_at"], "record": fact})

    def discover(self, apps=None):
        paths = set(Path(p).expanduser() for p in apps or [])
        if not paths:
            for root in self.config["app_roots"]:
                paths.update(Path(root).expanduser().glob("Xcode*.app"))
        bundles, invalid = [], []
        for path in sorted(paths):
            try:
                bundles.append(self.identify(path))
            except (MaintenanceError, OSError, KeyError, ValueError) as error:
                invalid.append({"path": str(path), "error": str(error)})
        return bundles, invalid

    def check(self, apps=None):
        bundles, invalid = self.discover(apps)
        seen = {}
        for bundle in bundles:
            fp = bundle["fingerprint"]
            bundle["duplicate_of"] = seen.get(fp)
            seen.setdefault(fp, bundle["path"])
            reports = []
            candidates = self.state / "candidates"
            if candidates.is_dir():
                for p in sorted(candidates.glob("*/review.json")):
                    report = read_json(p)
                    if report.get("xcode", {}).get("fingerprint") == fp:
                        seal = read_json(p.parent / "seal.json")["sha256"]
                        applied = self.state / ("applied-" + report["channel"] + ".json")
                        is_applied = applied.is_file() and read_json(applied).get("candidate_seal") == seal
                        valid, reason = True, None
                        try:
                            if is_applied:
                                self.verify_candidate_integrity(p.parent)
                                receipt = read_json(applied)
                                require(tree_digest(self.source(report["channel"])) == receipt["source_sha256"] == tree_digest(p.parent / "plugin"),
                                        "Applied plugin source changed after its receipt")
                            else:
                                self.verify_candidate(p.parent)
                        except (MaintenanceError, OSError, ValueError) as error:
                            valid, reason = False, str(error)
                        reports.append({"candidate": p.parent.name, "pending_decisions": sum(not d["resolved"] for d in report["pending_decisions"]), "seal": seal,
                                        "valid_for_current_tool": valid, "reason": reason,
                                        "validation_valid": report["validation"]["valid"],
                                        "status": "stale_or_invalid" if not valid else ("validation_failed" if not report["validation"]["valid"] else ("source_applied" if is_applied else "awaiting_review"))})
            bundle["candidates"] = reports
            bundle["needs_prepare"] = bundle["channel"] != "unknown" and not bundle["duplicate_of"] and not any(r["valid_for_current_tool"] for r in reports)
        source_states = {}
        for channel in ["stable", "preview"]:
            source = self.source(channel)
            source_states[channel] = {"path": str(source), "exists": source.is_dir()}
            if source.is_dir():
                source_states[channel].update({"digest": tree_digest(source), "skills": skills(source / "skills")})
        return {"read_only": True, "checked_at": now(), "bundles": bundles, "invalid_bundles": invalid,
                "sources": source_states, "preview_installed_xcode": any(b["channel"] == "preview" for b in bundles),
                "evidence_checked_at": self.evidence["checked_at"]}

    @contextlib.contextmanager
    def lock(self):
        self.state.mkdir(parents=True, exist_ok=True)
        lock = self.state / ".maintenance-lock"
        try:
            lock.mkdir()
        except FileExistsError:
            raise MaintenanceError("Another maintenance operation is running; inspect %s before removing a stale lock" % lock)
        try:
            yield
        finally:
            lock.rmdir()

    def baseline(self, channel):
        record = self.state / ("applied-" + channel + ".json")
        # The first Preview inherits the current Stable adaptations. Compare
        # those against their own last applied Apple export, not the legacy
        # manual export. Once Preview is applied, it always keeps its own base.
        if not record.is_file() and not skills(self.source(channel) / "skills"):
            adaptation = self.channel(channel).get("adaptation_source")
            if adaptation:
                donor = safe_target(adaptation)
                matches = [name for name in self.config["channels"] if self.source(name) == donor]
                require(len(matches) == 1 and matches[0] != channel,
                        "Adaptation source must identify a distinct configured channel")
                donor_record = self.state / ("applied-" + matches[0] + ".json")
                if donor_record.is_file():
                    record = donor_record
        if record.is_file():
            installed = read_json(record)
            root = self.state / installed["snapshot"] / "export"
            require(tree_digest(root) == installed["export_sha256"], "Applied baseline snapshot changed")
            return root
        baseline = self.state / "baselines/legacy"
        if not baseline.exists():
            original = Path(self.config["legacy_export"]).expanduser()
            manifest = read_json(Path(self.config["legacy_manifest"]).expanduser())
            expected = manifest["original_sha256"]
            for rel, expected_sha in expected.items():
                safe_relative(rel)
                p = original / rel
                require(p.is_file() and not p.is_symlink() and sha(p.read_bytes()) == expected_sha,
                        "Original baseline changed/missing: " + rel)
            baseline.mkdir(parents=True)
            for rel in expected:
                target = baseline / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(original / rel), str(target))
            write_json(self.state / "baselines/legacy-inventory.json", inventory(baseline))
        require(inventory(baseline) == read_json(self.state / "baselines/legacy-inventory.json"), "Legacy baseline was modified")
        return baseline

    def bind_xcode(self, app, launch=True):
        def processes():
            try:
                p = subprocess.run(["/bin/ps", "-axo", "pid=,comm="], capture_output=True, text=True, check=True)
            except (OSError, subprocess.CalledProcessError) as error:
                raise MaintenanceError("Cannot inspect Xcode process. Run prepare with permission to inspect/start Xcode: %s" % error)
            expected = str(Path(app).resolve() / "Contents/MacOS/Xcode")
            return [int(m.group(1)) for line in p.stdout.splitlines()
                    for m in [re.match(r"\s*(\d+)\s+(.+?)\s*$", line)] if m and m.group(2) == expected]
        found = processes()
        if not found and launch:
            subprocess.run(["/usr/bin/open", "-g", "-a", str(app)], check=True, capture_output=True, timeout=25)
            for _ in range(40):
                found = processes()
                if found:
                    break
                time.sleep(0.5)
        require(len(found) == 1, "Need exactly one running Xcode for the selected absolute bundle path")
        return found[0]

    def export(self, bundle, destination):
        app = Path(bundle["path"])
        require(not Path(destination).exists(), "Export destination must be new")
        pid = self.bind_xcode(app)
        env = dict(os.environ, DEVELOPER_DIR=str(app / "Contents/Developer"), MCP_XCODE_PID=str(pid))
        env.pop("MCP_XCODE_SESSION_ID", None)
        command = ["/usr/bin/xcrun", "agent", "skills", "export", str(destination)]
        p = subprocess.run(command, env=env, capture_output=True, text=True, timeout=180)
        require(p.returncode == 0, "Official exporter failed: " + (p.stderr or p.stdout).strip())
        require(self.identify(app)["fingerprint"] == bundle["fingerprint"], "Xcode changed during export")
        require(self.bind_xcode(app, launch=False) == pid, "Xcode process changed during export")
        require(skills(destination), "Official exporter returned no skill entrypoints")
        return {"command": command, "DEVELOPER_DIR": env["DEVELOPER_DIR"], "MCP_XCODE_PID": str(pid),
                "stdout": p.stdout, "stderr": p.stderr, "verified_process_bundle": str(app)}

    def snapshot(self, bundle):
        key = bundle["channel"] + "-" + bundle["version"] + "-" + bundle["build"] + "-" + bundle["fingerprint"][:12]
        target = self.state / "snapshots" / key
        if target.exists():
            record = read_json(target / "snapshot.json")
            require(record["export_sha256"] == tree_digest(target / "export"), "Prepared snapshot was modified")
            require(record["xcode"]["fingerprint"] == bundle["fingerprint"], "Snapshot identity mismatch")
            return target, record
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".export-", dir=target.parent))
        try:
            receipt = self.export(bundle, temporary / "export")
            record = {"schema_version": 1, "created_at": now(), "xcode": bundle, "exporter": receipt,
                      "inventory": inventory(temporary / "export"), "export_sha256": tree_digest(temporary / "export")}
            write_json(temporary / "snapshot.json", record)
            temporary.rename(target)
        except Exception as error:
            write_json(temporary / "failure.json", {"at": now(), "xcode": bundle, "error": str(error)})
            raise
        return target, record

    def prepare(self, app, channel):
        bundle = self.identify(app)
        require(bundle["channel"] != "unknown", "Channel unknown: verify the exact version/build on Apple's official releases page first")
        require(bundle["channel"] == channel, "Channel mismatch; never reuse RC/beta content as a stable export")
        with self.lock():
            baseline = self.baseline(channel)
            snapshot, record = self.snapshot(bundle)
            applied = self.state / ("applied-" + channel + ".json")
            if applied.is_file() and read_json(applied)["snapshot"] == str(snapshot.relative_to(self.state)):
                receipt = read_json(applied)
                return {"no_update": True, "channel": channel, "snapshot": receipt["snapshot"],
                        "source_drift_since_apply": tree_digest(self.source(channel)) != receipt["source_sha256"]}
            return self.build_candidate(snapshot, record, baseline, channel)

    def build_candidate(self, snapshot, snapshot_record, baseline, channel):
        source = self.source(channel)
        require(source.is_dir(), "Plugin source is not prepared: " + str(source))
        adaptation = source
        if not skills(source / "skills") and self.channel(channel).get("adaptation_source"):
            adaptation = safe_target(self.channel(channel)["adaptation_source"])
        local_digest, target_digest = tree_digest(adaptation), tree_digest(source)
        identity = {"channel": channel, "snapshot": str(snapshot.relative_to(self.state)),
                    "export_sha256": snapshot_record["export_sha256"], "base_sha256": tree_digest(baseline),
                    "adaptation_sha256": local_digest, "target_sha256": target_digest, "config_sha256": digest(self.config),
                    "tool_sha256": sha(Path(__file__).read_bytes())}
        key = channel + "-" + snapshot_record["xcode"]["version"] + "-" + snapshot_record["xcode"]["build"] + "-" + digest(identity)[:12]
        destination = self.state / "candidates" / key
        if destination.exists():
            self.verify_candidate(destination)
            return {"candidate": str(destination), "idempotent": True, "seal": read_json(destination / "seal.json")["sha256"]}
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".candidate-", dir=destination.parent))
        try:
            plugin = temporary / "plugin"
            copy_tree(adaptation, plugin)
            suffix = self.channel(channel).get("skill_name_suffix", "")
            normalize_preview_names(plugin, suffix)
            base_files, local_files, new_files = safe_files(baseline), logical_skill_files(adaptation), safe_files(snapshot / "export")
            excluded = set(self.config["excluded_skills"])
            existing_skills = {rel.split("/", 1)[0] for rel in local_files if rel.endswith("/SKILL.md")}
            new_skills = set(skills(snapshot / "export")) - existing_skills - excluded
            decisions, comparison, patches = [], [], []
            for name in sorted(new_skills):
                decisions.append({"id": "new-skill:" + name, "kind": "new_skill", "skill": name,
                                  "reason": "New Apple skill quarantined; review compatibility, overlap and tools before inclusion", "resolved": False})
            for rel in sorted(set(base_files) | set(local_files) | set(new_files)):
                skill = rel.split("/", 1)[0]
                if skill in excluded:
                    continue
                base = base_files[rel].read_bytes() if rel in base_files else None
                local = local_files[rel].read_bytes() if rel in local_files else None
                upstream = new_files[rel].read_bytes() if rel in new_files else None
                if skill in new_skills:
                    comparison.append({"path": rel, "base": sha(base), "adapted": sha(local), "upstream": sha(upstream), "action": "new_skill_quarantined", "requires_review": True})
                    try:
                        patches.extend(difflib.unified_diff([], (upstream or b"").decode().splitlines(True), fromfile="previous-apple/" + rel, tofile="new-apple/" + rel))
                    except UnicodeError:
                        patches.append("New quarantined binary: " + rel + "\n")
                    continue
                result, action, conflict = merge_file(rel, base, local, upstream)
                target = plugin / "skills" / local_skill_path(rel, suffix)
                if result is not None:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists() or target.read_bytes() != result:
                        write_content(target, result)
                    if rel in local_files:
                        shutil.copymode(str(local_files[rel]), str(target))
                if conflict:
                    # Keep the active adaptation until the user resolves the conflict.
                    if local is not None:
                        write_content(target, local)
                    elif target.exists():
                        target.unlink()
                    decisions.append({"id": "file:" + rel, "kind": "file", "path": rel,
                                      "reason": action, "resolved": False})
                comparison.append({"path": rel, "base": sha(base), "adapted": sha(local), "upstream": sha(upstream), "action": action, "requires_review": conflict})
                if base != upstream:
                    try:
                        patches.extend(difflib.unified_diff((base or b"").decode().splitlines(True), (upstream or b"").decode().splitlines(True), fromfile="previous-apple/" + rel, tofile="new-apple/" + rel))
                    except UnicodeError:
                        patches.append("Binary change: " + rel + "\n")
            aliases = normalize_preview_names(plugin, suffix)
            # Stable and Preview keep separate, durable identities.
            manifest_path = plugin / ".codex-plugin/plugin.json"
            manifest = read_json(manifest_path)
            cfg = self.channel(channel)
            manifest["name"] = cfg["plugin_id"]
            manifest.setdefault("interface", {})["displayName"] = cfg["display_name"]
            if suffix:
                text = manifest["interface"].get("longDescription", "")
                text = text.replace("Exige seleção exclusiva por projeto para evitar duplicar o Stable.",
                                    "Skills com sufixo -preview podem ficar ativas junto do Stable, com escolha pelo nome.")
                manifest["interface"]["longDescription"] = text
            parts = re.match(r"(\d+)\.(\d+)\.(\d+)", read_json(source / ".codex-plugin/plugin.json")["version"])
            require(parts is not None, "Current plugin version is not semver")
            manifest["version"] = "%s.%s.%s" % (parts.group(1), parts.group(2), int(parts.group(3)) + 1)
            write_json(manifest_path, manifest)
            provenance = {"schema_version": 2, "channel": channel, "xcode": snapshot_record["xcode"],
                          "snapshot": identity["snapshot"], "export_sha256": snapshot_record["export_sha256"],
                          "included_skills": skills(plugin / "skills"), "excluded_skills": sorted(excluded),
                          "retained_missing_upstream": sorted(set(existing_skills) - set(skills(snapshot / "export"))),
                          "legacy_snapshot_preserved": "source-snapshot.legacy.json"}
            if suffix:
                provenance.update(skill_name_suffix=suffix, skill_aliases=aliases)
            old_snapshot = plugin / "source-snapshot.json"
            legacy_copy = plugin / "source-snapshot.legacy.json"
            if old_snapshot.is_file() and not legacy_copy.exists():
                shutil.copy2(str(old_snapshot), str(legacy_copy))
            write_json(old_snapshot, provenance)
            validation = validate_plugin(plugin, cfg["plugin_id"], cfg["display_name"], excluded, suffix)
            old_validation = plugin / "validation-report.json"
            if old_validation.is_file() and not (plugin / "validation-report.legacy.json").exists():
                shutil.copy2(str(old_validation), str(plugin / "validation-report.legacy.json"))
            write_json(old_validation, {"schema_version": 2, "plugin_version": manifest["version"],
                                       "validation": validation, "exported_code_executed": False,
                                       "limits": ["Structural validation; no device execution or compilation of Apple examples", "Historical tests are preserved in validation-report.legacy.json"]})
            validation = validate_plugin(plugin, cfg["plugin_id"], cfg["display_name"], excluded, suffix)
            fresh_validation = read_json(old_validation)
            fresh_validation["validation"] = validation
            write_json(old_validation, fresh_validation)
            report = dict(identity, schema_version=1, created_at=now(), xcode=snapshot_record["xcode"],
                          target_source=str(source), adaptation_source=str(adaptation), comparison=comparison,
                          pending_decisions=decisions, validation=validation,
                          excluded_skills=sorted(excluded), new_skills_quarantined=sorted(new_skills),
                          possible_renames=self.config.get("possible_renames", {}),
                          source_baseline=str(baseline.relative_to(self.state)), status="awaiting_review")
            write_json(temporary / "review.json", report)
            (temporary / "upstream.diff").write_text("".join(patches))
            self.write_changelog(temporary, report)
            self.seal(temporary)
            temporary.rename(destination)
        except Exception:
            shutil.rmtree(temporary)
            raise
        return {"candidate": str(destination), "idempotent": False, "seal": read_json(destination / "seal.json")["sha256"],
                "pending_decisions": len(decisions), "validation": validation}

    def write_changelog(self, candidate, report):
        counts = {}
        for row in report["comparison"]:
            counts[row["action"]] = counts.get(row["action"], 0) + 1
        text = ["# Candidato: " + self.channel(report["channel"])["display_name"], "",
                "Xcode %s, build %s, canal %s." % (report["xcode"]["version"], report["xcode"]["build"], report["channel"]), "",
                "Preparado em staging. O plugin ativo ainda não foi atualizado.", "",
                "## Comparação", ""]
        text += ["- %s: %s" % (key, value) for key, value in sorted(counts.items())]
        text += ["", "## Decisões pendentes", ""]
        text += ["- `%s`: %s" % (item["id"], item["reason"]) for item in report["pending_decisions"] if not item["resolved"]] or ["- Nenhuma; ainda requer aprovação do hash do candidato."]
        text += ["", "Veja `review.json` e `upstream.diff`. Nenhum helper exportado foi executado.", ""]
        (candidate / "CHANGELOG.md").write_text("\n".join(text))

    def seal(self, candidate):
        inv = inventory(candidate)
        inv.pop("seal.json", None)
        seal = {"sha256": digest(inv), "inventory": inv}
        write_json(candidate / "seal.json", seal)
        return seal["sha256"]

    def verify_candidate_integrity(self, candidate):
        candidate = Path(candidate).resolve()
        require(candidate.parent == (self.state / "candidates").resolve(), "Candidate must be in this maintenance state")
        seal = read_json(candidate / "seal.json")
        inv = inventory(candidate)
        inv.pop("seal.json", None)
        require(inv == seal["inventory"] and digest(inv) == seal["sha256"], "Candidate changed after sealing; use resolve for reviewed changes")
        report = read_json(candidate / "review.json")
        require(tree_digest(self.state / report["snapshot"] / "export") == report["export_sha256"], "Export snapshot changed")
        require(tree_digest(self.state / report["source_baseline"]) == report["base_sha256"], "Previous Apple baseline changed")
        return report, seal

    def verify_candidate(self, candidate):
        report, seal = self.verify_candidate_integrity(candidate)
        require(report["config_sha256"] == digest(self.config), "Maintenance config changed; prepare a fresh candidate")
        require(report["tool_sha256"] == sha(Path(__file__).read_bytes()), "Maintenance tool changed; prepare a fresh candidate")
        return report, seal

    def resolve(self, candidate, decision_id, choice):
        candidate = Path(candidate).resolve()
        with self.lock():
            report, _ = self.verify_candidate(candidate)
            matches = [d for d in report["pending_decisions"] if d["id"] == decision_id]
            require(len(matches) == 1, "Decision not found")
            decision = matches[0]
            require(not decision["resolved"], "Decision already resolved")
            raw = self.state / report["snapshot"] / "export"
            plugin = candidate / "plugin"
            suffix = self.channel(report["channel"]).get("skill_name_suffix", "")
            require(choice in {"keep-local", "take-upstream"}, "Unsupported resolution")
            if choice == "take-upstream":
                if decision["kind"] == "new_skill":
                    name = decision["skill"]
                    copy_tree(raw / name, plugin / "skills" / (name + suffix))
                else:
                    rel = decision["path"]
                    target = plugin / "skills" / local_skill_path(rel, suffix)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    write_content(target, (raw / rel).read_bytes())
            decision.update(resolved=True, choice=choice, resolved_at=now())
            normalize_preview_names(plugin, suffix)
            provenance = read_json(plugin / "source-snapshot.json")
            provenance["included_skills"] = skills(plugin / "skills")
            write_json(plugin / "source-snapshot.json", provenance)
            cfg = self.channel(report["channel"])
            report["validation"] = validate_plugin(plugin, cfg["plugin_id"], cfg["display_name"], self.config["excluded_skills"], suffix)
            validation_report = read_json(plugin / "validation-report.json")
            validation_report["validation"] = report["validation"]
            write_json(plugin / "validation-report.json", validation_report)
            write_json(candidate / "review.json", report)
            self.write_changelog(candidate, report)
            return {"candidate": str(candidate), "new_seal": self.seal(candidate), "validation": report["validation"]}

    def replace_source(self, source, prepared):
        require(source.parent.is_dir(), "Source parent missing")
        temporary = Path(tempfile.mkdtemp(prefix="." + source.name + "-new-", dir=source.parent))
        temporary.rmdir()
        previous = temporary.with_name(temporary.name + "-previous")
        copy_tree(prepared, temporary)
        try:
            source.rename(previous)
            try:
                temporary.rename(source)
            except Exception:
                previous.rename(source)
                raise
            shutil.rmtree(previous)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def apply(self, candidate, approved=None, execute=False):
        candidate = Path(candidate).resolve()
        with self.lock():
            report, seal = self.verify_candidate(candidate)
            channel, source = report["channel"], self.source(report["channel"])
            applied_record = self.state / ("applied-" + channel + ".json")
            if applied_record.is_file() and read_json(applied_record).get("candidate_seal") == seal["sha256"]:
                require(tree_digest(source) == tree_digest(candidate / "plugin"), "Applied source was subsequently edited")
                return {"already_applied": True, "source": str(source)}
            require(tree_digest(source) == report["target_sha256"], "Plugin source changed since preparation")
            require(tree_digest(Path(report["adaptation_source"])) == report["adaptation_sha256"], "Adaptations changed since preparation")
            snapshot = self.state / report["snapshot"]
            require(tree_digest(snapshot / "export") == report["export_sha256"], "Export snapshot changed")
            require(not any(not d["resolved"] for d in report["pending_decisions"]), "Resolve every pending decision before apply")
            cfg = self.channel(channel)
            validation = validate_plugin(candidate / "plugin", cfg["plugin_id"], cfg["display_name"], self.config["excluded_skills"], cfg.get("skill_name_suffix", ""))
            require(validation["valid"], "Candidate validation failed: " + "; ".join(validation["errors"]))
            result = {"dry_run": not execute, "source": str(source), "candidate_seal": seal["sha256"],
                      "cache_changed": False, "activation": "Source only. Refresh/restart Codex and verify in a new task after approval."}
            if not execute:
                return result
            require(approved == seal["sha256"], "Explicit approval of this exact candidate sha256 is required")
            backup = self.state / "backups" / (channel + "-" + datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f") + "-" + seal["sha256"][:12])
            copy_tree(source, backup / "source")
            previous_record = read_json(applied_record) if applied_record.is_file() else None
            receipt = {"channel": channel, "target_source": str(source), "before_sha256": tree_digest(source),
                       "after_sha256": tree_digest(candidate / "plugin"), "candidate_seal": seal["sha256"], "previous_applied": previous_record,
                       "backup_inventory": inventory(backup / "source"), "created_at": now()}
            receipt["approval_sha256"] = digest(receipt)
            write_json(backup / "backup.json", receipt)
            self.replace_source(source, candidate / "plugin")
            require(tree_digest(source) == receipt["after_sha256"], "Post-apply source verification failed; preserve backup")
            write_json(applied_record, {"snapshot": report["snapshot"], "export_sha256": report["export_sha256"], "candidate_seal": seal["sha256"], "backup": str(backup.relative_to(self.state)), "source_sha256": receipt["after_sha256"]})
            return dict(result, backup=str(backup), rollback_approval_sha256=receipt["approval_sha256"])

    def rollback(self, backup, approved=None, execute=False):
        backup = Path(backup).resolve()
        require(backup.parent == (self.state / "backups").resolve(), "Backup must be in this maintenance state")
        with self.lock():
            receipt = read_json(backup / "backup.json")
            approval = receipt.pop("approval_sha256")
            require(digest(receipt) == approval, "Backup receipt changed")
            source = self.source(receipt["channel"])
            require(str(source) == receipt["target_source"], "Rollback target mismatch")
            require(inventory(backup / "source") == receipt["backup_inventory"], "Backup content changed")
            current = tree_digest(source)
            if current == receipt["before_sha256"]:
                return {"already_rolled_back": True, "source": str(source)}
            require(current == receipt["after_sha256"], "Source changed after apply; refusing to overwrite local edits")
            if not execute:
                return {"dry_run": True, "source": str(source), "approval_sha256": approval}
            require(approved == approval, "Explicit approval of this rollback receipt sha256 is required")
            copy_tree(source, backup / "replaced-on-rollback")
            self.replace_source(source, backup / "source")
            record = self.state / ("applied-" + receipt["channel"] + ".json")
            if receipt["previous_applied"] is None:
                if record.exists():
                    record.unlink()
            else:
                write_json(record, receipt["previous_applied"])
            write_json(backup / "rollback.json", {"at": now(), "source_sha256": tree_digest(source), "cache_changed": False})
            return {"rolled_back": True, "source": str(source), "cache_changed": False}

    def selection(self, channel):
        if channel in {"preview", "both"}:
            source = self.source("preview")
            require(source.is_dir() and skills(source / "skills"), "Preview has no approved beta/RC content yet")
            provenance = read_json(source / "source-snapshot.json")
            require(provenance.get("channel") == "preview" and provenance.get("xcode", {}).get("channel") == "preview", "Preview source lacks verified channel provenance")
            if channel == "both":
                require(self.channel("preview").get("skill_name_suffix") == "-preview", "Coexistence requires explicit Preview names")
                normal = {name.casefold() for name in skills(self.source("stable") / "skills")}
                preview = {name.casefold() for name in skills(source / "skills")}
                require(not normal.intersection(preview) and all(name.endswith("-preview") for name in preview),
                        "Stable and Preview skill names collide")
        lines = []
        for name in ["stable", "preview"]:
            identity = self.channel(name)["plugin_id"] + "@" + self.config["marketplace"]
            lines += ['[plugins."' + identity + '"]', "enabled = " + ("true" if channel in {name, "both"} else "false"), ""]
        return "\n".join(lines)


def with_claude_links(result, execute):
    """After a real apply/rollback, link skills that are new to ~/.claude/skills. Additive; never fails the command."""
    if not execute or result.get("dry_run"):
        return result
    try:
        import link_claude_skills
        return dict(result, claude_links=link_claude_skills.sync())
    except Exception as error:  # the source update already succeeded; linking is best-effort
        return dict(result, claude_links={"error": str(error)})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(Path(__file__).with_name("maintain.json")))
    subs = parser.add_subparsers(dest="command", required=True)
    check = subs.add_parser("check", help="Read-only inventory; suitable for a future recurring check")
    check.add_argument("--app", action="append")
    prepare = subs.add_parser("prepare", help="Official export and three-way candidate; never applies")
    prepare.add_argument("--app", required=True)
    prepare.add_argument("--channel", choices=["stable", "preview"], required=True)
    validate = subs.add_parser("validate")
    validate.add_argument("plugin")
    resolve = subs.add_parser("resolve", help="Resolve a reviewed decision and generate a new approval digest")
    resolve.add_argument("candidate")
    resolve.add_argument("--decision", required=True)
    resolve.add_argument("--choice", choices=["keep-local", "take-upstream"], required=True)
    for name in ["apply", "rollback"]:
        command = subs.add_parser(name, help="Dry-run unless --execute and exact approval digest are supplied")
        command.add_argument("path")
        command.add_argument("--approve-sha256")
        command.add_argument("--execute", action="store_true")
    selection = subs.add_parser("selection", help="Print channel selection; both requires distinct Preview names; writes nothing")
    selection.add_argument("--channel", choices=["stable", "preview", "both"], required=True)
    refresh = subs.add_parser("refresh-releases", help="Fetch exact release records from Apple over HTTPS")
    refresh.add_argument("--execute", action="store_true", help="Save verified official-page records; otherwise print only")
    args = parser.parse_args(argv)
    manager = Manager(args.config)
    if args.command == "check":
        result = manager.check(args.app)
    elif args.command == "prepare":
        result = manager.prepare(args.app, args.channel)
    elif args.command == "validate":
        plugin_id = read_json(Path(args.plugin) / ".codex-plugin/plugin.json").get("name")
        cfg = next((cfg for cfg in manager.config["channels"].values() if cfg["plugin_id"] == plugin_id), {})
        result = validate_plugin(args.plugin, excluded=manager.config["excluded_skills"], skill_suffix=cfg.get("skill_name_suffix", ""))
    elif args.command == "resolve":
        result = manager.resolve(args.candidate, args.decision, args.choice)
    elif args.command == "apply":
        result = manager.apply(args.path, args.approve_sha256, args.execute)
        result = with_claude_links(result, args.execute)
    elif args.command == "rollback":
        result = manager.rollback(args.path, args.approve_sha256, args.execute)
        result = with_claude_links(result, args.execute)
    elif args.command == "selection":
        print(manager.selection(args.channel))
        return 0
    else:
        result = fetch_release_evidence()
        if args.execute:
            # Preserve historical exact records if the rolling page no longer lists them.
            records = {(r["version"], r["build"], r["channel"]): r for r in manager.evidence["releases"]}
            for record in result["releases"]:
                key = (record["version"], record["build"], record["channel"])
                records[key] = dict(records.get(key, {}), **record)
            result["releases"] = list(records.values())
            with manager.lock():
                write_json(manager.evidence_path, result)
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 2 if args.command == "validate" and not result["valid"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (MaintenanceError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error), "outcome": "Failed. For apply/rollback, inspect source and backup receipts before retrying; no automatic retry."}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
