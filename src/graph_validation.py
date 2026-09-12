"""Validation for TwinWorld node-link graphs."""
from collections import Counter

RELATIONS = {"part_of", "touches", "nearby", "native_osm"}
MATERIALS = {
    "asphalt", "brick", "concrete", "glass", "metal", "plaster", "roofing",
    "stone", "gravel", "paving", "sett", "kerb", "rail_ballast", "unknown",
    "vegetation", "grass", "earth", "wood", "water", "soil", "plastic",
}

def is_surface(n):
    return n.get("kind") == "surface" or n.get("surface") != "building"

def validate_graph(data, raise_on_error=True):
    errors=[]; nodes=data.get("nodes",[]); edges=data.get("edges",data.get("links",[]))
    ids=[str(n.get("id")) for n in nodes]; idset=set(ids)
    by_id={str(n.get('id')):n for n in nodes}
    if len(ids)!=len(idset): errors.append("duplicate node IDs")
    parents=Counter()
    for e in edges:
        s,t=str(e.get("source")),str(e.get("target")); rel=e.get("relation")
        if s not in idset or t not in idset: errors.append(f"edge references missing node: {s}->{t}")
        if rel not in RELATIONS: errors.append(f"unknown relation: {rel}")
        if rel=="part_of":
            endpoints=[x for x in (s,t) if x in by_id and is_surface(by_id[x])]
            if len(endpoints)!=1: errors.append(f"part_of must connect one surface and one entity: {s}->{t}")
            else: parents[endpoints[0]]+=1
    for n in nodes:
        if not is_surface(n): continue
        nid=str(n["id"]); status=n.get("grounding_status")
        mat=str(n.get("material_class","unknown")).lower()
        if mat not in MATERIALS: errors.append(f"{nid}: material class outside vocabulary: {mat}")
        if status=="grounded" and parents[nid]!=1: errors.append(f"{nid}: grounded surface has {parents[nid]} part_of edges")
        if status in ("unresolved", "unassigned") and parents[nid]: errors.append(f"{nid}: {status} surface has part_of edge")
        # Old graphs may omit scope_status and still carry the legacy
        # `unassigned` value. Accept that only for backward-compatible reads;
        # the authoritative builder never emits it.
        legacy = n.get("scope_status") is None and status == "unassigned"
        if status not in ("grounded", "unresolved", "not_applicable") and not legacy:
            errors.append(f"{nid}: invalid grounding_status: {status}")
        scope=n.get("scope_status")
        if scope is not None and scope not in ("in_scope", "out_of_scope"):
            errors.append(f"{nid}: invalid scope_status: {scope}")
        if scope=="out_of_scope" and status!="not_applicable":
            errors.append(f"{nid}: out_of_scope surface must be not_applicable")
        if scope=="in_scope" and status=="not_applicable":
            errors.append(f"{nid}: in_scope surface cannot be not_applicable")
    if errors and raise_on_error: raise ValueError("graph validation failed:\n- "+"\n- ".join(errors[:50]))
    return errors
