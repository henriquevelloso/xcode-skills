# Localization of User-Facing Strings

App Intents string extraction depends on source literals, not on the eventual text a value holds at runtime. A `LocalizedStringResource` assembled from a runtime `String` can type-check and display normally without generating a string-catalog entry automatically. Such a key would need a separately maintained translation; prefer extractable literals for app-authored UI copy. A literal template with interpolated runtime arguments is different: the template can be extracted while the arguments remain data. The sections below cover that distinction.

## Feed literals to the string-bearing initializers — not runtime `String`s

For automatically extracted app-authored copy, pass a literal or a literal template directly to the localized string slot. Building the entire phrase into a `String` first and then passing it to `LocalizedStringResource(stringLiteral:)` hides the template from extraction. In contrast, `DisplayRepresentation(title: "Note: \(name)")` is a literal template with a dynamic argument and is the appropriate shape when the prefix should be translated.

```swift
// AVOID: static UI text laundered through a runtime String. `sectionName` is a
// stored value, so LocalizedStringResource(stringLiteral:) has nothing for the
// build-time extractor to key on — no catalog entry is generated, and this text
// ships English-only no matter how complete your localizations are.
struct ArchiveNotesIntent: AppIntent {
    static var title: LocalizedStringResource {
        let sectionName: String = "Notes"
        let text: String = "Archive \(sectionName)"
        return LocalizedStringResource(stringLiteral: text)   // no template extracted here
    }
}

// AVOID: forming the whole phrase as a String before wrapping it. The static
// "Note:" prefix is app-authored copy, but its template is no longer extracted.
struct NoteEntity: AppEntity {
    var name: String
    var displayRepresentation: DisplayRepresentation {
        let text: String = "Note: \(name)"
        return DisplayRepresentation(title: LocalizedStringResource(stringLiteral: text))
    }
}
```

```swift
// PREFER: a literal in the string slot. Because `title` is given a source literal,
// the build-time extractor lifts "Archive Notes" into the catalog and translators
// can reach it.
struct ArchiveNotesIntent: AppIntent {
    static var title: LocalizedStringResource { "Archive Notes" }
    static var description = IntentDescription("Archives the current section of notes.")
}

// PREFER: a literal template; the prefix is translatable and the instance name
// is an interpolated argument, not a separate UI translation key.
struct NoteEntity: AppEntity {
    var name: String
    static var typeDisplayRepresentation = TypeDisplayRepresentation(name: "Note")
    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "Note: \(name)")
    }
}
```

The same rule governs `@Parameter(title:)`, `IntentDialog`, `AppShortcut` `shortTitle`, and every `AppShortcutPhrase` you list — all of them are `LocalizedStringResource` / `ExpressibleByString(Literal|Interpolation)` slots that extract only from source literals. There's no supported way to make a runtime-assembled value extractable after the fact; the literal has to be in your source. (App Shortcut phrases are extracted into their own string catalog, **`AppShortcuts.xcstrings`**, separate from the app's main `Localizable.xcstrings`; that's where those phrases get localized.)

## Interpolate dynamic values into a localized template — don't concatenate

Dynamic *counts and quantities* are still static UI text with a variable inside, and they must stay translatable. The wrong instinct is to build the whole phrase at runtime by concatenation (which loses the key entirely) or to hand-pluralize with string math (which is unlocalizable and wrong for most languages). Instead, interpolate the number into a **literal** `LocalizedStringResource` and let the framework's numeric-format support drive pluralization from a `.stringsdict`. On `TypeDisplayRepresentation`, that is exactly what `numericFormat` is for: you write `numericFormat: "\(placeholder: .int) books"` as a literal and supply a `.stringsdict` with each plural rule (`zero` / `one` / `other`), so "1 note" vs. "3 notes" — and every locale's plural categories — resolve correctly.

```swift
// AVOID: hand-built plural via runtime concatenation. No literal template is
// extracted, so this can't be translated, and "1 items" / "many" pluralization
// is wrong in most languages.
struct DeleteNotesIntent: AppIntent {
    let count: Int
    var confirmationDialog: IntentDialog {
        IntentDialog(stringLiteral: "Delete " + String(count) + " items")   // unlocalizable
    }
}

// AVOID: naming your entity's count through raw string math instead of numericFormat.
static var typeDisplayRepresentation = TypeDisplayRepresentation(name: "Note")
// …and then formatting "\(count) Notes" by hand elsewhere — no plural rules, no key.
```

```swift
// PREFER: a literal template with the count interpolated as an argument; the
// framework keys on the template and applies the .stringsdict plural rules.
struct DeleteNotesIntent: AppIntent {
    let count: Int
    var confirmationDialog: IntentDialog {
        "Delete \(count) items"   // literal template → extractable, pluralizable
    }
}

// PREFER: TypeDisplayRepresentation.numericFormat with a .stringsdict for the
// entity's counted name. Pair the literal placeholder template with plural
// entries so "1 book" / "2 books" resolve per locale.
static var typeDisplayRepresentation = TypeDisplayRepresentation(
    name: "Book",
    numericFormat: "\(placeholder: .int) books"
)
```

A genuine, per-instance proper noun is a different case and needs no template: a user's note title, a song name, or an album name is *data the user authored*, not UI chrome, so interpolating it into a literal title (`DisplayRepresentation(title: "\(name)")`) is correct and expected — that value is legitimately non-translatable. The rule in this file is narrow: never route your app's own static UI text through a fake-localized wrapper. Instance names may flow through interpolation; static phrases may not.
