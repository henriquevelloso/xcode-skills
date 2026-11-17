# Portable Audit and Approved Apply Workflow

## Contents
- Audit evidence and scope
- Proposed changes and approval
- Approved implementation
- Validation and release evidence
- Optional decision record

## Audit evidence and scope

1. Identify the actual project/workspace, schemes and relevant targets. Do not infer
   project name from the working-directory basename. Inspect source-control status
   read-only when available; do not create a repository, commit, or clean changes.
2. Discover available tools and their documented input/output schema. Native Xcode
   tools, XcodeBuildMCP, and scoped file reads are alternatives, not aliases. If a tool
   is absent, do not guess a prefix or loop on unknown-tool errors.
3. Record installed Xcode/SDK, existing deployment targets, configurations, and
   destinations. For iOS 27 settings, verify their existence and signatures in an
   installed compatible SDK and current Apple documentation. Local beta SDK support
   does not prove App Store Connect accepts that SDK.
4. Enumerate targets from tool output or parse the project structure read-only. Keep
   the containing project plus target identity; names can collide across projects.
   Aggregate targets have no executable product. Distinguish app/executable, helper,
   app extension, test bundle, and library/framework. Do not grant process entitlements
   to libraries or unsupported product types.
5. Detect each target's compiled languages, including Objective-C++, file-type overrides,
   excluded sources, and linked code. A workspace-wide `.cpp` match is not evidence
   that every target compiles C++. Preserve Swift concurrency/language-mode settings.
6. Collect the exact target × configuration × SDK/destination snapshots in scope,
   including Debug and Release for proposed changes. Prefer saved authoritative output
   for strict read-only work. If CLI queries are authorized, use the active toolchain
   explicitly and verify relevant flags from its help, for example:

   ```sh
   DEVELOPER_DIR="$XCODE_DEVELOPER_DIR" xcodebuild \
     -project "$PROJECT_PATH" -scheme "$SCHEME" \
     -configuration "$CONFIGURATION" -destination "$DESTINATION" \
     -showBuildSettings -json -disableAutomaticPackageResolution -skipPackageUpdates
   ```

   Use `-workspace` instead of `-project` when appropriate, never both. These flags
   reduce package-update side effects; they do not guarantee zero filesystem writes.
   Do not resolve/download packages or change `Package.resolved` during a read-only
   review. When queries cannot run safely, report effective values as unverified and
   continue using source evidence. Do not invent configuration/SDK labels.
7. Read the scoped xcconfig include chain and the PBXProject/PBXNativeTarget configuration
   objects. Associate each source location with the owning configuration and target.
   Honor conditional assignments such as `[sdk=iphoneos*]`. A text-search hit is a
   discovery clue only, not proof of an active override or inherited project setting.
8. Read the evaluated `CODE_SIGN_ENTITLEMENTS` for each snapshot, then resolve that
   path with the tool's documented path semantics or the authoritative `SRCROOT`.
   Inspect the referenced file; do not pick an orphaned glob match. Detect files and
   xcconfigs shared by multiple targets/configurations before proposing edits.
9. Normalize saved settings with the helper described in `reading-build-settings.md`.
   Include proposed values, observed values, source provenance, applicability, and
   evidence gaps. `fast`, `debug`, and `extensive` are hardened C++ modes, not booleans.
   Missing values and unrecognized settings are unknown. An explicit `NO` means an
   observed override, not necessarily deliberate user intent; consult existing notes.

Return the audit and proposed change matrix **in the conversation**. Audit completion
must not write a plan/decision document, register a project file, alter entitlements,
enable settings, or delete anything. File creation needs a separate explicit request.

## Proposed changes and approval

For each recommendation identify:
- Project, target, configuration, SDK/destination and owning file/property.
- Current evaluated value and source, proposed value, and reason/language relevance.
- Entitlement keys and types, dependent settings, shared-file blast radius and opt-outs.
- Expected diagnostics, compatibility risks and before/after validation required.

Offer small deltas: warnings/static analysis separately from runtime protections; hardware
memory tagging separately from fatal checked-pointer-arithmetic enforcement. No options
are considered approved merely because a template marks them checked. Project-wide
`ENABLE_ENHANCED_SECURITY=YES` affects inherited targets and future ones: propose it only
when the user wants that scope and the consequences have been reviewed.

Only proceed when the user explicitly requests applying the concrete changes. Audit,
review, planning, or permission to save a report does not grant apply permission. If new
required changes appear, stop the affected item and request the exact scope extension.
Do not repeatedly prompt on a missing tool or ambiguous user response.

## Approved implementation

1. Re-read current source/effective settings before the edit; the audit can be stale.
   Preserve unrelated uncommitted changes and the project's existing configuration method.
   Do not introduce xcconfig, replace entitlements, or edit a shared file to affect unapproved
   consumers. Prefer narrower target/configuration overrides if supported and approved.
2. Edit the owning xcconfig or a documented project-scoped configuration tool. A structured
   project-file edit is a fallback only when its object/configuration linkage is understood;
   otherwise guide the user to the precise Xcode UI change and read back its actual scope.
   Do not claim project-level success from `grep ENABLE_ENHANCED_SECURITY` anywhere.
3. If process hardening is approved, apply both the build and entitlement halves required
   by the installed SDK. Use typed entitlement updates or minimal plist edits preserving
   unrelated keys. Creating a missing file and wiring `CODE_SIGN_ENTITLEMENTS` are separate
   deltas requiring approval. Shared entitlement files expand scope unless narrowed first.
4. For pointer authentication, inspect source packages, prebuilt framework/XCFramework slices,
   the effective architectures and Release `ONLY_ACTIVE_ARCH`. A simulator build cannot
   validate device slices. Missing binary slices may require vendor support or a specific
   opt-out; do not disable protections or modify dependencies without approval.
5. Memory tagging can uncover latent bugs. When approved, stage soft-mode diagnostics and
   review them before enforcing. Checked pointer arithmetic has separate requirements and
   no soft mode; memory-tagging soft mode does not make its faults nonfatal. Do not enable
   fatal enforcement as a blanket companion to a warning audit.
6. Scope diagnostic settings by compiled language. Preserve documented choices and existing
   per-configuration values. C bounds-safety annotation work and buffer rewrites are separate
   implementation scopes. `adopt-c-bounds-safety` is not bundled in this personal plugin;
   offer an explicit follow-up or current official Clang documentation, not a missing skill.
7. Read back every approved setting/entitlement in the same target/configuration/SDK matrix.
   Show a scoped diff and report partial failures; never claim atomic success. No automatic
   undo of unrelated edits, file deletion, Git operation, installation or upload is allowed.

## Validation and release evidence

Before applying compile/runtime hardening, establish an authorized **before** baseline.
After approved changes, require the same **after** checks for affected Debug and Release
configurations and relevant SDK/destinations. If builds/tests were not requested or cannot
be run, report them pending and do not label the change validated or release-ready.

| Evidence | What it proves | What it does not prove |
|---|---|---|
| Scoped source + effective settings readback | Intended configuration and inheritance | Successful compilation or runtime protection |
| Debug and Release builds, before/after | Compilation/linking for each tested destination | Device behavior, archive, signing or ASC acceptance |
| Build-and-analyze, where relevant | Enabled analyzer checks actually executed | Absence of all vulnerabilities |
| Targeted/full tests with nonzero counts, before/after | Tested behavior under the recorded configuration | Untested paths, purchases or accessibility |
| Simulator smoke tests + logs | Tested simulator behavior | arm64e/arm64e.x1 enforcement or hardware tagging |
| Supported physical device + runtime/crash diagnostics | Tested device enforcement and stability | Other hardware/configurations or distribution acceptance |
| Authorized archive/export + signing/entitlement/slice inspection | Distribution artifact integrity for that configuration | ASC processing, TestFlight installation or App Review approval |

Static review must not trigger builds, test runs, device/simulator interaction, or archive
creation implicitly. When this work is authorized, capture commands/tool inputs, Xcode/SDK,
configuration, destination, exit status, executed test counts and relevant privacy-safe
failures. Use existing test plans; avoid deleting user stores or resetting real devices.
For apps with durable content, compare approved test data before/after. For SnapSong,
verify audio, titles, lyrics, tags, cover art, dates, favorites and identifiers explicitly.

After hardening, investigate crashes/diagnostic reports on capable hardware and record
performance evidence when the risk warrants it. Valid settings and successful builds alone
are insufficient for release readiness. Distribution/account operations remain separately
approved; never assume a beta-SDK artifact is eligible for submission.

## Optional decision record

Only if explicitly asked to save/update one, follow `decision-document.md` at the approved
path. Saving does not imply project registration, committing, deleting an earlier plan,
changing security settings, or performing validation. Leave evidence gaps visible.
