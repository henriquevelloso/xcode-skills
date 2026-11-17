#!/usr/bin/env python3
"""Owner-authorized local Xcode export, review and automatic publication.

Python 3.9+, standard library only. All mutating subcommands require --execute.
Private exports, review receipts, event deduplication and backups stay in .local.
The Codex scheduled agent performs semantic review; this tool never calls a model.
"""
import argparse
import contextlib
import datetime
import difflib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("xcode_legacy", ROOT / "tools/legacy/maintain.py")
legacy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legacy)
REPOSITORY = "henriquevelloso/xcode-skills"
OWNER = "henriquevelloso"
CHANNELS = {"stable": "xcode-apple-skills", "preview": "xcode-apple-skills-preview"}
EXCLUDED = {"adopt-c-bounds-safety", "device-interaction"}
SOURCE = "https://developer.apple.com/news/releases/"
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".json"}


class UpdateError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise UpdateError(message)


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    fd, name = tempfile.mkstemp(prefix=".write-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
        os.chmod(name, 0o600 if ".local" in path.parts else 0o644)
        os.replace(name, str(path))
    finally:
        if os.path.exists(name):
            os.unlink(name)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def hash_value(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def command(args, cwd=None, timeout=120, env=None):
    result = subprocess.run([str(a) for a in args], cwd=str(cwd or ROOT), env=env,
                            text=True, capture_output=True, timeout=timeout)
    require(result.returncode == 0, "Command failed (%s): %s" % (args[0], result.stderr.strip() or result.stdout.strip()))
    return result.stdout.strip()


def version_tuple(version):
    require(bool(re.fullmatch(r"\d+(?:\.\d+){0,2}", version)), "Invalid Xcode version")
    values = tuple(int(x) for x in version.split("."))
    return values + (0,) * (3 - len(values))


def release_order(record):
    label = record["label"].lower()
    stage = 2 if record["channel"] == "stable" else (1 if re.search(r"\brc\b|release candidate", label) else 0)
    match = re.search(r"(?:beta|rc|release candidate)\s*(\d+)", label)
    return version_tuple(record["version"]), stage, int(match.group(1)) if match else 1, record.get("released_at", "")


def parse_releases(data):
    parser = legacy.ReleaseText()
    parser.feed(data.decode("utf-8"))
    text = " ".join(parser.text)
    pattern = r"\bXcode\s+(\d+(?:\.\d+)*)(\s+(?:beta|RC|Release Candidate)(?:\s+\d+)?)?\s*\(([A-Za-z0-9]+)\)"
    records = []
    for match in re.finditer(pattern, text, re.I):
        version, suffix, build = match.groups()
        item = {"version": version, "build": build, "channel": "preview" if suffix else "stable", "label": match.group(0)}
        date_match = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", text[match.end():match.end() + 150])
        if date_match:
            try:
                item["released_at"] = datetime.datetime.strptime(date_match.group(1), "%B %d, %Y").date().isoformat()
            except ValueError:
                pass
        if not any((x["version"], x["build"], x["channel"]) == (version, build, item["channel"]) for x in records):
            records.append(item)
    require(bool(records), "Official release page contains no exact Xcode version/build records")
    return records


def fetch_releases(previous):
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "Xcode-Skills-Maintenance/1"})
    with urllib.request.urlopen(req, timeout=25) as response:
        require(response.url.split("?", 1)[0].rstrip("/") == SOURCE.rstrip("/"), "Unexpected official release redirect")
        data = response.read(2 * 1024 * 1024 + 1)
    require(len(data) <= 2 * 1024 * 1024, "Release page exceeds size limit")
    fresh = parse_releases(data)
    # Preserve authoritative historical evidence after entries leave the current page.
    merged = {(r["version"], r["build"], r["channel"]): r for r in previous.get("releases", [])}
    merged.update({(r["version"], r["build"], r["channel"]): r for r in fresh})
    return {"schema_version": 1, "source": SOURCE, "checked_at": now(),
            "page_sha256": hashlib.sha256(data).hexdigest(), "releases": list(merged.values())}


def latest_releases(evidence):
    stable = max((r for r in evidence["releases"] if r["channel"] == "stable"), key=release_order, default=None)
    require(stable is not None, "No verified stable Xcode release")
    previews = [r for r in evidence["releases"] if r["channel"] == "preview" and version_tuple(r["version"]) > version_tuple(stable["version"])]
    return {"stable": stable, "preview": max(previews, key=release_order, default=None)}


def next_version(current, stable_xcode):
    major, minor, revision = (int(x) for x in current.split("."))
    target = version_tuple(stable_xcode)[:2]
    require(target >= (major, minor), "Refusing a package/Xcode downgrade")
    return "%d.%d.%d" % (target + (0 if target > (major, minor) else revision + 1,))


def logical_files(plugin, channel):
    result = {}
    for rel, path in legacy.safe_files(Path(plugin) / "skills").items():
        parts = Path(rel).parts
        name = parts[0]
        if channel == "preview":
            require(name.endswith("-preview"), "Preview skill lacks suffix")
            name = name[:-8]
        result[Path(name, *parts[1:]).as_posix()] = path
    return result


def target_relative(logical, channel):
    parts = Path(logical).parts
    return Path(parts[0] + ("-preview" if channel == "preview" else ""), *parts[1:])


def file_hashes(root):
    return {rel: hashlib.sha256(path.read_bytes()).hexdigest() for rel, path in legacy.safe_files(root).items()}


def skill_changes(before, after):
    a, b = {}, {}
    for store, root in [(a, before), (b, after)]:
        for name in legacy.skills(Path(root) / "skills"):
            store[name] = legacy.tree_digest(Path(root) / "skills" / name)
    return {"added": sorted(set(b) - set(a)), "removed": sorted(set(a) - set(b)),
            "updated": sorted(k for k in set(a) & set(b) if a[k] != b[k]),
            "unchanged": sorted(k for k in set(a) & set(b) if a[k] == b[k]), "notes": []}


def package_module(root):
    spec = importlib.util.spec_from_file_location("xcode_package", Path(root) / "tools/package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Updater:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.private = self.root / ".local"
        self.config_path = self.private / "config.json"

    def config(self):
        require(self.config_path.is_file(), "Run configure --legacy-root PATH --execute on the export Mac first")
        cfg = read(self.config_path)
        require(cfg.get("repository") == REPOSITORY and cfg.get("owner") == OWNER, "Repository authorization mismatch")
        require(cfg.get("automatic_publication") is True, "Automatic publication is not configured")
        return cfg

    @contextlib.contextmanager
    def lock(self):
        self.private.mkdir(parents=True, exist_ok=True)
        with (self.private / "updater.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise UpdateError("Another updater is running")
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def configure(self, legacy_root, execute=False):
        old = Path(legacy_root).expanduser().resolve()
        require((old / "maintain.json").is_file(), "Legacy maintainer not found")
        manager = legacy.Manager(old / "maintain.json")
        baselines, mirrors, fingerprints = {}, {}, {}
        for channel in CHANNELS:
            record = read(old / ".state" / ("applied-" + channel + ".json"))
            baseline = old / ".state" / record["snapshot"] / "export"
            require(legacy.tree_digest(baseline) == record["export_sha256"], "Legacy baseline integrity failure")
            source = manager.source(channel)
            snapshot = read(source / "source-snapshot.json")
            baselines[channel] = {"root": str(baseline), "sha256": record["export_sha256"]}
            mirrors[channel] = {"path": str(source), "sha256": legacy.tree_digest(source)}
            fingerprints[channel] = snapshot["xcode"].get("fingerprint")
        cfg = {"schema_version": 1, "repository": REPOSITORY, "owner": OWNER,
               "automatic_publication": True, "authorized_at": now(), "authorization": "Owner explicitly requested implementation of automatic public updates; no per-release approval.",
               "legacy_root": str(old), "app_roots": ["/Applications", "~/Applications"]}
        result = {"configured": execute, "repository": REPOSITORY, "private_state": str(self.private), "channels": list(CHANNELS)}
        if execute:
            require(not self.config_path.exists(), "Configuration already exists; preserve it")
            write(self.config_path, cfg)
            write(self.private / "baselines.json", baselines)
            write(self.private / "mirrors.json", mirrors)
            write(self.private / "fingerprints.json", fingerprints)
            write(self.private / "release-evidence.json", manager.evidence)
        return result

    def manager(self, evidence):
        cfg = self.config()
        manager = legacy.Manager(Path(cfg["legacy_root"]) / "maintain.json")
        manager.evidence = evidence
        manager.state = self.private / "exports"
        manager.config["app_roots"] = cfg["app_roots"]
        return manager

    def events(self, items, execute):
        file = self.private / "events.json"
        history = read(file) if file.exists() else {}
        fresh = [item for item in items if item["key"] not in history]
        if execute:
            for item in fresh:
                history[item["key"]] = dict(item, at=now())
            write(file, history)
        return fresh

    def check(self, execute=False):
        self.config()
        previous = read(self.private / "release-evidence.json")
        try:
            evidence = fetch_releases(previous)
        except Exception as error:
            return {"status": "network_error", "error": str(error), "events": self.events([{"key": "release_fetch_failed:" + type(error).__name__, "type": "failure", "message": "Could not refresh Apple's official Xcode releases; no publication attempted."}], execute)}
        if execute:
            write(self.private / "release-evidence.json", evidence)
        manager = self.manager(evidence)
        bundles, invalid = manager.discover()
        latest = latest_releases(evidence)
        release = read(self.root / "release.json")
        fingerprints = read(self.private / "fingerprints.json")
        events, pending = [], []
        for channel, desired in latest.items():
            if desired is None:
                continue
            matches = [b for b in bundles if b["channel"] == channel and b["version"] == desired["version"] and b["build"] == desired["build"]]
            if not matches:
                current = [{"version": b["version"], "build": b["build"]} for b in bundles if b["channel"] == channel]
                events.append({"key": "download:" + channel + ":" + desired["build"], "type": "download_required", "channel": channel, "available": desired, "installed": current, "download_url": "https://developer.apple.com/download/all/?q=Xcode"})
            published = release["channels"][channel]["xcode"]
            published_facts = [r for r in evidence["releases"] if r["channel"] == channel and r["version"] == published["version"] and r["build"] == published["build"]]
            published_order = release_order(published_facts[0] if published_facts else dict(published, label=published.get("label", "")))
            available = [b for b in bundles if b["channel"] == channel and not b.get("duplicate_of")]
            if available:
                def rank(bundle):
                    return release_order(bundle["channel_evidence"]["record"])
                selected = max(available, key=rank)
                if rank(selected) >= published_order and (selected["build"] != published["build"] or selected["fingerprint"] != fingerprints.get(channel)):
                    pending.append({"channel": channel, "bundle": selected})
        if invalid:
            events.append({"key": "invalid_bundles:" + hash_value(invalid), "type": "failure", "message": "Some Xcode bundles could not be verified", "bundles": invalid})
        return {"status": "updates_available" if pending else "current", "checked_at": evidence["checked_at"],
                "latest": latest, "installed": bundles, "pending": pending, "events": self.events(events, execute),
                "invalid_bundles": invalid, "publication": read(self.private / "publication.json") if (self.private / "publication.json").exists() else None}

    def candidate(self, path):
        candidate = Path(path).expanduser().resolve()
        require(self.private / "candidates" in candidate.parents, "Candidate is outside private staging")
        report = read(candidate / "review.json")
        require(report["channel"] in CHANNELS, "Invalid candidate channel")
        return candidate, report

    def normalize(self, candidate, channel):
        if channel != "preview":
            return
        provenance = candidate / "plugin/source-snapshot.json"
        write(provenance, {"skill_name_suffix": "-preview"})
        legacy.normalize_preview_names(candidate / "plugin", "-preview")
        # This staging-only alias receipt is not part of the distributable payload.
        provenance.unlink()

    def build_candidate(self, bundle, snapshot, snapshot_record):
        channel = bundle["channel"]
        baseline = read(self.private / "baselines.json")[channel]
        base_root = Path(baseline["root"])
        require(legacy.tree_digest(base_root) == baseline["sha256"], "Upstream baseline has changed")
        source = self.root / "plugins" / CHANNELS[channel]
        identity = hash_value({"fingerprint": bundle["fingerprint"], "source": legacy.tree_digest(source), "baseline": baseline["sha256"]})[:16]
        candidate = self.private / "candidates" / (channel + "-" + identity)
        if candidate.exists():
            return {"candidate": str(candidate), "review": read(candidate / "review.json"), "reused": True}
        candidate.mkdir(parents=True)
        shutil.copytree(source, candidate / "plugin")
        base, local, upstream = legacy.safe_files(base_root), logical_files(source, channel), legacy.safe_files(Path(snapshot) / "export")
        upstream_skills = set(legacy.skills(Path(snapshot) / "export")) - EXCLUDED
        current_skills = {rel.split("/", 1)[0] for rel in local if rel.endswith("/SKILL.md")}
        blocked, decisions, comparisons, patches = {}, [], [], []
        for rel, path in upstream.items():
            skill = rel.split("/", 1)[0]
            if skill not in upstream_skills:
                continue
            data = path.read_bytes()
            if Path(rel).suffix.lower() not in TEXT_SUFFIXES or data.startswith(b"#!"):
                if rel not in local or local[rel].read_bytes() != data:
                    blocked[skill] = "New or changed executable/binary requires a separate tooling change"
        for name in sorted(upstream_skills - current_skills - set(blocked)):
            decisions.append({"id": "new-skill:" + name, "kind": "new_skill", "skill": name, "resolved": False})
        for rel in sorted(set(base) | set(local) | set(upstream)):
            skill = rel.split("/", 1)[0]
            if skill in EXCLUDED or skill not in current_skills | upstream_skills:
                continue
            if skill in blocked:
                continue
            old = base[rel].read_bytes() if rel in base else None
            mine = local[rel].read_bytes() if rel in local else None
            new = upstream[rel].read_bytes() if rel in upstream else None
            if skill not in current_skills:
                result, action, conflict = new, "new_skill", False
            else:
                result, action, conflict = legacy.merge_file(rel, old, mine, new)
            dest = candidate / "plugin/skills" / target_relative(rel, channel)
            if result is not None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(mine if conflict and mine is not None else result)
                dest.chmod(0o644)
            if conflict:
                decisions.append({"id": "file:" + rel, "kind": "file", "path": rel, "reason": action, "resolved": False})
            comparisons.append({"path": rel, "action": action, "base": legacy.sha(old), "local": legacy.sha(mine), "upstream": legacy.sha(new)})
            if old != new:
                try:
                    patches.extend(difflib.unified_diff((old or b"").decode().splitlines(True), (new or b"").decode().splitlines(True), fromfile="previous-upstream/" + rel, tofile="new-upstream/" + rel))
                except UnicodeError:
                    pass
        self.normalize(candidate, channel)
        report = {"schema_version": 1, "channel": channel, "created_at": now(), "base_release_sha256": hash_value(read(self.root / "release.json")),
                  "source_sha256": legacy.tree_digest(source), "upstream_baseline": baseline, "snapshot": str(snapshot),
                  "export_sha256": snapshot_record["export_sha256"], "xcode": bundle, "comparisons": comparisons,
                  "decisions": decisions, "withheld_skills": blocked, "reviewed": False}
        report["candidate_sha256"] = legacy.tree_digest(candidate / "plugin")
        write(candidate / "review.json", report)
        (candidate / "upstream.diff").write_text("".join(patches))
        return {"candidate": str(candidate), "review": report, "reused": False}

    def prepare(self, execute=False):
        check = self.check(execute)
        if not execute or check["status"] == "network_error":
            return check
        publication = check.get("publication")
        if publication and publication.get("status") not in {"complete", "closed"}:
            return {"status": "publication_pending", "publication": publication, "events": check["events"],
                    "next_command": "resume --execute"}
        results, failures = [], []
        with self.lock():
            manager = self.manager(read(self.private / "release-evidence.json"))
            for item in check["pending"]:
                try:
                    bundle = item["bundle"]
                    command(["/usr/bin/codesign", "--verify", "--strict", bundle["path"]], timeout=90)
                    snapshot, record = manager.snapshot(bundle)
                    results.append(self.build_candidate(bundle, snapshot, record))
                except Exception as error:
                    failures.append({"channel": item["channel"], "error": str(error)})
        return {"status": "review_required" if results else check["status"], "candidates": results, "failures": failures, "events": check["events"]}

    def resolve(self, path, decision_id, choice, note, execute=False):
        candidate, report = self.candidate(path)
        choices = [x for x in report["decisions"] if x["id"] == decision_id]
        require(len(choices) == 1, "Unknown decision")
        require(bool(note.strip()), "Record an automated review rationale")
        decision = choices[0]
        if execute:
            if not decision.get("resolved") and choice == "take-upstream" and decision["kind"] == "file":
                source = Path(report["snapshot"]) / "export" / decision["path"]
                require(source.is_file() and source.suffix in TEXT_SUFFIXES, "Upstream selection is not a supported text file")
                dest = candidate / "plugin/skills" / target_relative(decision["path"], report["channel"])
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(source.read_bytes())
            elif not decision.get("resolved") and choice == "keep-local" and decision["kind"] == "new_skill":
                # Preserve the withheld new skill privately, do not delete it.
                name = decision["skill"] + ("-preview" if report["channel"] == "preview" else "")
                source = candidate / "plugin/skills" / name
                if source.exists():
                    (candidate / "withheld").mkdir(exist_ok=True)
                    source.rename(candidate / "withheld" / name)
                report["withheld_skills"][decision["skill"]] = note
            decision.update(resolved=True, choice=choice, review_note=note, reviewed_at=now())
            report["reviewed"] = False
            self.normalize(candidate, report["channel"])
            report["candidate_sha256"] = legacy.tree_digest(candidate / "plugin")
            write(candidate / "review.json", report)
        return {"dry_run": not execute, "decision": decision}

    def review(self, path, note, execute=False):
        candidate, report = self.candidate(path)
        require(bool(note.strip()), "Record a semantic review rationale")
        require(all(d.get("resolved") for d in report["decisions"]), "Resolve candidate decisions before review")
        require(legacy.tree_digest(Path(report["snapshot"]) / "export") == report["export_sha256"], "Export changed during review")
        # Use a complete disposable project for the same validator used by CI.
        with tempfile.TemporaryDirectory(prefix="xcode-review-") as temp:
            sandbox = Path(temp)
            for name in ["plugins", "tools"]:
                shutil.copytree(self.root / name, sandbox / name, ignore=shutil.ignore_patterns("__pycache__"))
            for name in ["release.json", "package-policy.json", "README.md", "README.pt-BR.md", "LICENSE", "THIRD_PARTY_NOTICES.md"]:
                if (self.root / name).exists():
                    shutil.copy2(self.root / name, sandbox / name)
            replacement = sandbox / "plugins" / CHANNELS[report["channel"]]
            shutil.rmtree(replacement)
            shutil.copytree(candidate / "plugin", replacement)
            metadata = read(sandbox / "release.json")
            metadata["channels"][report["channel"]]["xcode"] = public_xcode(report["xcode"])
            metadata["channels"][report["channel"]]["export_sha256"] = report["export_sha256"]
            metadata["version"] = next_version(metadata["version"], metadata["channels"]["stable"]["xcode"]["version"])
            write(sandbox / "release.json", metadata)
            pack = package_module(self.root)
            pack.generate(sandbox)
            validated = pack.validate(sandbox)
            require(validated["valid"], "Candidate package validation: " + "; ".join(validated["errors"]))
        result = {"candidate": str(candidate), "dry_run": not execute, "validation": validated}
        if execute:
            report.update(reviewed=True, review_note=note, reviewed_at=now(), review_kind="automated_agent", candidate_sha256=legacy.tree_digest(candidate / "plugin"))
            write(candidate / "review.json", report)
        return result

    def stage(self, execute=False):
        self.config()
        metadata = read(self.root / "release.json")
        reports = []
        for file in sorted((self.private / "candidates").glob("*/review.json")):
            report = read(file)
            if report.get("reviewed") and not report.get("staged") and report["base_release_sha256"] == hash_value(metadata):
                reports.append((file.parent, report))
        require(len({x[1]["channel"] for x in reports}) == len(reports), "Multiple reviewed candidates for one channel; select one")
        if not reports:
            return {"status": "no_reviewed_updates"}
        require(command(["git", "branch", "--show-current"], self.root) == "main", "Stage from main only")
        require(not command(["git", "status", "--porcelain"], self.root), "Commit or preserve local edits before staging an automated update")
        for candidate, report in reports:
            require(legacy.tree_digest(candidate / "plugin") == report["candidate_sha256"], "Candidate changed after automated review")
            require(legacy.tree_digest(self.root / "plugins" / CHANNELS[report["channel"]]) == report["source_sha256"], "Published adaptation changed during review")
            require(legacy.tree_digest(Path(report["snapshot"]) / "export") == report["export_sha256"], "Export changed after review")
        target = json.loads(json.dumps(metadata))
        target["changes"] = {}
        for channel, plugin in CHANNELS.items():
            source = self.root / "plugins" / plugin
            candidate = next((x for x in reports if x[1]["channel"] == channel), None)
            target["changes"][channel] = skill_changes(source, candidate[0] / "plugin" if candidate else source)
            if candidate:
                report = candidate[1]
                target["channels"][channel]["xcode"] = public_xcode(report["xcode"])
                target["channels"][channel]["export_sha256"] = report["export_sha256"]
                target["changes"][channel]["notes"].append("Verified a new Xcode source snapshot; unchanged skills remain listed explicitly.")
                for name, reason in report["withheld_skills"].items():
                    target["changes"][channel]["notes"].append("Withheld %s: %s" % (name, reason))
        target["version"] = next_version(metadata["version"], target["channels"]["stable"]["xcode"]["version"])
        result = {"status": "staged" if execute else "dry_run", "version": target["version"], "channels": [x[1]["channel"] for x in reports]}
        if execute:
            with self.lock(), tempfile.TemporaryDirectory(prefix="xcode-stage-") as temporary:
                sandbox = Path(temporary) / "project"
                shutil.copytree(self.root, sandbox, ignore=shutil.ignore_patterns(".git", ".local", "dist", "__pycache__"))
                for candidate, report in reports:
                    replacement = sandbox / "plugins" / CHANNELS[report["channel"]]
                    shutil.rmtree(replacement)
                    shutil.copytree(candidate / "plugin", replacement)
                write(sandbox / "release.json", target)
                pack = package_module(self.root)
                # Validate the complete new release before any tracked source is changed.
                pack.generate(sandbox)
                valid = pack.validate(sandbox)
                require(valid["valid"], "Staged project failed validation: " + "; ".join(valid["errors"]))
                receipt = {"version": target["version"], "candidates": [str(x[0]) for x in reports], "release_sha256": hash_value(target)}
                paths = ["plugins/" + plugin for plugin in CHANNELS.values()] + ["release.json", "VERSION", "README.md", "CHANGELOG.md", ".agents/plugins/marketplace.json", ".claude-plugin/marketplace.json", "releases/v" + target["version"] + ".md"]
                backup_root = self.private / "backups" / ("stage-" + target["version"] + "-" + hash_value(target)[:12])
                # A journal and preserved before-images support recovery without deleting backups.
                attempt = 1
                while backup_root.exists():
                    backup_root = backup_root.with_name(backup_root.name + "-retry" + str(attempt))
                    attempt += 1
                touched = []
                journal = dict(receipt, status="prepared", backup=str(backup_root), paths=paths)
                write(self.private / "stage-transaction.json", journal)
                try:
                    for rel in paths:
                        source, prepared, backup = self.root / rel, sandbox / rel, backup_root / rel
                        existed = source.exists()
                        touched.append((rel, existed))
                        if existed:
                            backup.parent.mkdir(parents=True, exist_ok=True)
                            source.rename(backup)
                        source.parent.mkdir(parents=True, exist_ok=True)
                        if prepared.is_dir():
                            shutil.copytree(prepared, source)
                        else:
                            shutil.copy2(prepared, source)
                    write(self.private / "staged.json", receipt)
                    journal["status"] = "completed"
                    write(self.private / "stage-transaction.json", journal)
                except Exception:
                    # Keep every partial result for diagnosis and restore the original checkout.
                    failed = backup_root / "failed-attempt"
                    for rel, existed in reversed(touched):
                        source, backup = self.root / rel, backup_root / rel
                        if source.exists():
                            destination = failed / rel
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            source.rename(destination)
                        if existed and backup.exists():
                            if backup.is_dir():
                                shutil.copytree(backup, source)
                            else:
                                shutil.copy2(backup, source)
                    journal["status"] = "rolled_back"
                    write(self.private / "stage-transaction.json", journal)
                    raise
                # The authoritative staging receipt was written only after every replacement.
                for candidate, report in reports:
                    report["staged"] = target["version"]
                    write(candidate / "review.json", report)
        return result

    def ensure_remote(self):
        self.config()
        require(command(["gh", "api", "user", "--jq", ".login"], self.root) == OWNER, "Wrong active GitHub account")
        url = command(["git", "remote", "get-url", "origin"], self.root)
        require(url in ["https://github.com/" + REPOSITORY + ".git", "https://github.com/" + REPOSITORY, "git@github.com:" + REPOSITORY + ".git"], "Unexpected Git remote")

    def publish(self, execute=False, _resume=False):
        self.ensure_remote()
        existing = self.private / "publication.json"
        if not _resume and existing.exists() and read(existing).get("status") not in {"complete", "closed"}:
            return self.resume(execute)
        release = read(self.root / "release.json")
        valid = package_module(self.root).validate(self.root)
        require(valid["valid"], "Package is invalid: " + "; ".join(valid["errors"]))
        version = release["version"]
        branch = "automation/update-" + version
        changed = command(["git", "diff", "--name-only", "HEAD"], self.root).splitlines()
        untracked = command(["git", "ls-files", "--others", "--exclude-standard"], self.root).splitlines()
        allowed = ("plugins/", "releases/", ".agents/plugins/", ".claude-plugin/")
        single = {"release.json", "VERSION", "CHANGELOG.md", "README.md", "README.pt-BR.md"}
        require(all(p in single or p.startswith(allowed) for p in changed + untracked), "Unexpected files changed; updater cannot publish tool/workflow/policy edits")
        result = {"dry_run": not execute, "branch": branch, "version": version}
        if not execute:
            return result
        with self.lock():
            # Persist intent before Git/network writes so interrupted pushes/PR creation resume.
            intent = dict(result, status="preparing", at=now())
            write(self.private / "publication.json", intent)
            current_branch = command(["git", "branch", "--show-current"], self.root)
            require(current_branch in {"main", branch}, "Another work branch is active")
            command(["git", "fetch", "origin", "main"], self.root)
            if current_branch == "main":
                require(command(["git", "rev-parse", "HEAD"], self.root) == command(["git", "rev-parse", "origin/main"], self.root), "Main moved; refresh and regenerate before publication")
                command(["git", "switch", "-c", branch], self.root)
            if changed or untracked:
                paths = sorted(set(changed + untracked))
                command(["git", "add", "--"] + paths, self.root)
                command(["git", "-c", "user.name=Henrique Velloso", "-c", "user.email=6364299+henriquevelloso@users.noreply.github.com", "commit", "-m", "Update Xcode skills package to " + version], self.root)
            head = command(["git", "rev-parse", "HEAD"], self.root)
            intent.update(commit=head, status="committed")
            write(self.private / "publication.json", intent)
            command(["git", "push", "-u", "origin", branch], self.root)
            prs = json.loads(command(["gh", "pr", "list", "--repo", REPOSITORY, "--head", branch, "--state", "open", "--json", "number,url"], self.root))
            if prs:
                url = prs[0]["url"]
            else:
                notes = self.root / "releases" / ("v" + version + ".md")
                body = notes.read_text() if notes.exists() else "Automatic verified Xcode instruction snapshot update."
                url = command(["gh", "pr", "create", "--repo", REPOSITORY, "--base", "main", "--head", branch, "--title", "Update Xcode skills package to " + version, "--body", body], self.root)
            intent.update(pr=url, status="awaiting_auto_merge")
            write(self.private / "publication.json", intent)
            command(["gh", "pr", "merge", "--repo", REPOSITORY, "--auto", "--squash", "--match-head-commit", head, url], self.root)
            result.update(pr=url, commit=head, status="auto_merge_requested", at=now())
            write(self.private / "publication.json", result)
        return result

    def resume(self, execute=False):
        """Resume a pending automatic PR, release and local mirror without a new version."""
        self.ensure_remote()
        path = self.private / "publication.json"
        if not path.exists():
            return {"status": "no_pending_publication"}
        state = read(path)
        if state.get("status") == "complete":
            return {"status": "complete", "version": state["version"], "pr": state["pr"]}
        if not state.get("pr"):
            require(read(self.root / "release.json")["version"] == state["version"], "Publication intent differs from checkout")
            return self.publish(execute, _resume=True)
        pr = json.loads(command(["gh", "pr", "view", state["pr"], "--repo", REPOSITORY, "--json", "state,headRefName,headRefOid,author,mergeCommit"], self.root))
        require(pr["author"]["login"] == OWNER and pr["headRefName"] == state["branch"], "Pending PR identity mismatch")
        require(pr["headRefOid"] == state["commit"], "Pending PR changed after publication request")
        if pr["state"] == "OPEN":
            if execute:
                # Safe retry also repairs interruption before auto-merge was enabled.
                command(["gh", "pr", "merge", "--repo", REPOSITORY, "--auto", "--squash", "--match-head-commit", state["commit"], state["pr"]], self.root)
            return {"status": "awaiting_ci_or_merge", "pr": state["pr"], "version": state["version"]}
        if pr["state"] == "CLOSED":
            return {"status": "closed_without_merge", "pr": state["pr"], "action_required": "The owner closed the automatic PR; it will not be reopened silently."}
        require(pr["state"] == "MERGED", "Unexpected PR state")
        if not execute:
            return {"status": "merged", "dry_run": True, "version": state["version"]}
        require(not command(["git", "status", "--porcelain"], self.root), "Preserve local changes before resuming a merged update")
        branch = command(["git", "branch", "--show-current"], self.root)
        require(branch in {"main", state["branch"]}, "Another work branch is active")
        command(["git", "fetch", "origin", "main"], self.root)
        if branch != "main":
            command(["git", "switch", "main"], self.root)
        command(["git", "merge", "--ff-only", "origin/main"], self.root)
        require(read(self.root / "release.json")["version"] == state["version"], "A later package advanced main; inspect publication receipt")
        process = subprocess.run(["gh", "release", "view", "v" + state["version"], "--repo", REPOSITORY, "--json", "isDraft"], cwd=str(self.root), text=True, capture_output=True)
        if process.returncode or json.loads(process.stdout).get("isDraft"):
            return {"status": "awaiting_release", "version": state["version"], "pr": state["pr"]}
        mirrored = self.mirror(True)
        state.update(status="complete", completed_at=now(), release=mirrored["release"])
        write(path, state)
        return {"status": "complete", "version": state["version"], "pr": state["pr"], "release": mirrored["release"]}

    def advance_baselines(self):
        staged = self.private / "staged.json"
        if not staged.exists():
            return
        data = read(staged)
        if data["version"] != read(self.root / "release.json")["version"]:
            return
        baselines = read(self.private / "baselines.json")
        fingerprints = read(self.private / "fingerprints.json")
        for path in data["candidates"]:
            _, report = self.candidate(path)
            baselines[report["channel"]] = {"root": str(Path(report["snapshot"]) / "export"), "sha256": report["export_sha256"]}
            fingerprints[report["channel"]] = report["xcode"]["fingerprint"]
        write(self.private / "baselines.json", baselines)
        write(self.private / "fingerprints.json", fingerprints)

    def mirror(self, execute=False):
        self.ensure_remote()
        version = read(self.root / "release.json")["version"]
        release = json.loads(command(["gh", "release", "view", "v" + version, "--repo", REPOSITORY, "--json", "isDraft,tagName,url"], self.root))
        require(not release["isDraft"] and release["tagName"] == "v" + version, "Release is not published")
        previous = self.private / "last-published.json"
        if previous.exists() and read(previous).get("version") == version:
            return {"dry_run": not execute, "version": version, "release": release["url"], "already_mirrored": True}
        # Only bytes from the immutable published tag may enter local mirrors.
        tag = "v" + version
        command(["git", "fetch", "origin", "tag", tag], self.root)
        for part in ["plugins", "release.json", "package-policy.json"]:
            require(not command(["git", "diff", tag, "--", part], self.root), "Local package differs from published tag")
        mirrors = read(self.private / "mirrors.json")
        for channel, record in mirrors.items():
            require(legacy.tree_digest(Path(record["path"])) == record["sha256"], "Local mirror was edited; preserve edits instead of overwriting")
        if execute:
            with self.lock():
                for channel, record in mirrors.items():
                    source = self.root / "plugins" / CHANNELS[channel]
                    target = Path(record["path"])
                    if legacy.tree_digest(source) == record["sha256"]:
                        continue
                    backup = self.private / "backups" / ("mirror-" + version) / channel
                    while backup.exists():
                        backup = backup.with_name(backup.name + "-retry")
                    backup.mkdir(parents=True)
                    prepared = backup / "prepared"
                    # Do all potentially failing copying before touching the live source.
                    shutil.copytree(source, prepared)
                    expected = legacy.tree_digest(source)
                    require(legacy.tree_digest(prepared) == expected, "Prepared mirror integrity failure")
                    shutil.copytree(target, backup / "source")
                    require(legacy.tree_digest(target) == record["sha256"], "Local edits appeared during mirror preparation")
                    previous_live = backup / "previous-live"
                    target.rename(previous_live)
                    try:
                        prepared.rename(target)
                        require(legacy.tree_digest(target) == expected, "Mirror swap integrity failure")
                    except Exception:
                        if target.exists():
                            target.rename(backup / "failed-replacement")
                        previous_live.rename(target)
                        raise
                    record["sha256"] = expected
                    write(self.private / "mirrors.json", mirrors)
                self.advance_baselines()
            for plugin in CHANNELS.values():
                command(["codex", "plugin", "add", plugin + "@personal", "--json"], self.root, timeout=180)
            write(self.private / "last-published.json", {"version": version, "release": release["url"], "at": now()})
        return {"dry_run": not execute, "version": version, "release": release["url"], "cache_edited_manually": False}


def public_xcode(bundle):
    fact = bundle.get("channel_evidence", {}).get("record") or bundle
    return {key: fact[key] for key in ["version", "build", "channel", "label"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ["configure", "check", "prepare", "resolve", "review", "stage", "publish", "mirror", "resume"]:
        sub = subs.add_parser(name)
        sub.add_argument("--execute", action="store_true")
        if name == "configure":
            sub.add_argument("--legacy-root", required=True)
        if name in {"resolve", "review"}:
            sub.add_argument("--candidate", required=True)
            sub.add_argument("--note", required=True)
        if name == "resolve":
            sub.add_argument("--decision", required=True)
            sub.add_argument("--choice", choices=["keep-local", "take-upstream"], required=True)
    args = parser.parse_args(argv)
    updater = Updater(args.root)
    if args.command == "configure":
        result = updater.configure(args.legacy_root, args.execute)
    elif args.command == "resolve":
        result = updater.resolve(args.candidate, args.decision, args.choice, args.note, args.execute)
    elif args.command == "review":
        result = updater.review(args.candidate, args.note, args.execute)
    else:
        result = getattr(updater, args.command)(args.execute)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (UpdateError, legacy.MaintenanceError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
