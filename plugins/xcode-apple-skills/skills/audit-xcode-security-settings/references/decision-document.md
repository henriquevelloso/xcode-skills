# Optional Decision Document

This is a user-requested audit record, not an automatic artifact. In audit/review/plan
mode, present decisions in the conversation. Only create/update a file when the user
explicitly requests it and approves its path. Saving does not authorize applying settings,
project registration, deleting a plan, or a Git operation.

## Read and merge safely

- Read the existing approved file before editing; preserve user notes and organization.
- Record only scoped decisions from this task, with project/target/configuration/SDK.
- Keep previous rationale/history when a decision changes; do not remove unrelated entries.
- Distinguish observed effective values, proposed/deferred changes, explicit opt-outs,
  undocumented overrides and unavailable evidence.
- Describe validations performed and still pending. A setting marked enabled is not
  equivalent to tested on hardware or accepted for distribution.

## Suggested structure

```markdown
# Xcode Security Settings

Project and toolchain: recorded from the inspected project and SDK.
Scope: exact targets, configurations and SDK/destinations.

## Observed active settings

| Target / configuration / SDK | Setting | Value | Source evidence | Validation |
|---|---|---|---|---|

## Approved changes

| Scope | Old / new value | Approval | Before / after evidence | Pending gates |
|---|---|---|---|---|

## Deferred or disabled

| Scope | Setting | Observed / proposed value | Rationale | Revisit condition |
|---|---|---|---|---|

## Unknowns

Missing source origin, unavailable SDK symbols, missing tests/device/archive evidence.
```

Record only privacy-safe setting details and citations, never full environment dumps,
credentials or private user content. Report the saved path and exact files changed. Do not
register the document in an Xcode project or delete anything unless separately requested.
