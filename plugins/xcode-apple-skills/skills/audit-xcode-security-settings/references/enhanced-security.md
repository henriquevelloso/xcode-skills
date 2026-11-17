# Enhanced Security

> Technical reference adapted from the supplied export. Setting names, defaults, hardware
> and platform support must be verified against the installed SDK/current Apple docs.
> This describes options, not authorization: audit is read-only; apply only approved
> target/configuration/SDK deltas and validate before/after Debug and Release.

Enhanced Security is an Xcode capability, not just a build setting. Enabling it fully touches **two places per target**:

1. Build settings (in pbxproj or xcconfig) — `ENABLE_ENHANCED_SECURITY` + pointer authentication.
2. Entitlements (in the target's `.entitlements` file) — the runtime-protection keys.

`ENABLE_ENHANCED_SECURITY = YES` is the build setting that turns on the compiler-driven pieces. The **Enhanced Security entitlements** (the `com.apple.security.hardened-process` key family) turn on the runtime-driven pieces and are what actually provisions the capability.

## Apple developer documentation

- [Enabling Enhanced Security for your app](https://developer.apple.com/documentation/Xcode/enabling-enhanced-security-for-your-app) — the canonical how-to.
- [Creating enhanced security helper extensions](https://developer.apple.com/documentation/Xcode/creating-enhanced-security-helper-extensions) — for XPC services / system extensions / driver extensions called from a hardened host.
- [Entitlements](https://developer.apple.com/documentation/BundleResources/Entitlements) — overview of every entitlement, including the `com.apple.security.hardened-process` family used below.

## Supported Product Types

Enhanced Security only applies on iOS, macOS, visionOS, and DriverKit, to these product types. Skip any target whose product type isn't in this list (frameworks, test bundles, app extensions other than those below, etc.) or whose platform isn't one of those four.

- `com.apple.product-type.application`
- `com.apple.product-type.application.on-demand-install-capable`
- `com.apple.product-type.xpc-service`
- `com.apple.product-type.driver-extension` (**build settings only** — entitlements do not apply to DriverKit)
- `com.apple.product-type.system-extension`
- `com.apple.product-type.tool`

## Libraries and Frameworks

Library and framework targets (frameworks, static frameworks, static libraries, dynamic libraries) are deliberately absent from the supported product-type list above — the Enhanced Security entitlements (the `com.apple.security.hardened-process` key family) apply only to executable targets that run directly on the OS, not to code linked into someone else's executable. The audit therefore skips entitlement edits on these targets.

Compiler protections can benefit library/framework targets too. If approved and supported by the active SDK/effective architecture settings, pointer authentication can add an `arm64e` slice alongside `arm64`. Review binary dependencies, consumer compatibility and artifact size before choosing that scope. This is a recommendation to evaluate, not a blanket instruction to alter every library. See `universal-binaries-for-libraries.md` for packaging checks.

## Part A — Build Settings

For a target/configuration where enabling this capability is explicitly approved, verify:

- `ENABLE_ENHANCED_SECURITY = YES` — listed in the capability's `requiredValues`. Cascades automatically to pointer authentication, stack zero init, security compiler warnings, typed allocators, and C++ stdlib hardening (the audit does not manipulate these cascaded settings directly).

The approved apply path is in `workflow.md`:

1. Select the existing owning configuration source and exact approved targets/configurations. A project-level change is appropriate only when its inherited current/future-target scope is explicitly approved. Verify PBXProject configuration linkage or project-level xcconfig ownership and each effective target value; a grep hit anywhere in the project is insufficient.
2. Inspect actual tools and use their documented interfaces or a minimal structured file edit. No exported tool name is required. Preserve existing overrides, and do not create a new configuration method automatically.
3. Read back simulator/device architectures and validate both Debug/Release. Simulator SDKs normally omit `arm64e`; do not add a blanket opt-out based on a failed device link. If a binary dependency lacks required slices, propose a scoped mitigation or vendor follow-up instead of silently disabling protection. See `pointer-authentication.md`.

A second build setting is relevant but outside the cascade: `ENABLE_HARDWARE_CHECKED_POINTER_ARITHMETIC_SLICE = YES` adds the `arm64e.x1` slice, which is a pre-requisite for run time enforcement of checked pointer arithmetic. It defaults to `NO`, is never set implicitly, and applies per target. See `checked-pointer-arithmetic.md`.

## Part B — Entitlements

Read each snapshot's evaluated `CODE_SIGN_ENTITLEMENTS` and inspect that referenced file. Multiple targets can share a file; do not assume one file per target. Audit is read-only; creating/wiring a missing file or changing shared keys requires explicit approved scope.

Required when the capability is enabled:

- [`com.apple.security.hardened-process`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process) `= <true/>` — the main toggle. Without this, the runtime protections below are inert.
- [`com.apple.security.hardened-process.enhanced-security-version-string`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process.enhanced-security-version-string) `= "2"` — selects v2 protections.

Default-ON sub-options (the audit reports missing keys; only approved apply changes them):

- [`com.apple.security.hardened-process.hardened-heap`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process.hardened-heap) — Memory Safety category. Adds extra type-isolation buckets to the allocator at runtime, regardless of compiler settings. Most effective in combination with the cascaded `CLANG_ENABLE_C_TYPED_ALLOCATOR_SUPPORT` / `CLANG_ENABLE_CPLUSPLUS_TYPED_ALLOCATOR_SUPPORT` build settings, which communicate type information from the compiler to the allocator.
- [`com.apple.security.hardened-process.dyld-ro`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process.dyld-ro) — Runtime Protections. Marks dyld state read-only.
- [`com.apple.security.hardened-process.platform-restrictions-string`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process.platform-restrictions-string) `= "2"` — Runtime Protections. Dyld + Mach messaging restrictions.

Default-OFF sub-options (audit reports state, does **not** auto-enable):

- [`com.apple.security.hardened-process.checked-allocations`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process.checked-allocations) and its related keys — Hardware Memory Tagging (MTE). See `hardware-memory-tagging.md` for supported hardware. Recommend soft-mode rollout when reporting state.
- [`com.apple.security.hardened-process.checked-allocations.enforce-checked-pointer-arithmetic-overflow`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process.checked-allocations.enforce-checked-pointer-arithmetic-overflow) — Checked Pointer Arithmetic (CPA2). Also needs the `arm64e.x1` slice from `ENABLE_HARDWARE_CHECKED_POINTER_ARITHMETIC_SLICE` for run time enforcement. See `checked-pointer-arithmetic.md`.

## Settings implied by Enhanced Security

These are automatically configured when `ENABLE_ENHANCED_SECURITY = YES` and do not need to be set explicitly:

- `GCC_WARN_SHADOW` — `-Wshadow`, detects variable declarations that shadow other variables.
- `CLANG_WARN_EMPTY_BODY` — `-Wempty-body`, detects empty bodies in control flow statements.
- `ENABLE_SECURITY_COMPILER_WARNINGS` — enables additional security-focused warnings (`-Wbuiltin-memcpy-chk-size`, `-Wformat-nonliteral`, `-Warray-bounds`, etc.). See `security-compiler-warnings.md`.
- `CLANG_CXX_STANDARD_LIBRARY_HARDENING` — set to `fast` in Release builds and `debug` in Debug builds (the cascade handles per-configuration differentiation automatically). This enables the hardened libc++ runtime checks only. It does NOT enable unsafe buffer usage warnings — that requires `ENABLE_CPLUSPLUS_BOUNDS_SAFE_BUFFERS` separately (see `cpp-hardening.md`).
- `CLANG_ENABLE_C_TYPED_ALLOCATOR_SUPPORT` — communicates type information from the compiler to the allocator for C code. Works in combination with the `hardened-heap` sub-option of Enhanced Security (see below).
- `CLANG_ENABLE_CPLUSPLUS_TYPED_ALLOCATOR_SUPPORT` — same, for C++ code.

## Settings NOT covered by Enhanced Security

These must be set independently and are out of scope for this reference:

- All `CLANG_ANALYZER_SECURITY_*` checkers
- Additional `CLANG_WARN_*` / `GCC_WARN_*` diagnostics not flipped by Enhanced Security (e.g. `CLANG_WARN_SUSPICIOUS_IMPLICIT_CONVERSION`, `GCC_WARN_ABOUT_RETURN_TYPE`)
- `GCC_TREAT_IMPLICIT_FUNCTION_DECLARATIONS_AS_ERRORS`, `CLANG_TIDY_*`
- `ENABLE_C_BOUNDS_SAFETY` / `ENABLE_CPLUSPLUS_BOUNDS_SAFE_BUFFERS` (defensive programming models, separate adoption)
