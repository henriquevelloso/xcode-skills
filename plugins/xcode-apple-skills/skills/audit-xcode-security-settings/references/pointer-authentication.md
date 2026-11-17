# Pointer Authentication

> Technical reference adapted from the supplied export. Setting names, defaults, hardware
> and platform support must be verified against the installed SDK/current Apple docs.
> This describes options, not authorization: audit is read-only; apply only approved
> target/configuration/SDK deltas and validate before/after Debug and Release.

Pointer authentication protects against control-flow hijacking attacks by signing pointers with cryptographic metadata and verifying the signatures before use.

> **Apple developer documentation:** [Preparing your app to work with pointer authentication](https://developer.apple.com/documentation/Security/preparing-your-app-to-work-with-pointer-authentication).

## What It Does

When enabled, the build system adds an **arm64e** slice — it appends `arm64e` to `ARCHS_STANDARD` alongside the existing `arm64`, so the target builds both slices — and arm64e enables pointer authentication. The system:

1. Generates signature metadata for pointers your app creates (memory allocation, C++ object construction)
2. Validates that signatures are unchanged when your app accesses memory through those pointers
3. Crashes your app if a pointer's signature is invalid

This prevents an attacker from overwriting function pointers or return addresses to redirect your app's control flow.

A second slice builds on this one: `arm64e.x1` adds other features on top of pointer authentication. It also raises the pointer-authentication baseline itself, because the compiler targets two features that plain `arm64e` does not:

- **FPAC** — a failed authentication faults at the authenticating instruction, instead of producing a pointer that faults later when it is used.
- **PAC with LR diversity** (`pauth-lr`) — return-address signing mixes in the address of the signing instruction, so a signed return address cannot be replayed at a different call site.

## What Vulnerabilities It Mitigates

- **Control-flow hijacking** — overwriting function pointers, vtable pointers, or return addresses
- **ROP/JOP attacks** — chaining existing code gadgets by corrupting pointer values
- **Code injection via pointer corruption** — modifying data pointers to point to attacker-controlled memory

## How to Enable

**Xcode UI:** Signing & Capabilities > Enhanced Security > check "Authenticate Pointers"

**Build setting:** `ENABLE_POINTER_AUTHENTICATION = Yes`

This is enabled by default when you add the Enhanced Security capability.

For detailed usage, see [Improving control flow integrity with pointer authentication](https://developer.apple.com/documentation/Apple-Silicon/improving-control-flow-integrity-with-pointer-authentication).

## How to Disable

**Xcode UI:** Uncheck "Authenticate Pointers" in the Enhanced Security capability

**Build setting:** `ENABLE_POINTER_AUTHENTICATION = No`

## Swift Package Manager Support

Package dependencies may need additional workspace settings to emit matching device slices.
Inspect current workspace settings and effective package architectures with the active SDK
before proposing a change. Candidate keys from the export are `iOSPackagesShouldBuildARM64e`,
`macOSPackagesShouldBuildARM64e`, and `visionOSPackagesShouldBuildARM64e`; verify current support.

For an embedded workspace, the settings file may be inside
`Project.xcodeproj/project.xcworkspace/xcshareddata/WorkspaceSettings.xcsettings`; for a standalone
workspace it may be inside `Workspace.xcworkspace/xcshareddata/WorkspaceSettings.xcsettings`.
Find the actual workspace rather than constructing a path from the current directory name.
Read and preserve existing keys; do not run unconditional `plutil -create`, replace a shared
settings file, or modify packages during a read-only audit. A new file/key affects package
builds and needs explicit approved scope plus before/after Debug/Release validation.

For a binary package/XCFramework, inspect the artifact's real slices. An absent required
slice can break linking; request a compatible vendor artifact or propose a scoped opt-out.
Neither modifying the dependency nor disabling protection is automatic authorization.

## Library and Framework Authors

Pointer authentication is **highly recommended** for libraries and frameworks distributed to other developers (e.g. a Swift Package, CocoaPod, or `.xcframework`). Enabling it already builds a **universal binary** — `arm64e` is appended alongside `arm64`, so the artifact contains both slices and consumers pick whichever matches their own build. For a distributed target, just make sure the shipped (Release) configuration builds the full arch list. Evaluate artifact size, consumer requirements, effective architecture overrides and dependencies before approval; only one slice is normally loaded at runtime. No library-wide change is automatic. See `universal-binaries-for-libraries.md` for the qualifying product types, the distribution check, and XCFramework guidance.

## Platform Availability

**Platforms that support arm64e:**
- iOS / iPadOS (SDKROOT: `iphoneos`)
- macOS (SDKROOT: `macosx`)
- visionOS (SDKROOT: `xros`)
- DriverKit (SDKROOT: `driverkit`)
- tvOS (SDKROOT: `appletvos`)
- watchOS (SDKROOT: `watchos`)

Every device platform defines an `arm64e` architecture and carries `arm64` in `ARCHS_STANDARD`, so enabling pointer authentication appends an `arm64e` slice on each of them — the build system treats them identically.

**Platforms that do NOT support arm64e:**
- Simulator (any `*simulator` SDKROOT) — the simulator SDKs define no `arm64e` architecture.

When `ENABLE_ENHANCED_SECURITY = YES` cascades `ENABLE_POINTER_AUTHENTICATION = YES` project-wide, `arm64e` is appended to the architecture list for every destination whose `ARCHS_STANDARD` contains `arm64`. This is safe for the Simulator with **no action required**: simulator SDKs define no `arm64e` architecture, so the build system drops `arm64e` from a simulator build's effective architectures automatically. The simulator slice simply builds as `arm64` (plus `x86_64`) without pointer authentication, while device builds still get the `arm64e` slice. Do **not** add an `ENABLE_POINTER_AUTHENTICATION = NO` override for the simulator: it is unnecessary, and an unconditional one would also disable pointer authentication on device builds.

## Performance and Stability Impact

- **Performance:** Low overhead. Pointer signing/verification is done in hardware.
- **Stability:** Code that manipulates raw pointers, casts between function pointer types, or uses inline assembly with pointers may crash. Test thoroughly.
- **Compatibility:** arm64e binaries are separate from arm64. Need to rebuild dependencies as arm64e. **If there are binary dependencies that you don't have the source code for, you will need to reach out to your dependency vendor to get a universal (arm64 and arm64e) version of the dependency.
