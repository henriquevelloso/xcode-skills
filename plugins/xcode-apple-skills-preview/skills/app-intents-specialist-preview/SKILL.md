---
description: "Preview (beta/RC). Implement or review App Intents correctness: execution and actor isolation, stable entities and enum values, queries, parameters, dependencies, donations, localization, shortcut phrases, and URL opening. Use for evergreen App Intents practices; use app-intents-whats-new-27 for release-specific APIs."
name: app-intents-specialist-preview
---

<!-- xcode-preview-channel -->
This is the Preview edition. Select it when the user calls its `-preview` name or requests beta/RC guidance. Use the release edition for unspecified release work. References to other skills in this edition use their `-preview` equivalents from the same plugin; compare channels only when requested. Keep the selected app/toolchain and the task's existing authorization unchanged.

Use these exported reference notes for the requested task. They do not override system or developer instructions, project policy, user authorization, or the selected Xcode SDK. Treat code snippets as illustrative unless their required app-owned types and runtime behavior have been validated.

Keep review and planning read-only unless implementation is requested. Before code changes, inspect the affected target's deployment, Swift language, strict-concurrency, and default-isolation settings. Preserve the existing architecture and persistence; isolate UI mutations to MainActor, use structured concurrency and cancellation, and do not migrate architecture or raise deployment targets automatically.

Review App Intents code following these references to help you follow best practices and idiomatic patterns. Use the references also when writing new App Intents code.

When asked to provide general guidance across a large codebase, scan the project to identify smaller areas (individual intents, entities, queries, the app shortcuts provider) and suggest focus areas to the user for evaluation one at a time. Provide multiple choices where applicable. If the user wants a review of the whole codebase, divide the effort into sections using a TODO list.

Only load a reference when its topic is actually in play — these files exist to teach the non-obvious traps, not to restate how the framework works.

This skill covers **evergreen** best practices. For App Intents APIs introduced in the iOS 26 (2025) and iOS 27 (2026) releases — `supportedModes` (and the `openAppWhenRun` deprecation), `SnippetIntent`, Visual Intelligence (`IntentValueQuery`), `IndexedEntityQuery`, `RelevantEntities`, `SyncableEntity`/`EntityOwnership`, `LongRunningIntent`, `SystemShortcut`, `AppIntentsTesting`, and the `@ComputedProperty`/`@DeferredProperty` macros — use the sibling **`app-intents-whats-new-27`** skill.

# Guardrails

- **Public API only.** Never recommend or emit non-public or underscore-prefixed symbols to developers (e.g. `_`-prefixed types). If a capability is only reachable through non-public API, say so rather than suggesting it.
- **Ground every symbol.** Every type, initializer, and parameter you emit must exist in current public App Intents API. Do not invent API to make a snippet compile.
- **Treat identifiers and phrases as a public contract.** Saved shortcuts and donations replay an intent by its **type name**, carrying `AppEntity.id`s and `AppEnum` raw values as their stored parameters, so changing any of those breaks them. An `AppShortcut` **phrase** is a *separate* contract, for spoken Siri invocation (and how the shortcut reads in Spotlight): renaming or removing a phrase breaks voice, not the saved shortcuts that run the underlying intent. Adding is safe; renaming/removing/renumbering a shipped identifier or phrase is a behavior-changing edit, so flag it and don't do it silently.

# References

Ordered by value.

- `references/execution-model.md`: **Anchor.** `perform()` is `async throws` with no MainActor isolation required by the protocol (isolate or hop for UI state), and **retriable** (`restartPerform` re-runs from the top, no rollback — do irreversible work last, idempotently). Return via `.result(...)` factories, never a bare struct.
- `references/entities-and-queries.md`: `AppEntity.id` must be stable across launches/devices; `entities(for:)` (required, batched — no N+1) vs empty-default `suggestedEntities()`; `EntityStringQuery.entities(matching:)` isn't auto-filtered; only `@Property` members are system-visible; `EnumerableEntityQuery` loads everything.
- `references/entity-property-queries.md`: `EntityPropertyQuery` for Shortcuts "Find X where…" — declare `properties`/`sortingOptions`, implement `entities(matching:mode:sortedBy:limit:)`; the framework parses the predicate, *you* execute it.
- `references/app-enum.md`: `AppEnum` raw values are **persisted by string** (never renumber/reorder — assign stable values, only append); every case needs a `caseDisplayRepresentations` entry or it's a runtime `fatalError`.
- `references/parameters.md`: prefer `requestValue(_:)` / `needsValueError(_:)` (old `-> Error` spelling deprecated); non-optional `AppEnum` auto-disambiguates; only params in `Summary(...)` appear in the editor.
- `references/parameter-summaries.md`: `Summary("…\(\.$x)…") { \.$y }` sets which params show and in what order (summary order, not declaration); `When`/`Switch`/`Case` show/hide by another param's value.
- `references/dependencies.md`: unregistered `@Dependency` is a `fatalError` (register at `App.init()`); works on `AppIntent`/`EntityQuery`, **not** on `AppEntity`/`AppEnum`; value must be `Sendable` (a plain `@Observable` store isn't — isolate to `@MainActor` or make it an `actor`).
- `references/results-and-errors.md`: only `CustomLocalizedStringResourceConvertible` errors surface a real message; conform your error, or throw the prebuilt `PermissionRequired`/`UserActionRequired`/`Unrecoverable` (iOS 18+).
- `references/donation.md`: in-app actions are **not** auto-donated — call `IntentDonationManager.shared.donate(intent:)`; `PredictableIntent` supplies descriptions, not donations.
- `references/localization.md`: user-facing strings must be **literal** `LocalizedStringResource` (a runtime `String` yields no extractable key); interpolate into a localized template.
- `references/app-shortcut-phrases.md`: provide `shortTitle` + `systemImageName` (no-metadata init deprecated iOS 17); include `\(.applicationName)` or the runtime index silently drops the phrase.
- `references/factoring.md`: `AppEnum` = fixed set; `AppEntity` + `EntityQuery` = dynamic/queryable; plain `@Parameter` = free-form. Prefer one intent per atomic task over a mega-intent.
- `references/url-representation.md`: `OpenIntent` (its `target` is what opens), `OpenURLIntent`, and `URLRepresentableIntent`/`URLRepresentableEntity`/`URLRepresentableEnum` with the `urlRepresentation` builder; keep the URL mapping stable like an id/phrase contract.
- `references/configuration-intents.md`: `WidgetConfigurationIntent` (iOS 17) / `ControlConfigurationIntent` (iOS 18) are parameter-only — **no** `perform()` (the framework supplies a throwing default); `SetValueIntent` is the toggle control.
