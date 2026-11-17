import contextlib
import importlib.util
import io
import json
from pathlib import Path
import plistlib
import shutil
import tempfile
import unittest
from unittest import mock

MODULE = Path(__file__).resolve().parents[1] / "maintain.py"
spec = importlib.util.spec_from_file_location("maintain", MODULE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def skill(name, body="Alpha\nBeta\nGamma\n", description="Fixture guidance"):
    return "---\nname: %s\ndescription: %s\n---\n%s" % (name, description, body)


class Harness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "plugins/stable"
        self.preview = self.root / "plugins/preview"
        self.old = self.root / "original"
        self.new = self.root / "upstream"
        self.app = self.root / "Xcode.app"
        for path in [self.old, self.new]:
            write(path / "demo-skill/SKILL.md", skill("demo-skill"))
            write(path / "demo-skill/references/ref.md", "A\nB\nC\n")
            write(path / "demo-skill/scripts/helper.py", "# existing helper\n")
        m.copy_tree(self.old, self.source / "skills")
        write(self.source / "skills/demo-skill/SKILL.md", skill("demo-skill", description="Local adapted metadata"))
        write(self.source / "skills/demo-skill/references/local.md", "Local addition\n")
        self.manifest(self.source, "xcode-apple-skills", "Xcode Apple Skills", "0.1.0")
        self.manifest(self.preview, "xcode-apple-skills-preview", "Xcode Apple Skills Preview", "0.0.0")
        m.write_json(self.source / "source-snapshot.json", {"original_sha256": {name: m.sha(p.read_bytes()) for name, p in m.safe_files(self.old).items()}})
        m.write_json(self.source / "validation-report.json", {"historical": True})
        m.write_json(self.app / "Contents/Info.plist.json", {})
        (self.app / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.apple.dt.Xcode"}))
        (self.app / "Contents/version.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": "1.2", "ProductBuildVersion": "A1", "CFBundleVersion": "100"}))
        write(self.app / "Contents/Developer/usr/bin/agent", "# Apple exporter fixture\n")
        write(self.app / "Contents/PlugIns/IDEIntelligenceChat.framework/Versions/A/Resources/demo.idechatprompttemplate", skill("demo-skill"))
        m.write_json(self.root / "evidence.json", {"source": "https://developer.apple.com/news/releases/", "checked_at": "fixture", "releases": [{"version": "1.2", "build": "A1", "channel": "stable", "label": "Xcode 1.2 (A1)"}]})
        self.config = {"schema_version": 1, "state_dir": ".state", "release_evidence": "evidence.json", "app_roots": [str(self.root)], "marketplace": "personal", "excluded_skills": ["device-interaction", "adopt-c-bounds-safety"], "possible_renames": {}, "legacy_export": str(self.old), "legacy_manifest": str(self.source / "source-snapshot.json"), "channels": {
            "stable": {"source": str(self.source), "plugin_id": "xcode-apple-skills", "display_name": "Xcode Apple Skills"},
            "preview": {"source": str(self.preview), "adaptation_source": str(self.source), "plugin_id": "xcode-apple-skills-preview", "display_name": "Xcode Apple Skills Preview"}}}
        m.write_json(self.root / "maintain.json", self.config)
        self.manager = m.Manager(self.root / "maintain.json")

    def manifest(self, folder, identity, name, version):
        m.write_json(folder / ".codex-plugin/plugin.json", {"name": identity, "version": version, "description": "Fixture", "skills": "./skills/", "interface": {"displayName": name}})

    def exporter(self, bundle, destination):
        m.copy_tree(self.new, destination)
        return {"fixture": True, "DEVELOPER_DIR": bundle["path"] + "/Contents/Developer"}

    def prepare(self):
        with mock.patch.object(self.manager, "export", side_effect=self.exporter):
            return Path(self.manager.prepare(self.app, "stable")["candidate"])

    def test_check_reads_without_creating_state(self):
        before = m.inventory(self.root)
        result = self.manager.check()
        self.assertEqual(result["bundles"][0]["channel"], "stable")
        self.assertEqual(before, m.inventory(self.root))
        self.assertFalse(self.manager.state.exists())

    def test_unknown_build_refuses_before_export_or_state(self):
        self.manager.evidence["releases"] = []
        with self.assertRaisesRegex(m.MaintenanceError, "Channel unknown"):
            self.manager.prepare(self.app, "stable")
        self.assertFalse(self.manager.state.exists())

    def test_channel_mismatch_cannot_promote_rc(self):
        self.manager.evidence["releases"][0]["channel"] = "preview"
        with self.assertRaisesRegex(m.MaintenanceError, "Channel mismatch"):
            self.manager.prepare(self.app, "stable")

    def test_stable_publication_wins_over_same_build_rc(self):
        self.manager.evidence["releases"].insert(0, {"version": "1.2", "build": "A1", "channel": "preview"})
        self.assertEqual(self.manager.identify(self.app)["channel"], "stable")

    def test_three_way_keeps_adaptations_and_applies_disjoint_change(self):
        write(self.source / "skills/demo-skill/references/ref.md", "Local A\nB\nC\n")
        write(self.new / "demo-skill/references/ref.md", "A\nB\nNew C\n")
        candidate = self.prepare()
        self.assertEqual((candidate / "plugin/skills/demo-skill/references/ref.md").read_text(), "Local A\nB\nNew C\n")
        self.assertIn("Local adapted metadata", (candidate / "plugin/skills/demo-skill/SKILL.md").read_text())
        self.assertTrue((candidate / "plugin/skills/demo-skill/references/local.md").exists())
        self.assertEqual((self.source / "skills/demo-skill/references/ref.md").read_text(), "Local A\nB\nC\n")

    def test_read_only_source_references_can_be_updated_in_candidate(self):
        original = self.source / "skills/demo-skill/references/ref.md"
        original.chmod(0o444)
        write(self.new / "demo-skill/references/ref.md", "A\nB\nUpdated C\n")
        candidate = self.prepare()
        self.assertEqual((candidate / "plugin/skills/demo-skill/references/ref.md").read_text(), "A\nB\nUpdated C\n")
        self.assertEqual(original.read_text(), "A\nB\nC\n")
        self.assertEqual(original.stat().st_mode & 0o777, 0o444)

    def test_conflict_preserves_local_and_blocks_apply(self):
        write(self.source / "skills/demo-skill/references/ref.md", "Local\n")
        write(self.new / "demo-skill/references/ref.md", "Upstream\n")
        candidate = self.prepare()
        self.assertEqual((candidate / "plugin/skills/demo-skill/references/ref.md").read_text(), "Local\n")
        with self.assertRaisesRegex(m.MaintenanceError, "pending decision"):
            self.manager.apply(candidate)
        resolved = self.manager.resolve(candidate, "file:demo-skill/references/ref.md", "keep-local")
        self.assertEqual(resolved["new_seal"], m.read_json(candidate / "seal.json")["sha256"])
        self.assertTrue(self.manager.apply(candidate)["dry_run"])

    def test_removed_upstream_keeps_skill_and_helper(self):
        shutil.rmtree(self.new / "demo-skill")
        write(self.new / "other/SKILL.md", skill("other"))
        candidate = self.prepare()
        self.assertTrue((candidate / "plugin/skills/demo-skill/SKILL.md").is_file())
        self.assertTrue((candidate / "plugin/skills/demo-skill/scripts/helper.py").is_file())
        self.assertFalse((candidate / "plugin/skills/other").exists())

    def test_new_skill_quarantined_and_exclusion_not_reintroduced(self):
        write(self.new / "new-skill/SKILL.md", skill("new-skill"))
        write(self.new / "device-interaction/SKILL.md", skill("device-interaction"))
        candidate = self.prepare()
        self.assertFalse((candidate / "plugin/skills/new-skill").exists())
        self.assertFalse((candidate / "plugin/skills/device-interaction").exists())
        report = m.read_json(candidate / "review.json")
        self.assertEqual(report["new_skills_quarantined"], ["new-skill"])
        self.assertIn("new-apple/new-skill/SKILL.md", (candidate / "upstream.diff").read_text())
        self.manager.resolve(candidate, "new-skill:new-skill", "take-upstream")
        self.assertTrue((candidate / "plugin/skills/new-skill/SKILL.md").is_file())

    def test_new_code_is_not_executed_and_needs_review(self):
        marker = self.root / "SHOULD_NOT_EXIST"
        write(self.new / "demo-skill/scripts/new.py", "from pathlib import Path\nPath(%r).touch()\n" % str(marker))
        candidate = self.prepare()
        self.assertFalse(marker.exists())
        self.assertFalse((candidate / "plugin/skills/demo-skill/scripts/new.py").exists())
        self.assertTrue(any(d["id"] == "file:demo-skill/scripts/new.py" for d in m.read_json(candidate / "review.json")["pending_decisions"]))

    def test_repeat_prepare_reuses_verified_snapshot_and_candidate(self):
        candidate = self.prepare()
        with mock.patch.object(self.manager, "export", side_effect=AssertionError("Should not export twice")):
            repeated = self.manager.prepare(self.app, "stable")
        self.assertTrue(repeated["idempotent"])
        self.assertEqual(Path(repeated["candidate"]), candidate)

    def test_apply_dry_run_approval_backup_and_rollback(self):
        before = m.tree_digest(self.source)
        candidate = self.prepare()
        seal = m.read_json(candidate / "seal.json")["sha256"]
        self.assertTrue(self.manager.apply(candidate)["dry_run"])
        self.assertEqual(m.tree_digest(self.source), before)
        with self.assertRaisesRegex(m.MaintenanceError, "Explicit approval"):
            self.manager.apply(candidate, "wrong", True)
        result = self.manager.apply(candidate, seal, True)
        self.assertNotEqual(m.tree_digest(self.source), before)
        self.assertTrue(self.manager.apply(candidate, seal, True)["already_applied"])
        backup = Path(result["backup"])
        self.assertTrue(self.manager.rollback(backup)["dry_run"])
        self.manager.rollback(backup, result["rollback_approval_sha256"], True)
        self.assertEqual(m.tree_digest(self.source), before)
        self.assertTrue(self.manager.rollback(backup)["already_rolled_back"])

    def test_apply_rejects_candidate_tampering(self):
        candidate = self.prepare()
        write(candidate / "plugin/skills/demo-skill/references/ref.md", "tampered")
        with self.assertRaisesRegex(m.MaintenanceError, "changed after sealing"):
            self.manager.apply(candidate)
        check = self.manager.check([self.app])
        self.assertEqual(check["bundles"][0]["candidates"][0]["status"], "stale_or_invalid")
        self.assertTrue(check["bundles"][0]["needs_prepare"])

    def test_prepare_after_apply_is_noop_for_same_snapshot(self):
        candidate = self.prepare()
        self.manager.apply(candidate, m.read_json(candidate / "seal.json")["sha256"], True)
        with mock.patch.object(self.manager, "export", side_effect=AssertionError("Should not export twice")):
            self.assertTrue(self.manager.prepare(self.app, "stable")["no_update"])

    def test_apply_rejects_source_drift(self):
        candidate = self.prepare()
        write(self.source / "skills/demo-skill/references/ref.md", "new local edit")
        with self.assertRaisesRegex(m.MaintenanceError, "source changed"):
            self.manager.apply(candidate)

    def test_apply_rejects_snapshot_tampering(self):
        candidate = self.prepare()
        report = m.read_json(candidate / "review.json")
        write(self.manager.state / report["snapshot"] / "export/demo-skill/references/ref.md", "changed snapshot")
        with self.assertRaisesRegex(m.MaintenanceError, "snapshot changed"):
            self.manager.apply(candidate)

    def test_rollback_rejects_later_local_edits(self):
        candidate = self.prepare()
        result = self.manager.apply(candidate, m.read_json(candidate / "seal.json")["sha256"], True)
        write(self.source / "skills/demo-skill/references/ref.md", "new independent edit")
        with self.assertRaisesRegex(m.MaintenanceError, "Source changed after apply"):
            self.manager.rollback(result["backup"], result["rollback_approval_sha256"], True)

    def test_local_upstream_new_file_collision(self):
        write(self.new / "demo-skill/references/local.md", "New upstream file")
        candidate = self.prepare()
        self.assertEqual((candidate / "plugin/skills/demo-skill/references/local.md").read_text(), "Local addition\n")
        self.assertTrue(any(d["reason"] == "local_upstream_collision" for d in m.read_json(candidate / "review.json")["pending_decisions"]))

    def test_symlink_and_cache_write_refused(self):
        (self.new / "demo-skill/references/link.md").symlink_to(self.old / "demo-skill/references/ref.md")
        with self.assertRaisesRegex(m.MaintenanceError, "Symlink"):
            m.inventory(self.new)
        with self.assertRaisesRegex(m.MaintenanceError, "cache"):
            m.safe_target(self.root / "cache/plugin")

    def test_baseline_traversal_refused(self):
        manifest = m.read_json(self.source / "source-snapshot.json")
        manifest["original_sha256"]["../outside"] = "x"
        m.write_json(self.source / "source-snapshot.json", manifest)
        with self.assertRaisesRegex(m.MaintenanceError, "Unsafe relative"):
            self.prepare()

    def test_validator_rejects_broken_links_and_identity(self):
        write(self.source / "skills/demo-skill/references/link.md", "[bad](missing.md)")
        result = m.validate_plugin(self.source, "wrong")
        self.assertFalse(result["valid"])
        self.assertTrue(any("Broken" in x for x in result["errors"]))

    def test_validate_cli_returns_nonzero_on_invalid_package(self):
        write(self.source / "skills/demo-skill/references/link.md", "[bad](missing.md)")
        with contextlib.redirect_stdout(io.StringIO()):
            status = m.main(["--config", str(self.root / "maintain.json"), "validate", str(self.source)])
        self.assertEqual(status, 2)

    def test_preview_empty_cannot_be_selected(self):
        with self.assertRaisesRegex(m.MaintenanceError, "no approved"):
            self.manager.selection("preview")
        snippet = self.manager.selection("stable")
        self.assertTrue(m.enabled_setting(snippet, "xcode-apple-skills@personal"))
        self.assertFalse(m.enabled_setting(snippet, "xcode-apple-skills-preview@personal"))

    def test_first_preview_uses_applied_donor_baseline_and_preserves_adaptations(self):
        added = "demo-skill/references/added.md"
        write(self.new / added, "A\nB\nC\n")
        stable = self.prepare()
        self.manager.apply(stable, m.read_json(stable / "seal.json")["sha256"], True)
        write(self.source / "skills" / added, "A\nLocal B\nC\n")
        write(self.new / added, "A\nB\nPreview C\n")
        self.manager.evidence["releases"][0]["channel"] = "preview"
        with mock.patch.object(self.manager, "export", side_effect=self.exporter):
            result = self.manager.prepare(self.app, "preview")
        candidate = Path(result["candidate"])
        report = m.read_json(candidate / "review.json")
        applied = m.read_json(self.manager.state / "applied-stable.json")
        self.assertEqual(report["source_baseline"], applied["snapshot"] + "/export")
        self.assertEqual((candidate / "plugin/skills" / added).read_text(), "A\nLocal B\nPreview C\n")
        self.assertFalse(report["pending_decisions"])
        self.assertFalse((self.manager.state / "applied-preview.json").exists())
        self.assertFalse((self.preview / "skills").exists())

    def test_preview_donor_baseline_tampering_refuses_before_export(self):
        stable = self.prepare()
        self.manager.apply(stable, m.read_json(stable / "seal.json")["sha256"], True)
        receipt = m.read_json(self.manager.state / "applied-stable.json")
        write(self.manager.state / receipt["snapshot"] / "export/demo-skill/SKILL.md", "tampered")
        self.manager.evidence["releases"][0]["channel"] = "preview"
        with mock.patch.object(self.manager, "export") as exporter:
            with self.assertRaisesRegex(m.MaintenanceError, "Applied baseline snapshot changed"):
                self.manager.prepare(self.app, "preview")
        exporter.assert_not_called()

    def test_applied_preview_keeps_own_baseline_after_stable_changes(self):
        stable = self.prepare()
        self.manager.apply(stable, m.read_json(stable / "seal.json")["sha256"], True)
        self.manager.evidence["releases"][0]["channel"] = "preview"
        with mock.patch.object(self.manager, "export", side_effect=self.exporter):
            preview = Path(self.manager.prepare(self.app, "preview")["candidate"])
        self.manager.apply(preview, m.read_json(preview / "seal.json")["sha256"], True)
        receipt = m.read_json(self.manager.state / "applied-preview.json")
        (self.manager.state / "applied-stable.json").unlink()
        self.assertEqual(self.manager.baseline("preview"), self.manager.state / receipt["snapshot"] / "export")

    def test_config_edit_preserves_unrelated_sections(self):
        initial = '[model]\nname = "keep"\n\n[plugins."xcode-apple-skills@personal"]\nenabled = true\n\n[unrelated]\nvalue = 42\n'
        result = m.set_enabled(initial, "xcode-apple-skills-preview@personal", False)
        self.assertIn(initial.rstrip(), result)
        self.assertFalse(m.enabled_setting(result, "xcode-apple-skills-preview@personal"))
        switched = m.set_enabled(result, "xcode-apple-skills@personal", False)
        self.assertFalse(m.enabled_setting(switched, "xcode-apple-skills@personal"))
        self.assertIn('[unrelated]\nvalue = 42', switched)

    def test_setting_enabled_preserves_newlines_comments_and_noop_bytes(self):
        text = '[plugins."demo@personal"]\nenabled = true  # keep\n\n[unrelated]\nvalue = 42\n\n'
        self.assertEqual(m.set_enabled(text, 'demo@personal', True), text)
        self.assertEqual(m.set_enabled(text, 'demo@personal', False), text.replace('enabled = true', 'enabled = false'))

    def enable_preview_names(self):
        self.manager.config['channels']['preview']['skill_name_suffix'] = '-preview'
        self.manager.evidence['releases'][0]['channel'] = 'preview'

    def test_preview_normalization_preserves_code_ui_policy_and_relative_links(self):
        m.copy_tree(self.source, self.preview / 'example')
        plugin = self.preview / 'example'
        write(plugin / 'skills/demo-skill/SKILL.md', skill('demo-skill', '[Self](../demo-skill/references/ref.md)\n`xctrace help`\n'))
        write(plugin / 'skills/demo-skill/agents/openai.yaml', 'interface:\n  display_name: "Demo"\n  default_prompt: "Use $demo-skill."\npolicy:\n  allow_implicit_invocation: true\n')
        helper = (plugin / 'skills/demo-skill/scripts/helper.py').read_bytes()
        m.normalize_preview_names(plugin, '-preview')
        self.assertEqual((plugin / 'skills/demo-skill-preview/scripts/helper.py').read_bytes(), helper)
        entry = (plugin / 'skills/demo-skill-preview/SKILL.md').read_text()
        self.assertIn('../demo-skill-preview/references/ref.md', entry)
        self.assertIn('`xctrace help`', entry)
        ui = (plugin / 'skills/demo-skill-preview/agents/openai.yaml').read_text()
        self.assertIn('display_name: "Demo Preview"', ui)
        self.assertIn('$demo-skill-preview.', ui)
        self.assertIn('allow_implicit_invocation: true', ui)
        before = m.inventory(plugin)
        m.normalize_preview_names(plugin, '-preview')
        self.assertEqual(m.inventory(plugin), before)

    def test_preview_upstream_update_merges_under_suffix_and_retains_helpers(self):
        self.enable_preview_names()
        with mock.patch.object(self.manager, 'export', side_effect=self.exporter):
            first = Path(self.manager.prepare(self.app, 'preview')['candidate'])
        self.manager.apply(first, m.read_json(first / 'seal.json')['sha256'], True)
        write(self.preview / 'skills/demo-skill-preview/references/ref.md', 'Local A\nB\nC\n')
        write(self.new / 'demo-skill/references/ref.md', 'A\nB\nUpdated C\n')
        version = plistlib.loads((self.app / 'Contents/version.plist').read_bytes())
        version['ProductBuildVersion'] = 'A2'
        (self.app / 'Contents/version.plist').write_bytes(plistlib.dumps(version))
        self.manager.evidence['releases'].append({'version':'1.2','build':'A2','channel':'preview'})
        with mock.patch.object(self.manager, 'export', side_effect=self.exporter):
            second = Path(self.manager.prepare(self.app, 'preview')['candidate'])
        self.assertEqual((second / 'plugin/skills/demo-skill-preview/references/ref.md').read_text(), 'Local A\nB\nUpdated C\n')
        self.assertEqual((second / 'plugin/skills/demo-skill-preview/scripts/helper.py').read_bytes(), (self.old / 'demo-skill/scripts/helper.py').read_bytes())
        self.assertFalse((second / 'plugin/skills/demo-skill').exists())
        self.assertFalse((second / 'plugin/skills/demo-skill-preview-preview').exists())
        self.assertEqual(m.read_json(second / 'review.json')['new_skills_quarantined'], [])
        self.assertFalse(m.read_json(second / 'review.json')['pending_decisions'])

    def test_preview_new_skill_resolution_uses_suffix_and_allows_both_channels(self):
        self.enable_preview_names()
        write(self.new / 'new-skill/SKILL.md', skill('new-skill'))
        write(self.new / 'device-interaction/SKILL.md', skill('device-interaction'))
        with mock.patch.object(self.manager, 'export', side_effect=self.exporter):
            candidate = Path(self.manager.prepare(self.app, 'preview')['candidate'])
        self.manager.resolve(candidate, 'new-skill:new-skill', 'take-upstream')
        self.assertTrue((candidate / 'plugin/skills/new-skill-preview/SKILL.md').is_file())
        self.assertFalse((candidate / 'plugin/skills/new-skill').exists())
        self.assertFalse((candidate / 'plugin/skills/device-interaction-preview').exists())
        self.manager.apply(candidate, m.read_json(candidate / 'seal.json')['sha256'], True)
        snippet = self.manager.selection('both')
        self.assertTrue(m.enabled_setting(snippet, 'xcode-apple-skills@personal'))
        self.assertTrue(m.enabled_setting(snippet, 'xcode-apple-skills-preview@personal'))

    def test_applied_receipt_remains_current_after_tool_or_config_change(self):
        candidate = self.prepare()
        self.manager.apply(candidate, m.read_json(candidate / 'seal.json')['sha256'], True)
        self.manager.config['channels']['preview']['skill_name_suffix'] = '-preview'
        check = self.manager.check([self.app])
        self.assertEqual(check['bundles'][0]['candidates'][0]['status'], 'source_applied')
        self.assertFalse(check['bundles'][0]['needs_prepare'])
        with self.assertRaisesRegex(m.MaintenanceError, 'config changed'):
            self.manager.verify_candidate(candidate)
        write(self.source / 'skills/demo-skill/references/ref.md', 'Later local edit\n')
        self.assertTrue(self.manager.check([self.app])['bundles'][0]['needs_prepare'])

    def test_preview_suffix_collision_is_rejected_without_overwrite(self):
        write(self.source / 'skills/demo-skill-preview/SKILL.md', skill('demo-skill-preview'))
        before = m.inventory(self.source)
        with self.assertRaisesRegex(m.MaintenanceError, 'naming collision'):
            m.normalize_preview_names(self.source, '-preview')
        self.assertEqual(m.inventory(self.source), before)

    def test_export_binds_pid_and_developer_dir_without_global_switch(self):
        bundle = self.manager.identify(self.app)
        destination = self.root / "official-export"
        def command(argv, **kwargs):
            self.assertEqual(argv[:4], ["/usr/bin/xcrun", "agent", "skills", "export"])
            self.assertEqual(kwargs["env"]["MCP_XCODE_PID"], "123")
            self.assertEqual(kwargs["env"]["DEVELOPER_DIR"], str(self.app.resolve() / "Contents/Developer"))
            m.copy_tree(self.new, destination)
            return type("Result", (), {"returncode": 0, "stdout": "fixture", "stderr": ""})()
        with mock.patch.object(self.manager, "bind_xcode", return_value=123), mock.patch.object(m.subprocess, "run", side_effect=command):
            self.manager.export(bundle, destination)

    def test_maintenance_lock_prevents_overlapping_writers(self):
        with self.manager.lock():
            with self.assertRaisesRegex(m.MaintenanceError, "Another maintenance"):
                with self.manager.lock():
                    self.fail("must not acquire twice")

    def test_html_release_reader_ignores_scripts(self):
        parser = m.ReleaseText()
        parser.feed('<h2>Xcode 1.2 (A1)</h2><script>Xcode 9.9 (FAKE)</script>')
        self.assertNotIn("FAKE", " ".join(parser.text))


if __name__ == "__main__":
    unittest.main()
