# @State as Macro
**Toolchain:** Xcode 27 / SwiftUI SDK 27 and later

`@State` has been migrated from a property wrapper to a macro. These initialization and synthesis changes are build-time behavior of the selected toolchain, not an iOS 27 runtime feature that can be hidden behind `if #available`. You may encounter source incompatibilities when rebuilding existing code, including targets that deploy to older OS versions. Confirm the affected case in the selected SDK rather than applying every fix below mechanically.

## Init Assignment Errors
**Issue:**
Projects that provide an initial value for a `@State` variable declaration and assign it again in an initializer, before all stored properties are assigned, may encounter errors like:

```
error: Variable 'self.name' used before being initialized
```

For example, this pattern can produce the diagnostic below; diagnostic behavior can vary by compiler build:
```swift
import SwiftUI

struct ContentView: View {
    var name: String
    @State private var counter: Int = 0

    init(name: String) {
        self.counter = 42
        self.name = name
    }

    var body: some View { Text("\(name): \(counter)") }
}
```

**Fix:**
When the initializer supplies the state value, omit the declaration-site initial value so the assignment initializes storage rather than invoking a setter on already-initialized state. Initialize other stored properties first. Do not merely reorder assignments while retaining a conflicting inline default.

```swift
struct ContentView: View {
    let name: String
    @State private var counter: Int

    init(name: String) {
        self.name = name
        self.counter = 42
    }

    var body: some View { Text("\(name): \(counter)") }
}
```

**Reason:**
The `@State` macro synthesizes real backing storage properties. If your `init` assigns to `@State` properties before other stored properties are set, the compiler catches this as premature `self` usage.

**Warning:**
Assigning a new value to a `@State` property that has an initial value is an anti-pattern and won't produce the expected behavior.

For example, the `body` for the following code will see `0` as the value for `counter`
```swift
struct ContentView: View {
    @State private var counter: Int = 0

    init() {
        self.counter = 42
    }
}
```

## Redeclaration errors with composed property wrappers
**Issue:**
Projects that apply additional property wrappers to properties using `@State` might see errors like:

```
error: invalid redeclaration of synthesized property '_counter'
```

**Fix:**
Refactor the property wrapper composition: remove the redundant wrapper or restructure so backing storage names don't collide. If unsure, ask the user how they prefer to proceed.

**Reason:**
Both the composed property wrapper and the `@State` macro try to synthesize a backing storage property with the same name.

## Changed memberwise initializer for private state
**Issue:**
For a private `@State` declaration using the deferred initialization path, the synthesized memberwise parameter may be named `_bar` and accept `State<Int>` rather than being named `bar` and accepting `Int`. An initializer in an extension that uses the old value label therefore fails. This is **not** evidence that the memberwise initializer is absent.

```
struct Foo: View {
  @State private var bar = 0
  private let baz: Int
  var body: some View { Text("\(bar): \(baz)") }
}

extension Foo {
  init(_ bar: Int, baz: Int) {
    self.init(bar: bar, baz: baz) // extraneous argument label 'bar:' in the verified fixture
  }
}
```

**Fix:**
Prefer an explicit initializer with intentionally owned state, omitting a declaration-site default when this initializer supplies the value:

```swift
struct Foo: View {
    @State private var bar: Int
    private let baz: Int

    init(_ bar: Int, baz: Int) {
        self.baz = baz
        self.bar = bar
    }

    var body: some View { Text("\(bar): \(baz)") }
}
```

For the exact synthesized signature in the fixture above, `self.init(_bar: State(initialValue: bar), baz: baz)` also type-checks. Do not assume that spelling for every access level, inline default, deployment target, or future SDK; inspect the actual macro expansion or compile a minimal fixture when synthesis is the issue.

**Reason:**
The macro changes the storage and synthesized initialization surface. On the private deferred path, the memberwise initializer exposes the `State` storage parameter rather than the original wrapped-value parameter. An explicit initializer avoids coupling app code to that synthesized signature.

**Validation scope:** minimal `View` fixtures were type-checked with Swift 6 and complete concurrency checking against Xcode 27.0 (27A266a), iOS 27.0 SDK, and Xcode 27.1 (27A9269), iOS 27.1 SDK. In both toolchains, the old `bar:` call failed at deployment iOS 27, the `_bar: State<Int>` call compiled at deployments iOS 18 and 27, and the explicit-initializer form compiled at deployment iOS 18. These checks validate those compile-time shapes, not runtime state retention or every project configuration.
