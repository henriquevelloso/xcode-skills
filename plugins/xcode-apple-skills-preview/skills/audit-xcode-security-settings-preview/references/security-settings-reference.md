# Security Settings Reference

> Technical reference adapted from the supplied export. Setting names, defaults, hardware
> and platform support must be verified against the installed SDK/current Apple docs.
> This describes options, not authorization: audit is read-only; apply only approved
> target/configuration/SDK deltas and validate before/after Debug and Release.

Reference for proposed security build settings and entitlements. Values describe candidate protections, not approval to change them. Apply only scoped, explicitly approved deltas; inspect language, configuration, platform and dependencies first.

> **Skill-internal use only.** Do not call this the "catalog" or use terms like "catalog macro" / "catalog regex" in user-facing narration — those are skill-internal jargon. In any text shown to the user, describe what's being checked plainly: "the known security build settings", "the security setting `CLANG_WARN_…`", etc.

**Language relevance:** Determine compiled languages per target/configuration. The Scope column limits applicability; a workspace-wide language match does not make every target eligible. Do not propose clang-only settings for pure Swift targets.

**Filtering recipe.** `scripts/filter_build_settings.py` accepts saved native-Xcode or xcodebuild JSON. It extracts exact first-column setting names and per-setting values from the tables below, then matches names exactly. It does not classify values using one global boolean predicate. See `reading-build-settings.md` for source/context requirements and limitations.

## Warnings — Candidate Scoped Recommendations

### Compiler Warnings

Fire on every build.

| Build Setting | Value | CLI Flag | Scope | Why Safe |
|---|---|---|---|---|
| `GCC_WARN_ABOUT_RETURN_TYPE` | `YES_ERROR` | `-Werror=return-type` | C/C++/ObjC/ObjC++ | Missing returns are always bugs |
| `GCC_WARN_UNINITIALIZED_AUTOS` | `YES_AGGRESSIVE` | `-Wuninitialized -Wconditional-uninitialized` | C/C++/ObjC/ObjC++ | Real bugs, rarely false |
| `CLANG_WARN_IMPLICIT_FALLTHROUGH` | `YES` | `-Wimplicit-fallthrough` | C/C++/ObjC/ObjC++ | Catches logic bugs in switch |
| `GCC_WARN_64_TO_32_BIT_CONVERSION` | `YES` | `-Wshorten-64-to-32` | C/C++/ObjC/ObjC++ | Truncation is a real issue |
| `GCC_TREAT_IMPLICIT_FUNCTION_DECLARATIONS_AS_ERRORS` | `YES` | `-Werror=implicit-function-declaration` | C/ObjC | Implicit decls cause wrong return types |

### Static Analyzer Warnings

Run during *Build and analyze*, not regular builds.

| Build Setting | Value | CLI Flag | Scope | Why Safe |
|---|---|---|---|---|
| `CLANG_ANALYZER_SECURITY_FLOATLOOPCOUNTER` | `YES` | checker: `security.FloatLoopCounter` | C/C++/ObjC/ObjC++ | Low false-positive rate |
| `CLANG_ANALYZER_SECURITY_INSECUREAPI_RAND` | `YES` | checker: `security.insecureAPI.rand` | C/C++/ObjC/ObjC++ | Flags insecure random |
| `CLANG_ANALYZER_SECURITY_INSECUREAPI_STRCPY` | `YES` | checker: `security.insecureAPI.strcpy` | C/C++/ObjC/ObjC++ | Flags unsafe string ops |

### Clang-Tidy Warnings

Clang-tidy-integrated checks that are part of the clang static analyzer; they fire only during *Build and analyze* (or `clang --analyze`), never on normal builds. They are compiler-integrated diagnostics rather than a new dependency. Verify the checker exists in the active SDK and run authorized analysis before claiming coverage; configuration policies can promote diagnostics to failures.

| Build Setting | Value | CLI Flag | Scope | Why Safe |
|---|---|---|---|---|
| `CLANG_TIDY_BUGPRONE_REDUNDANT_BRANCH_CONDITION` | `YES` | static analyzer check (integrated from clang-tidy): `bugprone-redundant-branch-condition` | C/C++/ObjC/ObjC++ | Runs during Build and analyze, not regular builds |

## Enhanced Security — Capability

### Build Settings

| Build Setting | Value | CLI Flag / Effect | Note |
|---|---|---|---|
| `ENABLE_ENHANCED_SECURITY` | `YES` | Enables the Enhanced Security capability (build-setting + entitlements) | See `enhanced-security.md` |
| `ENABLE_POINTER_AUTHENTICATION` | `YES` | Appends `arm64e` to `ARCHS_STANDARD` — builds both `arm64` and `arm64e` slices | Scope explicitly; project-level inheritance requires review of all affected targets. |
| `ENABLE_HARDWARE_CHECKED_POINTER_ARITHMETIC_SLICE` | `YES` | Appends `arm64e.x1` to `ARCHS_STANDARD`, with checked pointer arithmetic instructions and other features. | Defaults to `NO` and is **not** cascaded by `ENABLE_ENHANCED_SECURITY` — set it explicitly, per target. |

**Cascaded by `ENABLE_ENHANCED_SECURITY` (do not set manually):**

| Build Setting | Value | Effect | Note |
|---|---|---|---|
| `GCC_WARN_SHADOW` | `YES` | `-Wshadow` — variable declarations that shadow other variables | See `security-compiler-warnings.md` |
| `CLANG_WARN_EMPTY_BODY` | `YES` | `-Wempty-body` — empty bodies in control flow statements | See `security-compiler-warnings.md` |
| `ENABLE_SECURITY_COMPILER_WARNINGS` | `YES` | Enables additional security warnings (`-Wformat-nonliteral`, `-Warray-bounds`, etc.) | See `security-compiler-warnings.md` |
| `CLANG_CXX_STANDARD_LIBRARY_HARDENING` | `fast` / `debug` / `extensive` | Hardened libc++ runtime checks (fast in Release, debug in Debug — cascade handles per-configuration automatically) | Does not include unsafe buffer warnings — see `cpp-hardening.md` |
| `CLANG_ENABLE_STACK_ZERO_INIT` | `YES` | Zero-initializes automatic stack variables | Verify cascade and effective value in the active SDK. |
| `CLANG_ENABLE_C_TYPED_ALLOCATOR_SUPPORT` | `YES` | Communicates type information to the allocator for C code | Most effective with the `hardened-heap` sub-option of Enhanced Security |
| `CLANG_ENABLE_CPLUSPLUS_TYPED_ALLOCATOR_SUPPORT` | `YES` | Communicates type information to the allocator for C++ code | Most effective with the `hardened-heap` sub-option of Enhanced Security |

### Entitlements

These are managed per-target in each target's `.entitlements` file. See `enhanced-security.md` Part B for full details.

**Required by the approved capability/version (verify SDK and scope before changing):**

- [`com.apple.security.hardened-process`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process) = `<true/>` — main toggle for runtime protections
- [`com.apple.security.hardened-process.enhanced-security-version-string`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process.enhanced-security-version-string) = `"2"` — selects v2 protections

**Default-ON candidates (audit missing keys; changes still require approval):**

- [`com.apple.security.hardened-process.hardened-heap`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process.hardened-heap) — adds type-isolation buckets to the allocator at runtime; most effective with the cascaded `CLANG_ENABLE_C_TYPED_ALLOCATOR_SUPPORT` / `CLANG_ENABLE_CPLUSPLUS_TYPED_ALLOCATOR_SUPPORT` build settings (Memory Safety)
- [`com.apple.security.hardened-process.dyld-ro`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process.dyld-ro) — marks dyld state read-only (Runtime Protections)
- [`com.apple.security.hardened-process.platform-restrictions-string`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process.platform-restrictions-string) = `"2"` — dyld + Mach messaging restrictions (Runtime Protections)

**Default-OFF (report state, do not auto-enable):**

- [`com.apple.security.hardened-process.checked-allocations`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process.checked-allocations) — hardware memory tagging (MTE)
- [`com.apple.security.hardened-process.checked-allocations.soft-mode`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process.checked-allocations.soft-mode) — simulated crash reports without termination
- [`com.apple.security.hardened-process.checked-allocations.enable-pure-data`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process.checked-allocations.enable-pure-data) — tag non-pointer heap allocations
- [`com.apple.security.hardened-process.checked-allocations.no-tagged-receive`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process.checked-allocations.no-tagged-receive) — opt out of receiving tagged pointers via Mach IPC
- [`com.apple.security.hardened-process.checked-allocations.enforce-checked-pointer-arithmetic-overflow`](https://developer.apple.com/documentation/BundleResources/Entitlements/com.apple.security.hardened-process.checked-allocations.enforce-checked-pointer-arithmetic-overflow) — checked pointer arithmetic; needs the `arm64e.x1` slice from `ENABLE_HARDWARE_CHECKED_POINTER_ARITHMETIC_SLICE` and other requisites

## Additional Settings — Potentially More False Positives

| Build Setting | Value | CLI Flag | Scope | Note |
|---|---|---|---|---|
| `CLANG_WARN_SUSPICIOUS_IMPLICIT_CONVERSION` | `YES` | `-Wconversion` | C/C++/ObjC/ObjC++ | May be noisy in some codebases |
| `CLANG_ANALYZER_SECURITY_BUFFER_OVERFLOW_EXPERIMENTAL` | `YES` | checker: `security.ArrayBound` | C/C++/ObjC/ObjC++ | Higher false-positive rate |
| `CLANG_WARN_ASSIGN_ENUM` | `YES` | `-Wassign-enum` | C/C++/ObjC/ObjC++ | Code quality |
| `GCC_WARN_SIGN_COMPARE` | `YES` | `-Wsign-compare` | C/C++/ObjC/ObjC++ | Code quality |

### C++ / DriverKit / IOKit (only if C++ present)

| Build Setting | Value | CLI Flag |
|---|---|---|
| `CLANG_ANALYZER_OSOBJECT_C_STYLE_CAST` | `YES` | checker: `optin.osx.OSObjectCStyleCast` |

### Blocks (only if ObjC, ObjC++, or C with -fblocks present)

| Build Setting | Value | CLI Flag |
|---|---|---|
| `CLANG_WARN_COMPLETION_HANDLER_MISUSE` | `YES` | `-Wcompletion-handler` |

### ObjC-Specific (only if ObjC/ObjC++ present)

| Build Setting | Value | CLI Flag |
|---|---|---|
| `CLANG_WARN_OBJC_IMPLICIT_RETAIN_SELF` | `YES` | `-Wimplicit-retain-self` |
| `CLANG_WARN_OBJC_REPEATED_USE_OF_WEAK` | `YES` | `-Warc-repeated-use-of-weak` |

## Not Auto-Enabled (Mentioned in Report)

| Build Setting | Proposed Value | Why Not Auto-Enabled |
|---|---|---|
| `ENABLE_C_BOUNDS_SAFETY` | `YES` | Separate annotation/code migration requiring explicit scope |
| `ENABLE_CPLUSPLUS_BOUNDS_SAFE_BUFFERS` | `YES` | Separate buffer-pattern adoption and validation |

Hardware memory tagging uses `com.apple.security.hardened-process.checked-allocations`, not a boolean build-setting macro. Report its scoped entitlement state separately; see `hardware-memory-tagging.md`.

## Default-ON Security Checkers — Audit Only

These were documented as default-ON in the export; verify current SDK defaults. Inspect scoped explicit overrides and rationale, not project-wide counts. Audit alone does not enable them.

| Build Setting | Value | What It Checks | Scope |
|---|---|---|---|
| `CLANG_ANALYZER_SECURITY_KEYCHAIN_API` | `YES` | Improper Keychain API usage | C/C++/ObjC/ObjC++ |
| `CLANG_ANALYZER_SECURITY_INSECUREAPI_UNCHECKEDRETURN` | `YES` | Unchecked return values from security APIs | C/C++/ObjC/ObjC++ |
| `CLANG_ANALYZER_SECURITY_INSECUREAPI_GETPW_GETS` | `YES` | Use of insecure `getpw()` and `gets()` | C/C++/ObjC/ObjC++ |
| `CLANG_ANALYZER_SECURITY_INSECUREAPI_MKSTEMP` | `YES` | Insecure use of `mkstemp()` / `mktemp()` | C/C++/ObjC/ObjC++ |
| `CLANG_ANALYZER_SECURITY_INSECUREAPI_VFORK` | `YES` | Use of `vfork()` | C/C++/ObjC/ObjC++ |
| `GCC_WARN_TYPECHECK_CALLS_TO_PRINTF` | `YES` | Format string type checking (`-Wformat`) | C/C++/ObjC/ObjC++ |
