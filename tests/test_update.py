"""Behavioral updater tests: all paths, exports and commands stay in fixtures."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("xcode_update_tests", ROOT / "tools/update.py")
u = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(u)


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def fact(version, build, channel="stable", label=None):
    return {"version": version, "build": build, "channel": channel,
            "label": label or ("Xcode " + version + (" beta" if channel == "preview" else "") + " (" + build + ")")}


class ReleaseOrderingTests(unittest.TestCase):
    def test_version_order_is_numeric_and_normalized(self):
        self.assertEqual(u.version_tuple("27"), (27, 0, 0))
        self.assertEqual(u.version_tuple("27.2"), (27, 2, 0))
        self.assertGreater(u.version_tuple("27.10"), u.version_tuple("27.9"))
        with self.assertRaises(u.UpdateError):
            u.version_tuple("27.3 beta 2")

    def test_rc_beats_beta_and_release_supersedes_same_version_preview(self):
        stable = fact("27.2", "A1")
        beta = fact("27.3", "B9", "preview", "Xcode 27.3 beta 9 (B9)")
        rc = fact("27.3", "B10", "preview", "Xcode 27.3 RC (B10)")
        selected = u.latest_releases({"releases": [beta, stable, rc]})
        self.assertEqual(selected["preview"], rc)
        selected = u.latest_releases({"releases": [beta, stable, rc, fact("27.3", "B10")]})
        self.assertIsNone(selected["preview"])

    def test_beta_sequence_is_numeric_not_lexicographic(self):
        beta2 = fact("27.3", "B2", "preview", "Xcode 27.3 beta 2 (B2)")
        beta10 = fact("27.3", "B10", "preview", "Xcode 27.3 beta 10 (B10)")
        selected = u.latest_releases({"releases": [beta10, beta2, fact("27.2", "A1")]})
        self.assertEqual(selected["preview"], beta10)

    def test_html_reader_ignores_script_and_preserves_build_channel(self):
        html = b'<script>Xcode 99.0 (Evil)</script><h2>Xcode 27.2 (A1)</h2><p>October 29, 2026</p><h2>Xcode 27.3 beta 2 (B2)</h2><p>November 16, 2026</p>'
        records = u.parse_releases(html)
        self.assertEqual([r["build"] for r in records], ["A1", "B2"])
        self.assertEqual(records[1]["channel"], "preview")
        self.assertEqual(records[1]["released_at"], "2026-11-16")

    def test_package_revisions_are_shared_and_refuse_downgrades(self):
        self.assertEqual(u.next_version("27.2.4", "27.2.1"), "27.2.5")
        self.assertEqual(u.next_version("27.2.4", "27.3"), "27.3.0")
        with self.assertRaises(u.UpdateError):
            u.next_version("27.3.0", "27.2")


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        for name in ("release.json", "package-policy.json", "README.md", "README.pt-BR.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "VERSION"):
            shutil.copy2(ROOT / name, self.root / name)
        for name in ("plugins", "releases", ".agents", ".claude-plugin"):
            shutil.copytree(ROOT / name, self.root / name)
        (self.root / "tools").mkdir()
        shutil.copy2(ROOT / "tools/package.py", self.root / "tools/package.py")
        self.metadata = u.read(self.root / "release.json")
        self.old = Path(self.temp.name) / "old"
        self.old.mkdir()
        self.mirrors = {}
        self.baselines = {}
        config = {"schema_version": 1, "state_dir": ".state", "release_evidence": "evidence.json", "app_roots": [],
                  "marketplace": "personal", "channels": {}, "excluded_skills": list(u.EXCLUDED),
                  "legacy_export": str(self.old / "original"), "legacy_manifest": str(self.old / "original.json")}
        for channel, plugin in u.CHANNELS.items():
            source = self.root / "plugins" / plugin
            mirror = self.old / "mirrors" / plugin
            shutil.copytree(source, mirror)
            self.mirrors[channel] = mirror
            xcode = self.metadata["channels"][channel]["xcode"]
            u.write(mirror / "source-snapshot.json", {"xcode": dict(xcode, fingerprint="published-" + channel)})
            baseline = self.old / ".state/snapshots" / channel / "export"
            for rel, path in u.logical_files(source, channel).items():
                target = baseline / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())
                if target.name == "SKILL.md" and channel == "preview":
                    text = target.read_text().replace("name: " + target.parent.name + "-preview", "name: " + target.parent.name)
                    target.write_text(text)
            self.baselines[channel] = baseline
            u.write(self.old / ".state" / ("applied-" + channel + ".json"), {"snapshot": "snapshots/" + channel, "export_sha256": u.legacy.tree_digest(baseline)})
            config["channels"][channel] = {"source": str(mirror), "plugin_id": plugin, "display_name": plugin}
        self.evidence = {"source": u.SOURCE, "schema_version": 1, "checked_at": "fixture",
                         "releases": [self.metadata["channels"][c]["xcode"] for c in u.CHANNELS]}
        u.write(self.old / "maintain.json", config)
        u.write(self.old / "evidence.json", self.evidence)
        self.updater = u.Updater(self.root)

    def configured(self):
        self.updater.configure(self.old, True)
        return self.updater

    def bundle(self, channel="preview", version=None, build="NEW1", fingerprint="new-fingerprint", label=None):
        source = self.metadata["channels"][channel]["xcode"]
        record = fact(version or source["version"], build, channel, label)
        return dict(record, path=str(Path(self.temp.name) / "XcodeFixture.app"), fingerprint=fingerprint,
                    channel_evidence={"source": u.SOURCE, "record": record})

    def candidate(self, channel="preview", new_skill=False, new_code=False, version=None):
        self.configured()
        snapshot = self.root / ".local/exports" / channel
        shutil.copytree(self.baselines[channel], snapshot / "export")
        if new_skill:
            put(snapshot / "export/new-instructions/SKILL.md", "---\nname: new-instructions\ndescription: New fixture instruction reference\n---\nRead [notes](references/notes.md).\n")
            put(snapshot / "export/new-instructions/references/notes.md", "Fixture notes.\n")
        else:
            name = "swiftui-specialist"
            path = snapshot / "export" / name / "SKILL.md"
            path.write_text(path.read_text() + "\nA verified upstream fixture clarification.\n")
        if new_code:
            put(snapshot / "export/new-code/SKILL.md", "---\nname: new-code\ndescription: Fixture requiring executable code\n---\nRead the helper.\n")
            put(snapshot / "export/new-code/scripts/never.py", "raise AssertionError('exported code must never execute')\n")
        bundle = self.bundle(channel, version=version)
        record = {"export_sha256": u.legacy.tree_digest(snapshot / "export")}
        result = self.updater.build_candidate(bundle, snapshot, record)
        return Path(result["candidate"]), result["review"]

    def mock_git_clean(self, args, cwd=None, **kwargs):
        if args[:3] == ["git", "branch", "--show-current"]:
            return "main"
        if args[:3] == ["git", "status", "--porcelain"]:
            return ""
        raise AssertionError("Unexpected external command: " + repr(args))

    def mark_reviewed_fixture(self, candidate):
        # A fixture receipt for stage-only tests; the real review operation has
        # independent tests that must validate and seal the candidate itself.
        report = u.read(candidate / "review.json")
        report.update(reviewed=True, review_note="Fixture automated review", candidate_sha256=u.legacy.tree_digest(candidate / "plugin"))
        for decision in report["decisions"]:
            decision.update(resolved=True, choice="take-upstream")
        u.write(candidate / "review.json", report)
        return report

    def test_configure_dry_run_does_not_create_private_state(self):
        result = self.updater.configure(self.old)
        self.assertFalse(result["configured"])
        self.assertFalse((self.root / ".local").exists())

    def test_configure_verifies_baseline_before_recording_authorization(self):
        path = self.baselines["stable"] / "swiftui-specialist/SKILL.md"
        path.write_text(path.read_text() + "tampered\n")
        with self.assertRaisesRegex(u.UpdateError, "integrity"):
            self.updater.configure(self.old, True)
        self.assertFalse((self.root / ".local/config.json").exists())

    def test_missing_download_is_deduplicated_without_export_or_fake_version(self):
        self.configured()
        desired = self.bundle(build="NEW2")["channel_evidence"]["record"]
        evidence = dict(self.evidence, releases=self.evidence["releases"] + [desired])
        installed = []
        manager = mock.Mock()
        manager.discover.return_value = (installed, [])
        before = (self.root / "release.json").read_bytes()
        with mock.patch.object(u, "fetch_releases", return_value=evidence), mock.patch.object(self.updater, "manager", return_value=manager):
            first = self.updater.check(True)
            second = self.updater.check(True)
        self.assertEqual({event["type"] for event in first["events"]}, {"download_required"})
        self.assertFalse(second["events"])
        self.assertFalse(first["pending"])
        self.assertEqual(before, (self.root / "release.json").read_bytes())
        manager.snapshot.assert_not_called()

    def test_check_dry_run_does_not_write_state_or_notification_receipts(self):
        self.configured()
        before = u.file_hashes(self.root / ".local")
        manager = mock.Mock()
        manager.discover.return_value = ([], [])
        with mock.patch.object(u, "fetch_releases", return_value=self.evidence), mock.patch.object(self.updater, "manager", return_value=manager):
            self.updater.check(False)
        self.assertEqual(before, u.file_hashes(self.root / ".local"))

    def test_network_failure_is_deduplicated_and_does_not_publish(self):
        self.configured()
        with mock.patch.object(u, "fetch_releases", side_effect=OSError("offline")), mock.patch.object(u, "command") as external:
            first = self.updater.check(True)
            second = self.updater.check(True)
        self.assertEqual(first["status"], "network_error")
        self.assertEqual(len(first["events"]), 1)
        self.assertEqual(second["events"], [])
        external.assert_not_called()

    def test_preview_new_skill_gets_suffix_and_review_decision_without_execution(self):
        candidate, report = self.candidate(new_skill=True)
        entry = candidate / "plugin/skills/new-instructions-preview/SKILL.md"
        text = entry.read_text()
        self.assertIn("name: new-instructions-preview", text)
        self.assertIn("Preview (beta/RC)", text)
        self.assertIn("new-skill:new-instructions", {x["id"] for x in report["decisions"]})
        self.assertTrue((entry.parent / "references/notes.md").is_file())

    def test_new_executable_skill_is_withheld_without_importing_or_running_it(self):
        candidate, report = self.candidate(new_code=True)
        self.assertIn("new-code", report["withheld_skills"])
        self.assertFalse((candidate / "plugin/skills/new-code-preview").exists())
        self.assertTrue((Path(report["snapshot"]) / "export/new-code/scripts/never.py").is_file())

    def test_keep_local_new_skill_preserves_private_withheld_copy(self):
        candidate, _ = self.candidate(new_skill=True)
        result = self.updater.resolve(candidate, "new-skill:new-instructions", "keep-local", "Tools not applicable", True)
        self.assertFalse(result["dry_run"])
        self.assertFalse((candidate / "plugin/skills/new-instructions-preview").exists())
        self.assertTrue((candidate / "withheld/new-instructions-preview/SKILL.md").is_file())
        self.assertIn("new-instructions", u.read(candidate / "review.json")["withheld_skills"])

    def test_review_of_valid_candidate_succeeds_and_seals_exact_bytes(self):
        candidate, _ = self.candidate()
        report = u.read(candidate / "review.json")
        for decision in report["decisions"]:
            self.updater.resolve(candidate, decision["id"], "keep-local", "Preserve scoped adaptation", True)
        result = self.updater.review(candidate, "Verified references, neutral guidance and selected SDK scope.", True)
        self.assertTrue(result["validation"]["valid"])
        receipt = u.read(candidate / "review.json")
        self.assertTrue(receipt["reviewed"])
        self.assertEqual(receipt["candidate_sha256"], u.legacy.tree_digest(candidate / "plugin"))
        self.assertEqual(receipt["review_kind"], "automated_agent")

    def test_stage_preview_only_bumps_shared_version_and_preserves_stable_content(self):
        candidate, _ = self.candidate()
        self.mark_reviewed_fixture(candidate)
        stable = self.root / "plugins" / u.CHANNELS["stable"] / "skills"
        before = u.legacy.tree_digest(stable)
        with mock.patch.object(u, "command", side_effect=self.mock_git_clean):
            result = self.updater.stage(True)
        metadata = u.read(self.root / "release.json")
        self.assertEqual(metadata["version"], u.next_version(self.metadata["version"], self.metadata["channels"]["stable"]["xcode"]["version"]))
        self.assertEqual(result["channels"], ["preview"])
        self.assertEqual(before, u.legacy.tree_digest(stable))
        for plugin in u.CHANNELS.values():
            manifest = u.read(self.root / "plugins" / plugin / ".codex-plugin/plugin.json")
            self.assertEqual(manifest["version"], metadata["version"])

    def test_stage_dry_run_does_not_modify_sources_or_private_receipts(self):
        candidate, _ = self.candidate()
        self.mark_reviewed_fixture(candidate)
        before = u.file_hashes(self.root)
        with mock.patch.object(u, "command", side_effect=self.mock_git_clean):
            result = self.updater.stage(False)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(before, u.file_hashes(self.root))

    def test_stage_rejects_candidate_tampering_before_live_sources_change(self):
        candidate, _ = self.candidate()
        self.mark_reviewed_fixture(candidate)
        path = candidate / "plugin/skills/swiftui-specialist-preview/SKILL.md"
        path.write_text(path.read_text() + "unreviewed change\n")
        before = u.legacy.tree_digest(self.root / "plugins")
        with mock.patch.object(u, "command", side_effect=self.mock_git_clean), self.assertRaisesRegex(u.UpdateError, "changed after"):
            self.updater.stage(True)
        self.assertEqual(before, u.legacy.tree_digest(self.root / "plugins"))

    def test_stage_rejects_published_source_drift(self):
        candidate, _ = self.candidate()
        self.mark_reviewed_fixture(candidate)
        path = self.root / "plugins" / u.CHANNELS["preview"] / "skills/swiftui-specialist-preview/SKILL.md"
        path.write_text(path.read_text() + "concurrent local edit\n")
        with mock.patch.object(u, "command", side_effect=self.mock_git_clean), self.assertRaisesRegex(u.UpdateError, "adaptation changed"):
            self.updater.stage(True)

    def test_pending_publication_resumes_without_reexporting(self):
        self.configured()
        publication = {"version": self.metadata["version"], "status": "auto_merge_requested", "pr": "https://github.com/fixture/pr/1"}
        u.write(self.root / ".local/publication.json", publication)
        manager = mock.Mock()
        checked = {"status": "updates_available", "publication": publication, "pending": [{"channel": "preview", "bundle": self.bundle()}], "events": []}
        with mock.patch.object(self.updater, "check", return_value=checked), mock.patch.object(self.updater, "manager", return_value=manager), mock.patch.object(u, "command", return_value=""):
            self.updater.prepare(True)
        manager.snapshot.assert_not_called()

    def public_files(self):
        return {name: data for name, data in u.file_hashes(self.root).items() if not name.startswith(".local/")}

    def test_fetch_preserves_old_authoritative_builds_after_catalog_page_changes(self):
        response = mock.MagicMock()
        response.url = u.SOURCE
        response.read.return_value = b"<h2>Xcode 27.3 beta 2 (LATEST2)</h2>"
        response.__enter__.return_value = response
        with mock.patch.object(u.urllib.request, "urlopen", return_value=response):
            evidence = u.fetch_releases(self.evidence)
        builds = {item["build"] for item in evidence["releases"]}
        self.assertIn("LATEST2", builds)
        self.assertTrue({item["build"] for item in self.evidence["releases"]} <= builds)

    def test_prepare_dry_run_never_launches_or_exports_xcode(self):
        checked = {"status": "updates_available", "pending": [{"channel": "preview", "bundle": self.bundle()}], "events": []}
        with mock.patch.object(self.updater, "check", return_value=checked), mock.patch.object(self.updater, "manager") as manager, mock.patch.object(u, "command") as external:
            result = self.updater.prepare(False)
        self.assertEqual(result, checked)
        manager.assert_not_called()
        external.assert_not_called()

    def test_review_accepts_new_stable_minor_before_staging_package_version(self):
        major, minor, _ = u.version_tuple(self.metadata["channels"]["stable"]["xcode"]["version"])
        candidate, report = self.candidate("stable", version="%s.%s" % (major, minor + 1))
        for decision in report["decisions"]:
            self.updater.resolve(candidate, decision["id"], "keep-local", "Preserve scoped adaptation", True)
        result = self.updater.review(candidate, "New release SDK and source version verified in fixture.", True)
        self.assertTrue(result["validation"]["valid"])
        self.assertTrue(u.read(candidate / "review.json")["reviewed"])
        self.assertEqual(u.read(self.root / "release.json")["version"], self.metadata["version"])

    def test_stage_generator_failure_preserves_checkout_and_review_then_retry_succeeds(self):
        candidate, _ = self.candidate()
        self.mark_reviewed_fixture(candidate)
        before = self.public_files()
        receipt_before = (candidate / "review.json").read_bytes()
        pack = u.package_module(self.root)
        with mock.patch.object(u, "command", side_effect=self.mock_git_clean), mock.patch.object(u, "package_module", return_value=pack), mock.patch.object(pack, "generate", side_effect=RuntimeError("Injected generator failure")), self.assertRaisesRegex(RuntimeError, "Injected generator"):
            self.updater.stage(True)
        self.assertEqual(before, self.public_files())
        self.assertEqual(receipt_before, (candidate / "review.json").read_bytes())
        self.assertFalse((self.root / ".local/staged.json").exists())
        with mock.patch.object(u, "command", side_effect=self.mock_git_clean):
            result = self.updater.stage(True)
        self.assertEqual(result["status"], "staged")
        self.assertEqual(u.read(candidate / "review.json")["staged"], result["version"])

    def test_stage_copy_failure_rolls_back_replacements_without_deleting_backups(self):
        candidate, _ = self.candidate()
        self.mark_reviewed_fixture(candidate)
        before = self.public_files()
        receipt_before = (candidate / "review.json").read_bytes()
        original_copy = u.shutil.copy2
        failed = []
        def fail_once(src, dst, *args, **kwargs):
            if Path(dst).resolve() == (self.root / "VERSION").resolve() and ".local" not in Path(src).parts and not failed:
                failed.append(True)
                raise OSError("Injected replacement failure")
            return original_copy(src, dst, *args, **kwargs)
        with mock.patch.object(u, "command", side_effect=self.mock_git_clean), mock.patch.object(u.shutil, "copy2", side_effect=fail_once), self.assertRaisesRegex(OSError, "Injected replacement"):
            self.updater.stage(True)
        self.assertTrue(failed)
        self.assertEqual(before, self.public_files())
        self.assertEqual(receipt_before, (candidate / "review.json").read_bytes())
        self.assertEqual(u.read(self.root / ".local/stage-transaction.json")["status"], "rolled_back")
        self.assertTrue(list((self.root / ".local/backups").glob("stage-*")))
        with mock.patch.object(u, "command", side_effect=self.mock_git_clean):
            self.assertEqual(self.updater.stage(True)["status"], "staged")

    def publication_fixture(self, pr_state="MERGED"):
        self.configured()
        state = {"status": "auto_merge_requested", "version": self.metadata["version"], "branch": "automation/update-" + self.metadata["version"], "commit": "a" * 40, "pr": "https://github.com/fixture/pr/1"}
        u.write(self.root / ".local/publication.json", state)
        pr = {"state": pr_state, "headRefName": state["branch"], "headRefOid": state["commit"], "author": {"login": u.OWNER}, "mergeCommit": {"oid": "b" * 40}}
        return state, pr

    def test_merged_publication_resumes_main_release_and_mirror_without_new_version(self):
        state, pr = self.publication_fixture()
        calls = []
        def fake(args, cwd=None, **kwargs):
            calls.append(args)
            if args[:3] == ["gh", "pr", "view"]:
                return json.dumps(pr)
            if args[:3] == ["git", "status", "--porcelain"]:
                return ""
            if args[:3] == ["git", "branch", "--show-current"]:
                return state["branch"]
            if args[:3] == ["git", "fetch", "origin"] or args[:3] == ["git", "switch", "main"] or args[:3] == ["git", "merge", "--ff-only"]:
                return ""
            raise AssertionError("Unexpected external command: " + repr(args))
        with mock.patch.object(self.updater, "ensure_remote"), mock.patch.object(u, "command", side_effect=fake), mock.patch.object(u.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout='{"isDraft":false}')), mock.patch.object(self.updater, "mirror", return_value={"release": "https://github.com/fixture/release"}) as mirror:
            result = self.updater.resume(True)
        self.assertEqual(result["status"], "complete")
        mirror.assert_called_once_with(True)
        self.assertIn(["git", "merge", "--ff-only", "origin/main"], calls)
        self.assertEqual(u.read(self.root / ".local/publication.json")["status"], "complete")
        self.assertEqual(u.read(self.root / "release.json")["version"], state["version"])

    def test_open_publication_resume_retries_auto_merge_but_does_not_export(self):
        state, pr = self.publication_fixture("OPEN")
        calls = []
        def fake(args, cwd=None, **kwargs):
            calls.append(args)
            if args[:3] == ["gh", "pr", "view"]:
                return json.dumps(pr)
            if args[:3] == ["gh", "pr", "merge"]:
                return ""
            raise AssertionError("Unexpected external command: " + repr(args))
        with mock.patch.object(self.updater, "ensure_remote"), mock.patch.object(u, "command", side_effect=fake), mock.patch.object(self.updater, "mirror") as mirror:
            result = self.updater.resume(True)
        self.assertEqual(result["status"], "awaiting_ci_or_merge")
        self.assertTrue(any(args[:3] == ["gh", "pr", "merge"] for args in calls))
        mirror.assert_not_called()

    def test_merged_resume_dry_run_does_not_change_checkout_or_receipts(self):
        _, pr = self.publication_fixture()
        before = u.file_hashes(self.root)
        with mock.patch.object(self.updater, "ensure_remote"), mock.patch.object(u, "command", return_value=json.dumps(pr)), mock.patch.object(self.updater, "mirror") as mirror:
            result = self.updater.resume(False)
        self.assertEqual(result["status"], "merged")
        self.assertEqual(before, u.file_hashes(self.root))
        mirror.assert_not_called()

    def test_local_mirror_edits_are_not_overwritten(self):
        self.configured()
        path = self.mirrors["stable"] / "skills/swiftui-specialist/SKILL.md"
        path.write_text(path.read_text() + "local user edit\n")
        before = u.legacy.tree_digest(self.mirrors["stable"])
        def fake(args, cwd=None, **kwargs):
            if args[:3] == ["gh", "release", "view"]:
                return json.dumps({"isDraft": False, "tagName": "v" + self.metadata["version"], "url": "https://github.com/fixture/release"})
            if args[:3] == ["git", "fetch", "origin"] or args[:2] == ["git", "diff"]:
                return ""
            raise AssertionError("Unexpected external command: " + repr(args))
        with mock.patch.object(self.updater, "ensure_remote"), mock.patch.object(u, "command", side_effect=fake), self.assertRaisesRegex(u.UpdateError, "mirror was edited"):
            self.updater.mirror(True)
        self.assertEqual(before, u.legacy.tree_digest(self.mirrors["stable"]))


if __name__ == "__main__":
    unittest.main()
