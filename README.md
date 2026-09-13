# TraceMat

Code, data and an offline interactive demo for reviewing the material-grounded urban graph, its evidence, and the radio/LiDAR property layers. The interactive scene is Maradona; the recorded graphs and reconstruction checks cover all three evaluated scenes.

## Start here

- **Inspect the method and data:** [query schema](docs/query_schema.md), [graphs](data/graphs/), [graph construction code](src/build_scene_graphs.py).
- **Review the evidence:** [labelled audit sample](audit/grounding_audit_labelled.csv), [audit protocol](audit/LABELLING_PROTOCOL.md), [reported metrics](results/grounding_audit_metrics.json).
- **Run the demo:** follow the instructions below; a five-minute walkthrough and expected query results are included.
- **Verify the artifact:** run `python verify_review.py --rebuild`; see [recorded checks](REVIEW_CHECKS.json).

The files can be inspected directly through the review repository. To interact with the 3D scene, download the complete repository snapshot and run it locally: a repository's source-code preview does not execute the viewer.

## Start the demo

1. Download the complete repository snapshot from the review link and extract it into a folder. Keep its directory structure intact; do not open HTML inside a ZIP.
2. Open a terminal in that folder and run:

   ```bash
   python start_review.py
   ```

   On Windows, `py start_review.py` also works. On macOS/Linux, use `python3 start_review.py` if needed.
3. A browser opens the landing page; choose **Launch interactive demo**. Keep the terminal open while reviewing, then press Ctrl+C to stop.

Requirements: Python 3.10+ and a modern browser with WebGL (Chrome, Edge or Firefox). The launcher uses only Python's standard library. No pip install, login, GitHub access, API key, internet connection or Ollama service is required for the demo. Three.js r128 and its license are included locally. Model loading and rendering depend on the machine's graphics hardware.

If a browser does not open automatically, copy the URL printed in the terminal. If port 8765 is occupied, the launcher selects another free port. Do not double-click viewer/index.html: browser fetch requests require the local HTTP server.

## Five-minute walkthrough

1. **Inspect grounding:** the first guided button highlights the unresolved surfaces and runs a typed provenance filter. Maradona contains 6 unresolved surfaces. Select a result row to inspect its record.
2. **Check provenance:** the second button inspects the recorded components and relations of building 915551373. Click a surface or graph node for its material, evidence and physical properties.
3. **Switch physical layer:** the third button alternates radio-material classes and LiDAR reflectance priors. The PBR/mode control cycles all views; the rain control compares dry/wet states.
4. **Try a query:** choose a controlled question and press Run. The interface shows the canonical typed query and computes results over the local graph. Browser-supported frozen benchmark questions are available in the same selector, including questions the graph cannot answer.

Expected Maradona query results:

| Query | Rows |
| --- | ---: |
| Unresolved surfaces | 6 |
| Brick surfaces | 38 |
| Supported EM properties (dry, 3.5 GHz) | 394 |
| Road reflectance priors | 201 |
| Geometrically recovered assignments | 0 |
| Roofs with recorded wet-state changes | 0 |

Zero results for the last two queries are expected in Maradona. Geometric recovery is represented in other scene graphs. Query results cover the viewer's complete graph; the paper's aggregate evaluation uses its explicit in-scope surface definition.

## Verify the data and claims

```bash
python verify_review.py
python verify_review.py --rebuild
```

Both commands use only the standard library. They check graph invariants, recorded input fingerprints, aggregate coverage, and the audit calculation. `--rebuild` additionally rebuilds the graphs in memory and compares every field to this anonymous snapshot; it does not overwrite data.

Reported coverage is 3,717 / 3,918 in-scope surfaces (94.9%) across three scenes. Audited precision is 126 / 133 settled cases (94.7%), with 17 uncertain cases excluded. These are different quantities. See [the audit protocol](audit/LABELLING_PROTOCOL.md), [audit results](results/grounding_audit_metrics.json), and [query schema](docs/query_schema.md).

To recompute the complete audit summary into a separate folder:

```bash
python audit/score_audit.py --input audit/grounding_audit_labelled.csv --out-dir review_results
```

The labelled CSV is also readable with audit/audit_tool.html (load the CSV into the tool). Original workstation viewer URLs have been removed; full 3D viewers for the other two scenes are not included.

## Contents and limits

- `viewer/`: offline Maradona demo, reduced-resolution GLB, frozen queries, radio and LiDAR overlays.
- `data/graphs/`: all three evaluated graphs.
- `source_graphs/`, `ue_osm_matches/`, `src/`: preserved inputs and graph construction/validation code.
- `audit/`, `results/`: labelled audit sample, scoring code and metrics.
- `docs/`: query schema and anonymization notes.

Full-resolution geometry for all scenes, model weights, and the complete experiment environment are outside this compact review package. The complete benchmark JSON retains Python-only operations such as `grid`; these are not offered as executable browser queries. The optional Python query/LLM utilities in src/ have separate dependencies; they are not needed for the browser demo or verify_review.py. Radio views expose material parameters, not simulated coverage fields. LiDAR views expose material-level reflectance priors, not calibrated sensor returns.

## Anonymous review snapshot

Personal workstation paths and repository-owner links have been removed. The ZIP contains no Git history, credentials, deployment workflows or Python bytecode. Source filenames in graph metadata use portable paths, and input fingerprints have been recomputed after anonymizing descriptive input headers. Scientific nodes, edges and properties are unchanged. See [anonymization notes](docs/reviewer-anonymization.md). Third-party library attribution is preserved.
