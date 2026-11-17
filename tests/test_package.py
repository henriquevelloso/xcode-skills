"""Behavioral regression tests for distributable instruction packages."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("xcode_package", ROOT / "tools/package.py")
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        for name in ("release.json", "package-policy.json", "README.md", "VERSION", "LICENSE", "THIRD_PARTY_NOTICES.md"):
            shutil.copy2(ROOT / name, self.root / name)
        for name in ("plugins", ".agents", ".claude-plugin", "releases"):
            shutil.copytree(ROOT / name, self.root / name)
        self.base_version = p.read_json(self.root / "release.json")["version"]
        self.stable = self.root / "plugins/xcode-apple-skills"
        self.preview = self.root / "plugins/xcode-apple-skills-preview"

    def errors(self):
        result = p.validate(self.root)
        self.assertFalse(result["valid"], result)
        return "\n".join(result["errors"])

    def update_release(self, **values):
        data = p.read_json(self.root / "release.json")
        data.update(values)
        (self.root / "release.json").write_text(p.json_text(data))

    def test_generated_package_has_shared_version_and_distinct_channels(self):
        p.generate(self.root)
        self.assertTrue(p.validate(self.root)["valid"])
        for folder in (self.stable, self.preview):
            a = p.read_json(folder / ".codex-plugin/plugin.json")
            b = p.read_json(folder / ".claude-plugin/plugin.json")
            self.assertEqual(a["version"], b["version"])
            self.assertEqual(a["version"], self.base_version)
        self.assertIn("Preview", p.read_json(self.preview / ".claude-plugin/plugin.json")["displayName"])
        self.assertTrue(all(name.endswith("-preview") for name in p.skill_names(self.preview)))

    def test_generate_is_idempotent_and_preserves_historical_notes(self):
        history = self.root / "releases/v26.0.0.md"
        history.write_text("Historical release evidence\n")
        p.generate(self.root)
        before = {name: file.read_bytes() for name, file in p.files(self.root).items()}
        p.generate(self.root)
        after = {name: file.read_bytes() for name, file in p.files(self.root).items()}
        self.assertEqual(before, after)
        self.assertEqual(history.read_text(), "Historical release evidence\n")

    def test_metadata_drift_rejected(self):
        path = self.preview / ".claude-plugin/plugin.json"
        data = p.read_json(path)
        data["version"] = "1.0.0"
        path.write_text(p.json_text(data))
        self.assertIn("metadata drift", self.errors())

    def test_stable_package_prefix_follows_published_source_not_preview(self):
        major, minor, _ = self.base_version.split(".")
        self.update_release(version="%s.%s.0" % (major, int(minor) + 1))
        self.assertIn("included stable Xcode", self.errors())

    def test_preview_only_revision_updates_both_plugin_versions(self):
        data = p.read_json(self.root / "release.json")
        major, minor, revision = self.base_version.split(".")
        next_version = "%s.%s.%s" % (major, minor, int(revision) + 1)
        data["version"] = next_version
        data["channels"]["preview"]["xcode"].update(build="27C5035i", label="Xcode 27.3 beta 2 (27C5035i)")
        data["changes"]["stable"] = {"added": [], "updated": [], "removed": [], "unchanged": p.skill_names(self.stable), "notes": ["Content unchanged."]}
        (self.root / "release.json").write_text(p.json_text(data))
        p.generate(self.root)
        self.assertTrue(p.validate(self.root)["valid"])
        self.assertEqual(p.read_json(self.stable / ".codex-plugin/plugin.json")["version"], next_version)
        self.assertIn("beta 2", p.read_json(self.preview / ".claude-plugin/plugin.json")["displayName"])
        self.assertIn("Content unchanged", (self.root / "releases" / ("v" + next_version + ".md")).read_text())

    def test_modified_reviewed_helper_is_rejected_without_execution(self):
        helper = self.stable / "skills/audit-xcode-security-settings/scripts/filter_build_settings.py"
        helper.write_text(helper.read_text() + "\nraise AssertionError('must not run')\n")
        p.generate(self.root)
        self.assertIn("Unreviewed executable bytes", self.errors())

    def test_new_executable_disguised_as_markdown_is_rejected(self):
        path = self.stable / "skills/swiftui-specialist/references/new.md"
        path.write_text("#!/bin/sh\nexit 99\n")
        p.generate(self.root)
        self.assertIn("Unreviewed executable bytes", self.errors())

    def test_symlink_is_rejected_even_when_target_is_inside_plugin(self):
        path = self.stable / "skills/swiftui-specialist/references/link.md"
        path.symlink_to("structure.md")
        self.assertIn("Symlink", self.errors())

    def test_broken_and_escaping_links_are_rejected(self):
        path = self.stable / "skills/swiftui-specialist/references/new.md"
        path.write_text("[Missing](missing.md)\n[Escape](../../../../release.json)\n")
        p.generate(self.root)
        errors = self.errors()
        self.assertIn("missing.md", errors)
        self.assertIn("release.json", errors)

    def test_private_path_and_credential_shapes_are_rejected(self):
        path = self.stable / "skills/swiftui-specialist/references/new.md"
        path.write_text("Local source: /" + "Users/fixture/project\n" + "ghp_" + "x" * 30 + "\n")
        p.generate(self.root)
        self.assertIn("Private path or credential-shaped", self.errors())

    def test_private_release_note_metadata_is_rejected_before_artifact_creation(self):
        data = p.read_json(self.root / "release.json")
        data["changes"]["stable"]["notes"] = ["Private diagnostics: /" + "Users/qa_fixture/private.swift"]
        (self.root / "release.json").write_text(p.json_text(data))
        self.assertIn("Private path", self.errors())
        with self.assertRaisesRegex(ValueError, "Private path"):
            p.generate(self.root)
        out = Path(self.temp.name) / "unsafe-release"
        with self.assertRaisesRegex(ValueError, "validation failed"):
            p.build(self.root, out)
        self.assertFalse(out.exists())

    def test_json_escaped_windows_profile_path_is_rejected(self):
        data = p.read_json(self.root / "release.json")
        data["changes"]["stable"]["notes"] = ["C:" + chr(92) + "Users" + chr(92) + "qa_fixture" + chr(92) + "private.swift"]
        (self.root / "release.json").write_text(p.json_text(data))
        self.assertIn("Private path", self.errors())
        with self.assertRaisesRegex(ValueError, "Private path"):
            p.generate(self.root)

    def test_credential_shape_in_release_metadata_is_rejected(self):
        data = p.read_json(self.root / "release.json")
        data["changes"]["preview"]["notes"] = ["ghp_" + "x" * 30]
        (self.root / "release.json").write_text(p.json_text(data))
        self.assertIn("credential-shaped", self.errors())

    def test_private_readme_text_outside_generated_catalog_is_rejected(self):
        path = self.root / "README.md"
        path.write_text(path.read_text() + "\nPrivate diagnostics: /" + "Users/qa_fixture/private.swift\n")
        self.assertIn("public document: README.md", self.errors())

    def test_private_historical_notes_are_not_ignored(self):
        (self.root / "releases/v25.0.0.md").write_text("Private source: /" + "Users/qa_fixture/secret.swift\n")
        self.assertIn("releases/v25.0.0.md", self.errors())

    def test_personal_architecture_and_tool_preference_is_rejected(self):
        path = self.stable / "skills/swiftui-specialist/SKILL.md"
        path.write_text(path.read_text() + "\nFor this environment, use SwiftUI/MV and Axiom.\n")
        p.generate(self.root)
        self.assertIn("Personal architecture/tool preference", self.errors())

    def test_excluded_skill_cannot_be_published(self):
        path = self.stable / "skills/device-interaction/SKILL.md"
        path.parent.mkdir()
        path.write_text("---\nname: device-interaction\ndescription: Test fixture\n---\nExcluded.\n")
        p.generate(self.root)
        self.assertIn("Excluded skill", self.errors())

    def test_readme_catalog_drift_is_rejected(self):
        path = self.root / "README.md"
        path.write_text(path.read_text().replace("**Package version: `" + self.base_version + "`**", "**Package version: `invalid`**"))
        self.assertIn("README inventory drift", self.errors())

    def test_artifacts_are_reproducible_and_checksums_match(self):
        a, b = Path(self.temp.name) / "out-a", Path(self.temp.name) / "out-b"
        p.build(self.root, a)
        p.build(self.root, b)
        first = {name: file.read_bytes() for name, file in p.files(a).items()}
        second = {name: file.read_bytes() for name, file in p.files(b).items()}
        self.assertEqual(first, second)
        for line in (a / "SHA256SUMS").read_text().splitlines():
            checksum, name = line.split("  ", 1)
            self.assertEqual(checksum, p.sha((a / name).read_bytes()))
        for archive in a.glob("*.zip"):
            with zipfile.ZipFile(archive) as stream:
                names = stream.namelist()
                self.assertIn(".codex-plugin/plugin.json", names)
                self.assertIn(".claude-plugin/plugin.json", names)
                self.assertIn("THIRD_PARTY_NOTICES.md", names)
                self.assertFalse(any(n.startswith("/") or ".." in Path(n).parts or ".state" in Path(n).parts for n in names))

    def test_existing_reviewed_helpers_pass_behavioral_regressions(self):
        for plugin in (self.stable, self.preview):
            auditor = "audit-xcode-security-settings" + ("-preview" if plugin == self.preview else "")
            result = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", str(plugin / "skills" / auditor / "tests"), "-v"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Ran ", result.stderr)

    def test_unrequested_root_agent_cannot_be_distributed(self):
        path = self.stable / "agents/unsafe.md"
        path.parent.mkdir()
        path.write_text("Unexpected agent definition.\n")
        p.generate(self.root)
        self.assertIn("outside the declared skill library", self.errors())

    def test_previous_artifacts_are_not_deleted_or_mixed_into_a_new_build(self):
        out = Path(self.temp.name) / "out"
        out.mkdir()
        previous = out / "previous-version.zip"
        previous.write_bytes(b"previous artifact")
        with self.assertRaisesRegex(ValueError, "fresh output directory"):
            p.build(self.root, out)
        self.assertEqual(previous.read_bytes(), b"previous artifact")

    def test_invalid_package_cannot_produce_artifacts(self):
        (self.root / "VERSION").write_text("broken\n")
        out = Path(self.temp.name) / "out"
        with self.assertRaisesRegex(ValueError, "validation failed"):
            p.build(self.root, out)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
