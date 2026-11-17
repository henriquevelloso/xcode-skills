# Task: Dynamic and asymmetric safe areas

Implementation patterns apply only after authorization for the requested surface. Preserve intentional edge-to-edge presentation, visual margins, public callers and product policy. Reviews report findings without edits or source TODOs. A view using a safe-area API correctly needs no change.

## Detect the assumption, not just the spelling

Look for hardcoded bar/home-indicator offsets, `topLayoutGuide`/`bottomLayoutGuide`, one inset reused on both edges, horizontal insets gated by orientation, stored insets without updates, insets read from an unrelated window/ancestor, double-added scroll insets, and custom keyboard frame math.

In existing SwiftUI code, inspect content and controls under bars, broad `ignoresSafeArea`, and padding that duplicates an inset. Backgrounds, media, maps, scrims and deliberate design margins may correctly extend to the edges. A literal alone does not prove an inset bug.

## Local geometry and direction

- Read from the view whose content is positioned. A sheet, popover, split-view column and its window can have different insets.
- A horizontal inset can persist and can change without the view's size changing. Do not infer its edge or magnitude from a model name, width, orientation or size class.
- Read each edge separately. Do not apply one edge's value or `max(left, right)` to both sides.
- `UIEdgeInsets.left/right` are physical edges; leading/trailing are directional. Prefer `safeAreaLayoutGuide.leadingAnchor` and `.trailingAnchor` for directional constraints. Preserve deliberate physical-edge behavior.
- Use directional margins when the design follows layout direction. Preserve an intentional physical margin and any deliberate system-minimum override; report an unclear product choice rather than changing it automatically.
- `bounds.width - safeAreaInsets.left - safeAreaInsets.right` can correctly describe the total inset width. Do not rewrite correct arithmetic merely because it mentions both insets.
- Preserve conditionals unless the requested fix establishes that they are obsolete. An inset check can guard behavior beyond the inset itself.

## UIKit guides and dynamic updates

`topLayoutGuide` and `bottomLayoutGuide` belong to a view controller. The safe area belongs to its view:

| Old use | Replacement when semantically equivalent |
| --- | --- |
| `topLayoutGuide.bottomAnchor` | `view.safeAreaLayoutGuide.topAnchor` |
| `bottomLayoutGuide.topAnchor` | `view.safeAreaLayoutGuide.bottomAnchor` |
| `topLayoutGuide.length` | `view.safeAreaInsets.top` at a valid layout/update point |
| `bottomLayoutGuide.length` | `view.safeAreaInsets.bottom` at a valid layout/update point |
| `topLayoutGuide.topAnchor` | `view.topAnchor`, not the safe-area top |

Prefer constraints against the appropriate guide. For manual layout, read current insets during the relevant layout pass. An early or one-time read can be zero or stale. If a cached value is necessary, preserve its public contract and ensure an initial calculation plus complete invalidation; do not delete stored properties or their readers blindly.

Use `safeAreaInsetsDidChange()` on a view and `viewSafeAreaInsetsDidChange()` on a view controller to invalidate the relevant layout, calling `super` as required. `setNeedsLayout()` schedules a layout pass; use `setNeedsUpdateConstraints()` if recalculation lives in `updateConstraints`. Do not read a dependent view's final frame before layout has updated it.

`additionalSafeAreaInsets` is additive: include only the additional space the app's own chrome needs. Adding the current system safe area again double-counts it.

For scroll views, inspect the intended container behavior before replacing a deliberate `.never`. Let the automatic adjustment handle the safe area where appropriate, and do not add that area a second time to `adjustedContentInset`.

For keyboard layout, `view.keyboardLayoutGuide` is available from iOS 15. Consider it when replacing layout-only keyboard frame math. Preserve observers that serve non-layout behavior, existing compatibility, floating-keyboard behavior and the product's intended interaction.

## Vertical bar edge: iOS 27.1+

`traitCollection.verticalBarEdge` expresses the preferred leading/trailing edge; it does not measure the inset or prove a bar is currently visible. Read the relevant view's insets for available space.

If a derived value is stored outside a supported automatically tracked override, observe the system traits that affect the edge and update its consumer:

```swift
registerForTraitChanges(UITraitCollection.systemTraitsAffectingVerticalBarEdge) {
    (controller: ResizableViewController, _) in
    controller.view.setNeedsLayout()
}
```

Inside a view subclass, invalidate that view. A transient read does not by itself require a stored observer. Respect the iOS 27.1 availability floor; on older targets retain a valid layout based on dynamic safe-area guides/insets rather than guessing the bar edge.

## Corner-aware regions: iOS 26+

Where content demonstrably clips at rounded corners, the ordinary safe-area rectangle may not provide the desired corner clearance. Use the region appropriate to the content:

```swift
let guide = view.layoutGuide(for: .safeArea(cornerAdaptation: .horizontal))
let insets = view.directionalEdgeInsets(for: .safeArea(cornerAdaptation: .horizontal))
```

The returned insets are directional. Use these APIs only on supported targets and when the corner issue exists; preserve the compatible path on earlier releases. They do not replace every safe-area guide in an app.

## Existing SwiftUI

- Keep native SwiftUI and its reactive layout. `EdgeInsets.leading/trailing` are already directional.
- Use `safeAreaBar(edge:)` for bar content when available (iOS 26+), `safeAreaInset(edge:)` for inset content, and `safeAreaPadding` for an intentional fixed margin. Preserve earlier-target fallbacks and deliberate appearance/scroll-edge behavior.
- A controls bar implemented as an overlay can cover content behind it. Move it into the appropriate inset/bar layout when that is the demonstrated defect. Preserve backgrounds and other overlays that intentionally do not reserve content space.
- `safeAreaPadding` adds a margin; it does not turn an arbitrary bar-height literal into a dynamic inset. Distinguish a design margin from a duplicated system offset before removing padding.
- Scope `ignoresSafeArea` to the edges/regions the content intentionally reaches. A full-bleed background may correctly ignore every edge, while interactive content above it still respects safe areas.
- Inspect the actual container, proposed size and modifier order before applying `GeometryProxy.safeAreaInsets`. Avoid adding or subtracting the same inset twice. Do not assume every `GeometryProxy.size` in every hierarchy has identical safe-area semantics, and retain legitimate `GeometryReader` measurements.
- When the view needs the preferred vertical-bar edge, `@Environment(\.toolbarVerticalEdge)` is available from iOS 27.1. It is an optional directional edge. Do not infer bar visibility, invent a non-optional value, or cache a second copy in a model.

## Verification

Exercise asymmetric left/right insets, RTL, a safe-area change without a size change, live resizing, sheets/popovers, scroll adjustment, keyboard behavior, deliberate full-bleed layers, and the earlier deployment target. Do not change unrelated layout or convert UIKit code to SwiftUI as part of this task.
