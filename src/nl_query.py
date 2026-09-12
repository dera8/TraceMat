"""
nl_query.py - natural language -> structured query -> exact graph answer.

This is NOT a RAG system and NOT an agent. The LLM's only job is to TRANSLATE
a natural-language question into one small JSON query object from a fixed
schema. The answer is then computed EXACTLY by queries.py using networkx -
the LLM never sees the graph and never produces the numeric/count answer.

SETUP
  1. Install Ollama (https://ollama.com), then in a terminal:
       ollama serve            (leave running)
       ollama pull qwen2.5:7b
  2. pip install requests networkx   (this repo already has both)
  3. graphs/*.json are the paper's authoritative graphs, deterministically
     rebuilt by `python build_scene_graphs.py --all` (see queries.py and
     FINAL_REPOSITORY_AUDIT.md). If graphs/<Scene>_graph.json is missing,
     regenerate it that way; do NOT run legacy/build_scene_graphs.py
     against it (superseded).

EXAMPLE COMMANDS
  python nl_query.py --scene Maradona --q "which roofs get wet when it rains?"
  python nl_query.py --scene Siemensstadt --q "show low-confidence assignments"
  python nl_query.py --scene Maradona --q "glass surfaces and their EM and thermal properties"
  python nl_query.py --scene Maradona            (interactive loop, no --q)
  python nl_query.py --selftest
"""
import argparse
import difflib
import json
import re
import sys

import requests

import queries

OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5:7b"
DISCLAIMER = "LLM writes the query; the answer is computed exactly over the graph."

# --------------------------------------------------------------- 1. SCHEMA --

SCHEMA_PROMPT = """You translate a natural-language question about an urban
material scene graph into ONE structured query. You never answer the
question yourself - you only choose the query.

GRAPH SCHEMA
Node attributes (on "part" nodes, i.e. individual surfaces/meshes):
  surface              wall | roof | window | road | furniture | other | ...
  material_class         material class, e.g. glass, asphalt, concrete, brick,
                         plaster, metal, wood, vegetation, roofing, unknown.
                         "unknown" means the material was never resolved -
                         it is outside the evaluated scope, retained for
                         maintenance only.
  osm_id                id of the parent OSM building/way this surface belongs to
  permittivity_dry/wet  relative permittivity, dry vs. rain-wet
  conductivity_dry/wet  S/m, dry vs. rain-wet
  reflectance           0-1 broadband reflectance
  wettable              bool - true only for HORIZONTAL absorbent surfaces
                         (road, roof, ground) that pond water. Vertical
                         facades shed rain and are NOT wettable regardless of
                         material. wet_reason gives the justification.
  confidence            0-1, how trustworthy the physical properties are
  confidence_reason     text explaining the confidence value
  heat_capacity, emissivity, thermal_conductivity   thermal properties
  itu_family            nearest ITU-R P.2040 material category

Edge relations: part_of (surface -> its building), touches (buildings whose
footprints are essentially in contact), nearby (buildings that are close but
not verified touching).

ALLOWED QUERIES - reply with EXACTLY ONE of these JSON shapes:
  {"op":"filter","surface":"roof","wettable":true}
  {"op":"filter","material_class":"asphalt"}
  {"op":"filter","material_contains":"glass"}
  {"op":"filter","surface":"roof","has_wet_state":true}
  {"op":"provenance","osm_id":"12345"}
  {"op":"provenance","osm_id":"12345","surface_scope":["wall","roof","window"]}
  {"op":"state_change","state":"wet"}
  {"op":"quality","max_confidence":0.6}
  {"op":"cross_modal","material_class":"glass","return":["permittivity","emissivity"]}
  {"op":"grid","cell_m":100}
  {"op":"score","top":10}
  {"op":"distribution","attribute":"material_class"}
  {"op":"coverage"}
  {"op":"radio_materials","frequency_ghz":3.5,"state":"dry"}
  {"op":"radio_materials","surface":"window","material_contains":"glass","frequency_ghz":3.5}
  {"op":"radio_state_change","surface_scope":["wall","roof","window","road"]}
  {"op":"lidar_pseudoreflectance","surface":"road"}
  {"op":"lidar_pseudoreflectance","surface":"road","sort":"descending"}
  {"op":"provenance_filter","surface_scope":["wall","roof","window","road"],"evidence_tier":"geometric"}
  {"op":"nearest_street","street_name":"Via Claudio"}
  {"op":"unsupported","reason":"The graph does not contain the requested information.","missing_concepts":["temporal_information"]}
"grid" bins surfaces into a spatial grid to find areas of high density/
wet_fraction. "score" ranks entities by an illustrative composite EM-change
score. "distribution" reports the value distribution of one attribute -
"attribute" must be one of: material_class, surface, permittivity_src,
link_source. "coverage" reports how much of the scene has measured vs
class-default physical values. "has_wet_state" (filter) asks whether a
surface has an actual stored wet-state value, stricter than "wettable".
"surface_scope" (provenance/radio_state_change/provenance_filter) restricts
to a list drawn from: wall, roof, window, road. "radio_state_change" reports
surfaces whose radio-relevant (permittivity/conductivity) values differ
dry vs wet. "provenance_filter" reports surfaces by "evidence_tier" (one of:
exact, label_supported, sidecar_supported, geometric, unassigned) - it is a
provenance-transparency query, not a physical-property query.
"nearest_street" matches a named road against stored road labels and returns
the nearest distinct road using stored mesh geometry.
All fields except "op" are optional within a shape; omit what the question
didn't ask for. Use only field values that appear in the schema above.
"return" is ONLY a valid field for "cross_modal" - every other op already
returns every stored attribute for each matched surface, so there is
nothing to additionally project; never add "return" to those ops.
Choose "unsupported" when answering would require attributes absent from the
graph schema - use "missing_concepts" drawn from: maintenance_history,
temporal_information, real_world_observation, damage_state. Never turn
missing information into an empty-result query.
Use radio_materials/radio_state_change for traceable downstream radio material assignments, never coverage.
Use lidar_pseudoreflectance only for the normalised inspection indicator; it is not calibrated LiDAR intensity.
ALWAYS answer "unsupported" for questions asking to CHOOSE, OPTIMISE, or
RECOMMEND something (e.g. "best position for an antenna", "optimal antenna
placement", "where should I place a sensor", "which route is safest") - this
graph never computes an optimisation, a coverage/propagation simulation, or
a recommendation; it only exports traceable per-surface material records.
Do not guess a "filter"/"cross_modal" query with an invented material for
these - that produces a misleading 0-result answer instead of an honest one.
A "filter" with NONE of surface/material_class/material_contains/wettable/
has_wet_state set is not a valid request for "everything" - it is an error.
Likewise "cross_modal" always needs "material_class" set. If the question
doesn't specify anything that fits the schema, answer "unsupported" instead
of an unconstrained query.

WORKED EXAMPLES

Q: Show me all the wet roofs that are also made of concrete.
<think>Two conditions on filter: surface=roof and material_class=concrete, plus wettable=true.</think>
{"op":"filter","surface":"roof","material_class":"concrete","wettable":true}

Q: What are the thermal and EM properties of the metal surfaces?
<think>Material lookup with a property projection is cross_modal, not filter.</think>
{"op":"cross_modal","material_class":"metal","return":["permittivity","thermal"]}

Q: Which surfaces were repainted last year?
<think>The graph has no maintenance-history or timestamp attribute at all.</think>
{"op":"unsupported","reason":"The graph stores material and physical properties, not maintenance or repainting history.","missing_concepts":["maintenance_history","temporal_information"]}

OUTPUT FORMAT - your entire reply must be:
  <think>one or two sentences of reasoning about which op and fields fit</think>
  {"op": ...}
Nothing else. No markdown, no code fences, no text after the JSON line.
"""

FIELD_EXPANSION = {
    "permittivity": ["permittivity_dry", "permittivity_wet"],
    "conductivity": ["conductivity_dry", "conductivity_wet"],
    "thermal": ["heat_capacity", "emissivity", "thermal_conductivity"],
}


# ------------------------------------------------------------ 2. TRANSLATE --

def _check_ollama():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        r.raise_for_status()
    except requests.exceptions.RequestException:
        print(f"Could not reach Ollama at {OLLAMA_URL}.\n"
              f"Start it first:  ollama serve\nThen: ollama pull {MODEL}")
        sys.exit(1)
    names = [m.get("name", "") for m in r.json().get("models", [])]
    if not any(n.startswith(MODEL) for n in names):
        print(f"Ollama is running but '{MODEL}' is not pulled.\nRun: ollama pull {MODEL}")
        sys.exit(1)


def _call_ollama(prompt: str) -> str:
    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0}},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["response"]


def _parse_reply(raw: str):
    think_m = re.search(r"<think>(.*?)</think>", raw, re.S)
    think = think_m.group(1).strip() if think_m else ""
    rest = raw[think_m.end():] if think_m else raw
    json_m = re.search(r"\{.*\}", rest, re.S)
    if not json_m:
        return think, None
    try:
        return think, json.loads(json_m.group(0))
    except json.JSONDecodeError:
        return think, None


class QueryValidationError(Exception):
    """Raised when the LLM never produces a schema-valid query, even after
    one corrective retry. Carries every raw attempt so the failure can be
    shown in full - callers must NOT execute a query that failed
    validation (FIX 1: reject, don't silently drop the bad fields and run
    an unconstrained query anyway)."""
    def __init__(self, question, attempts):
        self.question = question
        self.attempts = attempts  # list of (raw_text, problem_description)
        detail = "\n".join(f"--- attempt {i+1} ({why}) ---\n{raw}" for i, (raw, why) in enumerate(attempts))
        super().__init__(f"no valid query produced for {question!r} after {len(attempts)} attempt(s):\n{detail}")


def translate(question: str):
    prompt = f"{SCHEMA_PROMPT}\nQuestion: {question}\n"
    raw = _call_ollama(prompt)
    think, query = _parse_reply(raw)
    attempts = []
    if query is None:
        attempts.append((raw, "not parseable JSON"))
        # one retry for a totally unparseable reply
        stricter = (
            f"{prompt}\nYour previous reply could not be parsed. Reply again with EXACTLY: "
            f"<think>...</think> then, on its own line, ONE valid JSON object and nothing else."
        )
        raw = _call_ollama(stricter)
        think, query = _parse_reply(raw)
        if query is None:
            attempts.append((raw, "not parseable JSON"))
            raise QueryValidationError(question, attempts)
    # FIX 1: a query that PARSES but fails schema/key validation (e.g. an
    # invented field like "material_class" spelled wrong, or an
    # unconstrained filter) must never be silently executed with its bad
    # fields dropped - retry once with the SPECIFIC validation error, then
    # give up loudly rather than run a misleadingly-broad query.
    try:
        query = validate_query(_normalize_query(query))
        return think, query, raw
    except ValueError as e:
        attempts.append((raw, str(e)))
        correction = (
            f"{prompt}\nYour previous reply was:\n{json.dumps(query)}\n"
            f"That query is invalid: {e}\n"
            f"Reply again, fixing exactly this problem, in the same <think>/JSON output format."
        )
        raw2 = _call_ollama(correction)
        think2, query2 = _parse_reply(raw2)
        if query2 is None:
            attempts.append((raw2, "not parseable JSON"))
            raise QueryValidationError(question, attempts) from e
        try:
            query2 = validate_query(_normalize_query(query2))
            return think2, query2, raw2
        except ValueError as e2:
            attempts.append((raw2, str(e2)))
            raise QueryValidationError(question, attempts) from e2


# --------------------------------------------------------------- 3. EXECUTE --

def _known_values(G, field):
    """Every distinct value actually present for `field` on a part/surface
    node in this scene's graph - the ground truth the LLM's query is checked
    against."""
    return {d[field] for _, d in queries._part_nodes(G) if d.get(field) is not None}


def _check_known(G, field, value):
    """The LLM only translates language into a query - it can still invent a
    value that isn't in this scene (e.g. surface='skyscraper'). Left
    unchecked that silently returns 0 results and looks like a legitimate
    answer, so this is checked eagerly and printed as a loud warning with the
    closest real values instead."""
    if value is None:
        return
    known = _known_values(G, field)
    known_str = [str(v) for v in known]
    if any(value.lower() == k.lower() for k in known_str):
        return
    close = difflib.get_close_matches(value.lower(), [k.lower() for k in known_str], n=3, cutoff=0.3)
    hint = f"closest valid options: {', '.join(close)}" if close else f"valid options: {', '.join(sorted(known_str))}"
    print(f"WARNING: '{value}' is not a known '{field}' value in this scene - {hint}. "
          f"The query below will likely return 0 results because of this, not because the answer is actually empty.")


# ------------------------------------------------------------------------- #

ALLOWED_KEYS = {
    "filter": {"surface", "material_class", "material_contains", "wettable", "has_wet_state"},
    "provenance": {"osm_id", "surface_scope"},
    "state_change": {"state"},
    "quality": {"max_confidence"},
    "cross_modal": {"material_class", "return"},
    "grid": {"cell_m", "min_surfaces"},
    "score": {"top"},
    "distribution": {"attribute"},
    "coverage": set(),
    "unsupported": {"reason", "missing_fields", "missing_concepts"},
    "radio_materials": {"frequency_ghz", "state", "surface", "material_contains"},
    "radio_state_change": {"surface_scope", "frequency_ghz"},
    "lidar_pseudoreflectance": {"surface", "sort"},
    "provenance_filter": {"surface_scope", "evidence_tier"},
    "nearest_street": {"street_name"},
}

# FIX 3: the stored attribute is `material_class`; these older field names
# ("material" on filter, "appearance" on cross_modal) are accepted as
# silent, undocumented aliases for backward compatibility only - the schema
# prompt documents "material_class" exclusively, since the earlier
# material/material_class name mismatch was the model's actual source of
# invented-field errors, not a training/prompting failure on its part.
FIELD_ALIASES = {
    "filter": {"material": "material_class"},
    "cross_modal": {"appearance": "material_class"},
}

# ops where an ALL-empty query (no field beyond "op") is nonsensical rather
# than "match everything" - FIX 2
_REQUIRES_ONE_OF = {
    "filter": {"surface", "material_class", "material_contains", "wettable", "has_wet_state"},
}


def _normalize_query(query: dict):
    """Rename any accepted legacy alias key to its canonical name (FIX 3),
    before validation/execution ever sees it."""
    if not isinstance(query, dict):
        return query
    aliases = FIELD_ALIASES.get(query.get("op"), {})
    return {aliases.get(k, k): v for k, v in query.items()}


def validate_query(query: dict):
    """The LLM can send a field name that isn't part of the op's shape -
    execute() below only ever reads the documented keys, so an unrecognized
    one being silently dropped can make a filter look broader (or narrower)
    than intended without any error, up to and including running a
    completely unconstrained filter that looks like a legitimate answer.
    FIX 1: raise here instead of failing silently - callers (translate())
    retry once with this exact message, then give up loudly rather than
    execute anything."""
    if not isinstance(query,dict): raise ValueError("query must be an object")
    op=query.get('op')
    if op not in ALLOWED_KEYS: raise ValueError(f"unknown op '{op}'")
    allowed = ALLOWED_KEYS[op]
    for k in query:
        if k == "op" or k in allowed:
            continue
        raise ValueError(f"unrecognized field '{k}' for op '{op}' - valid fields for '{op}' are: {', '.join(sorted(allowed))}")
    required={'provenance':{'osm_id'},'state_change':{'state'},'cross_modal':{'material_class','return'},'unsupported':{'reason'},'nearest_street':{'street_name'}}.get(op,set())
    missing=required-set(query)
    if missing: raise ValueError(f"missing required fields: {sorted(missing)}")
    if op=='unsupported':
        concepts=query.get('missing_concepts') or query.get('missing_fields')
        if not query.get('reason') or not concepts: raise ValueError('unsupported requires nonempty reason and missing_concepts (or legacy missing_fields)')
    # FIX 2: an unconstrained filter/cross_modal is an error, not "everything"
    one_of = _REQUIRES_ONE_OF.get(op)
    if one_of and not (one_of & set(query)):
        raise ValueError(f"'{op}' with none of {sorted(one_of)} set is not a valid request for 'everything' - "
                          f"this is an error, not an unconstrained query; use 'unsupported' if nothing in the schema fits")
    return query


def execute(G, query: dict):
    query = validate_query(_normalize_query(query))
    op = query.get("op")
    if op == "unsupported":
        return {
            "unsupported": True,
            "reason": query.get("reason", "The requested information is not represented in the graph."),
            "missing_concepts": query.get("missing_concepts", query.get("missing_fields", [])),
            "missing_fields": query.get("missing_fields", []),
        }
    if op == "filter":
        _check_known(G, "surface", query.get("surface"))
        _check_known(G, "material_class", query.get("material_class"))
        return queries.q1_filter(
            G,
            surface=query.get("surface"),
            material_class=query.get("material_class"),
            material_contains=query.get("material_contains"),
            wettable=query.get("wettable"),
            has_wet_state=query.get("has_wet_state"),
        )
    if op == "provenance":
        return queries.q2_provenance(G, query.get("osm_id"), query.get("surface_scope"))
    if op == "state_change":
        return queries.q3_state_change(G, query.get("state", "wet"))
    if op == "quality":
        return queries.q4_quality(G, query.get("max_confidence", 0.6))
    if op == "cross_modal":
        _check_known(G, "material_class", query.get("material_class"))
        fields = []
        for f in query.get("return", []):
            fields.extend(FIELD_EXPANSION.get(f, [f]))
        return queries.q5_cross_modal(G, query.get("material_class"), fields)
    if op == "grid":
        return queries.q6_grid(G, query.get("cell_m", 100.0), query.get("min_surfaces", 10))
    if op == "score":
        return queries.q7_score(G, query.get("top", 10))
    if op == "distribution":
        attribute = query.get("attribute", "material_class")
        if attribute not in queries.DISTRIBUTION_ATTRIBUTES:
            close = difflib.get_close_matches(attribute, queries.DISTRIBUTION_ATTRIBUTES, n=3, cutoff=0.3)
            hint = f"closest valid options: {', '.join(close)}" if close else f"valid options: {', '.join(queries.DISTRIBUTION_ATTRIBUTES)}"
            print(f"WARNING: '{attribute}' is not a known distribution attribute - {hint}. Returning no results instead of guessing.")
            return []
        return queries.q8_distribution(G, attribute)
    if op == "coverage":
        return queries.q9_coverage(G)
    if op == "radio_materials":
        return queries.q_radio_materials(G,query.get("frequency_ghz",3.5),query.get("state","dry"),query.get("surface"),query.get("material_contains"))
    if op == "radio_state_change":
        return queries.q_radio_state_change(G,query.get("surface_scope"),query.get("frequency_ghz",3.5))
    if op == "lidar_pseudoreflectance":
        return queries.q_lidar_pseudoreflectance(G,query.get("surface"),query.get("sort"))
    if op == "provenance_filter":
        return queries.q_provenance_filter(G,query.get("surface_scope"),query.get("evidence_tier"))
    if op == "nearest_street":
        return queries.q_nearest_street(G,query.get("street_name"))
    raise ValueError(f"unknown op '{op}' - not in the allowed schema")


# ---------------------------------------------------------------- 4. REPORT --

def report(question, think, query, result):
    print(f"\nQ: {question}")
    print(f"reasoning: {think}")
    print(f"structured query: {json.dumps(query)}")
    if isinstance(result, dict) and result.get("unsupported"):
        print(f"unsupported: {result.get('reason')}")
        print(f"missing fields: {', '.join(result.get('missing_fields', [])) or '(not specified)'}")
    elif isinstance(result, dict) and "found" in result:  # provenance / street shape
        if query.get("op") == "nearest_street":
            if result.get("found"):
                print(f"exact result (this is not an estimate): nearest street to {result.get('matched_street')} is "
                      f"{result.get('nearest_street')} ({result.get('distance_m')} m; {result.get('distance_source')})")
            else:
                print(f"no exact street result: {result.get('reason')}")
            return
        print(f"exact result (this is not an estimate): building {result.get('osm_id')}, "
              f"found={result.get('found')}, n_parts={result.get('n_parts', 0)}")
        for p in result.get("parts", [])[:3]:
            print(f"  - {p['id']}: material={p.get('material')} "
                  f"confidence={p.get('confidence')} ({p.get('confidence_reason')})")
    elif isinstance(result, dict):  # coverage shape
        print(f"exact result (this is not an estimate): {result.get('total', 0)} surfaces - "
              f"{result.get('measured', 0)} measured, {result.get('estimated', 0)} estimated, "
              f"{result.get('unresolved', result.get('unassigned', 0))} unresolved; "
              f"{result.get('out_of_scope', 0)} out of scope")
    elif query.get("op") == "grid":
        print(f"exact result count (this is not an estimate): {len(result)} cells")
        for row in result[:3]:
            print(f"  - cell ({row['cell_x']},{row['cell_z']}): {row['n_surfaces']} surfaces, "
                  f"wet_fraction={row['wet_fraction']:.2f}, sum_delta_sigma={row['sum_delta_sigma']:.3f}")
    elif query.get("op") == "score":
        print(f"exact result count (this is not an estimate): {len(result)} entities")
        for row in result[:3]:
            print(f"  - osm_id={row['osm_id']}: score={row['score']:.3f} "
                  f"({row['n_wettable']}/{row['n_surfaces']} wettable) [illustrative score, not calibrated]")
    elif query.get("op") == "distribution":
        print(f"exact result count (this is not an estimate): {len(result)} distinct values")
        for row in result[:5]:
            print(f"  - {row['value']}: {row['count']} ({row['pct']}%)")
    else:
        print(f"exact result count (this is not an estimate): {len(result)}")
        for row in result[:3]:
            conf = row.get("confidence")
            reason = row.get("confidence_reason")
            print(f"  - {row.get('id')}: material={row.get('material')} surface={row.get('surface')} "
                  f"confidence={conf} ({reason})")
    print(f"[{DISCLAIMER}]")


# ------------------------------------------------------------------- CLI --

SELFTEST_QUESTIONS = [
    "which roofs get wet when it rains?",
    "show me glass surfaces",
    "show low-confidence assignments",
    "tell me everything about building 225285143",
    "glass surfaces and their EM and thermal properties",
]


def run_one(scene: str, question: str):
    G = queries.load_graph(scene)
    try:
        think, query, _raw = translate(question)
    except QueryValidationError as e:
        print(f"\nQ: {question}")
        print(f"Could not produce a valid query - not executing anything:\n{e}")
        return
    result = execute(G, query)
    report(question, think, query, result)


def selftest():
    _check_ollama()
    G = queries.load_graph("Maradona")
    ok = 0
    for q in SELFTEST_QUESTIONS:
        try:
            think, query, _raw = translate(q)
            execute(G, query)
            print(f"OK   : {q!r} -> {query}")
            ok += 1
        except SystemExit:
            print(f"FAIL : {q!r} -> LLM never produced parseable JSON")
        except Exception as exc:
            print(f"FAIL : {q!r} -> {exc}")
    print(f"\n{ok}/{len(SELFTEST_QUESTIONS)} questions ran end to end.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scene", choices=queries.SCENES, default="Maradona")
    ap.add_argument("--q", help="natural-language question; omit for interactive mode")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    _check_ollama()

    if args.q:
        run_one(args.scene, args.q)
        return

    print(f"Interactive mode on scene '{args.scene}'. Ctrl-C to quit.")
    while True:
        try:
            q = input("\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if q:
            run_one(args.scene, q)


if __name__ == "__main__":
    main()
