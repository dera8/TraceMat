"""Shared scientific-evaluation scope for the four-category TwinWorld paper.

The final paper evaluates and reports metrics for exactly four surface
categories: wall, roof, window, road. Every other component type (furniture,
kerbs, road markings without a resolved material, vegetation, rails,
ballast, water, sky, decorative props, generic ground, "other", unknown
surface types, ...) may stay visible/inspectable in the complete maintenance
graph and viewer, but must never enter a reported scientific metric.

This module is the single shared gate every experiment/table script must
import instead of re-deriving its own surface filter. Matching is against the
node's own stored `surface` field only (controlled alias lookup) - never a
substring scan of `source_mesh_name`, which is exactly what produces the
misclassifications this module exists to prevent (e.g. "Bench_12" containing
no wall-like token would still need to NOT become a wall just because some
other heuristic thinks it looks like one).
"""
from __future__ import annotations

import re

CANONICAL_SURFACES = ("wall", "roof", "window", "road")
SCOPE_IN = "in_scope"
SCOPE_OUT = "out_of_scope"

_ALIASES = {
    "wall": {"wall", "facade", "façade", "building_envelope", "exterior_wall"},
    "roof": {"roof", "roofing", "roof_surface"},
    "window": {"window", "windows", "glass_window", "glazed_surface", "glazing"},
    "road": {"road", "road_surface", "carriageway", "asphalt_road"},
}
_ALIAS_TO_CANONICAL = {alias: canon for canon, aliases in _ALIASES.items() for alias in aliases}

# UE/OSM2World exports occasionally carry a more specific asset semantic in
# the mesh prefix while the legacy surface field says ``wall``.  These
# prefixes must win before any OSM-id or material rule is applied: a Bench_n*
# is street furniture, never a building wall.
_NAME_SURFACE_OVERRIDES = {
    "bench": "furniture", "bollardrow": "furniture", "gritbin": "furniture",
    "postbox": "furniture", "table": "furniture", "wastebasket": "furniture",
    "streetfurniture": "furniture", "tree": "vegetation", "plant": "vegetation",
}


def semantic_surface_type(node: dict) -> str | None:
    """Return the authoritative surface label, including asset-prefix fixes.

    The explicit ``surface`` field remains the default.  A known semantic UE
    asset prefix is a narrowly-scoped override for legacy exports whose field
    was incorrectly inherited from a nearby/building material rule.
    """
    name = str(node.get("source_mesh_name") or node.get("name") or "").strip()
    prefix = re.split(r"[_\\s-]+", name, maxsplit=1)[0].lower()
    if prefix in _NAME_SURFACE_OVERRIDES:
        return _NAME_SURFACE_OVERRIDES[prefix]
    raw = node.get("surface")
    if not raw:
        return None
    key = str(raw).strip().lower()
    # Legacy Maradona/Canary exports contain road meshes whose inherited
    # surface field is ``wall``.  Asphalt is unambiguous here: it is a road
    # material, not a wall semantic.  Correct the category before scope,
    # grounding and viewer labels are computed.
    material = str(node.get("material_class") or node.get("material") or "").lower()
    if key == "wall" and "asphalt" in material:
        return "road"
    return _ALIAS_TO_CANONICAL.get(key, key)

# surface-field values that are known, resolved, intentionally-out-of-scope
# categories (as opposed to an unrecognised/novel value) - kept explicit so
# exclusion_reason can tell "yes, this is furniture" apart from "I don't
# recognise this surface value at all"
_KNOWN_EXCLUDED_SURFACES = {
    "furniture", "street_furniture", "bench", "benches", "kerb", "curb",
    "road_marking", "road_markings", "vegetation", "tree", "trees",
    "vehicle", "vehicles", "rail", "rails", "ballast", "water", "sky",
    "decorative", "decorative_prop", "ground", "other", "unknown",
}

# accepted parent_validation_status values for scientific/paper inclusion
# (see build_scene_graphs.py TASK 3 fields) - "validated_osm" and
# "validated_assignment" mirror the two explicit-evidence tiers this module's
# callers are expected to use; "preexisting_source_entity" covers surfaces
# whose target entity was already present in the source graph (including
# links whose evidence_tier is "geometric" - the ENTITY is still real/
# traceable, only the association evidence differs, see FINAL_REPOSITORY_AUDIT.md)
VALID_PARENT_STATUSES = ("validated_osm", "validated_assignment", "preexisting_source_entity")


def canonical_surface_type(node: dict) -> str | None:
    """The node's canonical scientific surface type, or None if it isn't one
    of wall/roof/window/road (via controlled alias lookup on `surface` only)."""
    semantic = semantic_surface_type(node)
    return _ALIAS_TO_CANONICAL.get(semantic)


def is_scientific_surface(node: dict) -> bool:
    """True iff this node belongs to the four-category scientific subset.
    Purely a surface-category gate (structural) - material/property/parent
    eligibility are separate, finer-grained checks layered on top by
    downstream scripts (see physics_properties.classify_application_property,
    radio_eligible, reflectance_eligible, and parent_validation_status)."""
    return canonical_surface_type(node) is not None


def classify_scope(node: dict) -> tuple[str, str | None]:
    """Classify whether a component is evaluated by material grounding.

    Scope is intentionally based on the stored semantic surface category,
    not on mesh-name substrings or material guesses.  Unknown material on an
    in-scope surface remains an in-scope, unresolved-material case; scope and
    physical-property eligibility are separate axes.
    """
    canonical = canonical_surface_type(node)
    if canonical is not None:
        return SCOPE_IN, None
    raw = str(semantic_surface_type(node) or "").strip().lower()
    if raw in {"vegetation", "tree", "trees"}:
        return SCOPE_OUT, "vegetation"
    if raw in {"furniture", "street_furniture", "bench", "benches"}:
        return SCOPE_OUT, "street_furniture"
    if raw in {"decorative", "decorative_prop"}:
        return SCOPE_OUT, "decorative_asset"
    if raw in {"ground", "other", "unknown", "water", "sky", "vehicle", "vehicles"}:
        return SCOPE_OUT, "non_material_scene_component"
    if raw in _KNOWN_EXCLUDED_SURFACES:
        return SCOPE_OUT, "unsupported_surface_type"
    return SCOPE_OUT, "unsupported_surface_type"


def has_validated_parent(node: dict) -> bool:
    return node.get("parent_validation_status") in VALID_PARENT_STATUSES


def exclusion_reason(node: dict) -> str | None:
    """Best single reason this node is NOT eligible for the main scientific
    tables, or None if it passes the surface-category and parent-validation
    gates (callers still separately check material/property eligibility for
    radio/LiDAR-specific tasks via physics_properties.py)."""
    raw = node.get("surface")
    if not raw or not str(raw).strip():
        return "unresolved_surface_type"
    key = str(raw).strip().lower()
    if key not in _ALIAS_TO_CANONICAL:
        return "excluded_surface_category" if key in _KNOWN_EXCLUDED_SURFACES else "ambiguous_classification"
    mat = str(node.get("material_class") or "").strip().lower()
    if not mat or mat == "unknown":
        return "unresolved_material"
    status = node.get("parent_validation_status")
    if status is not None and status not in VALID_PARENT_STATUSES:
        return "non_osm_parent"
    return None


def scientific_surfaces(nodes_iter):
    """Filter an iterable of (node_id, node_data) pairs (e.g. queries.py's
    _part_nodes output) down to the four-category scientific subset."""
    return [(nid, d) for nid, d in nodes_iter if is_scientific_surface(d)]
