#!/usr/bin/env python3
"""Validate real plugin installation with pinned, sandboxed native CLI builds.

Only explicitly locked npm registry tarball members are extracted. No npm
lifecycle script, model request, login, or existing user profile is used.
"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
MAX_ARCHIVE = 512 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def verify_archive(data, integrity):
    algorithm, encoded = integrity.split("-", 1)
    require(algorithm == "sha512", "CLI lock must use SHA-512")
    require(hashlib.sha512(data).digest() == base64.b64decode(encoded, validate=True),
            "CLI registry archive integrity mismatch")


def extract_binary(data, member, target):
    parts = Path(member).parts
    require(member.startswith("package/") and ".." not in parts,
            "Unsafe locked archive member")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        info = archive.getmember(member)
        require(info.isfile() and not info.issym() and not info.islnk(),
                "Locked CLI member must be a regular binary")
        require(0 < info.size <= MAX_ARCHIVE, "Invalid CLI binary size")
        source = archive.extractfile(info)
        require(source is not None, "CLI binary could not be read")
        content = source.read(MAX_ARCHIVE + 1)
        require(len(content) == info.size, "CLI binary extraction was incomplete")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o755)


def install_cli(spec, target):
    parsed = urllib.parse.urlsplit(spec["url"])
    require(parsed.scheme == "https" and parsed.netloc == "registry.npmjs.org"
            and not parsed.query and not parsed.fragment, "CLI URL is not the official npm registry")
    request = urllib.request.Request(spec["url"], headers={"User-Agent": "xcode-skills-ci/1"})
    data = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                final = urllib.parse.urlsplit(response.url)
                require(final.scheme == "https" and final.netloc == "registry.npmjs.org",
                        "CLI download redirected outside the official npm registry")
                chunks, size = [], 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    require(size <= MAX_ARCHIVE, "CLI archive exceeds size limit")
                    chunks.append(chunk)
                data = b"".join(chunks)
            break
        except (OSError, urllib.error.URLError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    require(data is not None, "CLI archive could not be downloaded")
    verify_archive(data, spec["integrity"])
    extract_binary(data, spec["member"], target)


def isolated_env(directory):
    # Do not forward provider keys, Git credentials, GitHub tokens or the live
    # shell's Codex/Claude settings. The PATH is for OS helpers such as git.
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "LANG", "LC_ALL", "SSL_CERT_FILE")
           if key in os.environ}
    env.update({
        "HOME": str(directory / "home"),
        "CODEX_HOME": str(directory / "codex"),
        "CLAUDE_CONFIG_DIR": str(directory / "claude"),
        "XDG_CONFIG_HOME": str(directory / "xdg"),
        "XDG_CACHE_HOME": str(directory / "cache"),
        "TMPDIR": str(directory / "tmp"),
        "CI": "true", "NO_COLOR": "1", "DISABLE_AUTOUPDATER": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1",
        "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
    })
    for key in ("HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "TMPDIR"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    return env


def run(command, env, cwd):
    result = subprocess.run([str(x) for x in command], cwd=str(cwd), env=env,
                            capture_output=True, text=True, timeout=150)
    require(result.returncode == 0,
            "%s failed (%s):\n%s\n%s" % (" ".join(str(x) for x in command), result.returncode,
                                         result.stdout[-9000:], result.stderr[-3000:]))
    return result.stdout


def skill_names(root):
    names = set()
    for entry in root.glob("skills/*/SKILL.md"):
        match = re.search(r"^name:\s*[\"']?([a-z0-9-]+)", entry.read_text(), re.M)
        require(match is not None, "Skill lacks a discoverable name")
        require(match.group(1) not in names, "Duplicate skill name")
        names.add(match.group(1))
    return names


def smoke(root, directory):
    lock = json.loads((root / ".github/cli-lock.json").read_text())
    machine = {"amd64": "x86_64", "aarch64": "arm64"}.get(platform.machine().lower(), platform.machine().lower())
    key = platform.system().lower() + "-" + machine
    require(key in lock["platforms"], "No reviewed CLI lock for " + key)
    binaries = {}
    for name in ("codex", "claude"):
        binaries[name] = directory / "bin" / name
        install_cli(lock["platforms"][key][name], binaries[name])
    return verify_plugins(root, directory, binaries, lock["versions"], key)


def verify_plugins(root, directory, binaries, expected_versions, platform_key):
    env = isolated_env(directory)
    codex, claude = binaries["codex"], binaries["claude"]
    versions = {name: run([binary, "--version"], env, directory).strip()
                for name, binary in binaries.items()}
    for name, expected in expected_versions.items():
        require(expected in versions[name], "Unexpected " + name + " binary version")
    identities = ("xcode-apple-skills", "xcode-apple-skills-preview")
    expected_skills = set()
    for identity in identities:
        current = skill_names(root / "plugins" / identity)
        require(not (expected_skills & current), "The two plugins collide on skill names")
        expected_skills.update(current)
    run([codex, "plugin", "marketplace", "add", root, "--json"], env, directory)
    catalog = run([codex, "plugin", "list", "--available", "--json"], env, directory)
    require(all(identity in catalog for identity in identities), "Codex did not discover both catalog entries")
    for identity in identities:
        run([codex, "plugin", "add", identity + "@xcode-skills", "--json"], env, directory)
    codex_cache = Path(env["CODEX_HOME"]) / "plugins/cache/xcode-skills"
    discovered = set()
    for entry in codex_cache.glob("*/*/skills/*/SKILL.md"):
        match = re.search(r"^name:\s*[\"']?([a-z0-9-]+)", entry.read_text(), re.M)
        if match:
            discovered.add(match.group(1))
    require(discovered == expected_skills, "Codex installed skill inventory differs from package inventory")
    run([claude, "plugin", "validate", root, "--strict"], env, directory)
    for identity in identities:
        run([claude, "plugin", "validate", root / "plugins" / identity, "--strict"], env, directory)
    run([claude, "plugin", "marketplace", "add", root], env, directory)
    for identity in identities:
        run([claude, "plugin", "install", identity + "@xcode-skills", "--scope", "user"], env, directory)
    installed = run([claude, "plugin", "list", "--json"], env, directory)
    require(all(identity + "@xcode-skills" in installed for identity in identities),
            "Claude Code did not install both plugins")
    for identity in identities:
        details = run([claude, "plugin", "details", identity + "@xcode-skills"], env, directory)
        require(identity in details, "Claude Code could not read installed plugin details")
    return {"valid": True, "platform": platform_key, "versions": versions,
            "plugins": list(identities), "skills": sorted(expected_skills),
            "profiles_isolated": True, "model_requests": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--sandbox", type=Path, help="New directory to retain isolated CLI smoke evidence")
    args = parser.parse_args()
    if args.sandbox:
        require(not args.sandbox.exists(), "Retained smoke sandbox must be new")
        args.sandbox.mkdir(parents=True)
        result = smoke(args.root.resolve(), args.sandbox.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="xcode-skills-cli-") as temp:
            result = smoke(args.root.resolve(), Path(temp))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
