# Swift Testing UI tests in this Preview

Apple's Xcode 27.3 beta (27C5020n) guidance adds support for Swift Testing in UI-test bundles. This is a toolchain and test-runner capability; an OS availability check alone does not enable it.

Keep existing XCTest UI tests unless their migration was requested. Before migrating, confirm the selected Xcode, the UI-test bundle type, CI's runner/toolchain, actor isolation, launch/setup/cleanup, discovery and selectors. XCTest `measure` cases remain XCTest. Preserve the existing fail-fast and asynchronous-completion behavior documented in the migration guide.

The following Apple guidance is retained for that explicit migration. A type check does not establish successful UI execution, runner restart behavior, or CI compatibility. Run a scoped passing and intentionally failing UI case before broad migration, only on an authorized app/destination.

## Apple 27.3 beta guidance


Swift Testing tests in UI test bundles can use XCUIAutomation APIs directly.

In UI test mode, tests are run serially on the main actor. Most XCUIAutomation
API is `@MainActor`-bound, so UI test suites or test functions should be
`@MainActor` so the isolation is explicit and the test doesn't need extra
`await`s.

Failures inside XCUIAutomation APIs will end tests
automatically even if the test function is not marked `throws`. When
a test fails as a result of an automation failure like a missing
element or an event that fails to deliver, the entire test
runner exits and is relaunched to continue running the rest of the
test suite. Keep this in mind as it may cause global values to be
reinitialized, which may perform side effects.

When migrating XCUIAutomation UI tests from XCTest, replace
base XCTAssert calls with Swift Testing equivalents, but do not
insert defensive existence checks unless they match existing
assertion patterns.

Example:

```swift
@MainActor
struct MyUITests {
    let app = XCUIApplication()

    init() {
        app.launch()
    }

    @Test
    func `Increment button adds 1 to title`() throws {
        let incrementButton = app.buttons["Increment"].firstMatch
        let valueText = app.textFields["Value"].firstMatch
        // Ensure the text is 0 to begin with, otherwise
        // the post-tap comparison will be wrong.
        try #require(valueText.value as? String == "0")
        incrementButton.tap()
        #expect(valueText.value as? String == "1")
    }
}
```
