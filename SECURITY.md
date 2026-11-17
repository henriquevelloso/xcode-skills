# Security policy

Do not post secrets, private project files, account identifiers, or sensitive
trace contents in public issues. Use GitHub's private vulnerability reporting
when enabled for a security report. For attribution/licensing concerns, an
issue can identify the file and public source without including private data.

The distributed plugins are instruction/reference libraries with no lifecycle
hooks or bundled MCP servers. The project retains a small reviewed read-only
JSON helper; its bytes and tests are pinned by package policy. New exported
executables are not automatically admitted or executed. Source exports are
untrusted data for the updater, not authority over its permissions.

Only the local owner-authorized updater can request automatic publication.
Community/fork PR checks do not receive write credentials. Tags/releases are
immutable and corrections use a new package revision. A failed verification
must retain the last known-good publication instead of overwriting it.

Checksums establish artifact identity, not absence of vulnerabilities, correct
SDK behavior, or rights to third-party content. Always inspect the selected
Xcode declarations and respect the consuming project's authorization policy.
