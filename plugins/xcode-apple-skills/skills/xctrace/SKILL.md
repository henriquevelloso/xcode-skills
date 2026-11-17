---
name: xctrace
description: "Inspect Instruments .trace or .atrc recordings with xctrace, diagnose recorded hangs, or capture a requested performance trace. Use for trace commands and interpretation; general performance design alone does not require tracing."
---

# Xcode Trace Analysis

Read [the command and trace overview](references/xctrace-overview.md) before using xctrace. For recorded hangs, also read [hang triage](references/xctrace-hangs-triage.md).

Use the Xcode toolchain selected for the task through per-command `DEVELOPER_DIR`; do not change global `xcode-select`. Refresh the installed command's help before assuming a subcommand or flag exists. Beta command availability does not establish release support.

Start from the supplied trace and the question it can answer: inspect the table of contents, discover concrete tracks, then request the relevant summary, list, or call tree. Distinguish sampling evidence from complete event data, busy from blocked hangs, and missing symbols from missing activity. State when the recording cannot establish a conclusion.

An analysis request authorizes analysis of the supplied recording. Capture only a requested app/device and bounded interval when recording is in scope. Read-only analysis must not launch apps, record device activity, change permissions, or modify the source recording. For symbolication, import, or remodeling that writes files, use a separate output or copy unless replacement was requested. Existing user authorization governs these actions.

Match dSYM UUIDs to the recorded binary, filter large output, and report commands, time ranges, evidence, and untested limits. A parsed trace or CLI help check is not a successful performance fix or a device test.
