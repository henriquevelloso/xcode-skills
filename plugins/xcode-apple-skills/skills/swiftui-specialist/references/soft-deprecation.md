# Soft-Deprecated APIs

SwiftUI SDK headers use deprecation versions such as `100000.0` to signal APIs no longer recommended for new code without emitting ordinary deployment-version warnings. They may still compile and work.

## Identify the requested surface

Use [the API index](soft-deprecated-apis.md) to search a specific symbol, then verify against the selected SDK when it differs from the index snapshot. Do not scan unrelated views during a narrow feature or bug fix.

## New code

Prefer the current public replacement for supported targets. Preserve intentional compatibility paths and existing APIs outside the requested scope.

## Read-only review or migration planning

Discuss soft-deprecated usages only in the requested review surface. Explain the replacement and relevant availability as an informational modernization opportunity, not an automatic correctness failure. Return findings or a proposal; do not edit files or require code output to make a review valid.

## Feature implementation or bug fix

Preserve an existing soft-deprecated API if replacing it is unrelated to the requested change. When the directly affected view uses one, briefly identify a separate optional migration if useful. Do not expand the diff or mention unrelated views merely because they share a file.

## Authorized modernization

Apply the requested replacement, confirm runtime/deployment compatibility, and validate the affected behavior. Do not invent availability, API signatures, or permission for project-wide cleanup.
