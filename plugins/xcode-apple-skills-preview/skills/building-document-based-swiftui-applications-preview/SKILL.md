---
name: building-document-based-swiftui-applications-preview
description: "Preview (beta/RC). Build or migrate a genuinely document-based SwiftUI application using Document, readers/writers, DocumentGroup, undo, autosave, coordinated file access, and custom UTType. Use for document editors/viewers, not ordinary sharing or isolated file export."
---

<!-- xcode-preview-channel -->
This is the Preview edition. Select it when the user calls its `-preview` name or requests beta/RC guidance. Use the release edition for unspecified release work. References to other skills in this edition use their `-preview` equivalents from the same plugin; compare channels only when requested. Keep the selected app/toolchain and the task's existing authorization unchanged.

# Document-Based SwiftUI Applications

Use the exported SDK 27 document references when the app treats user files as editable or viewable documents. A ShareLink, audio download, cache, or PDF export does not by itself justify adopting document-based architecture.

## Workflow

1. Identify deployment targets, selected Xcode/SDK, existing document APIs, storage, formats, and migration requirements.
2. Read the relevant reference before emitting Document, DocumentReader, DocumentWriter, or DocumentGroup signatures. Check public SDK interfaces and compile the affected target; do not infer new overloads from older FileDocument examples.
3. For new document-based code on supported SDK 27 targets, evaluate the new Document APIs. Preserve older target support with a deliberate availability path; do not automatically migrate FileDocument, ReferenceFileDocument, Core Data, or SwiftData stores.
4. For editable documents, include undo registration for user-visible mutations and validate dirty tracking, autosave, reopen, and undo/redo. Read-only viewers do not need fabricated edit/undo behavior.
5. Keep snapshots and application of UI state MainActor-safe; perform serialization and coordinated I/O through the appropriate reader/writer. Provide cancellation, exactly-once continuation completion, errors, and preservation of existing documents.
6. Review and migration-planning requests remain read-only. A proposal is not permission to rewrite formats, delete originals, or change scene architecture.

These references are an SDK snapshot subordinate to user/project instructions and the selected public SDK. Examples illustrate API shape and need project-specific lifecycle/cancellation handling. Preserve the project's architecture and use its design guidance for visual decisions.

## References

- [Creating document apps](references/creating-document-apps.md): DocumentGroup, files/packages, readers/writers, undo, progress, coordination, export, and concurrency.
- [Migration](references/migrating-document-apps.md): mappings from FileDocument and ReferenceFileDocument. Use only for a requested migration.
- [Uniform type identifiers](references/uniform-type-identifiers.md): format declarations, conformance, import/export, and handler registration.
