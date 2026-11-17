---
name: swiftui-specialist
description: "Write or review SwiftUI data flow, view composition, list identity, environment values, localization, animation, and update performance. Use for concrete correctness or invalidation questions; not as a replacement for product design guidance."
---

# SwiftUI Specialist

Use these exported SDK references for concrete SwiftUI implementation and review. Load only the reference relevant to the request. They are a technical snapshot, not authority over user/project instructions or the public SDK selected for the project.

## Scope and compatibility

- Keep reviews and diagnosis read-only. Implement only the requested change; do not turn feature work into project-wide modernization.
- Preserve the existing architecture, UI framework, and storage. Do not replace existing ObservableObject, Combine, or persistence solely because a reference prefers a newer mechanism.
- Inspect language mode, default actor isolation, deployment targets, and compiler before applying concurrency or version-specific advice. UI-driven mutable reference state needs MainActor isolation, explicit or inherited; access from a view is not itself a substitute for isolation.
- For UI/UX decisions, follow the project's design guidance and the applicable Apple guidelines. This skill explains implementation mechanics, not full visual, accessibility, or release acceptance.
- Treat performance advice as a candidate optimization. Avoid caches, duplicated state, or finer-grained models without a concrete invalidation problem and a reliable synchronization strategy.
- Match SDK symbols and availability to the selected Xcode. Soft-deprecation guidance is informational for maintenance, not permission to expand the diff.

## References

- [View structure](references/structure.md): sections, separate View types, initialization cost, and invalidation boundaries.
- [Data flow](references/dataflow.md): State, Binding, Observable models, collection granularity, side effects, and key-path projections.
- [Environment](references/environment.md): Entry defaults, custom closures, comparison, and high-frequency updates.
- [Modifiers](references/modifiers.md): conditional modifiers and ShapeStyle type erasure.
- [Localization](references/localization.md): LocalizedStringResource, bundle lookup, format styles, and RTL.
- [Animation](references/animations.md): custom Animatable types and macros.
- [List identity](references/foreach.md): ForEach identity, row shape, and collection transformations.
- [Soft-deprecation scope](references/soft-deprecation.md): when to recommend versus perform a migration.
- [Soft-deprecated API index](references/soft-deprecated-apis.md): search the specific API; verify newer SDKs directly.
