# Task: Idiom and available space

Implementation patterns apply only to authorized changes in the requested surface. A review reports findings without editing files. Preserve intentional platform, hardware, asset, analytics and product distinctions.

## Classify before replacing

Detect `UIDevice.current.userInterfaceIdiom`, `UI_USER_INTERFACE_IDIOM()`, `UITraitCollection.current`, local `traitCollection.userInterfaceIdiom`, and app-defined helpers such as `IS_PAD`. Read helper definitions and their callers before changing semantics.

| Actual purpose | Approach |
| --- | --- |
| Wide/narrow layout, columns, sidebar, presentation room | The view's available geometry or horizontal size class, according to the design |
| Constrained vertical space | Available height or vertical size class |
| Genuine scene idiom dependence | Keep the comparison and read the closest local trait collection when available |
| Hardware capability, assets, analytics, platform/entitlement gate, deliberate test fixture | Preserve the existing meaning; this migration does not replace it with a size class |
| Unclear feature/product choice | Report the ambiguity and request only the missing decision |

An idiom is not a window size. Compact/regular are categories, not exact widths; use actual geometry when the design needs a threshold in points. Do not map every `.pad` to `.regular` or every `.phone` to `.compact` without checking what the original code intended.

## UIKit

For a space-based layout in a `UIView` or `UIViewController`, read that object's traits. A helper with a reachable view uses that view; do not add a parameter unnecessarily. A helper without context may receive the required value or trait collection, preserving public callers and forwarding bridges as needed. A signature change that changes a public contract requires the appropriate authorization.

```swift
// Width-driven layout; preserve both branches.
stackView.axis = traitCollection.horizontalSizeClass == .regular
    ? .horizontal : .vertical
```

For genuine idiom behavior, retain all idioms the previous helper covered. `UIDevice.current` describes a device; local traits describe the environment rendering the content. Keep device-level reads where device identity is the actual question. Do not convert idiom-derived orientation masks as part of a layout-only migration.

### Initial value and invalidation

A newly trait-derived decision can change during resizing. If it feeds cached layout, constraints or a configured subview, recalculate when the relevant trait changes:

```swift
registerForTraitChanges([UITraitHorizontalSizeClass.self]) {
    (view: ResizableView, _) in
    view.setNeedsLayout()
}
```

Register for the trait actually used: horizontal/vertical size class, or `UITraitUserInterfaceIdiom` for genuine idiom state. The update method must read the current value and update its consumer. A non-view helper cannot register as a trait environment; pass current values at use time or let the owning view invalidate its cached result.

Registration does not establish an initial layout by itself. Calculate the initial state when the relevant view/traits are available, or read it during the normal layout pass. Do not assume an `init` read is final, or assume a registration callback always supplies the initial value.

`registerForTraitChanges` and these built-in trait types require iOS/Mac Catalyst/tvOS 17 or visionOS 1. Retain a compatible `traitCollectionDidChange` path when older targets require it. Automatic tracking applies only to supported overrides on supported OS releases; verify that a method belongs to that set rather than treating every lifecycle callback as automatically tracked.

## Native SwiftUI

Read environment values in the view that owns the layout:

```swift
@Environment(\.horizontalSizeClass) private var horizontalSizeClass
@Environment(\.verticalSizeClass) private var verticalSizeClass

// When the design specifically wants a wide-width variant:
var useWideLayout: Bool { horizontalSizeClass == .regular }
```

Use `== .regular` for a positive space test when an absent size class should choose the narrow fallback. `!= .compact` also matches `nil`, so it expresses a different policy. Height decisions use the vertical axis. Prefer the actual proposed/available size when a size class is too coarse.

SwiftUI updates a view when its environment changes; do not mirror size classes into a model or introduce a view model just for resizing. At an existing representable boundary, use `context.environment` in both creation and update methods. There is no general SwiftUI idiom environment value to invent as a replacement for a genuine device-dependent requirement.

## Verification

Check width and height decisions independently; keep branch semantics and every case of an idiom helper. Exercise a narrow iPad window, a wider phone window, an absent SwiftUI size class, and a trait change after initial display. Preserve orientation locks and out-of-scope assets, analytics and capability gates.
