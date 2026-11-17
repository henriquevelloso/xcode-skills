# Xcode Skills contributor guidance

This repository publishes two instruction libraries, not an Xcode SDK or an official Apple product.
Use English for source, skill guidance and technical documentation. Preserve upstream provenance.
Keep guidance neutral: preserve each consuming project’s architecture, toolchain and instructions.
The package version is shared by both plugins; its first two components follow the published stable Xcode, and its third is the package revision.
Never put local snapshots, backups, personal configuration, credentials or raw Downloads exports in Git.
Do not introduce hooks, bundled servers or execute newly exported code in the update pipeline.
Only the owner-authorized local updater may request automatic publication; community PRs require maintainer action.
Use the documented validation and packaging commands before publication. Tags and released assets are immutable.
