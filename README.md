# Xcode Skills

[![CI](https://github.com/henriquevelloso/xcode-skills/actions/workflows/ci.yml/badge.svg)](https://github.com/henriquevelloso/xcode-skills/actions/workflows/ci.yml)
[![Latest release](https://img.shields.io/github/v/release/henriquevelloso/xcode-skills)](https://github.com/henriquevelloso/xcode-skills/releases/latest)

**Release and preview Xcode instruction libraries for Codex and Claude Code.**
Maintained by **Henrique Velloso**. One repository, two independently selectable
plugins, one shared package version.

[Português](README.pt-BR.md) · [Changelog](CHANGELOG.md) · [Maintenance](docs/maintenance.md) · [Provenance and licensing](THIRD_PARTY_NOTICES.md)

These are community adaptations of Xcode-exported guidance, **not an official
Apple plugin**. Instructions respect each consuming project's architecture,
toolchain, permissions, and policies. They do not require Axiom or a particular
application architecture. Reading the notes does not install Xcode, supply
missing tools, or establish that every example compiles on your SDK.

## Included sources and skills

<!-- GENERATED CATALOG START -->
**Package version: `27.2.1`**

| Channel | Xcode source | Build | Skills |
| --- | --- | --- | ---: |
| stable | Xcode 27.2 | `27B52` | 9 |
| preview | Xcode 27.3 beta 2 | `27C5035i` | 13 |

| Release skill | Preview counterpart |
| --- | --- |
| `app-intents-specialist` | `app-intents-specialist-preview` |
| `app-intents-whats-new-27` | `app-intents-whats-new-27-preview` |
| `app-resizability` | `app-resizability-preview` |
| `audit-xcode-security-settings` | `audit-xcode-security-settings-preview` |
| `building-document-based-swiftui-applications` | `building-document-based-swiftui-applications-preview` |
| — | `foundation-models-specialist-preview` |
| — | `macos-touch-gestures-preview` |
| `modernize-tests` | `modernize-tests-preview` |
| — | `siri-app-integration-preview` |
| — | `siri-evaluations-preview` |
| `swiftui-specialist` | `swiftui-specialist-preview` |
| `swiftui-whats-new-27` | `swiftui-whats-new-27-preview` |
| `xctrace` | `xctrace-preview` |
<!-- GENERATED CATALOG END -->

The preview plugin's skills have `-preview` names and descriptions. You may
install both plugins without name collisions and explicitly select a preview
skill when you need beta/RC guidance. Source versions above describe the files
actually exported, not the latest version merely announced by Apple.

## Install in Codex

Use a current Codex CLI with plugin marketplace support:

```sh
codex plugin marketplace add henriquevelloso/xcode-skills
codex plugin add xcode-apple-skills@xcode-skills
codex plugin add xcode-apple-skills-preview@xcode-skills
```

Install only the channel you need, or both. Start a new chat to verify the
loaded catalog; installing files does not imply hot reload in an existing chat.
Examples: `$xcode-apple-skills:swiftui-specialist` or
`$xcode-apple-skills-preview:swiftui-specialist-preview`.

To refresh the Git-backed catalog:

```sh
codex plugin marketplace upgrade xcode-skills
```

Then use the supported plugin update/install interface for your client and
verify the installed version. No manual edits to the Codex cache are required.

## Install in Claude Code

In Claude Code:

```text
/plugin marketplace add henriquevelloso/xcode-skills
/plugin install xcode-apple-skills@xcode-skills
/plugin install xcode-apple-skills-preview@xcode-skills
```

Examples: `/xcode-apple-skills:swiftui-specialist` and
`/xcode-apple-skills-preview:swiftui-specialist-preview`.

Use Claude Code's plugin manager to update the marketplace/plugins. Do not
also link the same skills into a personal skills directory: duplicate
installation paths can produce confusing discovery behavior. Existing manual
links are not removed by this project.

## Pin a version or use another agent

Choose a tag from [Releases](https://github.com/henriquevelloso/xcode-skills/releases),
clone/check out that tag, and register the local repository as a marketplace.
For Codex, the Git marketplace also supports `--ref v27.2.0`. Other agents that
support Agent Skills can read the selected plugin's `skills/` folders directly;
plugin-manifest support and execution tools vary by host. Do not assume a cloud
Linux environment can run Xcode or Apple-device tooling.

Each release provides a ZIP for each plugin, `SHA256SUMS`, aggregate provenance,
and release notes. ZIPs contain complete plugin roots with both client
manifests. Verify checksums before use. Tags and released assets are not
rewritten; corrections receive a new package revision.

## Version policy

Both plugins and the repository share `MAJOR.MINOR.REVISION`. The first two
components follow the **included stable Xcode**; the third is our package
publication sequence, not necessarily an Xcode patch number. A preview-only
update increments the package revision too. Exact Xcode versions/builds remain
separate in provenance and the source table. A new source build with identical
instructions still receives notes explicitly saying the content is unchanged.
Checks without new source or content do not produce another release.

## Automatic maintenance

The owner's local Codex routine checks official Apple releases and installed
Xcodes daily at **09:00 America/Sao_Paulo**. Missing Xcode versions produce a
deduplicated download notice, not a fabricated export. Xcode downloads,
installation, account sign-in, and global toolchain switches are not automated.
The local updater prepares and reviews candidates, while GitHub CI validates
and publishes owner-generated updates without per-release human approval.

The local Mac and Codex must be available for export/adaptation. A pending
update resumes on a later successful run. CI runs structural/package checks;
it does not claim app/device, Siri, or App Store release validation.
See [the operational guide](docs/maintenance.md) for commands, failure handling,
and publication boundaries.

## Development

Python 3.9+ and the standard library are sufficient for project tests/tooling:

```sh
python3 -B -m unittest discover -s tests -v
python3 -B -m unittest discover -s tools/legacy/tests -v
python3 -B tools/package.py generate
python3 -B tools/package.py validate
python3 -B tools/package.py build
```

Client CLIs additionally validate their own formats in isolated CI profiles.
Packaging never imports or executes newly exported helper code. The few
previously reviewed Python helper/test files are hash-pinned; new executables,
hooks, bundled servers, binaries, symlinks, and unrelated source files cannot
silently enter a release. `device-interaction` and `adopt-c-bounds-safety` remain
excluded from automatic imports.

## Rights and contributions

The [MIT license](LICENSE) covers only project-authored contributions; it does
not relicense Apple-derived material. Read [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
for the provenance limits before redistributing. Publication does not establish
upstream licensing permission. Community PRs do not auto-merge or receive
publication credentials. See [Contributing](CONTRIBUTING.md) and [Security](SECURITY.md).
