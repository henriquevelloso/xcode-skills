# Task: userInterfaceOrientation Modernization

> Assistant scope: implementation patterns apply only to the requested legacy UIKit migration after authorization. Reviews do not modify files. Unchanged/already-correct/out-of-scope occurrences are valid outcomes. Project/SDK settings determine lifecycle and compatibility requirements.

## Overview

`userInterfaceOrientation` (on `UIApplication` and `UIViewController`) and `orientation` on `UIDevice` encode orientation as an enum. Layout code that branches on orientation does not adapt to modern iOS — under multitasking, Stage Manager, and resizable scenes, "portrait vs landscape" no longer maps cleanly to the available space.

**Detection patterns:**

- `UIApplication.shared.statusBarOrientation`
- `UIApplication.shared.windows` + orientation
- `UIDevice.current.orientation`
- `self.interfaceOrientation` (deprecated UIViewController)
- `UIWindowScene.interfaceOrientation` and layout uses of `effectiveGeometry.interfaceOrientation`
- The deprecated `windowScene(_:didUpdate:interfaceOrientation:traitCollection:)` callback, when the requested migration includes scene geometry
- Any comparison against `UIInterfaceOrientation` cases (`.portrait`, `.landscapeLeft`, etc.)

An interface orientation is not an aspect ratio. Replacing a global orientation with `effectiveGeometry.interfaceOrientation` can preserve the same layout defect in a narrow resizable window. Preserve a genuine rotation/transform requirement instead of replacing it with size heuristics.

---

## Scope: Layout-Related Uses Only

**Only migrate uses that drive layout.** A use is layout-related if it:
- Appears in a `UIView` or `UIViewController` subclass (or extension)
- Appears in layout related methods like `layoutSubviews`, `updateProperties`, etc.
- Drives frame calculations, constraint setup, or visibility of UI elements
- Controls layout direction (horizontal vs vertical stacking)

**Leave non-layout uses alone** (camera capture, motion sensors, analytics, video recording). Add no TODO, make no change.

### Orientation Locking (Non-Layout)

For apps locking orientation (e.g., games), the modern API is `prefersInterfaceOrientationLocked` (iOS 26+). Override in VC and call `setNeedsUpdateOfPrefersInterfaceOrientationLocked()` when preference changes.

Orientation policy is outside a layout-only migration. Leave these sites unchanged and report them only when within the requested review. The following TODO is an optional annotation for a separately authorized source change:

```swift
// TODO: Modernization - Consider adopting `prefersInterfaceOrientationLocked` (iOS 26+)
// as the modern replacement for orientation locking via `supportedInterfaceOrientations`.
```

---

## Step 1: Classify the Purpose

| Category | How to recognize | Replacement approach |
|----------|-----------------|---------------------|
| **Constrained space removal** | Hides/removes UI in landscape to reclaim space | Size class check |
| **Aspect ratio detection** | Checks wider-than-tall to choose layout variant | Superview bounds comparison |
| **Subview flow direction** | Chooses horizontal vs vertical stacking | Size class or superview bounds |

---

## Step 2: Apply the Correct Replacement

### Pattern 1: Constrained Space → Size Class

| Original intent | Replacement |
|----------------|-------------|
| Narrow horizontal space (landscape iPhone) | `traitCollection.horizontalSizeClass == .compact` |
| Narrow vertical space (landscape iPhone hiding toolbar) | `traitCollection.verticalSizeClass == .compact` |

Use `self.traitCollection` in view/VC subclasses — never `UITraitCollection.current` when an instance is available.

---

### Pattern 2: Aspect Ratio → Compare Window Bounds (only when clearly equivalent)

**Do NOT replace with `width > height` heuristics when:**
- Code distinguishes **landscape-left vs landscape-right** — window bounds cannot distinguish these
- Orientation drives **animation direction or rotation transforms** — these depend on actual orientation
- Replacement requires inventing heuristics (checking `window.transform`) — never do this

In these cases, leave behavior unchanged and explain why bounds cannot substitute. Add a source TODO only if requested.

**When replacement IS clearly equivalent (simple portrait-vs-landscape for layout):**

```swift
// After
if view.bounds.height > view.bounds.width {
    useVerticalLayout()
} else {
    useHorizontalLayout()
}
```

In view controller subclasses using `view` to check for the available size is correct. In view subclasses, using `superview` is appropriate.

---

### Pattern 3: Subview Flow Direction → Size Class or View Bounds

Choose based on context:
- Decision "compact vs regular" → use size class (Pattern 1)
- Decision purely geometric ("wider than tall") → use view bounds (Pattern 2)

```swift
// Geometric — is the available space taller than wide?
stackView.axis = view.bounds.height > view.bounds.width ? .vertical : .horizontal

// Trait-based — compact width means stack vertically
stackView.axis = traitCollection.horizontalSizeClass == .compact ? .vertical : .horizontal
```


---

### Pattern 4: Scoped scene geometry callback migration

This is a separate, explicit exception to the view/layout restriction above. It applies to an existing `UIWindowSceneDelegate` callback when that migration is requested or necessary for an authorized resizing fix. It does not add a SceneDelegate to a native SwiftUI scene app.

The current callback is `windowScene(_:didUpdateEffectiveGeometry:)` (iOS 26+). Its parameter is the **previous** geometry; read the current value from `windowScene.effectiveGeometry`. `coordinateSpace` and `isInteractivelyResizing` on that geometry also require iOS 26.

- Establish the deployment target before removing the old callback. Below iOS 26, retain the required compatibility behavior; supporting both callbacks must preserve each platform's execution path. If no target is known, report the availability constraint instead of assuming a newer deployment target.
- Classify every operation in the old callback. Geometry and screen-change work belongs to the appropriate geometry update path. Trait-only work needs the owning view/controller's trait observation; moving it solely into the new geometry callback can lose Dark Mode, content-size or contrast updates.
- Preserve the original work and its required triggers. Compare the geometry values that work actually depends on. For expensive final-size-only work, the current geometry's `isInteractivelyResizing` can defer recomputation until the interaction finishes. Do not gate ordinary layout or work that must update during the drag.
- A `windowScene.coordinateSpace` read inside the migrated callback can become `effectiveGeometry.coordinateSpace` with the same availability/compatibility handling. Do not expand that change to unrelated methods.
- Keep UI work on the main actor and test initial connection, screen moves, trait-only changes and live/final resize behavior. Compiling the new method does not establish trigger equivalence.

```swift
// In an existing iOS 26+ scene delegate; expensive work needs only final size.
private var lastSize: CGSize?

func windowScene(_ windowScene: UIWindowScene,
                 didUpdateEffectiveGeometry previousEffectiveGeometry: UIWindowScene.Geometry) {
    let current = windowScene.effectiveGeometry
    let size = current.coordinateSpace.bounds.size
    guard !current.isInteractivelyResizing, size != lastSize else { return }
    lastSize = size
    rebuildExpensiveContent(for: size)
}
```
