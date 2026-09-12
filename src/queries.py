"""Exact query functions over the material-grounded scene graphs in
graphs/*.json. Every function returns EXACT results computed with networkx -
no LLM involved anywhere in this file. nl_query.py only decides WHICH of
these to call and with what arguments; it never computes the answer itself.

graphs/*.json are the paper's authoritative graphs, deterministically
rebuilt by `python build_scene_graphs.py --all` from the immutable
source_graphs/*_source.json exports (see FINAL_REPOSITORY_AUDIT.md) - this
replaced the earlier hand-placed/superseded-extractor split.
legacy/build_scene_graphs.py remains superseded; never run it against these
graphs. Nodes DO carry a "kind" attribute ("entity" or "surface"): a building
entity has kind=="entity" and id prefix "B_..."; every other node has
kind=="surface", id'd by a bare index string ("0", "1", ...). Building
targets on edges use the "B_<osm_id>" id form (not "B:<osm_id>").
Everything below only ever READS these stored attributes - nothing here
infers wettable/measured/material-class from anything else. Scientific
(paper) evaluation is further restricted to wall/roof/window/road via
evaluation_scope.py - that restriction is NOT applied inside these query
functions themselves (they operate over the complete maintenance graph);
callers building paper tables must filter through evaluation_scope first.
"""
import json
import math
import re
import unicodedata
from pathlib import Path

import networkx as nx
from physics_properties import em_state, numeric, provenance, radio_eligible, reflectance_eligible, normalise
from lidar_reflectance_903nm import lookup as lidar_prior_lookup

ROOT = Path(__file__).resolve().parent.parent
GRAPH_DIR = ROOT / "data" / "graphs"

SCENES = ["Maradona", "Siemensstadt", "CanaryWharf"]


def load_graph(scene: str) -> nx.Graph:
    if scene not in SCENES:
        raise ValueError(f"unknown scene '{scene}', expected one of {SCENES}")
    path = GRAPH_DIR / f"{scene}_graph.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - place the authoritative graph there")
    data = json.loads(path.read_text(encoding="utf-8"))
    return nx.node_link_graph(data, edges="edges")


def _part_nodes(G: nx.Graph):
    return sorted(((str(nid), d) for nid, d in G.nodes(data=True) if d.get("kind") == "surface" or d.get("surface") != "building"), key=lambda x:x[0])


def _building_id(osm_id: str) -> str:
    return f"B_{osm_id}"


def _neighbors_by_relation(G: nx.Graph, building_id: str, relation: str):
    out = []
    for u, v, edata in G.edges(building_id, data=True):
        if edata.get("relation") != relation:
            continue
        other = v if u == building_id else u
        out.append({"node": other, "osm_id": G.nodes[other].get("osm_id"), "distance_m": edata.get("distance_m")})
    return sorted(out, key=lambda r:r["node"])


# --------------------------------------------------------------------- q1 --

def q1_filter(G: nx.Graph, surface=None, material_class=None, material_contains=None, wettable=None, has_wet_state=None):
    """Filter part-nodes by any combination of: exact surface, exact
    `material_class` (case-insensitively since the schema prompt asks the
    LLM for lowercase classes but the graph stores them capitalized -
    parameter name matches the stored attribute name 1:1, deliberately: an
    earlier mismatch here, where the query parameter was called `material`
    while the stored/displayed attribute was `material_class`, was the root
    cause of the LLM inventing the (wrong) key `material_class` for this
    op), material_contains (substring match against the class label OR the
    raw source material name), wettable (bool - read directly from the
    stored `wettable` attribute, never inferred from material),
    has_wet_state (bool - whether ANY dry/wet property pair actually has a
    stored non-null wet value; a stricter, more honest check than
    `wettable`, which is only a declared orientation flag and can be true
    with no recorded wet value)."""
    # The legacy PBR ``reflectance_wet`` fields may remain in historical graph
    # serializations for auditability, but they are not a state-calibrated
    # physical layer.  Optical wet-state availability is provided exclusively
    # by the external 903.9 nm LiDAR property layer.
    wet_fields = ("permittivity_wet", "conductivity_wet", "thermal_conductivity_wet", "roughness_wet")
    out = []
    for nid, d in _part_nodes(G):
        if surface is not None and d.get("surface") != surface:
            continue
        if material_class is not None and (d.get("material_class") or "").lower() != material_class.lower():
            continue
        if material_contains is not None:
            needle = material_contains.lower()
            hay = f"{d.get('material_class','')} {d.get('material','')}".lower()
            if needle not in hay:
                continue
        if wettable is not None and bool(d.get("wettable")) != bool(wettable):
            continue
        if has_wet_state is not None:
            present = any(d.get(f) is not None for f in wet_fields)
            if present != bool(has_wet_state):
                continue
        out.append({"id": nid, **d})
    return sorted(out, key=lambda r:r["id"])


# --------------------------------------------------------------------- q2 --

def q2_provenance(G: nx.Graph, osm_id: str, surface_scope=None):
    """Everything known about one OSM building/way: its parts (with material
    + confidence/confidence_reason) and its touches/nearby neighbours.
    `surface_scope` (optional list, e.g. ["wall","roof","window"]) restricts
    the returned `parts` to those surface types only; touches/nearby and
    n_parts (the TRUE total part count) are unaffected by the restriction."""
    building_id = _building_id(osm_id)
    if building_id not in G:
        return {"found": False, "osm_id": osm_id}
    parts=[]
    for neighbor in G.neighbors(building_id):
        edge=G.get_edge_data(building_id,neighbor) or {}
        if edge.get("relation") == "part_of": parts.append({"id":str(neighbor),**G.nodes[neighbor]})
    parts.sort(key=lambda p:p["id"])
    # Some exported mesh components carry an OSM id directly but are not
    # children of a building entity (e.g. a pole/fence or street furniture).
    # Keep them queryable, while exposing that this is a direct component and
    # not a building with zero surfaces.
    direct = [{"id": str(nid), **data} for nid, data in G.nodes(data=True)
              if data.get("kind") == "surface" and str(data.get("osm_id")) == str(osm_id)]
    if not parts and direct:
        parts = sorted(direct, key=lambda p: p["id"])
    n_parts=len(parts)
    if surface_scope is not None:
        scope=set(surface_scope)
        parts=[p for p in parts if p.get("surface") in scope]
    direct_only = bool(direct and not any(
        G.get_edge_data(building_id, p["id"], {}).get("relation") == "part_of" for p in direct))
    return {
        "found": True,
        "osm_id": osm_id,
        "n_parts": n_parts,
        "parts": parts,
        "entity_kind": G.nodes[building_id].get("kind"),
        "entity_surface": G.nodes[building_id].get("surface"),
        "reported_kind": (direct[0].get("surface") if direct_only else "building"),
        "direct_component": direct_only,
        "touches": _neighbors_by_relation(G, building_id, "touches"),
        "nearby": _neighbors_by_relation(G, building_id, "nearby"),
    }


# --------------------------------------------------------------------- q3 --

def q3_state_change(G: nx.Graph, state: str = "wet", abs_tol: float = 1e-9, rel_tol: float = 1e-6):
    """Surfaces with an actual stored dry/wet physical-property change.

    This deliberately compares the authoritative values rather than using
    ``wettable`` as a proxy.  A row is returned when either permittivity or
    conductivity differs between the dry and wet states.
    """
    if state != "wet":
        raise ValueError("only state='wet' is modelled in this demo")
    pairs = (
        ("permittivity_dry", "permittivity_wet"),
        ("conductivity_dry", "conductivity_wet"),
        ("thermal_conductivity_dry", "thermal_conductivity_wet"),
        ("roughness_dry", "roughness_wet"),
    )
    out=[]
    for nid,d in _part_nodes(G):
        changed=[]; dry_values={}; wet_values={}; absolute={}; relative={}; missing=[]; unchanged=[]
        for dry,wet in pairs:
            if dry not in d and wet not in d: continue
            name=dry[:-4]; dv,wv=d.get(dry),d.get(wet); dry_values[name]=dv; wet_values[name]=wv
            if dv is None or wv is None: missing.append(name); continue
            try: diff=abs(float(wv)-float(dv)); rel=diff/max(abs(float(dv)),abs(float(wv)),abs_tol)
            except (TypeError,ValueError): continue
            absolute[name]=diff; relative[name]=rel
            if diff>abs_tol and rel>rel_tol: changed.append(name)
            else: unchanged.append(name)
        if changed:
            out.append({'id':nid,'node_id':nid,'osm_id':d.get('osm_id'),'surface':d.get('surface'),'material_class':d.get('material_class'),
              'changed_fields':changed,'dry_values':dry_values,'wet_values':wet_values,'absolute_differences':absolute,
              'relative_differences':relative,'missing_wet_fields':missing,'explicitly_unchanged_fields':unchanged,
              'provenance':d.get('wet_src') or d.get('permittivity_src')})
    return out

def state_change_summary(G, **kwargs):
    rows=q3_state_change(G,**kwargs); props={}
    for r in rows:
        for p in r['changed_fields']: props.setdefault(p,[]).append(r['absolute_differences'][p])
    return {'changed_surface_count':len(rows),'affected_entity_count':len({r['osm_id'] for r in rows if r['osm_id']}),
      'affected_material_classes':sorted({r['material_class'] for r in rows if r['material_class']}),
      'changes':{p:{'mean':sum(v)/len(v),'maximum':max(v)} for p,v in sorted(props.items())},'geometry_changes':0}


# --------------------------------------------------------------------- q4 --

def q4_quality(G: nx.Graph, max_confidence: float = 0.6):
    """Low-confidence / effectively-unassigned physical properties: parts
    whose confidence is at or below the given threshold (i.e. class-default
    heuristics rather than the scene's physical-metadata catalog)."""
    out = []
    for nid, d in _part_nodes(G):
        if d.get("confidence", 0.0) <= max_confidence:
            out.append({"id": nid, **d})
    return sorted(out, key=lambda r:r["id"])


# --------------------------------------------------------------------- q5 --

def q5_cross_modal(G: nx.Graph, material_class: str, return_fields):
    """Parts whose `material_class` matches (e.g. 'glass', case-insensitive),
    projected down to just the requested fields (plus id/osm_id/material for
    context, always included). Parameter renamed from the earlier `appearance`
    to match the stored attribute name 1:1 (see q1_filter's docstring for why
    that mismatch mattered); `appearance` is still accepted as a query-schema
    alias in nl_query.py's execute(), just not as this function's own kwarg."""
    always = ["id", "osm_id", "material_class", "surface"]
    out = []
    for nid, d in _part_nodes(G):
        if (d.get("material_class") or "").lower() != material_class.lower():
            continue
        row = {k: (nid if k == "id" else d.get(k)) for k in always}
        for f in return_fields:
            row[f] = d.get(f)
        out.append(row)
    return sorted(out, key=lambda r:r["id"])


# --------------------------------------------------------------------- q6 --

def q6_grid(G: nx.Graph, cell_m: float = 100.0, min_surfaces: int = 10):
    """Spatial aggregation: bins non-building nodes into cell_m x cell_m XZ
    cells using each node's stored `centroid` (floor(centroid[0]/cell_m),
    floor(centroid[2]/cell_m)); reads wettable, conductivity_dry/wet and
    heat_capacity - never recomputes any of them. Returns cells with at
    least min_surfaces surfaces, sorted by wet_fraction descending."""
    cells = {}
    for nid, d in _part_nodes(G):
        c = d.get("centroid")
        if not c:
            continue
        key = (int(c[0] // cell_m), int(c[2] // cell_m))
        cell = cells.get(key)
        if cell is None:
            cell = {"cell_x": key[0], "cell_z": key[1], "n_surfaces": 0, "n_wettable": 0,
                     "sum_delta_sigma": 0.0, "n_high_heat_capacity": 0}
            cells[key] = cell
        cell["n_surfaces"] += 1
        if d.get("wettable"):
            cell["n_wettable"] += 1
            cd, cw = d.get("conductivity_dry"), d.get("conductivity_wet")
            if cd is not None and cw is not None:
                cell["sum_delta_sigma"] += cw - cd
        hc = d.get("heat_capacity")
        if hc is not None and hc >= 1000:
            cell["n_high_heat_capacity"] += 1
    out = [c for c in cells.values() if c["n_surfaces"] >= min_surfaces]
    for c in out:
        c["wet_fraction"] = c["n_wettable"] / c["n_surfaces"]
    out.sort(key=lambda c: c["wet_fraction"], reverse=True)
    return out


# --------------------------------------------------------------------- q7 --

def q7_score(G: nx.Graph, top: int = 10):
    """Composite per-entity score: for each osm_id, sums (conductivity_wet -
    conductivity_dry) * bbox_footprint_area over its wettable surfaces that
    have both conductivity values, where bbox_footprint_area is derived from
    the stored bbox_min/bbox_max. Reads wettable/conductivity_dry/wet/
    bbox_min/bbox_max only - never recomputes them. Returns the top-N
    entities by score.

    The weighting (raw footprint area, no distance/frequency/antenna model)
    is ILLUSTRATIVE, not calibrated: it ranks entities by the magnitude of
    their own stored EM state change, it does not predict a physical field
    or signal strength anywhere else in the scene.
    """
    scores = {}
    for nid, d in _part_nodes(G):
        osm_id = d.get("osm_id")
        if not osm_id:
            continue
        entry = scores.get(osm_id)
        if entry is None:
            entry = {"osm_id": osm_id, "n_surfaces": 0, "n_wettable": 0, "score": 0.0}
            scores[osm_id] = entry
        entry["n_surfaces"] += 1
        if not d.get("wettable"):
            continue
        entry["n_wettable"] += 1
        cd, cw = d.get("conductivity_dry"), d.get("conductivity_wet")
        bbox_min, bbox_max = d.get("bbox_min"), d.get("bbox_max")
        if cd is None or cw is None or not bbox_min or not bbox_max:
            continue
        area = (bbox_max[0] - bbox_min[0]) * (bbox_max[2] - bbox_min[2])
        entry["score"] += (cw - cd) * area
    out = sorted(scores.values(), key=lambda e: e["score"], reverse=True)
    return out[:top]


# --------------------------------------------------------------------- q8 --

DISTRIBUTION_ATTRIBUTES = ("material_class", "surface", "permittivity_src", "link_source")


def q8_distribution(G: nx.Graph, attribute: str = "material_class"):
    """Attribute distribution: counts non-building nodes per distinct value
    of the given stored attribute (one of DISTRIBUTION_ATTRIBUTES), with
    percentage share, sorted by count descending. Reads only that one
    attribute; nodes where it is missing are excluded from both the count
    and the percentage base."""
    if attribute not in DISTRIBUTION_ATTRIBUTES:
        raise ValueError(f"unsupported attribute '{attribute}', expected one of {DISTRIBUTION_ATTRIBUTES}")
    counts = {}
    total = 0
    for nid, d in _part_nodes(G):
        v = d.get(attribute)
        if v is None:
            continue
        counts[v] = counts.get(v, 0) + 1
        total += 1
    out = [{"value": v, "count": c, "pct": round(100 * c / total, 2)} for v, c in counts.items()]
    out.sort(key=lambda r: r["count"], reverse=True)
    return out


# --------------------------------------------------------------------- q9 --

def q9_coverage(G: nx.Graph):
    """Provenance-completeness audit over non-building nodes: reads
    permittivity_src, osm_id, link_source and confidence only. Reports total
    count; measured (permittivity_src == 'metadata') vs estimated (anything
    else); unassigned (no osm_id); the link_source distribution; and the
    confidence distribution. A pure tally of stored provenance fields -
    nothing here is recomputed."""
    total = measured = estimated = unresolved = out_of_scope = 0
    link_source_distribution = {}
    confidence_distribution = {}
    for nid, d in _part_nodes(G):
        total += 1
        if d.get("permittivity_src") == "metadata":
            measured += 1
        else:
            estimated += 1
        status = d.get("grounding_status")
        if status == "unresolved" or (status == "unassigned" and d.get("scope_status") is None):
            unresolved += 1
        if d.get("scope_status") == "out_of_scope":
            out_of_scope += 1
        ls = d.get("link_source")
        link_source_distribution[ls] = link_source_distribution.get(ls, 0) + 1
        conf = d.get("confidence")
        confidence_distribution[conf] = confidence_distribution.get(conf, 0) + 1
    return {
        "total": total,
        "measured": measured,
        "estimated": estimated,
        "unresolved": unresolved,
        "out_of_scope": out_of_scope,
        "link_source_distribution": link_source_distribution,
        "confidence_distribution": confidence_distribution,
    }

def q_em_state_sensitivity(G, frequency_ghz=3.5, minimum_relative_change=0.0):
    out=[]
    for nid,d in _part_nodes(G):
        vals=[numeric(d.get(k)) for k in ('permittivity_dry','permittivity_wet','conductivity_dry','conductivity_wet')]
        if any(v is None for v in vals):continue
        try:dry=em_state(vals[0],vals[2],frequency_ghz);wet=em_state(vals[1],vals[3],frequency_ghz)
        except ValueError:continue
        rel=abs(wet['attenuation_db_per_m']-dry['attenuation_db_per_m'])/max(abs(dry['attenuation_db_per_m']),1e-15)
        if rel<minimum_relative_change:continue
        out.append({'id':nid,'node_id':nid,'mesh_id':d.get('source_mesh_name',d.get('name')),'osm_id':d.get('osm_id'),'surface':d.get('surface'),'material_class':d.get('material_class'),'frequency_ghz':frequency_ghz,'attenuation_db_per_m_dry':dry['attenuation_db_per_m'],'attenuation_db_per_m_wet':wet['attenuation_db_per_m'],'relative_attenuation_change':rel,'unit':'dB m^-1','source':f"{d.get('permittivity_src')}; {d.get('conductivity_src')}",'provenance':d.get('confidence_reason')})
    return sorted(out,key=lambda r:(-r['relative_attenuation_change'],r['id']))

def q_road_reflectance(G,state='dry'):
    if state not in ('dry','wet'):raise ValueError('state must be dry or wet')
    out=[]
    for nid,d in _part_nodes(G):
        if d.get('surface')!='road':continue
        specific=numeric(d.get(f'reflectance_{state}'));static=numeric(d.get('reflectance'));value=specific if specific is not None else static
        src,prov=provenance(d,'reflectance');out.append({'id':nid,'node_id':nid,'mesh_id':d.get('source_mesh_name',d.get('name')),'osm_id':d.get('osm_id'),'surface':'road','material_class':d.get('material_class'),'state':state,'value':value,'unit':'1','source':src,'provenance':prov,'static_fallback':specific is None and static is not None,'missing':value is None})
    return sorted(out,key=lambda r:r['id'])

def q_radio_materials(G,frequency_ghz=3.5,state='dry',surface=None,material_contains=None):
    if state not in ('dry','wet') or frequency_ghz<=0:raise ValueError('invalid radio query')
    out=[]
    for nid,d in _part_nodes(G):
        if surface is not None and d.get('surface')!=surface:continue
        if material_contains is not None:
            hay=f"{d.get('material_class','')} {d.get('material','')}".lower()
            if material_contains.lower() not in hay:continue
        if not radio_eligible(d,state):continue
        er=numeric(d.get(f'permittivity_{state}'));sigma=numeric(d.get(f'conductivity_{state}'));derived=em_state(er,sigma,frequency_ghz)
        out.append({'id':nid,'node_id':nid,'mesh_id':d.get('source_mesh_name',d.get('name')),'osm_id':d.get('osm_id'),'surface':d.get('surface'),'material_class':d.get('material_class'),'itu_family':d.get('itu_family'),'state':state,'frequency_ghz':frequency_ghz,'relative_permittivity':er,'conductivity_s_per_m':sigma,'loss_tangent':derived['loss_tangent'],'attenuation_db_per_m':derived['attenuation_db_per_m'],'source':f"epsilon:{d.get('permittivity_src')}; sigma:{d.get('conductivity_src')}",'provenance':d.get('confidence_reason'),'claim':'Radio-material assignment for downstream simulation; no radio coverage field is computed.'})
    return sorted(out,key=lambda r:r['id'])

def q_lidar_reflectance_prior(G, surface=None, sort=None, state='dry'):
    """Return dry 903.9 nm material-level LiDAR priors.

    The catalog is an external overlay: this function only reads graph
    material classes and never writes node or edge attributes. Unknown and
    unsupported classes are excluded from the scientific ranking by default.
    """
    out = []
    for nid, d in _part_nodes(G):
        if surface is not None and d.get('surface') != surface:
            continue
        prior = lidar_prior_lookup(d.get('material_class'), state=state, allow_unknown=False)
        if prior is None:
            continue
        row = prior.as_dict()
        row.update({
            'id': nid, 'node_id': nid,
            'mesh_id': d.get('source_mesh_name', d.get('name')),
            'osm_id': d.get('osm_id'), 'surface': d.get('surface'),
            # Deprecated aliases retained for the public benchmark schema.
            'source_reflectance': prior.reflectance_mean,
            'pseudo_reflectance': prior.reflectance_mean,
            'unit': 'fraction_0_to_1', 'source': 'urmat_lidar_reflectance_dry_wet_903nm_v2_corrected.json',
            'normalisation_min': None, 'normalisation_max': None,
            'normalisation_scope': None,
        })
        out.append(row)
    if sort in ('ascending', 'descending'):
        out.sort(key=lambda r: (r['reflectance_mean'], r['id']), reverse=sort == 'descending')
    else:
        out.sort(key=lambda r: r['id'])
    return out


def q_lidar_pseudoreflectance(G, surface=None, sort=None, state='dry'):
    """Backward-compatible wrapper for the 903.9 nm LiDAR prior query."""
    return q_lidar_reflectance_prior(G, surface=surface, sort=sort, state=state)

def q_radio_state_change(G,surface_scope=None,frequency_ghz=3.5):
    """Surfaces within `surface_scope` (default: the four scientific
    categories) whose radio-relevant properties (permittivity, conductivity)
    actually differ between the stored dry and wet states - E1's op. Reuses
    the same stored-value comparison as q3_state_change, restricted to the
    two radio-relevant pairs and to the given surface scope."""
    scope=set(surface_scope) if surface_scope is not None else None
    pairs=(('permittivity_dry','permittivity_wet'),('conductivity_dry','conductivity_wet'))
    out=[]
    for nid,d in _part_nodes(G):
        if scope is not None and d.get('surface') not in scope:continue
        changed=[];dry_values={};wet_values={}
        for dry,wet in pairs:
            name=dry[:-4];dv,wv=numeric(d.get(dry)),numeric(d.get(wet));dry_values[name]=dv;wet_values[name]=wv
            if dv is None or wv is None:continue
            if abs(wv-dv)>1e-9 and abs(wv-dv)/max(abs(dv),abs(wv),1e-9)>1e-6:changed.append(name)
        if not changed:continue
        out.append({'id':nid,'node_id':nid,'osm_id':d.get('osm_id'),'surface':d.get('surface'),'material_class':d.get('material_class'),
          'changed_fields':changed,'dry_values':dry_values,'wet_values':wet_values,'frequency_ghz':frequency_ghz,
          'provenance':d.get('permittivity_src'),'claim':'Radio-material dry/wet state comparison; no propagation field is computed.'})
    return sorted(out,key=lambda r:r['id'])

def q_provenance_filter(G,surface_scope=None,evidence_tier=None):
    """Evaluated surfaces (within `surface_scope`, if given) filtered by
    `evidence_tier` (e.g. "geometric") - E3's op, a transparency query over
    HOW a surface's parent relation was established, not a physical-property
    query. Reads the stored `evidence_tier`/`parent_validation_status`
    fields only; never re-derives them."""
    scope=set(surface_scope) if surface_scope is not None else None
    out=[]
    for nid,d in _part_nodes(G):
        if scope is not None and d.get('surface') not in scope:continue
        if evidence_tier is not None and d.get('evidence_tier')!=evidence_tier:continue
        out.append({'id':nid,'node_id':nid,'osm_id':d.get('osm_id'),'surface':d.get('surface'),'material_class':d.get('material_class'),
          'evidence_tier':d.get('evidence_tier'),'parent_validation_status':d.get('parent_validation_status'),
          'parent_validation_source':d.get('parent_validation_source'),'grounding_status':d.get('grounding_status')})
    return sorted(out,key=lambda r:r['id'])


# ---------------------------------------------------------- nearest street --

def _street_key(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"^(road|roadjunction|surfaceparking)[_ ]+", "", text)
    text = re.sub(r"\d+$", "", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _road_distance(a, b):
    amin, amax = a.get("bbox_min"), a.get("bbox_max")
    bmin, bmax = b.get("bbox_min"), b.get("bbox_max")
    if amin and amax and bmin and bmax:
        dx = max(float(amin[0]) - float(bmax[0]), float(bmin[0]) - float(amax[0]), 0.0)
        dz = max(float(amin[2]) - float(bmax[2]), float(bmin[2]) - float(amax[2]), 0.0)
        return math.hypot(dx, dz), "bbox_geometry"
    ac, bc = a.get("centroid"), b.get("centroid")
    if ac and bc:
        return math.hypot(float(ac[0]) - float(bc[0]), float(ac[2]) - float(bc[2])), "centroid_geometry"
    return None, None


def q_nearest_street(G: nx.Graph, street_name: str):
    """Return the nearest distinct named road using stored road geometry."""
    query_key = _street_key(street_name)
    roads = []
    for nid, d in _part_nodes(G):
        if d.get("surface") != "road":
            continue
        labels = [d.get("osm_id"), d.get("name"), d.get("source_mesh_name")]
        keys = {_street_key(v) for v in labels if v}
        roads.append((nid, d, keys))
    matches = [(nid, d, keys) for nid, d, keys in roads if query_key and query_key in keys]
    if not matches:
        return {"found": False, "street_name": street_name, "reason": "no named road matched", "candidate_count": len(roads)}
    target_ids = {str(d.get("osm_id") or _street_key(d.get("name"))) for _, d, _ in matches}
    candidates = []
    for nid, d, keys in roads:
        # Unnamed generated ground patches are retained in the graph, but are
        # not street entities and must not answer a street-name query.
        if not d.get("osm_id"):
            continue
        identity = str(d.get("osm_id") or next(iter(keys), ""))
        if identity in target_ids:
            continue
        distances = [_road_distance(td, d) for _, td, _ in matches]
        distances = [x for x in distances if x[0] is not None]
        if distances:
            distance, source = min(distances, key=lambda x: x[0])
            candidates.append((distance, nid, d, source))
    if not candidates:
        return {"found": False, "street_name": street_name, "reason": "matched road has no comparable road geometry", "matched_meshes": len(matches)}
    distance, nid, d, source = min(candidates, key=lambda x: (x[0], str(x[2].get("osm_id") or ""), str(x[1])))
    return {
        "found": True,
        "street_name": street_name,
        "matched_street": matches[0][1].get("osm_id") or matches[0][1].get("name"),
        "matched_meshes": len(matches),
        "nearest_street": d.get("osm_id") or d.get("name"),
        "nearest_mesh_id": str(nid),
        "nearest_mesh_name": d.get("source_mesh_name") or d.get("name"),
        "distance_m": round(distance, 3),
        "distance_source": source,
        "surface": "road",
    }



if __name__ == "__main__":
    G = load_graph("Maradona")
    print("nodes:", G.number_of_nodes(), "edges:", G.number_of_edges())
    print("glass parts:", len(q1_filter(G, material_class="glass")))
    print("wettable (state_change wet):", len(q3_state_change(G)))
    print("low confidence (<=0.6):", len(q4_quality(G, 0.6)))
