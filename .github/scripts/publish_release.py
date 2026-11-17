#!/usr/bin/env python3
"""Publish immutable, validated package assets, resuming incomplete drafts.

GITHUB_TOKEN/gh are used only by the trusted main-branch release workflow.
No existing tag, asset, release body or published package is overwritten.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.parse


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "henriquevelloso/xcode-skills"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GitHub:
    def __init__(self, repository):
        require(repository == REPOSITORY, "Publication repository is not owner-authorized")
        self.repository = repository
        self.base = "repos/" + repository

    def api(self, endpoint, method="GET", body=None, optional=False, binary=False):
        command = ["gh", "api", "--method", method, endpoint,
                   "-H", "X-GitHub-Api-Version: 2022-11-28"]
        if binary:
            command += ["-H", "Accept: application/octet-stream"]
        else:
            command += ["-H", "Accept: application/vnd.github+json"]
        if body is not None:
            command += ["--input", "-"]
        result = subprocess.run(command, input=json.dumps(body).encode() if body is not None else None,
                                capture_output=True, timeout=120)
        if result.returncode:
            if optional and re.search(rb"HTTP 404", result.stderr):
                return None
            raise RuntimeError("GitHub API request failed: %s %s (exit %s)" %
                               (method, endpoint, result.returncode))
        return result.stdout if binary else (json.loads(result.stdout) if result.stdout else None)

    def get_tag(self, tag):
        result = self.api(self.base + "/git/ref/tags/" + urllib.parse.quote(tag, safe=""), optional=True)
        if result is None:
            return None
        obj = result["object"]
        for _ in range(5):
            if obj["type"] == "commit":
                return obj["sha"]
            require(obj["type"] == "tag", "Existing tag does not resolve to a commit")
            obj = self.api(self.base + "/git/tags/" + obj["sha"])["object"]
        raise RuntimeError("Existing annotated tag chain is too deep")

    def create_tag(self, tag, commit):
        self.api(self.base + "/git/refs", method="POST", body={"ref": "refs/tags/" + tag, "sha": commit})
        require(self.get_tag(tag) == commit, "Published tag failed read-back verification")

    def get_release(self, tag):
        return self.api(self.base + "/releases/tags/" + urllib.parse.quote(tag, safe=""), optional=True)

    def create_release(self, tag, commit, body):
        return self.api(self.base + "/releases", method="POST", body={
            "tag_name": tag, "target_commitish": commit, "name": "Xcode Skills " + tag,
            "body": body, "draft": True, "prerelease": False,
        })

    def list_assets(self, release_id):
        results = []
        page = 1
        while True:
            batch = self.api(self.base + "/releases/%s/assets?per_page=100&page=%s" % (release_id, page))
            results.extend(batch)
            if len(batch) < 100:
                return results
            page += 1

    def asset_bytes(self, asset_id):
        return self.api(self.base + "/releases/assets/" + str(asset_id), binary=True)

    def upload(self, tag, path):
        result = subprocess.run(["gh", "release", "upload", tag, str(path), "--repo", self.repository],
                                capture_output=True, timeout=180)
        require(result.returncode == 0, "Asset upload failed without overwriting: " + path.name)

    def publish_draft(self, release_id):
        return self.api(self.base + "/releases/" + str(release_id), method="PATCH",
                        body={"draft": False, "prerelease": False, "make_latest": "legacy"})


def package_inputs_equal(root, previous, commit, version):
    # A later README/workflow-only commit may reuse an already published
    # version. Changes to inputs that can change an archive require a bump.
    paths = ["release.json", "VERSION", "package-policy.json", "plugins", "tools/package.py",
             "releases/v" + version + ".md"]
    result = subprocess.run(["git", "diff", "--quiet", previous, commit, "--"] + paths,
                            cwd=str(root), capture_output=True, timeout=30)
    require(result.returncode in (0, 1), "Could not compare the immutable package tag inputs")
    return result.returncode == 0


def expected_assets(dist, version):
    names = ["xcode-apple-skills-%s.zip" % version,
             "xcode-apple-skills-preview-%s.zip" % version,
             "SHA256SUMS", "provenance.json", "RELEASE_NOTES.md"]
    files = {}
    for name in names:
        path = dist / name
        require(path.is_file() and not path.is_symlink(), "Missing or unsafe release asset: " + name)
        require(path.stat().st_size > 0, "Empty release asset: " + name)
        files[name] = path
    actual = {p.name for p in dist.iterdir()}
    require(actual == set(files), "Unexpected files in release artifact directory")
    checksums = {}
    for line in files["SHA256SUMS"].read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        require(match is not None, "Malformed release checksum manifest")
        digest, name = match.groups()
        require(name not in checksums, "Duplicate release checksum entry")
        checksums[name] = digest
    require(set(checksums) == set(files) - {"SHA256SUMS"}, "Release checksum manifest inventory differs")
    for name, digest in checksums.items():
        require(file_hash(files[name]) == digest, "Release checksum differs: " + name)
    return files


def verify_assets(client, release_id, files, allow_missing):
    assets = client.list_assets(release_id)
    by_name = {}
    for asset in assets:
        require(asset["name"] not in by_name, "Duplicate existing release asset name")
        by_name[asset["name"]] = asset
    require(set(by_name).issubset(files), "Unexpected existing release assets; refusing to change them")
    for name, asset in by_name.items():
        content = client.asset_bytes(asset["id"])
        require(hashlib.sha256(content).hexdigest() == file_hash(files[name]),
                "Existing immutable asset has different bytes: " + name)
        require(len(content) == asset["size"] == files[name].stat().st_size,
                "Existing asset size differs: " + name)
    missing = sorted(set(files) - set(by_name))
    require(allow_missing or not missing, "Release is missing expected assets")
    return missing


def publish(root, dist, repository, commit, client=None, compare=None):
    require(repository == REPOSITORY, "Wrong repository for automatic publication")
    require(re.fullmatch(r"[a-f0-9]{40}", commit) is not None, "Release commit must be an exact SHA")
    metadata = json.loads((root / "release.json").read_text())
    version = metadata["version"]
    require(re.fullmatch(r"\d+\.\d+\.\d+", version) is not None, "Invalid shared package version")
    require(metadata["repository"] == repository, "Package repository differs from publication target")
    tag = "v" + version
    files = expected_assets(dist, version)
    notes = files["RELEASE_NOTES.md"].read_text()
    client = client or GitHub(repository)
    previous = client.get_tag(tag)
    if previous and previous != commit:
        equivalent = compare(previous, commit, version) if compare else package_inputs_equal(root, previous, commit, version)
        require(equivalent, "Version already tags different package inputs; bump the package revision")
    if not previous:
        client.create_tag(tag, commit)
        previous = commit
    release = client.get_release(tag)
    created = release is None
    if created:
        release = client.create_release(tag, previous, notes)
    require(release["tag_name"] == tag and release["prerelease"] is False,
            "Existing release metadata does not match the stable package release")
    require((release.get("body") or "").replace("\r\n", "\n") == notes.replace("\r\n", "\n"),
            "Existing release notes differ; never overwrite published release notes")
    missing = verify_assets(client, release["id"], files, allow_missing=True)
    for name in missing:
        client.upload(tag, files[name])
    verify_assets(client, release["id"], files, allow_missing=False)
    if release["draft"]:
        client.publish_draft(release["id"])
    current = client.get_release(tag)
    require(current is not None and current["draft"] is False and current["prerelease"] is False,
            "Release publication failed read-back verification")
    require(client.get_tag(tag) == previous, "Immutable tag changed during publication")
    return {"published": True, "version": version, "tag": tag, "commit": previous,
            "idempotent": not created and not missing, "uploaded": missing,
            "url": current.get("html_url", "https://github.com/" + repository + "/releases/tag/" + tag)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--dist", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    commit = os.environ.get("RELEASE_COMMIT", "")
    repository = os.environ.get("GH_REPO", "")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True,
                          text=True, check=True).stdout.strip()
    require(head == commit, "Checkout does not match the successful CI commit")
    result = publish(root, args.dist or root / "dist", repository, commit)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
