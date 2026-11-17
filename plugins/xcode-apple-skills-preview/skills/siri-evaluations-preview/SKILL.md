---
name: siri-evaluations-preview
description: "Preview (beta/RC). Write, run, and analyze SiriEvaluations scenarios, which measure how well Siri selects and fills in an app's App Intents. Use when the developer wants to evaluate how Siri uses their App Intents, App Entities, or App Skills; to add or fix a Siri scenario or expectation; to run a Siri evaluation or fix one that fails before grading; or to explain why a Siri scenario failed and what to change in the app. Takes an optional stage: write, run, or analyze."
argument-hint: "[write | run | analyze]"
---

<!-- xcode-preview-channel -->
This is the Preview edition. Select it when the user calls its `-preview` name or requests beta/RC guidance. Use the release edition for unspecified release work. References to other skills in this edition use their `-preview` equivalents from the same plugin; compare channels only when requested. Keep the selected app/toolchain and the task's existing authorization unchanged.

SiriEvaluations tests how Siri uses an app's App Intents. A test describes what a user says to Siri,
turn by turn, and what Siri should do in response: which intents it calls and with which parameters,
which entities it finds, which App Skills it loads, and what it replies. Running the test drives Siri
and produces a report that grades each expectation. This skill writes those tests, runs them, and
explains the report.

# Guardrails

- **Public API only.** Write evaluations with the public SiriEvaluations API the references show.
  Never emit underscore-prefixed symbols.
- **Ground every name.** Every intent, entity, parameter, and App Skill name in a scenario comes from
  the app's source. Don't invent one to make a scenario compile.
- **Identifiers are a contract.** When a fix belongs in the app, don't make it by renaming an intent or
  entity type, changing an `AppEntity` id scheme, renumbering an `AppEnum`, or adding, removing, or
  renaming a parameter. That breaks existing integrations and every scenario that names them. Flag
  such a change instead of making it.
- **Respect the requested stages.** A write-only or analyze-only request does not authorize a device run or app changes. When the developer requests the complete loop, proceed through the authorized stages in order. Running drives Siri on a physical device; review remains read-only unless fixes were requested.

# Choosing the stage

| Stage | The developer wants to… | Read |
|---|---|---|
| `write` | create or change Siri scenarios and expectations from the app's App Intents | references/writing.md, then references/api.md as needed |
| `run` | run the evaluation on a device, find its report, or fix an error that stopped it before grading | references/running.md |
| `analyze` | understand why scenarios failed and what to change in the app or the test | references/analyzing.md |

Use the stage the developer named (`/siri-evaluations analyze`, "just run them"). "Diagnose" and
"explain" mean `analyze`. Otherwise, infer it from the request; if it could be more than one, ask. A
request for the whole loop ("get my app passing a Siri evaluation") starts at the first stage whose
prerequisites aren't met.

Read only the references for the chosen stage.

# Toolchain and device scope

This Preview comes from Xcode 27.3 beta (27C5020n). Verify the matching public SiriEvaluations framework and use per-command `DEVELOPER_DIR`; do not switch global Xcode selection. Device runs require a compatible physical device; simulators are unsupported. Do not enable Developer Mode, Siri, Apple Intelligence, Automation Mode, or change accounts as an automatic fix. Have the developer complete required device setup and enter any passcode themselves. Metadata and scenarios may contain real app data; keep reports local unless sharing was requested.

# Prerequisites

Before starting a stage, check that what it needs exists:

- **Tests**, needed by `run`: a test target with a SiriEvaluations suite (search the test sources for
  `SiriService.run(scenario:`, `SiriScenarioLoader`, and `.evaluates(`).
- **A report**, needed by `analyze`, in order of preference: one the developer points to, the result
  bundle of a run earlier in this conversation, or the newest `.xcresult` in the project's
  DerivedData `Logs/Test/` that contains a Siri evaluation. A report older than the last change to the
  tests or to the app's App Intents code is stale.

When something is missing, say what, and offer to produce it before continuing.
Continue through missing prerequisites already authorized by the request. Ask only when an additional stage or material change is outside that scope, then follow each stage's own guardrails.