# Additional Settings

> Technical reference adapted from the supplied export. Setting names, defaults, hardware
> and platform support must be verified against the installed SDK/current Apple docs.
> This describes options, not authorization: audit is read-only; apply only approved
> target/configuration/SDK deltas and validate before/after Debug and Release.

Additional diagnostic settings that can find more issues but may also produce false positives. These are proposed only when applicable, and applied only for exact explicitly approved target/configuration/SDK deltas.
[Read the build settings reference](https://developer.apple.com/documentation/Xcode/build-settings-reference) for the complete list of available settings.

## Settings

- `CLANG_WARN_SUSPICIOUS_IMPLICIT_CONVERSION = YES`
- `CLANG_ANALYZER_SECURITY_BUFFER_OVERFLOW_EXPERIMENTAL = YES`
- `CLANG_WARN_ASSIGN_ENUM = YES`
- `GCC_WARN_SIGN_COMPARE = YES`

**C++ / DriverKit / IOKit (only if C++ present):**

- `CLANG_ANALYZER_OSOBJECT_C_STYLE_CAST = YES`

**Blocks (only if ObjC, ObjC++, or C with -fblocks present):**

- `CLANG_WARN_COMPLETION_HANDLER_MISUSE = YES`

**ObjC-specific (only if ObjC/ObjC++ present):**

- `CLANG_WARN_OBJC_IMPLICIT_RETAIN_SELF = YES`
- `CLANG_WARN_OBJC_REPEATED_USE_OF_WEAK = YES`

## Procedure

Evaluate relevance from languages actually compiled by each target/configuration, document source evidence, and propose exact deltas. Apply only after explicit approval. Return decisions in the conversation; save/update a document only when separately requested. Validate affected Debug/Release builds and authorized analysis before claiming diagnostic coverage.
