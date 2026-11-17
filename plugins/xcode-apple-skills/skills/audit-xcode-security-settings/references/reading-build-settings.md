# Reading and Classifying Build Settings

## Scope and provenance first

A setting is meaningful only for its **project × target × configuration × SDK/destination**.
Keep that identity with every saved snapshot and row. Read source ownership from linked
PBXProject/PBXNativeTarget configuration objects, base xcconfig references, include chains,
and matching conditional selectors. Project-wide grep counts are not override evidence.

An evaluated value says what one invocation sees, not where it was set. An inherited `NO`
may be the toolchain default or a project/xcconfig override. Do not label it deliberately
disabled without a scoped source and documented rationale. `xcodebuild` JSON alone does
not expose `targetValue`; target-level origin remains unknown until the source is inspected.

## Accepted saved JSON formats

The helper accepts native Xcode export rows:

```json
{
  "project": "Example.xcodeproj",
  "target": "Example",
  "configuration": "Release",
  "sdk": "iphoneos",
  "buildSettings": [
    {"macroName": "ENABLE_ENHANCED_SECURITY", "evaluatedValue": "NO", "targetValue": "NO"}
  ]
}
```

Native `targetValue` means a target override in that snapshot. Missing evaluated values
are unknown/empty, not `NO`. Actual tool schema can differ: read its description and adapt
saved data explicitly; do not fabricate a native tool call. The optional metadata above
must identify the query actually performed, not a desired destination.

Standard `xcodebuild -showBuildSettings -json` output is a list of snapshots:

```json
[
  {
    "target": "Example",
    "buildSettings": {
      "PROJECT_FILE_PATH": "Example.xcodeproj",
      "CONFIGURATION": "Release",
      "SDKROOT": "iphoneos",
      "CLANG_CXX_STANDARD_LIBRARY_HARDENING": "fast"
    }
  }
]
```

For these snapshots, context precedence is evaluated `buildSettings` fields
(`PROJECT_FILE_PATH`, `TARGET_NAME`, `CONFIGURATION`, `SDKROOT`), then matching top-level
`project` / `target` / `configuration` / `sdk` metadata, then fill-only CLI labels.
This preserves declared metadata even when evaluated context fields are missing.
If both evaluated and top-level context are present but differ, the helper rejects the
input rather than silently changing identity. Supply identical, authoritative identifiers
at both levels; it does not guess whether a project name and filesystem path are equivalent.
CLI labels never override existing context; selectors can therefore produce zero matches.

The helper also accepts its normalized envelope `{"settings": [...]}`. Each normalized
row has `macroName`, `evaluatedValue`, `project`, `target`, `configuration`, `sdk`, `source`,
`explicitScope`, and `sourceLocations`. A supplied `targetValue` is preserved, not inferred.
To annotate an origin verified by scoped source inspection, add both `explicitScope`
(`target`, `project`, `xcconfig`, or `command-line`) and a matching `explicitSource` object:

```json
{
  "scope": "xcconfig",
  "project": "Example.xcodeproj",
  "target": "Example",
  "configuration": "Release",
  "sdk": "iphoneos"
}
```

Populate `sourceLocations` with exact file/line/property evidence. The helper checks that
all `explicitSource` identity fields match the row; it does **not** parse pbxproj/xcconfig
itself or verify the authenticity of supplied provenance. If origins are missing/mismatched,
report `disabled-origin-unknown` instead of a verified override. Even a verified override
is not a claim about user intent. Missing target/configuration/SDK/project prevents a scoped
explicit-disable classification and must block automatic mutation decisions.

## Read-only helper usage

Resolve `SKILL_ROOT` to the folder containing this skill's `SKILL.md`. Use an authorized
saved input; the helper does not run Xcode, create files, or change settings.

```sh
python3 "$SKILL_ROOT/scripts/filter_build_settings.py" "$SAVED_JSON"
python3 "$SKILL_ROOT/scripts/filter_build_settings.py" "$SAVED_JSON" --show-overrides
python3 "$SKILL_ROOT/scripts/filter_build_settings.py" "$SAVED_JSON" --unhardened-only
python3 "$SKILL_ROOT/scripts/filter_build_settings.py" "$SAVED_JSON" --normalized-json
```

`--project`, `--target`, `--configuration`, and `--sdk` select an exact existing context and
fill missing metadata **only with a known label from the query actually performed**. They
never overwrite existing metadata, collapse different targets/configurations, or turn an
unscoped grep hit into an override. Do not use labels to reclassify unrelated evidence.

`--regex` is optional and uses full-name matching within the tracked-name set. A custom
regex cannot introduce arbitrary environment/build settings into the report. The normal
filter parses names/values from first-column setting rows in `security-settings-reference.md`,
not every uppercase backtick token. It also keeps limited context metadata such as entitlements
path, platforms and architectures. `--unhardened-only` excludes metadata and hardened rows,
but keeps unknown/unavailable and weaker security values visible.

Text output is context-tagged and JSON-quotes values. `--normalized-json` writes JSON only
to stdout; saving it to a file is a separate user-authorized operation. Do not dump full
raw build settings: they may contain secrets or private environment values.

## Value families and classifications

| Classification | Meaning | Audit action |
|---|---|---|
| `hardened` | Value matches the documented per-setting rule | Record applicable protection; do not claim runtime proof |
| `weaker-value` | Valid warning level below the proposed scoped hardening value | Propose change only if warranted/approved |
| `explicitly-disabled` | Known off-value and matching explicit origin + complete identity | Read rationale; do not infer intent or auto-enable |
| `disabled-origin-unknown` | Known off-value, no verified matching origin | Inspect scoped source; never assume default or deliberate opt-out |
| `unset-or-unavailable` | Empty/missing evaluated value | Check SDK availability and query context |
| `unsupported-value` | Value outside the documented family | Verify SDK/source; do not treat as `NO` |
| `metadata` | Context/path/architecture setting, not a security toggle | Use for eligibility and exact file resolution |

Boolean settings use their documented value, usually `YES`. The two warning-level settings
use `YES_ERROR` and `YES_AGGRESSIVE`; a plain `YES` is weaker, not disabled. C++ library
hardening is an enum: `fast`, `debug`, and `extensive` are hardened modes; `none`/`disabled`
are off. A valid mode may still differ from the intended Debug/Release policy: report that
separately, do not misclassify it as disabled. Verify modes against the installed SDK.

## Evidence table and readback

Use one row per project/target/configuration/SDK/setting, including:
- Snapshot command/tool and Xcode/SDK version/date.
- Evaluated value, applicability, desired value, and classification.
- Source level, matching conditional selectors, include chain and exact citations.
- Relevant shared files/targets, entitlement state and actual effective architectures.
- Observed vs proposed vs unknown, approval and validation status.

For project-level inheritance, inspect the relevant **PBXProject** configuration object's
build settings or project base xcconfig linkage, then read each affected target's evaluated
value. A PBXNativeTarget `YES` can override a project `NO`, so a grep match anywhere cannot
prove project-level enablement. Re-read after approved changes; never reuse pre-edit
snapshots as post-edit validation. Product type comes from actual tool/project evidence,
not inference from names. Aggregate targets have no executable product.

## Regression tests for the helper

Run only these local fixture-based tests when authorized; they do not run Xcode:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$SKILL_ROOT/tests" -v
```

They check normalization, exact matching, enum/boolean handling, project/target/config/SDK
isolation, origin mismatches, unknown metadata, error paths and stdout CLI roundtrips.
Passing these tests validates the helper, not an app, live MCP, active SDK or release.
