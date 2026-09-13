# Anonymous review snapshot

This artifact is designed for distribution as a standalone supplementary ZIP. It does not require a public source repository or a hosted site.

Changes from the research working copy:

- Removed the repository-owner link from the landing page.
- Replaced personal absolute workstation paths in the three matching-input summaries with descriptive basenames. These headers describe original full-resolution source files; those full-resolution files are not included or needed for the demo/rebuild.
- Normalized the graph metadata source paths to forward slashes and refreshed source-file SHA-256 fingerprints for the included input bytes.
- Removed legacy localhost viewer URLs from audit rows, preserving labels and all scoring fields.
- Excluded Git history/configuration, deployment workflows, caches and bytecode from the archive.

Graph nodes and edges, semantic assignments, numeric properties, model geometry and audit labels are unchanged. Graph byte sequences differ from the original working copy because anonymized provenance metadata differs; verify_review.py --rebuild checks the internally consistent anonymous snapshot rather than claiming byte identity with the non-anonymous original.

Automated screening checks the known author identifiers, personal home-directory paths and email-like strings in the distributed project files. This is not a guarantee against inference from research content. The bundled third-party library retains its original copyright and license.
