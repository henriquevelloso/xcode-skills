import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import maintain as m
import setup_scaffold as setup


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve() / "home"
        self.tool = self.home / "workspace/maintainer"
        self.stable = self.home / "plugins/xcode-apple-skills"
        self.preview = self.home / "plugins/xcode-apple-skills-preview"
        self.destination = self.home / "plugins/xcode-skills-maintenance"
        self.tool.mkdir(parents=True)
        m.write_json(self.stable / ".codex-plugin/plugin.json", {"name": "xcode-apple-skills", "version": "0.1.0", "skills": "./skills/", "interface": {"displayName": "Xcode Apple Skills"}})
        m.write_json(self.home / ".agents/plugins/marketplace.json", {"name": "personal", "plugins": [{"name": "xcode-apple-skills", "source": {"source": "local", "path": "./plugins/xcode-apple-skills"}}]})
        self.config_path = self.home / ".codex/config.toml"
        self.config_path.parent.mkdir(parents=True)
        self.config_path.write_text('[plugins."xcode-apple-skills@personal"]\nenabled = true\n\n[unrelated]\nvalue = 42\n')
        config = m.read_json(ROOT / "maintain.json")
        config["channels"]["stable"]["source"] = str(self.stable)
        config["channels"]["preview"]["source"] = str(self.preview)
        m.write_json(self.tool / "maintain.json", config)
        m.write_json(self.tool / "release-evidence.json", m.read_json(ROOT / "release-evidence.json"))
        m.copy_tree(ROOT / "scaffold", self.tool / "scaffold")
        (self.tool / "maintain.py").write_text("# deployment fixture; never executed\n")

    def test_setup_dry_run_has_no_mutations(self):
        before = m.inventory(self.home)
        self.assertTrue(setup.deploy(self.tool, self.destination, self.home)["dry_run"])
        self.assertEqual(before, m.inventory(self.home))

    def test_setup_registers_disabled_preview_and_keeps_stable(self):
        before = m.tree_digest(self.stable)
        result = setup.deploy(self.tool, self.destination, self.home, True)
        self.assertTrue(result["stable_verified_unchanged"])
        self.assertEqual(before, m.tree_digest(self.stable))
        self.assertEqual(m.skills(self.preview / "skills"), [])
        self.assertTrue(m.enabled_setting(self.config_path.read_text(), "xcode-apple-skills@personal"))
        self.assertFalse(m.enabled_setting(self.config_path.read_text(), "xcode-apple-skills-preview@personal"))
        self.assertIn('[unrelated]\nvalue = 42', self.config_path.read_text())
        setup.deploy(self.tool, self.destination, self.home, True)
        entries = m.read_json(self.home / ".agents/plugins/marketplace.json")["plugins"]
        self.assertEqual(len(entries), 2)
        self.assertEqual(before, m.tree_digest(self.stable))

    def test_setup_refuses_conflicting_registration(self):
        registry = self.home / ".agents/plugins/marketplace.json"
        data = m.read_json(registry)
        data["plugins"].append({"name": "xcode-apple-skills-preview", "source": {"source": "local", "path": "./other"}})
        m.write_json(registry, data)
        before = m.inventory(self.home)
        with self.assertRaisesRegex(m.MaintenanceError, "registration differs"):
            setup.deploy(self.tool, self.destination, self.home, True)
        self.assertEqual(before, m.inventory(self.home))

    def test_setup_preserves_explicit_selection_changes(self):
        self.config_path.write_text(m.set_enabled(self.config_path.read_text(), "xcode-apple-skills-preview@personal", True))
        with self.assertRaisesRegex(m.MaintenanceError, "explicitly enabled"):
            setup.deploy(self.tool, self.destination, self.home, True)


if __name__ == "__main__":
    unittest.main()
