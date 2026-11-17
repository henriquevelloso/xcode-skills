---
name: audit-xcode-security-settings-preview
description: "Preview (beta/RC). Audit security-oriented Xcode compiler settings and runtime hardening, or apply specifically approved configuration changes. Use for build-configuration security reviews, warnings, static analysis, and Enhanced Security; not a replacement for privacy, network security, or signing audits."
---

<!-- xcode-preview-channel -->
This is the Preview edition. Select it when the user calls its `-preview` name or requests beta/RC guidance. Use the release edition for unspecified release work. References to other skills in this edition use their `-preview` equivalents from the same plugin; compare channels only when requested. Keep the selected app/toolchain and the task's existing authorization unchanged.

# Audit Xcode Security Settings

Inspect the existing target/configuration matrix before recommending compiler warnings,
Enhanced Security, pointer authentication, memory tagging, or checked pointer arithmetic.
Preserve deployment targets, architecture, storage, dependencies, and documented opt-outs.

## Select the operating mode

- **Audit / review / plan:** read-only by default. Return findings and a proposed change
  matrix in the conversation. Do not change settings, entitlements, source, schemes,
  project registration, or create/update/delete a report file. Saving a report requires
  a separate explicit request; it does not authorize project registration or cleanup.
- **Apply:** only when the user explicitly requests implementation of specific changes.
  Confirm the affected project, targets, configurations, destinations, and setting/value
  or entitlement deltas. A generic security audit, skill invocation, or checked box in a
  generated template is not authorization. Resolve ambiguous or expanded scope before
  mutation. Never blanket-enable hardening across current or future targets.
- No mode authorizes Git operations, installations, global toolchain changes, account
  writes, uploads, production modifications, or destructive cleanup. Runtime/build work
  also needs authorization appropriate to the current request and workspace policy.

Read [references/workflow.md](references/workflow.md) for the detailed discovery,
approval, apply, and validation procedure. Its validation matrix separates a settings
inspection from compilation, runtime, device, and distribution proof.

## Discover capabilities, do not assume Xcode tools

Inspect the current tool registry. Use actual project-scoped MCP tools when available;
do not assume exported names such as `XcodeGlob`, `GetTargetBuildSettings`,
`AddEntitlement`, `AskUserQuestion`, or `TaskCreate` exist. Use ordinary conversation for
questions and a local evidence table for progress; no proprietary task API is required.

If useful capabilities are absent, scoped file reads and installed Xcode CLIs are valid
fallbacks. Inspect the actual project/workspace and active SDK. Set `DEVELOPER_DIR` per
command if selecting another installed Xcode; never change global `xcode-select`.
Verify CLI flags against that toolchain's help before use. Do not fabricate SDK support
or a tool signature. State unresolved capabilities and continue with static evidence.

An `xcodebuild -showBuildSettings -json` query can resolve dependencies or write caches.
For a strict no-side-effect review, prefer existing saved evidence and project-file
reads. Do not permit package updates/resolution, lockfile changes, or run builds merely
to produce an audit unless the user/workspace scope authorizes them.

## Build-setting evidence and helper

Read [references/reading-build-settings.md](references/reading-build-settings.md) for
target/configuration/SDK scoping, source provenance, and supported JSON formats.
The read-only helper [scripts/filter_build_settings.py](scripts/filter_build_settings.py)
normalizes saved native-Xcode exports and `xcodebuild` JSON, filters **exact** tracked
setting names, and classifies values per setting. It never runs Xcode or modifies files.
Use it only on authorized saved input; its results do not prove the live configuration.

Never infer a target's override or user intent from project-wide text-search counts.
Never infer project-level inheritance from a grep hit anywhere in `project.pbxproj`.
Treat missing context, unresolved origins, unexpected values, and unavailable settings
as unknown, not as disabled. A valid `fast`/`debug` C++ hardening mode is not a boolean.

## Load only relevant technical references

- [security-settings-reference.md](references/security-settings-reference.md): tracked
  names, proposed values, language scope, and runtime entitlement families.
- [enhanced-security.md](references/enhanced-security.md): build-setting/entitlement
  halves, executable versus library targets, and platform eligibility.
- [pointer-authentication.md](references/pointer-authentication.md) and
  [universal-binaries-for-libraries.md](references/universal-binaries-for-libraries.md):
  binary dependencies, Swift packages, and distributed slices.
- [hardware-memory-tagging.md](references/hardware-memory-tagging.md) and
  [checked-pointer-arithmetic.md](references/checked-pointer-arithmetic.md): hardware
  requirements, soft-mode limits, and potential crashes. Verify against the installed
  SDK and current Apple documentation before changing version-specific settings.
- [security-compiler-warnings.md](references/security-compiler-warnings.md),
  [cpp-hardening.md](references/cpp-hardening.md),
  [typed-allocators.md](references/typed-allocators.md),
  [stack-zero-init.md](references/stack-zero-init.md),
  [readonly-platform-memory.md](references/readonly-platform-memory.md), and
  [runtime-restrictions.md](references/runtime-restrictions.md): individual protections.
- [additional-settings.md](references/additional-settings.md) and
  [adoption-strategy.md](references/adoption-strategy.md): opt-in diagnostics and staged
  validation, not blanket enablement orders.
- [decision-document.md](references/decision-document.md): optional record only when
  the user explicitly asks to save/update one.

## Report

Lead with observed findings, impact, exact target/configuration/SDK and file/line evidence.
Separate hypotheses and recommendations. Show only scoped setting values; do not dump
environment variables, credentials, or private app data. Report approved deltas separately
from deferred/unknown items and list what was actually validated versus still pending.
