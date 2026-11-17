#!/usr/bin/env python3
"""Read saved Xcode build settings, filter exact names, and classify scoped values.

This helper never invokes Xcode, accesses the network, or writes files. Accepted inputs:
- native Xcode {"buildSettings": [{"macroName": ..., "evaluatedValue": ...}, ...]}
- xcodebuild -showBuildSettings -json [{"target": ..., "buildSettings": {...}}, ...]
- normalized {"settings": [{...}, ...]} emitted by --normalized-json
"""

import argparse
import json
import re
import sys
from pathlib import Path

REFERENCE_PATH = Path(__file__).resolve().parent.parent / "references" / "security-settings-reference.md"
EXTRA_NAMES = {
    "CODE_SIGN_ENTITLEMENTS", "SDKROOT", "SUPPORTED_PLATFORMS", "ARCHS",
    "ARCHS_STANDARD", "ONLY_ACTIVE_ARCH", "PRODUCT_TYPE", "PRODUCT_TYPE_IDENTIFIER",
}
_TABLE_NAME_RX = re.compile(r"^\|\s*`([A-Z][A-Z0-9_]{2,})`\s*\|")
_BACKTICK_VALUE_RX = re.compile(r"`([A-Za-z][A-Za-z0-9_]*)`")
_EXPLICIT_SCOPES = {"target", "project", "xcconfig", "command-line"}
_WARNING_ALTERNATIVES = {
    "GCC_WARN_ABOUT_RETURN_TYPE": {"YES", "YES_ERROR"},
    "GCC_WARN_UNINITIALIZED_AUTOS": {"YES", "YES_AGGRESSIVE"},
}


def load_reference_rules(path=REFERENCE_PATH):
    """Read only first-column setting-table names and their second-column values."""
    rules = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        match = _TABLE_NAME_RX.match(line)
        if not match:
            continue
        name = match.group(1)
        cells = line.split("|")
        values = set(_BACKTICK_VALUE_RX.findall(cells[2]))
        if values:
            rules[name] = values
    if not rules:
        raise ValueError("reference contains no setting/value rules")
    return rules


def _scalar(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, (str, int, float)):
        return str(value)
    raise ValueError("setting values must be JSON scalars")


def _context_string(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("snapshot context must be a string")
    return value


def _native_row(raw, context, source):
    if not isinstance(raw, dict) or not isinstance(raw.get("macroName"), str):
        raise ValueError("each setting row needs a string macroName")
    row = {
        "macroName": raw["macroName"],
        "evaluatedValue": _scalar(raw.get("evaluatedValue")),
        "project": _context_string(raw.get("project", context.get("project", ""))),
        "target": _context_string(raw.get("target", context.get("target", ""))),
        "configuration": _context_string(raw.get("configuration", context.get("configuration", ""))),
        "sdk": _context_string(raw.get("sdk", context.get("sdk", ""))),
        "source": _context_string(raw.get("source", source)),
        "explicitScope": _context_string(raw.get("explicitScope", "unknown")),
        "sourceLocations": raw.get("sourceLocations", []),
    }
    if not isinstance(row["sourceLocations"], list) or not all(
        isinstance(item, str) for item in row["sourceLocations"]
    ):
        raise ValueError("sourceLocations must be a list of scoped source citations")
    if "targetValue" in raw:
        row["targetValue"] = _scalar(raw["targetValue"])
        # Native Xcode exports distinguish a target-level override explicitly.
        # Other formats must provide independently scoped provenance.
        if source == "xcode-export" and "explicitScope" not in raw:
            row["explicitScope"] = "target"
    if "explicitSource" in raw:
        origin = raw["explicitSource"]
        if not isinstance(origin, dict):
            raise ValueError("explicitSource must be a scoped provenance object")
        row["explicitSource"] = {
            key: _context_string(origin.get(key, ""))
            for key in ("scope", "project", "target", "configuration", "sdk")
        }
    return row


def _resolve_snapshot_context(evaluated, declared, label, field):
    """Prefer evaluated context; reject conflicting declared identity, fill gaps only."""
    evaluated = _context_string(evaluated)
    declared = _context_string(declared)
    label = _context_string(label)
    if evaluated and declared and evaluated != declared:
        raise ValueError(f"conflicting evaluated and declared snapshot {field} context")
    return evaluated or declared or label


def normalize_build_settings(payload, *, target="", configuration="", sdk="", project=""):
    """Preserve existing context; labels fill missing metadata, never override it."""
    labels = {"target": target, "configuration": configuration, "sdk": sdk, "project": project}
    if isinstance(payload, dict) and isinstance(payload.get("settings"), list):
        return [_native_row(row, labels, "normalized") for row in payload["settings"]]
    if isinstance(payload, dict) and isinstance(payload.get("buildSettings"), list):
        context = {
            key: _context_string(payload.get(key) or labels[key])
            for key in labels
        }
        if not context["target"]:
            context["target"] = _context_string(payload.get("targetName", ""))
        return [_native_row(row, context, "xcode-export") for row in payload["buildSettings"]]
    snapshots = payload if isinstance(payload, list) else [payload]
    result = []
    for snapshot in snapshots:
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("buildSettings"), dict):
            raise ValueError("unsupported JSON shape: expected native, xcodebuild, or normalized settings")
        settings = snapshot["buildSettings"]
        evaluated_fields = {
            "target": "TARGET_NAME",
            "configuration": "CONFIGURATION",
            "sdk": "SDKROOT",
            "project": "PROJECT_FILE_PATH",
        }
        context = {
            key: _resolve_snapshot_context(settings.get(setting), snapshot.get(key), labels[key], key)
            for key, setting in evaluated_fields.items()
        }
        for name, value in settings.items():
            result.append(_native_row({"macroName": name, "evaluatedValue": value}, context, "xcodebuild"))
    return result


def _has_scoped_explicit_origin(row):
    if row["explicitScope"] not in _EXPLICIT_SCOPES:
        return False
    # Unknown context cannot identify a safe mutation scope.
    if not all(row[key] for key in ("project", "target", "configuration", "sdk")):
        return False
    origin = row.get("explicitSource")
    if origin is not None:
        return origin["scope"] == row["explicitScope"] and all(
            origin[key] == row[key] for key in ("project", "target", "configuration", "sdk")
        )
    return row["source"] == "xcode-export" and row["explicitScope"] == "target" and "targetValue" in row


def classify_setting(row, rules):
    """Classify value and origin independently; never equate inheritance with intent."""
    name, value = row["macroName"], row["evaluatedValue"].strip()
    if name in EXTRA_NAMES:
        return "metadata"
    accepted = rules.get(name)
    if accepted is None:
        return "unknown-setting"
    if not value:
        return "unset-or-unavailable"
    if value in accepted:
        return "hardened"
    if value in _WARNING_ALTERNATIVES.get(name, set()):
        return "weaker-value"
    # Only known off-values of the relevant value family count as disabled.
    off_values = {"none", "disabled"} if "fast" in accepted else {"NO", "FALSE", "0"}
    if value in off_values:
        return "explicitly-disabled" if _has_scoped_explicit_origin(row) else "disabled-origin-unknown"
    return "unsupported-value"


def filter_settings(rows, rules, *, regex=None, unhardened_only=False,
                    target=None, configuration=None, sdk=None, project=None):
    tracked = set(rules) | EXTRA_NAMES
    pattern = re.compile(regex) if regex is not None else None
    result = []
    for row in rows:
        name = row["macroName"]
        if name not in tracked or (pattern is not None and pattern.fullmatch(name) is None):
            continue
        selectors = {"target": target, "configuration": configuration, "sdk": sdk, "project": project}
        if any(value is not None and row[key] != value for key, value in selectors.items()):
            continue
        status = classify_setting(row, rules)
        if unhardened_only and status in {"hardened", "metadata"}:
            continue
        result.append({**row, "classification": status})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saved_file", help="Authorized saved JSON file; '-' reads stdin")
    parser.add_argument("--regex", help="Optional full-match regex restricted to exact tracked names")
    parser.add_argument("--show-overrides", action="store_true", help="Show verified scoped explicit overrides")
    parser.add_argument("--unhardened-only", action="store_true", help="Exclude hardened values and metadata")
    parser.add_argument("--normalized-json", action="store_true", help="Emit normalized rows including classification")
    for key in ("project", "target", "configuration", "sdk"):
        parser.add_argument("--" + key, help="Select context; also label missing metadata with the known snapshot value")
    args = parser.parse_args(argv)
    try:
        if args.saved_file == "-":
            payload = json.load(sys.stdin)
        else:
            with open(args.saved_file, encoding="utf-8") as stream:
                payload = json.load(stream)
        rules = load_reference_rules()
        selectors = {key: getattr(args, key) for key in ("project", "target", "configuration", "sdk")}
        rows = normalize_build_settings(payload, **{key: value or "" for key, value in selectors.items()})
        rows = filter_settings(rows, rules, regex=args.regex, unhardened_only=args.unhardened_only, **selectors)
    except (OSError, ValueError, TypeError, re.error) as error:
        # Do not echo the raw payload, environment, or arbitrary setting values.
        parser.error("invalid input or reference: " + (str(error) if isinstance(error, ValueError) else type(error).__name__))
    if args.normalized_json:
        print(json.dumps({"settings": rows}, indent=2))
    else:
        for row in rows:
            context = " ".join(f"{key}={json.dumps(row[key] or '?')}" for key in ("project", "target", "configuration", "sdk"))
            override = " [scoped-explicit-override]" if args.show_overrides and _has_scoped_explicit_origin(row) else ""
            print(f"[{context}] {row['macroName']}={json.dumps(row['evaluatedValue'])} [{row['classification']}]{override}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
