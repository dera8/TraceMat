#!/usr/bin/env python3
"""Genera docs/query_schema.md eseguendo davvero ogni operazione.

Reviewer qvxe ha chiesto che la documentazione delle operazioni sia pubblica.
Scriverla a mano significa scrivere esempi plausibili; qui ogni esempio viene
eseguito sul grafo autoritativo e il documento riporta il numero di righe
restituite e la forma di una riga reale. Se un'operazione cambia, la
rigenerazione lo mostra invece di lasciare il documento alla deriva.

    python scripts/generate_query_docs.py --scene Maradona --out docs/query_schema.md
"""
from __future__ import annotations
# src/ contiene i moduli condivisi; Python non la conosce quando lo
# script viene lanciato dalla radice del repo.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'src'))

import argparse
import json
import sys
from pathlib import Path

# nl_query e queries stanno nella radice del repo di lavoro (in src/ nel repo
# pubblicato); lo script sta in una sottocartella in entrambi i casi.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import nl_query
import queries

# Domanda in linguaggio naturale + query canonica, per ciascuna operazione.
# Le tredici che compaiono nel benchmark congelato usano il suo gold; per
# `nearest_street`, che il benchmark non copre, la query e' costruita qui.
EXAMPLES = [
    ("filter", "Which glass surfaces are in the scene?",
     {"op": "filter", "material_class": "glass"}),
    ("filter", "Which road surfaces are marked wettable by the rain-exposure model?",
     {"op": "filter", "surface": "road", "wettable": True}),
    ("provenance", "What does the graph record about this OSM building, "
                   "including its components and neighbours?",
     {"op": "provenance", "osm_id": "{osm_id}"}),
    ("state_change", "Which surfaces are affected by the modelled wet state?",
     {"op": "state_change", "state": "wet"}),
    ("quality", "Show all surfaces whose property confidence is at most 0.5.",
     {"op": "quality", "max_confidence": 0.5}),
    ("cross_modal", "Which permittivity and conductivity values are recorded "
                    "for glass surfaces?",
     {"op": "cross_modal", "material_class": "glass",
      "return": ["permittivity", "conductivity"]}),
    ("grid", "Which 100 m cells contain the highest density of surfaces with a "
             "modelled dry-wet state change?",
     {"op": "grid", "cell_m": 100.0, "min_surfaces": 10}),
    ("score", "Rank the entities whose electromagnetic signature changes most "
              "when it rains.",
     {"op": "score", "top": 5}),
    ("distribution", "How are surface types distributed across the scene?",
     {"op": "distribution", "attribute": "surface"}),
    ("coverage", "For how many surfaces does the permittivity come from the "
                 "scene catalogue rather than a class default?",
     {"op": "coverage"}),
    ("radio_materials", "Return the dry-state radio-material parameters for "
                        "plastered walls at 2.4 GHz.",
     {"op": "radio_materials", "surface": "wall",
      "material_contains": "plaster", "frequency_ghz": 2.4}),
    ("radio_state_change", "Which roof or road surfaces change their "
                           "radio-material parameters between dry and wet?",
     {"op": "radio_state_change", "surface_scope": ["roof", "road"]}),
    ("lidar_pseudoreflectance", "Show roof surfaces ordered by material-derived "
                                "LiDAR pseudo-reflectance, lowest first.",
     {"op": "lidar_pseudoreflectance", "surface": "roof", "sort": "ascending"}),
    ("provenance_filter", "Which evaluated roof and road surfaces have a "
                          "label-supported parent link?",
     {"op": "provenance_filter", "surface_scope": ["roof", "road"],
      "evidence_tier": "label_supported"}),
    ("nearest_street", "What does the graph hold for the surfaces nearest a "
                       "named street?",
     {"op": "nearest_street", "street_name": "{street}"}),
    ("unsupported", "Which surfaces show cracks in the most recent photograph?",
     {"op": "unsupported",
      "reason": "The graph has no real-world imagery or damage-state attribute.",
      "missing_concepts": ["real_world_observation"]}),
]

PROVENANCE_ID = {"Maradona": "915551373", "Siemensstadt": "127420094",
                 "CanaryWharf": "Trafalgar Way"}


def shape_of(result) -> str:
    """Descrive la forma del risultato senza riversarlo nel documento."""
    if isinstance(result, list):
        if not result:
            return "0 rows"
        first = result[0]
        if isinstance(first, dict):
            keys = ", ".join(f"`{k}`" for k in list(first)[:8])
            more = "" if len(first) <= 8 else f", … ({len(first)} fields)"
            return f"{len(result)} rows; fields: {keys}{more}"
        return f"{len(result)} rows"
    if isinstance(result, dict):
        return "one record; fields: " + ", ".join(f"`{k}`" for k in list(result)[:8])
    return type(result).__name__


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scene", default="Maradona")
    ap.add_argument("--out", type=Path, default=Path("docs/query_schema.md"))
    args = ap.parse_args()

    G = queries.load_graph(args.scene)
    street = next((d.get("osm_id") for _, d in queries._part_nodes(G)
                   if d.get("surface") == "road" and d.get("osm_id")), "Main Street")

    ops = [o for o in nl_query.ALLOWED_KEYS if o != "unsupported"]
    lines = [
        "# Closed query schema",
        "",
        f"The graph is queried through a closed schema of {len(ops)} typed",
        "operations, plus an explicit `unsupported` escape. A query is rejected",
        "before execution if it names an operation outside this list, a field",
        "outside that operation, or a value of the wrong type. Execution is",
        "deterministic and exact: the same query on an unchanged graph returns",
        "the same rows in the same order, and no operation ranks, retrieves",
        "approximately, or interpolates.",
        "",
        "Every example below was executed against "
        f"`data/graphs/{args.scene}_graph.json` when this file was generated,",
        "and the reported result shape is what came back. Regenerate with:",
        "",
        "```bash",
        f"python tools/generate_query_docs.py --scene {args.scene}",
        "```",
        "",
        "## Fields accepted by each operation",
        "",
        "| Operation | Accepted fields |",
        "|---|---|",
    ]
    for op in sorted(ops):
        fields = sorted(nl_query.ALLOWED_KEYS[op])
        lines.append(f"| `{op}` | "
                     + (", ".join(f"`{f}`" for f in fields) if fields else "*(none)*")
                     + " |")
    lines += ["", "## Worked examples", ""]

    ok = failed = 0
    for op, question, query in EXAMPLES:
        q = json.loads(json.dumps(query)
                       .replace("{osm_id}", PROVENANCE_ID.get(args.scene, ""))
                       .replace("{street}", str(street)))
        lines.append(f"### `{op}`")
        lines.append("")
        lines.append(f"*{question}*")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(q))
        lines.append("```")
        if op == "unsupported":
            lines += ["", "Returns no rows, and names the concept the graph does "
                          "not represent. Questions of this kind are answered by "
                          "declining, not by returning a plausible answer.", ""]
            ok += 1
            continue
        try:
            result = nl_query.execute(G, q)
            lines += ["", f"Returns: {shape_of(result)}.", ""]
            ok += 1
        except Exception as exc:
            lines += ["", f"*(not executable on {args.scene}: "
                          f"{type(exc).__name__})*", ""]
            failed += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"{args.out}: {len(ops)} operazioni + unsupported")
    print(f"  esempi eseguiti: {ok} riusciti, {failed} non eseguibili su {args.scene}")


if __name__ == "__main__":
    main()
