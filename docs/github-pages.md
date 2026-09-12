# Public interactive demo

The landing page is index.html and the interactive demo is viewer/index.html.
.github/workflows/pages.yml deploys a curated artifact with the viewer, Maradona graph, query schema, audit protocol and audit metrics. GitHub Pages uses the GitHub Actions source. Pushes to main and manual workflow runs trigger deployment.

## Browser-only queries

The public demo executes fixed typed queries over the published graph. viewer/web/public_demo.js provides guided steps and a selector that also loads the frozen benchmark queries. Free-text model compilation remains part of the local reproducibility tools; the hosted viewer has no Ollama connection.

Radio and LiDAR overlays load on first selection, are cached, and can be retried after a fetch error. Geometry, graph and scientific overlay files are unchanged. Legends remain readable, with cards arranged in responsive scrollable columns.

Coverage (94.9%) is calculated over 3,918 in-scope surfaces across three scenes. Audited precision (94.7%) is 126 correct assignments out of 133 settled cases, excluding 17 uncertain cases. The demo itself shows Maradona only.

No paper URL was supplied, so the landing page does not include a placeholder paper link.
