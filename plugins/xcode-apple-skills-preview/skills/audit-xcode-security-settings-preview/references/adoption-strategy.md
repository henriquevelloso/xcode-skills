# Adoption Strategy

> Technical reference adapted from the supplied export. Setting names, defaults, hardware
> and platform support must be verified against the installed SDK/current Apple docs.
> This describes options, not authorization: audit is read-only; apply only approved
> target/configuration/SDK deltas and validate before/after Debug and Release.

A staged order for evaluating and validating explicitly approved Xcode hardening changes. This is not an instruction to enable every protection or mutate unrelated targets.

Adding the Enhanced Security capability enables all cascaded settings at once. The phases below represent the order in which to **validate and fix issues** — not separate enablement steps. Phase 1 features are mostly compiler-focused or low-overhead (behavior still requires validation), Phase 2 may need minor code changes, and Phase 3 requires active annotation or rewriting.

## Phase 1: Compiler Diagnostics and Lower-Overhead Protections

Start here. Compiler warnings have no runtime enforcement. Initialization and memory protections have different behavior/costs; measure affected paths and test instead of claiming universal zero cost.

| Feature | Why first | Reference |
|---------|----------|-----------|
| **Security Compiler Warnings** | Compile-time only. Zero runtime cost. Identifies real bugs. | `security-compiler-warnings.md` |
| **Stack Zero Initialization** | Initializes stack variables; can change previously undefined behavior. Validate affected code. | `stack-zero-init.md` |
| **Read-Only Platform Memory** | No impact on well-behaved code. Blocks post-exploitation. | `readonly-platform-memory.md` |

**Action:** After enabling Enhanced Security, build and fix any new warnings. Do not infer runtime safety from compilation alone.

## Phase 2: Low-Effort Runtime Protections

Next, validate runtime protections that require minimal or no code changes for most apps.

| Feature | Effort | Reference |
|---------|--------|-----------|
| **Runtime Restrictions** | No changes if using XPC or no IPC. Review needed only for raw Mach IPC. | `runtime-restrictions.md` |
| **Typed Allocators** | No changes for standard `malloc`/`free`. Update custom allocator wrappers if present. | `typed-allocators.md` |

**Action:** Test thoroughly. If you use raw Mach IPC, read the Mach IPC conformance guide.

## Phase 3: Annotation and Code Hardening

These features require active code changes — annotations, pointer type updates, or fixing unsafe patterns.

| Feature | Effort | Reference |
|---------|--------|-----------|
| **Pointer Authentication** | Add `__ptrauth` qualifiers to security-critical function/data pointers. Review pointer casts. | `pointer-authentication.md` |
| **C++ Stdlib Hardening** | Fix out-of-bounds container access and unsafe buffer operations. | `cpp-hardening.md` |

**Action:** Prioritize security-critical code paths first (parsers, network handlers, IPC).

Additionally, consider adopting **C Bounds Safety** (`-fbounds-safety`) as a complementary feature for C codebases — see https://clang.llvm.org/docs/BoundsSafetyAdoptionGuide.html. The `adopt-c-bounds-safety` skill is not bundled here.

## Phase 4: Hardware-Dependent Protections

These require specific hardware and OS versions.

| Feature | Requirement | Reference |
|---------|------------|-----------|
| **Hardware Memory Tagging** | iPhone/iPad with an A19 chip or later; Mac/Vision Pro with an M5 chip or later; Apple Watch with an S11 chip or later | `hardware-memory-tagging.md` |
| **Checked Pointer Arithmetic** | device running iOS with an A20 Pro chip or later; device running watchOS with an S11 chip or later. | `checked-pointer-arithmetic.md` |

**Action for Hardware Memory Tagging:**
1. Enable with soft mode first — this generates simulated crash reports without terminating the app
2. Test internally using only separately authorized distribution/devices
3. Review simulated crash reports and fix memory bugs
4. Disable soft mode for production enforcement

**Action for Checked Pointer Arithmetic:** enable hardware memory tagging first — run time enforcement requires it — and finish that rollout before adding this. Then build the `arm64e.x1` slice, add the enforcement entitlement, and test on capable hardware. There is no soft mode here, and memory tagging's soft mode does not cover these faults: a latent pointer-arithmetic bug terminates the app. Read `checked-pointer-arithmetic.md` for instructions on how to enable checked pointer arithmetic and additional notes about adoption.

## Decision Matrix

Use this to decide which features to prioritize based on your codebase:

| If your app... | Prioritize |
|---|---|
| Is pure Swift | Phase 1 + Runtime Restrictions + Read-Only Memory |
| Has C code | All of Phase 1-3, plus consider C Bounds Safety (separate skill) |
| Has C++ code | All of Phase 1-3, especially C++ Hardening |
| Processes untrusted input | All features, prioritize bounds checking, memory tagging, and checked pointer arithmetic |
| Uses Mach IPC | Review runtime restrictions carefully before enabling |
| Targets MTE-capable hardware (iPhone/iPad with chip A19 or later, Mac/Vision Pro with chip M5 or later, Apple Watch with chip S11 or later) | Consider hardware memory tagging (start with soft mode) |
| Runs on devices running iOS with an A20 Pro chip or later, or devices running watchOS with an S11 chip or later | Consider checked pointer arithmetic — it requires hardware memory tagging for run time enforcement |
| Is a DriverKit extension | All applicable features — elevated privilege means higher stakes |

## General Principles

1. **Review the approved capability as a bundle** — identify its cascaded changes and scope before enabling anything
2. **Fix warnings before testing runtime protections** — compiler warnings often reveal the same bugs that runtime protections would crash on
3. **Fix undefined behavior in pointer arithmetic** — most checked pointer arithmetic failures are a consequence of undefined behavior, such as subtracting pointers into different objects
4. **Test in soft mode before hard mode** — applies to hardware memory tagging
5. **Prioritize security-critical code** — parsers, network handlers, IPC, auth logic
6. **Don't skip testing** — Enhanced Security features turn latent bugs into crashes, which is the point, but you want to find them before your users do
