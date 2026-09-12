#!/usr/bin/env python3
"""Score manually completed v2 audits; blanks/uncertain never count as correct."""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict
from pathlib import Path

def wilson(k,n,z=1.96):
    if not n:return (None,None)
    p=k/n; d=1+z*z/n; c=(p+z*z/(2*n))/d; h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return (c-h,c+h)
def summary(rows):
    resolved=[r for r in rows if (r.get("audit_label") or "").strip().lower() in {"correct","incorrect"}]
    k=sum((r.get("audit_label") or "").strip().lower()=="correct" for r in resolved); lo,hi=wilson(k,len(resolved))
    return {"n_total":len(rows),"n_resolved":len(resolved),"n_correct":k,"n_incorrect":len(resolved)-k,"n_uncertain":sum((r.get("audit_label") or "").strip().lower()=="uncertain" for r in rows),"n_blank":sum(not (r.get("audit_label") or "").strip() for r in rows),"precision_resolved":None if not resolved else k/len(resolved),"wilson95_low":lo,"wilson95_high":hi}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--input",type=Path,default=Path("audit/grounding_audit_sample.csv")); ap.add_argument("--out-dir",type=Path,default=Path("results")); a=ap.parse_args(); rows=list(csv.DictReader(a.input.open(encoding="utf-8")))
 out=[dict({"group":"overall","value":"all"},**summary(rows))]
 for field in ("scene","canonical_evidence_tier","surface"):
  groups=defaultdict(list)
  for r in rows:groups[r.get(field,"")].append(r)
  out += [dict({"group":field,"value":v},**summary(rs)) for v,rs in sorted(groups.items())]
 # Agreement requires two independent labels for the same audit id in a merged file.
 byid=defaultdict(list)
 for r in rows:
  if (r.get("annotator") or "").strip() and (r.get("audit_label") or "").strip():byid[r["audit_id"]].append(r)
 paired=[v for v in byid.values() if len({x["annotator"] for x in v})>=2]
 report={"inter_annotator_agreement":None,"agreement_note":"requires two independent annotators per audit_id","rows":out}
 a.out_dir.mkdir(parents=True,exist_ok=True); (a.out_dir/"grounding_audit_metrics.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
 with (a.out_dir/"grounding_audit_metrics.csv").open("w",newline="",encoding="utf-8") as f:w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
 print(json.dumps(out[0]))
if __name__=="__main__":main()
