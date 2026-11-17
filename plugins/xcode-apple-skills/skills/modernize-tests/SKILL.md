---
name: modernize-tests
description: "Review or incrementally migrate XCTest unit tests to Swift Testing, or modernize existing Swift Testing suites. Preserve test behavior, asynchronous completion, cleanup, isolation, CI discovery, and XCTest UI/performance cases."
---

# Modernize Tests

Use for a requested test review or migration, not automatically during feature work. Read [the migration guide](references/migration-guide.md) for the relevant mappings only.

## Behavior-preserving workflow

1. Inspect compiler settings, runtimes, CI selectors, fixtures, isolation, shared state, and cleanup.
2. Review/planning remains read-only. For implementation, establish original results and discovered case counts, then migrate one suite at a time.
3. Preserve fail-fast, expected failures, skips, callback completion, and cleanup. MainActor and serialized execution address different concerns; inspect both rather than annotate every suite.
4. Keep XCUIAutomation and XCTest performance cases in XCTest. Frameworks may coexist during migration; do not mix their assertion APIs within one migrated test.
5. confirmation does not wait for later callbacks. Its closure must await an operation that guarantees the event occurred, or use a cancellation-aware bridge. Retain XCTest without a safe equivalent.
6. Validate nonzero discovery, preserved coverage/CI selection, passing cases, cleanup, and a controlled failing case that still fails. Parameterization may change case counts; account for that explicitly.
7. Verify SDK-sensitive APIs such as Test.cancel, attachments, traits, and SourceLocation against the selected toolchain. Preserve architecture/production code unless a scoped testability change was requested.

Report exact cases exercised and remaining limits. Syntax checks or framework conversion alone do not prove preserved semantics.
