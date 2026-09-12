"""Deterministically build all authoritative TwinWorld graphs from preserved exports."""
import argparse, hashlib, json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from graph_validation import MATERIALS, validate_graph
from itu_p2040 import resolve
from evaluation_scope import classify_scope, semantic_surface_type

ROOT=Path(__file__).resolve().parent.parent; SCENES=("Maradona","Siemensstadt","CanaryWharf")
VERSION="2.0.0"; TOUCHES_M=0.5; NEARBY_M=25.0
MATCH_FILES={
    "Maradona": ROOT/'ue_osm_matches'/'maradona_ue_mesh_osm_match.json',
    "Siemensstadt": ROOT/'ue_osm_matches'/'siemensstadt_ue_mesh_osm_match.json',
    "CanaryWharf": ROOT/'ue_osm_matches'/'canarywharf_ue_mesh_osm_match.json',
}
# source_graphs/*.json store whatever material_type vocabulary their own
# (per-scene, sometimes untraceable) generator used, which isn't always a
# member of MATERIALS - untranslated it silently became "unknown" below,
# discarding a real classification (confirmed: Maradona's stadium roof/
# shell, material_class=="Steel" - correctly identified upstream, "elevated
# flat plate above a wall extrusion", but "steel" isn't in MATERIALS, only
# "metal" is). "gravel" is a member of MATERIALS in its own right (added
# alongside its itu_p2040 justification) and needs no alias - it used to be
# routed through "roofing" as a workaround for a since-fixed gap.
MATERIAL_CLASS_ALIASES={
    "steel":"metal", "cobblestone":"paving", "road_marking":"asphalt",
    "paving_stone":"paving", "sett":"sett",
    "kerb":"kerb", "rail_ballast":"rail_ballast", "grass":"grass",
    "earth":"earth", "water":"water",
}

def _tier(rule):
    r=(rule or "").lower()
    if "georef" in r or "polygon" in r or "geometric" in r: return "geometric"
    if "label" in r or "name" in r: return "label_supported"
    if "sidecar" in r or "assignment" in r: return "sidecar_supported"
    if "id" in r: return "exact"
    return "unassigned"

# TASK 3 (parent-validation vocabulary): every part_of relation created below
# links a surface to an entity that is ALREADY real - either a `surface==
# "building"` node present verbatim in source_graphs/*.json, or an entity
# materialized directly from a real, non-empty osm_id already asserted on
# the surface (see the entity-materialization loop below) - so no part_of
# target here is ever an arbitrary/invented string. _validation_status maps
# the existing evidence _tier() to the coarser paper-inclusion vocabulary:
# "exact"/"label_supported"/"sidecar_supported" are explicit link evidence
# (an id, a name match, or an assignment-file entry); "geometric" means the
# TARGET entity is still real/preexisting, only the surface<->entity
# ASSOCIATION was inferred from polygon containment rather than given
# directly - evidence_tier keeps that distinction queryable on its own.
def _validation_status(tier):
    return {
        "exact": "validated_osm",
        "label_supported": "validated_assignment",
        "sidecar_supported": "validated_assignment",
        "geometric": "preexisting_source_entity",
    }.get(tier, "unresolved")

def _validation_source(tier, rule):
    return {
        "exact": "exact OSM identifier field on surface",
        "label_supported": f"name/label match ({rule})" if rule else "name/label match",
        "sidecar_supported": f"assignment JSON sidecar ({rule})" if rule else "assignment JSON sidecar",
        "geometric": "geometric polygon containment against a preexisting source entity",
    }.get(tier)

def build_scene(scene, source=None, timestamp=None):
    source=source or ROOT/'source_graphs'/f'{scene}_source.json'
    raw=json.loads(Path(source).read_text(encoding='utf-8')); old_edges=raw.get('edges',raw.get('links',[]))
    # A small legacy gap in Siemensstadt left roof fragments unassigned in
    # source_graphs even though the preserved mesh matcher has exact OSM
    # building links. Restore only exact mesh-name matches; never use a
    # nearest-neighbour guess for parent association.
    match_path=MATCH_FILES.get(scene)
    exact_matches={}
    if match_path and match_path.exists():
        exact_matches={m.get('ue_mesh'):m for m in json.loads(match_path.read_text(encoding='utf-8')).get('matches',[])}
    for n in raw['nodes']:
        # Asphalt only: its ITU wet endpoint (medium_dry_ground -> wet_ground,
        # declared proxy) is a real P.2040 row via resolve(). No fallback for
        # other porous classes (concrete/plaster/brick/roofing/vegetation) -
        # P.2040 has no wet row for construction materials and none of the
        # reflectance_wet.py citations are electromagnetic quantities, so
        # asserting a number for them would be exactly the false-provenance
        # pattern this pipeline exists to avoid. They stay unparameterised.
        if (n.get('wettable') and str(n.get('material_class') or '').lower() == 'asphalt'
                and (n.get('permittivity_wet') is None or n.get('conductivity_wet') is None)):
            eps_wet, sig_wet, _ = resolve('asphalt', 3.5, 'wet')
            n['permittivity_wet'] = eps_wet
            n['conductivity_wet'] = sig_wet
        if n.get('surface')!='roof' or n.get('osm_id') not in (None,''):
            continue
        m=exact_matches.get(n.get('source_mesh_name') or n.get('name'))
        # Restores exact mesh-name matches AND parent-name-to-OSM-name
        # matches (both checked below) - never a nearest-neighbour guess.
        if (m and m.get('osm_key') and m.get('osm_kind') in {'building','building_name'}
                and m.get('match_source') in {'source_exact_mesh_name','source_parent_name_to_osm_name'}):
            n['osm_id']=str(m['osm_key'])
            n['link_source']=m.get('match_source')
    # Maradona's roof fragments were exported with their own node_* parent,
    # while the corresponding wall used a different node_* parent. When the
    # horizontal XZ footprint overlaps the wall footprint, restore the roof
    # parent from that explicit geometric identity. A strict IoU threshold
    # avoids assigning isolated/ambiguous roof plates to an adjacent building.
    walls=[n for n in raw['nodes'] if n.get('surface')=='wall' and n.get('osm_id')
           and n.get('bbox_min') and n.get('bbox_max')]
    for n in raw['nodes']:
        if n.get('surface')!='roof' or not n.get('bbox_min') or not n.get('bbox_max'):
            continue
        def area_xz(x):
            return max(0.0,x['bbox_max'][0]-x['bbox_min'][0]) * max(0.0,x['bbox_max'][2]-x['bbox_min'][2])
        def iou_xz(a,b):
            ix=max(0.0,min(a['bbox_max'][0],b['bbox_max'][0])-max(a['bbox_min'][0],b['bbox_min'][0]))
            iz=max(0.0,min(a['bbox_max'][2],b['bbox_max'][2])-max(a['bbox_min'][2],b['bbox_min'][2]))
            inter=ix*iz; union=area_xz(a)+area_xz(b)-inter
            return inter/union if union else 0.0
        best=max(((iou_xz(n,w),w) for w in walls),key=lambda x:x[0],default=(0.0,None))
        if best[1] is not None and best[0]>=0.8:
            n['osm_id']=str(best[1]['osm_id'])
            n['link_source']='roof_wall_bbox_geometric'
    nodes=[]; entities={}; surfaces=[]
    for n0 in raw['nodes']:
        n=dict(n0); n['id']=str(n['id']); n['scene']=scene
        semantic_surface = semantic_surface_type(n)
        if semantic_surface and semantic_surface != str(n.get('surface') or '').strip().lower():
            n['surface'] = semantic_surface
            n['surface_semantic_source'] = 'mesh_name_prefix_override'
        if n.get('surface')=='building':
            n['kind']='entity'; entities[str(n.get('osm_id'))]=n['id']
        else:
            n['kind']='surface'; n['source_mesh_name']=n.get('source_mesh_name',n.get('name',n['id']))
            n['scope_status'], n['scope_reason'] = classify_scope(n)
            mat=str(n.get('material_class') or 'unknown').lower()
            mat=MATERIAL_CLASS_ALIASES.get(mat,mat)
            n['material_class']=mat if mat in MATERIALS else 'unknown'
            surfaces.append(n)
        nodes.append(n)
    # Some legacy exports omitted entity nodes while retaining an exact OSM ID
    # on the source mesh. Materialize those traceability entities reproducibly.
    for oid in sorted({str(n['osm_id']) for n in surfaces if n.get('osm_id') not in (None,'')} - set(entities)):
        eid=f'B_{oid}'; entity={'id':eid,'kind':'entity','surface':'building','osm_id':oid,'scene':scene,'n_parts':0,'source':'surface_osm_id'}
        nodes.append(entity); entities[oid]=eid
    evidence={str(e['source']):e for e in old_edges if e.get('relation')=='part_of'}
    edges=[]; rules=Counter(); unresolved=0; out_of_scope=0
    for n in surfaces:
        if n.get('scope_status') == 'out_of_scope':
            n['grounding_status']='not_applicable'; n['evidence_tier']='not_applicable'
            n['parent_validation_status']='not_applicable'; n['parent_validation_source']=None
            n['source_part_of_present']=n['id'] in evidence if 'evidence' in locals() else False; out_of_scope += 1
            continue
        oid=str(n.get('osm_id')) if n.get('osm_id') not in (None,'') else None
        if oid and oid in entities:
            old=evidence.get(n['id'],{}); rule=old.get('grounding_rule',old.get('rule',n.get('link_source','explicit_osm_id')))
            tier=_tier(rule); status=_validation_status(tier); vsource=_validation_source(tier,rule)
            has_source_edge=n['id'] in evidence
            n['grounding_status']='grounded'; n['evidence_tier']=tier
            n['parent_validation_status']=status; n['parent_validation_source']=vsource; n['source_part_of_present']=has_source_edge
            rules[rule]+=1
            e={'source':n['id'],'target':entities[oid],'relation':'part_of','grounding_rule':rule,'evidence_tier':tier,
               'parent_validation_status':status,'parent_validation_source':vsource,'source_part_of_present':has_source_edge,
               'provenance':old.get('provenance',n.get('confidence_reason','source OSM identifier')),
               'candidate_count':old.get('candidate_count',1),'source_reference':old.get('source_reference',str(source.name))}
            score=old.get('score');
            if score is not None: e['score']=score
            edges.append(e)
        else:
            n['grounding_status']='unresolved'; n['evidence_tier']='unresolved'; n['osm_id']=None; unresolved+=1
            n['parent_validation_status']='unresolved'; n['parent_validation_source']=None; n['source_part_of_present']=False
    # Preserve only relation evidence already derived from metric geometry; never create k-NN edges.
    node_ids={n['id'] for n in nodes}
    for e0 in old_edges:
        if e0.get('relation') == 'part_of':
            src = str(e0.get('source')); tgt = str(e0.get('target'))
            src_node = next((x for x in nodes if x['id'] == src), None)
            # Preserve an authoritative source part_of for a retained
            # out-of-scope component. It is traceability, not a successful
            # material-grounding assignment, and is excluded from coverage.
            if (src_node and src_node.get('scope_status') == 'out_of_scope'
                    and src in node_ids and tgt in node_ids):
                edges.append(dict(e0, source=src, target=tgt))
            continue
        if e0.get('relation') not in ('touches','nearby','native_osm'): continue
        e=dict(e0); e['source']=str(e['source']); e['target']=str(e['target'])
        if e['source'] in node_ids and e['target'] in node_ids: edges.append(e)
    nodes.sort(key=lambda n:n['id']); edges.sort(key=lambda e:(e['relation'],e['source'],e['target']))
    rels=Counter(e['relation'] for e in edges); kinds=Counter(n['kind'] for n in nodes)
    ts=timestamp or datetime.fromtimestamp(Path(source).stat().st_mtime,timezone.utc).isoformat()
    # Every file actually read while building this scene, not just the
    # primary source export - the roof osm_id backfill above reads
    # match_path too, and an undeclared second input means the hash of
    # `source` alone cannot guarantee a byte-identical rebuild.
    input_files=[Path(source)]
    if match_path and match_path.exists(): input_files.append(match_path)
    meta={'scene':scene,'generation_timestamp':ts,'generator_version':VERSION,
      'source_files':[str(p.relative_to(ROOT)) for p in input_files],
      'source_file_sha256':[hashlib.sha256(p.read_bytes()).hexdigest() for p in input_files],
      'node_counts':dict(kinds),'edge_counts':dict(rels),
      'grounding_rule_counts':dict(rules),'unresolved_count':unresolved,
      'out_of_scope_count':out_of_scope,
      'in_scope_count':sum(n.get('scope_status') == 'in_scope' for n in surfaces),
      'grounded_in_scope_count':sum(n.get('grounding_status') == 'grounded' for n in surfaces),
      'unresolved_in_scope_count':unresolved,
      'not_applicable_count':sum(n.get('grounding_status') == 'not_applicable' for n in surfaces),
      'scope_reason_counts':dict(Counter(n.get('scope_reason') for n in surfaces if n.get('scope_status') == 'out_of_scope')),
      'unknown_material_in_scope_count':sum(n.get('scope_status') == 'in_scope' and n.get('material_class') == 'unknown' for n in surfaces),
      'unknown_material_total_count':sum(n.get('material_class') == 'unknown' for n in surfaces),
      'unknown_material_count':sum(n.get('material_class')=='unknown' for n in surfaces),
      'registration':{'parameters':None,'control_point_count':None,'residual_statistics':{'mean':None,'median':None,'maximum':None}},
      'touches_threshold_m':TOUCHES_M,'nearby_threshold_m':NEARBY_M,
      'relation_note':'Existing metric-derived relations preserved; no k-nearest-neighbour edges generated.'}
    out={'directed':False,'multigraph':False,'graph':meta,'nodes':nodes,'edges':edges}; validate_graph(out); return out

def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--all',action='store_true'); ap.add_argument('--scene',choices=SCENES); ap.add_argument('--validate-only',action='store_true'); a=ap.parse_args(argv)
    chosen=SCENES if a.all or not a.scene else (a.scene,)
    for scene in chosen:
        path=ROOT/'data'/'graphs'/f'{scene}_graph.json'
        if a.validate_only: validate_graph(json.loads(path.read_text(encoding='utf-8'))); print(f'VALID {scene}'); continue
        data=build_scene(scene); path.parent.mkdir(exist_ok=True); path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8'); print(f"WROTE {path}: {len(data['nodes'])} nodes, {len(data['edges'])} edges")
if __name__=='__main__': main()
