# Third-party provenance and licensing boundaries

**Project author and maintainer: Henrique Velloso.** This identifies authorship
of the community project and its original tooling/adaptations, not authorship
of Apple's guidance. This is not an official Apple, OpenAI, or Anthropic plugin,
and no affiliation or endorsement is claimed.

## Xcode-derived instruction material

The skills and substantial reference material in `skills/` are derived from
instruction exports produced by the official Xcode `agent skills export`
command. Their Xcode version, build, channel, original export digest, and
adapted file hashes are recorded in each plugin's `provenance.json`. Apple is
the upstream author of the exported Apple guidance. Adapted entrypoints and
reviewed helper code are community-maintained and may differ from the export.

No standalone license file accompanied the source export used for the initial
package. **This repository does not establish or grant redistribution rights
for Apple material, and does not label that material MIT or public domain.**
The project's MIT license applies only to the original contributions it covers;
it does not override Apple's or any other rightsholder's terms. Users and
redistributors must assess the applicable terms for their use, especially for
pre-release material. Availability as instruction text is not itself a license.

Relevant upstream references:

- [Xcode and Apple SDKs Agreement](https://www.apple.com/legal/sla/docs/xcode.pdf)
- [Apple agreements and guidelines](https://developer.apple.com/support/terms/)
- [Apple developer releases](https://developer.apple.com/news/releases/)

No Xcode binaries, SDK libraries, developer account credentials, private local
snapshots, or raw Downloads folders are distributed by these packages.

## Original project contributions

The maintenance/packaging tools, their original tests, documentation, and
original adaptation text are covered by `LICENSE` to the extent authored by
Henrique Velloso. The security-settings JSON filter and its tests are reviewed
project helpers; their exact distributable bytes are pinned in the repository's
package policy. None of this changes the provenance of surrounding references.

## Trademarks and corrections

Xcode, Apple, Swift, and associated product names identify their respective
owners' technologies. Codex/OpenAI and Claude/Anthropic names identify supported
clients; their software is not bundled with these instruction packages.

Report attribution, rights, or provenance concerns through a repository issue
without posting private data. The maintainer will investigate corrections or
removal requests. A checksum proves file identity, not legal permission or SDK
correctness.
