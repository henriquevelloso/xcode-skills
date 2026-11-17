---
name: app-resizability
description: "Review or fix layouts that change size at runtime, multiwindow, Split View, Stage Manager, and iPhone Duo readiness. Covers local geometry, idiom, asymmetric safe areas, and targeted legacy UIKit/Objective-C API migrations. Preserve existing UI frameworks, architecture, deployment targets, lifecycle, and orientation policy."
---

# App Resizability

Use for a concrete resizing problem, an app readiness review, or a requested migration of screen, orientation, idiom, safe-area, or scene-lifecycle code. This consolidates the former `uikit-app-modernization` skill; use this entrypoint for those legacy migrations too.

## Scope before edits

- Establish the requested surface, affected files, frameworks, deployment targets, scene setup, and selected public SDK. Preserve the project's architecture, data flow, actor isolation, and language mode. Preserve the project's existing UI framework and architecture; this is not an instruction to replace them or introduce a new persistence system.
- For review, audit, diagnosis, or planning, inspect and report without writing project files, adding TODOs, changing configuration, or applying migrations. An already-correct or out-of-scope occurrence is a valid outcome.
- For authorized implementation, fix the demonstrated issue or requested API migration. A broad iPhone Duo or resizing request warrants an initial survey of the relevant task areas, not automatic edits to every task or every file.
- Preserve control flow, guards, fallbacks, existing public callers, orientation policy, lifecycle behavior, and unrelated formatting. Do not manufacture a non-empty diff. Do not remove a branch unless the requested fix and its semantics justify that change.
- Read geometry and traits from the closest appropriate view, window, or scene. Avoid global scene enumeration, device-model heuristics, and hardcoded device sizes.
- An API replacement and its necessary invalidation form one logical change. Preserve deprecated forwarding bridges when required. Retain compatibility on older targets; a newer SDK does not raise the deployment target.
- Resolve a behavior-changing product choice or public signature change with the user only when the session has not already authorized it. If blocked, report the concrete choice; do not insert project TODOs during a read-only review.
- SwiftUI scene apps do not need a SceneDelegate merely because they interoperate with UIKit. Scene-lifecycle migration applies only to an existing legacy UIKit app when relevant and authorized.
- Use available scoped file/CLI tools. This skill supplies no Xcode-only tool aliases, mandatory delegation, or permission to execute exported helpers.

For a whole-project readiness request, inspect the effective launch-screen, supported-orientation and full-screen settings without changing them. Account for target/configuration overrides; do not assume one file always wins. Confirm current Apple requirements before declaring a configuration invalid. If the request names files only, keep that scope and do not search for an unrelated project.

For iOS/iPadOS 27 SDK submissions, check the effective launch-screen configuration against [TN3208](https://developer.apple.com/documentation/technotes/tn3208-preparing-your-apps-launch-screen-to-meet-app-store-requirements). A full-screen key does not prove resizing is disabled: [TN3192](https://developer.apple.com/documentation/technotes/tn3192-migrating-your-app-from-the-deprecated-uirequiresfullscreen-key) describes discrete resizing and migration. Preserve those keys and orientation policy until the applicable behavior change is authorized and tested.

## Workflow

1. Inspect the requested surface and list relevant occurrences with file/line evidence. Classify the actual question: available width/height, display scale, orientation policy, safe area, idiom-dependent behavior, scene ownership, or cached rendering.
2. Read only the matching reference below. In native SwiftUI, prefer the view's environment and actual proposed/available geometry; use UIKit patterns only at an existing UIKit boundary.
3. Separate layout decisions from hardware, assets, analytics, capability gates, and product decisions. A device name, idiom, or orientation alone does not describe a resizable view's space.
4. Recommend or implement the smallest correct replacement, including initial calculation and updates when its inputs change. Follow the selected SDK's availability and automatic-trait-tracking rules; keep a compatible update path on older targets.
5. Record each requested occurrence as changed, already correct, not applicable, out of scope, or blocked with a reason. A scale-only fix does not authorize a scene-lifecycle or orientation-policy migration elsewhere.
6. Validate compilation where code changes. For behavior changes, exercise relevant narrow/wide sizes, live resizing, rotation, safe-area changes without a size change, RTL, scene reconnection, and fallbacks. Build success alone does not prove those runtime paths.

## Task references

- [UIScreen](references/uiscreen-task.md): local scale/bounds, invalidation, compatibility forwarding, and scene geometry when no view/window exists.
- [Orientation](references/orientation-task.md): layout adaptation versus orientation policy; scoped migration of deprecated geometry callbacks.
- [Scene lifecycle](references/scene-lifecycle-task.md): an authorized migration of a legacy AppDelegate-only UIKit app.
- [Safe areas](references/safe-area-task.md): dynamic/asymmetric insets, directional margins, vertical bars, keyboard and scroll containers, and existing SwiftUI safe-area code.
- [Idiom](references/idiom-task.md): available space versus genuine idiom dependence, including native SwiftUI and UIKit interoperability.
