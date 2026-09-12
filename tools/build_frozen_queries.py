#!/usr/bin/env python3
"""Estrae le domande congelate del benchmark e le loro query canoniche.

Il pannello Ask del viewer compila una domanda in una query tipata usando un
modello servito in locale. Su una pagina ospitata quel modello non c'e', e il
pannello si limita a segnalare l'errore. Ma l'esecuzione della query e' gia'
lato browser e deterministica: solo la compilazione richiede il modello.

Questo script spedisce il risultato della compilazione per le 18 domande del
benchmark congelato, cosi' la demo pubblica mostra domanda, query tipata in cui
e' stata compilata, e le righe che l'esecuzione restituisce davvero --- che e'
la meta' deterministica del contributo. Non finge di compilare: dichiara che la
query e' quella canonica del benchmark.

    python scripts/build_frozen_queries.py --out ../twin-graph-demo/viewer/assets/frozen_queries.json
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

# Nella cartella di lavoro tutto e' piatto; nel repo pubblicato nl_benchmark
# sta in experiments/ e i moduli condivisi in src/. Aggiungiamo entrambe.
_root = Path(__file__).resolve().parent.parent
for _p in (_root, _root / "experiments", _root / "src"):
    sys.path.insert(0, str(_p))

from nl_benchmark import PROVENANCE_IDS, QUESTIONS


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scene", default="Maradona")
    ap.add_argument("--out", type=Path,
                    default=Path("../twin-graph-demo/viewer/assets/frozen_queries.json"))
    args = ap.parse_args()

    osm_id = PROVENANCE_IDS[args.scene]
    items = []
    for qid, audience, template, gold in QUESTIONS:
        items.append({
            "id": qid,
            "audience": audience,
            "question": template.format(osm_id=osm_id),
            "query": json.loads(json.dumps(gold).replace("{osm_id}", osm_id)),
        })

    payload = {
        "scene": args.scene,
        "note": ("Canonical queries for the frozen benchmark questions. The "
                 "query shown for each question is the reference compilation "
                 "used in the paper's evaluation, not a live compilation; "
                 "execution over the graph is performed in the browser and is "
                 "deterministic."),
        "questions": items,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")

    infeasible = sum(1 for i in items if i["query"]["op"] == "unsupported")
    print(f"{args.out}: {len(items)} domande ({infeasible} infeasible), scena {args.scene}")


if __name__ == "__main__":
    main()
