"""Trust-boundary and immutable-release tests; no network or live profiles."""
import base64
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / ".github/scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


publisher = load("publisher", "publish_release.py")
smoke = load("cli_smoke", "cli_smoke.py")


class FakeGitHub:
    def __init__(self):
        self.tag = None
        self.release = None
        self.assets = {}
        self.calls = []

    def get_tag(self, tag):
        return self.tag

    def create_tag(self, tag, commit):
        self.calls.append(("create_tag", tag, commit))
        self.tag = commit

    def get_release(self, tag):
        return copy.deepcopy(self.release)

    def create_release(self, tag, commit, body):
        self.calls.append(("create_release", tag))
        self.release = {"id": 1, "tag_name": tag, "draft": True, "prerelease": False,
                        "body": body, "html_url": "https://github.com/henriquevelloso/xcode-skills/releases/tag/" + tag}
        return copy.deepcopy(self.release)

    def list_assets(self, release_id):
        return [{"id": name, "name": name, "size": len(content)} for name, content in self.assets.items()]

    def asset_bytes(self, asset_id):
        return self.assets[asset_id]

    def upload(self, tag, path):
        if path.name in self.assets:
            raise AssertionError("Attempted to overwrite immutable asset")
        self.calls.append(("upload", path.name))
        self.assets[path.name] = path.read_bytes()

    def publish_draft(self, release_id):
        self.calls.append(("publish", release_id))
        self.release["draft"] = False


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dist = self.root / "dist"
        self.dist.mkdir()
        (self.root / "release.json").write_text(json.dumps({"repository": publisher.REPOSITORY, "version": "27.2.0"}))
        for name, data in {
            "xcode-apple-skills-27.2.0.zip": b"stable fixture",
            "xcode-apple-skills-preview-27.2.0.zip": b"preview fixture",
            "SHA256SUMS": b"checksums fixture\n",
            "provenance.json": b"{}\n",
            "RELEASE_NOTES.md": b"# Release fixture\n",
        }.items():
            (self.dist / name).write_bytes(data)
        self.checksums()
        self.client = FakeGitHub()
        self.sha = "a" * 40

    def checksums(self):
        files = sorted(p for p in self.dist.iterdir() if p.name != "SHA256SUMS")
        (self.dist / "SHA256SUMS").write_text("".join(hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n" for p in files))

    def publish(self, sha=None, compare=None):
        return publisher.publish(self.root, self.dist, publisher.REPOSITORY, sha or self.sha,
                                 client=self.client, compare=compare)

    def test_new_release_stays_draft_until_every_asset_passes_readback(self):
        result = self.publish()
        self.assertTrue(result["published"])
        self.assertFalse(result["idempotent"])
        self.assertEqual(len(self.client.assets), 5)
        self.assertEqual(self.client.calls[-1], ("publish", 1))

    def test_repeat_publication_never_rewrites_anything(self):
        self.publish()
        self.client.calls = []
        result = self.publish()
        self.assertTrue(result["idempotent"])
        self.assertEqual(self.client.calls, [])

    def test_incomplete_draft_resumes_only_missing_assets(self):
        self.client.tag = self.sha
        self.client.create_release("v27.2.0", self.sha, "# Release fixture\n")
        self.client.assets["provenance.json"] = b"{}\n"
        self.client.calls = []
        result = self.publish()
        self.assertEqual(len(result["uploaded"]), 4)
        self.assertNotIn(("upload", "provenance.json"), self.client.calls)
        self.assertFalse(self.client.release["draft"])

    def test_failed_upload_keeps_draft_for_retry(self):
        with mock.patch.object(self.client, "upload", side_effect=RuntimeError("fixture upload failed")):
            with self.assertRaisesRegex(RuntimeError, "upload failed"):
                self.publish()
        self.assertTrue(self.client.release["draft"])
        self.assertNotIn(("publish", 1), self.client.calls)
        self.publish()
        self.assertFalse(self.client.release["draft"])

    def test_changed_existing_asset_blocks_without_clobber(self):
        self.publish()
        original = self.client.assets["provenance.json"]
        (self.dist / "provenance.json").write_bytes(b'{"changed":true}\n')
        self.checksums()
        with self.assertRaisesRegex(RuntimeError, "different bytes"):
            self.publish()
        self.assertEqual(self.client.assets["provenance.json"], original)

    def test_changed_notes_are_not_rewritten(self):
        self.publish()
        (self.dist / "RELEASE_NOTES.md").write_text("Different notes\n")
        self.checksums()
        with self.assertRaisesRegex(RuntimeError, "notes differ"):
            self.publish()
        self.assertEqual(self.client.release["body"], "# Release fixture\n")

    def test_docs_only_commit_reuses_tag_without_new_release(self):
        self.publish()
        self.client.calls = []
        later = "b" * 40
        result = self.publish(later, compare=lambda old, new, version: old == self.sha and new == later)
        self.assertTrue(result["idempotent"])
        self.assertEqual(result["commit"], self.sha)
        self.assertEqual(self.client.calls, [])

    def test_changed_package_at_existing_version_requires_bump(self):
        self.publish()
        self.client.calls = []
        with self.assertRaisesRegex(RuntimeError, "bump the package revision"):
            self.publish("b" * 40, compare=lambda *args: False)
        self.assertEqual(self.client.calls, [])
        self.assertEqual(self.client.tag, self.sha)

    def test_unexpected_dist_and_release_assets_block(self):
        (self.dist / "private-backup.json").write_text("{}")
        with self.assertRaisesRegex(RuntimeError, "Unexpected files"):
            self.publish()
        self.assertIsNone(self.client.tag)
        (self.dist / "private-backup.json").unlink()
        self.publish()
        self.client.assets["unknown.zip"] = b"unknown"
        with self.assertRaisesRegex(RuntimeError, "Unexpected existing"):
            self.publish()

    def test_bad_checksum_manifest_blocks_before_creating_tag(self):
        (self.dist / "provenance.json").write_text('{"changed":true}\n')
        with self.assertRaisesRegex(RuntimeError, "checksum differs"):
            self.publish()
        self.assertIsNone(self.client.tag)

    def test_wrong_repository_and_nonexact_commit_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Wrong repository"):
            publisher.publish(self.root, self.dist, "someone/else", self.sha, client=self.client)
        with self.assertRaisesRegex(RuntimeError, "exact SHA"):
            self.publish("main")


class SandboxTests(unittest.TestCase):
    def test_cli_sandbox_never_inherits_provider_keys_or_github_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "fixture", "ANTHROPIC_API_KEY": "fixture", "GH_TOKEN": "fixture", "CODEX_HOME": "live"}):
                env = smoke.isolated_env(Path(temp))
            for secret in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GH_TOKEN", "GITHUB_TOKEN"):
                self.assertNotIn(secret, env)
            for key in ("HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR"):
                self.assertTrue(Path(env[key]).is_relative_to(Path(temp)))

    def test_cli_tarball_integrity_is_required(self):
        data = b"fixture"
        correct = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
        smoke.verify_archive(data, correct)
        with self.assertRaisesRegex(RuntimeError, "integrity mismatch"):
            smoke.verify_archive(b"modified", correct)

    def test_only_regular_locked_archive_member_is_extracted(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo("package/claude")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            archive.addfile(info)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, "regular binary"):
                smoke.extract_binary(buffer.getvalue(), "package/claude", Path(temp) / "claude")
            self.assertFalse((Path(temp) / "claude").exists())

    def test_action_sources_are_full_sha_pins_and_no_untrusted_secret_trigger(self):
        import re
        for workflow in (ROOT / ".github/workflows").glob("*.yml"):
            text = workflow.read_text()
            self.assertNotIn("pull_request_target", text)
            self.assertNotIn("self-hosted", text)
            self.assertNotIn("secrets.", text)
            for action in re.findall(r"uses:\s*(\S+)", text):
                self.assertRegex(action, r"^[A-Za-z0-9_./-]+@[0-9a-f]{40}$")
        text = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("github.event.workflow_run.event == 'push'", text)
        self.assertIn("github.event.workflow_run.head_repository.full_name == github.repository", text)
        self.assertIn("cancel-in-progress: false", text)


if __name__ == "__main__":
    unittest.main()
