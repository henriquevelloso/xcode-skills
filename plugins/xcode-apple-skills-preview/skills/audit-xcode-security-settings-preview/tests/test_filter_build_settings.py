"""Fixture-only regression tests; no Xcode, network, builds, or project mutations."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_ROOT / "scripts" / "filter_build_settings.py"
SPEC = importlib.util.spec_from_file_location("filter_build_settings", SCRIPT)
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)

CONTEXT = {
    "project": "Example.xcodeproj",
    "target": "Example",
    "configuration": "Release",
    "sdk": "iphoneos",
}


def native_row(name, value, *, override=False, context=None):
    raw = {"macroName": name, "evaluatedValue": value}
    if override:
        raw["targetValue"] = value
    payload = {**(CONTEXT if context is None else context), "buildSettings": [raw]}
    return HELPER.normalize_build_settings(payload)[0]


class FilterBuildSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = HELPER.load_reference_rules()

    def test_native_target_override_preserves_full_snapshot_identity(self):
        row = native_row("ENABLE_ENHANCED_SECURITY", "NO", override=True)
        self.assertEqual(row["explicitScope"], "target")
        self.assertEqual(row["targetValue"], "NO")
        self.assertEqual(HELPER.classify_setting(row, self.rules), "explicitly-disabled")
        for key, value in CONTEXT.items():
            self.assertEqual(row[key], value)

    def test_native_missing_evaluated_value_is_unknown_not_off(self):
        payload = {**CONTEXT, "buildSettings": [{"macroName": "ENABLE_ENHANCED_SECURITY"}]}
        row = HELPER.normalize_build_settings(payload)[0]
        self.assertEqual(HELPER.classify_setting(row, self.rules), "unset-or-unavailable")

    def test_missing_context_does_not_verify_explicit_disable(self):
        row = native_row("ENABLE_ENHANCED_SECURITY", "NO", override=True, context={})
        self.assertEqual(HELPER.classify_setting(row, self.rules), "disabled-origin-unknown")

    def test_valid_cpp_enum_modes_are_hardened(self):
        for mode in ("fast", "debug", "extensive"):
            with self.subTest(mode=mode):
                row = native_row("CLANG_CXX_STANDARD_LIBRARY_HARDENING", mode, override=True)
                self.assertEqual(HELPER.classify_setting(row, self.rules), "hardened")

    def test_cpp_off_and_unrecognized_enum_are_distinct(self):
        off = native_row("CLANG_CXX_STANDARD_LIBRARY_HARDENING", "none", override=True)
        unexpected = native_row("CLANG_CXX_STANDARD_LIBRARY_HARDENING", "custom", override=True)
        self.assertEqual(HELPER.classify_setting(off, self.rules), "explicitly-disabled")
        self.assertEqual(HELPER.classify_setting(unexpected, self.rules), "unsupported-value")

    def test_plain_yes_is_weaker_than_error_or_aggressive_warning(self):
        for name, value in (("GCC_WARN_ABOUT_RETURN_TYPE", "YES_ERROR"),
                            ("GCC_WARN_UNINITIALIZED_AUTOS", "YES_AGGRESSIVE")):
            with self.subTest(name=name):
                self.assertEqual(HELPER.classify_setting(native_row(name, value), self.rules), "hardened")
                self.assertEqual(HELPER.classify_setting(native_row(name, "YES"), self.rules), "weaker-value")

    def test_boolean_false_is_off_but_unknown_origin_stays_unknown(self):
        row = native_row("ENABLE_ENHANCED_SECURITY", False)
        self.assertEqual(row["evaluatedValue"], "NO")
        self.assertEqual(HELPER.classify_setting(row, self.rules), "disabled-origin-unknown")

    def test_xcodebuild_normalization_does_not_infer_target_overrides(self):
        payload = [{"target": "Example", "buildSettings": {
            "PROJECT_FILE_PATH": "Example.xcodeproj", "CONFIGURATION": "Release",
            "SDKROOT": "iphoneos", "ENABLE_ENHANCED_SECURITY": "NO",
        }}]
        row = next(row for row in HELPER.normalize_build_settings(payload)
                   if row["macroName"] == "ENABLE_ENHANCED_SECURITY")
        self.assertNotIn("targetValue", row)
        self.assertEqual(row["explicitScope"], "unknown")
        self.assertEqual(HELPER.classify_setting(row, self.rules), "disabled-origin-unknown")

    def test_multiple_projects_targets_and_configurations_do_not_conflate(self):
        snapshots = []
        for project, target, config, sdk, value in (
            ("One.xcodeproj", "App", "Release", "iphoneos", "NO"),
            ("One.xcodeproj", "App", "Debug", "iphonesimulator", "YES"),
            ("One.xcodeproj", "Other", "Release", "iphoneos", "YES"),
            ("Two.xcodeproj", "App", "Release", "iphoneos", "YES"),
        ):
            snapshots.append({"target": target, "buildSettings": {
                "PROJECT_FILE_PATH": project, "CONFIGURATION": config,
                "SDKROOT": sdk, "ENABLE_ENHANCED_SECURITY": value,
            }})
        rows = HELPER.normalize_build_settings(snapshots)
        filtered = HELPER.filter_settings(rows, self.rules, project="One.xcodeproj",
            target="App", configuration="Release", sdk="iphoneos")
        relevant = [row for row in filtered if row["macroName"] == "ENABLE_ENHANCED_SECURITY"]
        self.assertEqual(len(relevant), 1)
        self.assertEqual(relevant[0]["evaluatedValue"], "NO")
        self.assertEqual(relevant[0]["classification"], "disabled-origin-unknown")

    def test_known_labels_fill_missing_context_without_relabelling(self):
        payload = [{"target": "Actual", "buildSettings": {"ENABLE_ENHANCED_SECURITY": "NO"}}]
        rows = HELPER.normalize_build_settings(payload, **CONTEXT)
        self.assertEqual(rows[0]["target"], "Actual")
        self.assertEqual(rows[0]["configuration"], "Release")
        self.assertEqual(HELPER.filter_settings(rows, self.rules, target="Example"), [])

    def test_snapshot_metadata_preserves_reviewer_app_and_library_contexts(self):
        payload = [
            {"target": "App", "project": "Demo", "configuration": "Release", "buildSettings": {
                "SDKROOT": "iphoneos27.1", "CLANG_CXX_STANDARD_LIBRARY_HARDENING": "fast",
                "ENABLE_ENHANCED_SECURITY": "NO",
            }},
            {"target": "Library", "project": "Demo", "configuration": "Debug", "buildSettings": {
                "SDKROOT": "iphoneos27.1", "CLANG_CXX_STANDARD_LIBRARY_HARDENING": "debug",
                "ENABLE_ENHANCED_SECURITY": "YES",
            }},
        ]
        rows = HELPER.filter_settings(HELPER.normalize_build_settings(payload), self.rules)
        protections = [row for row in rows if row["macroName"] != "SDKROOT"]
        self.assertEqual(len(protections), 4)
        self.assertEqual({(row["project"], row["target"], row["configuration"], row["sdk"])
                          for row in protections},
                         {("Demo", "App", "Release", "iphoneos27.1"),
                          ("Demo", "Library", "Debug", "iphoneos27.1")})
        self.assertEqual([row["classification"] for row in protections],
                         ["hardened", "disabled-origin-unknown", "hardened", "hardened"])

    def test_evaluated_and_matching_declared_context_take_precedence_over_labels(self):
        payload = [{**CONTEXT, "buildSettings": {
            "PROJECT_FILE_PATH": CONTEXT["project"], "TARGET_NAME": CONTEXT["target"],
            "CONFIGURATION": CONTEXT["configuration"], "SDKROOT": CONTEXT["sdk"],
            "ENABLE_ENHANCED_SECURITY": "YES",
        }}]
        rows = HELPER.normalize_build_settings(payload, **{key: "Unrelated" for key in CONTEXT})
        for row in rows:
            for key, value in CONTEXT.items():
                self.assertEqual(row[key], value)

    def test_top_level_sdk_metadata_fills_missing_evaluated_sdk(self):
        payload = [{**CONTEXT, "buildSettings": {"ENABLE_ENHANCED_SECURITY": "NO"}}]
        row = HELPER.normalize_build_settings(payload)[0]
        self.assertEqual({key: row[key] for key in CONTEXT}, CONTEXT)
        self.assertEqual(row["explicitScope"], "unknown")

    def test_conflicting_evaluated_and_declared_context_is_rejected(self):
        evaluated_fields = {"project": "PROJECT_FILE_PATH", "target": "TARGET_NAME",
                            "configuration": "CONFIGURATION", "sdk": "SDKROOT"}
        for field, setting in evaluated_fields.items():
            with self.subTest(field=field):
                payload = [{**CONTEXT, "buildSettings": {
                    setting: "Conflicting", "ENABLE_ENHANCED_SECURITY": "NO",
                }}]
                with self.assertRaisesRegex(ValueError, "conflicting.*snapshot " + field):
                    HELPER.normalize_build_settings(payload)

    def test_cli_conflicting_context_exits_nonzero_without_emitting_rows(self):
        payload = [{**CONTEXT, "buildSettings": {
            "CONFIGURATION": "Debug", "ENABLE_ENHANCED_SECURITY": "NO",
        }}]
        result = subprocess.run([sys.executable, str(SCRIPT), "-", "--normalized-json"],
            input=json.dumps(payload), text=True, capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("conflicting evaluated and declared snapshot configuration context", result.stderr)

    def test_matching_scoped_xcconfig_origin_is_recognized(self):
        raw = {**CONTEXT, "macroName": "ENABLE_ENHANCED_SECURITY", "evaluatedValue": "NO",
               "explicitScope": "xcconfig", "source": "xcodebuild",
               "explicitSource": {"scope": "xcconfig", **CONTEXT},
               "sourceLocations": ["Configuration/Release.xcconfig:12"]}
        row = HELPER.normalize_build_settings({"settings": [raw]})[0]
        self.assertEqual(HELPER.classify_setting(row, self.rules), "explicitly-disabled")

    def test_origin_mismatch_in_any_dimension_remains_unknown(self):
        for key in ("project", "target", "configuration", "sdk"):
            with self.subTest(key=key):
                origin = {"scope": "xcconfig", **CONTEXT, key: "Unrelated"}
                raw = {**CONTEXT, "macroName": "ENABLE_ENHANCED_SECURITY", "evaluatedValue": "NO",
                       "explicitScope": "xcconfig", "explicitSource": origin}
                row = HELPER.normalize_build_settings({"settings": [raw]})[0]
                self.assertEqual(HELPER.classify_setting(row, self.rules), "disabled-origin-unknown")

    def test_project_wide_counts_are_not_override_evidence(self):
        raw = {**CONTEXT, "macroName": "ENABLE_ENHANCED_SECURITY", "evaluatedValue": "NO",
               "numMatchesInPbxproj": 12, "numMatchesInXCConfigs": 4}
        row = HELPER.normalize_build_settings({"settings": [raw]})[0]
        self.assertEqual(HELPER.classify_setting(row, self.rules), "disabled-origin-unknown")

    def test_filter_does_not_match_prefix_or_suffix_names(self):
        names = ("ENABLE_ENHANCED_SECURITY", "ENABLE_ENHANCED_SECURITY_EXTRA", "MY_ENABLE_ENHANCED_SECURITY")
        rows = [native_row(name, "YES") for name in names]
        self.assertEqual([row["macroName"] for row in HELPER.filter_settings(rows, self.rules)],
                         ["ENABLE_ENHANCED_SECURITY"])

    def test_custom_regex_fullmatches_and_cannot_expose_untracked_settings(self):
        rows = [native_row("ENABLE_ENHANCED_SECURITY", "YES"), native_row("PRIVATE_API_KEY", "fixture")]
        self.assertEqual(HELPER.filter_settings(rows, self.rules, regex="ENABLE"), [])
        self.assertEqual([row["macroName"] for row in HELPER.filter_settings(rows, self.rules, regex=".*")],
                         ["ENABLE_ENHANCED_SECURITY"])

    def test_unhardened_filter_keeps_unknown_and_weaker_but_excludes_metadata(self):
        rows = [native_row("SDKROOT", "iphoneos"), native_row("ENABLE_ENHANCED_SECURITY", "YES"),
                native_row("GCC_WARN_ABOUT_RETURN_TYPE", "YES"),
                native_row("ENABLE_POINTER_AUTHENTICATION", ""),
                native_row("CLANG_CXX_STANDARD_LIBRARY_HARDENING", "debug")]
        filtered = HELPER.filter_settings(rows, self.rules, unhardened_only=True)
        self.assertEqual({row["classification"] for row in filtered}, {"weaker-value", "unset-or-unavailable"})
        self.assertEqual(len(filtered), 2)

    def test_reference_extractor_ignores_prose_uppercase_tokens(self):
        sample = "Prose `YES` and `ARCHS_STANDARD`.\n| `MY_SECURITY_SETTING` | `YES` | note |\n"
        with patch.object(Path, "read_text", return_value=sample):
            self.assertEqual(HELPER.load_reference_rules(Path("unused")), {"MY_SECURITY_SETTING": {"YES"}})

    def test_stack_init_and_separate_bounds_settings_are_tracked(self):
        for name in ("CLANG_ENABLE_STACK_ZERO_INIT", "ENABLE_C_BOUNDS_SAFETY", "ENABLE_CPLUSPLUS_BOUNDS_SAFE_BUFFERS"):
            self.assertIn(name, self.rules)

    def test_normalization_does_not_mutate_input(self):
        payload = {**CONTEXT, "buildSettings": [{"macroName": "ENABLE_ENHANCED_SECURITY",
                                               "evaluatedValue": "NO", "targetValue": "NO"}]}
        before = copy.deepcopy(payload)
        HELPER.filter_settings(HELPER.normalize_build_settings(payload), self.rules)
        self.assertEqual(payload, before)

    def test_normalized_output_roundtrip_preserves_context_and_classification(self):
        rows = [native_row("CLANG_CXX_STANDARD_LIBRARY_HARDENING", "fast", override=True),
                native_row("ENABLE_ENHANCED_SECURITY", "NO", override=True)]
        filtered = HELPER.filter_settings(rows, self.rules)
        roundtrip = HELPER.filter_settings(HELPER.normalize_build_settings({"settings": filtered}), self.rules)
        self.assertEqual(roundtrip, filtered)

    def test_malformed_shapes_and_values_fail_without_fabricated_results(self):
        for payload in ({}, {"buildSettings": "invalid"}, {"buildSettings": [{}]},
                        {"buildSettings": [{"macroName": "ENABLE_ENHANCED_SECURITY", "evaluatedValue": []}]}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    HELPER.normalize_build_settings(payload)

    def test_cli_accepts_stdin_and_outputs_filtered_normalized_json(self):
        payload = {**CONTEXT, "buildSettings": [
            {"macroName": "CLANG_CXX_STANDARD_LIBRARY_HARDENING", "evaluatedValue": "debug"},
            {"macroName": "PRIVATE_API_KEY", "evaluatedValue": "fixture-secret-never-output"},
        ]}
        result = subprocess.run([sys.executable, str(SCRIPT), "-", "--normalized-json"],
            input=json.dumps(payload), text=True, capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(len(output["settings"]), 1)
        self.assertEqual(output["settings"][0]["classification"], "hardened")
        self.assertNotIn("fixture-secret-never-output", result.stdout + result.stderr)

    def test_cli_invalid_shape_exits_nonzero_without_dumping_payload(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "-"],
            input=json.dumps({"unknown": "fixture-sensitive-value"}), text=True,
            capture_output=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("fixture-sensitive-value", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
