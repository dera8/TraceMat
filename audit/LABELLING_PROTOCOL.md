# Grounding audit — labelling protocol

Input: `results_v2/grounding_audit_labelsheet.csv` (150 rows, stratified by scene,
evidence tier and surface type). Fill four columns: `audit_label`, `audit_reason`,
`annotator`, `notes`. Everything else is read-only context.

Score with:

```bash
python scripts/score_grounding_audit_v2.py --input results_v2/grounding_audit_labelsheet.csv
```

Blank and `uncertain` never count as correct, so an unfinished sheet understates
precision rather than inflating it.

To open the `viewer_url` links, serve the repository root first:

```bash
python -m http.server 8000
```

---

## What each label means

The sheet mixes two decisions, separated automatically by the
`canonical_evidence_tier` grouping in the scorer. Judge the decision the row
actually made:

**Rows with an assigned parent** (`parsed_identifier`, `descriptive_label`,
`geometric`) — the question is *does this component belong to this urban entity?*

- `correct` — the assigned parent is the entity this component is part of.
- `incorrect` — the component belongs to a different entity, or to none.
- `uncertain` — the available evidence does not settle it. Use this freely; it
  is reported separately and costs nothing but a smaller denominator.

**Rows with `grounding_status = unresolved`** (20 rows) — the question is
*was leaving this component unassigned the right call?*

- `correct` — no defensible parent exists, so unresolved is right.
- `incorrect` — a defensible parent does exist and was missed.
- `uncertain` — as above.

Do not let these two senses blur: a `correct` on an unresolved row is a
statement about the abstention, not about a link.

## How to use the decision aids

`dist_to_assigned_m` is the 2D distance from the component to its assigned
parent's centroid, and `assigned_parent_rank` is where that parent sits among
all candidate entities ordered by distance (rank 1 = nearest). Parent centroids
are derived from the parent's *other* child surfaces, excluding the component
under audit, so a wrong assignment cannot drag the centroid onto itself.

**Distance is evidence, not truth.** Read it with the tier in mind:

| Tier | n with distance | median | max | How to read it |
|---|---|---|---|---|
| `parsed_identifier` | 31 | 0.0 m | 20.2 m | A non-zero distance is worth a look; the identifier came from the mesh name and should coincide. |
| `geometric` | 35 | 1.2 m | 6.3 m | Tight and plausible. Check the ones above ~5 m. |
| `descriptive_label` | 33 | 47.4 m | 533.8 m | **The weak tier.** Large distances are sometimes legitimate — a long road's centroid is far from any one segment — and sometimes a place-name string matched the wrong entity. This tier needs the most care. |

`assigned_parent_rank` > 1 (40 rows, 16 of them at rank 2) means a nearer
candidate existed. That is a prompt to look, not a verdict: for roads and large
buildings the nearest centroid is routinely the wrong parent.

## Rows that need extra care

- **`prechecked_anomaly = YES` (11 rows).** These appear in
  `grounding_semantic_inconsistencies.csv`: grounded records carrying confidence
  0.0 and/or the evidence phrase `unassigned fragment`. The published coverage
  figure depends on these being right. Label them first.
- **20 rows where the parent centroid could not be derived.** The parent
  entity's only positional evidence *is* the surface being audited, so geometry
  cannot corroborate the link at all. Judge from the mesh name, the OSM id and
  the viewer; if that is not enough, `uncertain` is the honest answer.
- **13 rows with no usable geometry** — same guidance.

## `audit_reason` — use the controlled vocabulary

Free text makes the audit unanalysable. Pick one token; add detail in `notes`.

For `correct`:
- `id_match` — the parent's OSM id matches the identifier in the mesh name
- `geometry_consistent` — the component sits within/on the parent footprint
- `viewer_confirmed` — confirmed visually in the scene viewer
- `abstention_justified` — unresolved, and no candidate parent is defensible

For `incorrect`:
- `wrong_entity_name_collision` — a place-name string matched the wrong entity
- `wrong_entity_proximity` — a nearer or overlapping entity is the real parent
- `parent_not_an_entity` — the assigned parent is not a real urban object
- `missed_parent` — unresolved, but a defensible parent exists
- `component_spans_entities` — the component straddles two entities, so a single
  parent is wrong by construction

For `uncertain`:
- `insufficient_geometry` — no centroid or footprint to judge with
- `ambiguous_source_name` — the mesh name does not identify anything decisively
- `needs_external_source` — would require imagery or survey data we do not have

These tokens double as the error taxonomy for the paper: they answer the
reviewer question "what is the reason components remain unresolved, OSM data or
the method?" without a second pass over the data.

## Two annotators

The scorer computes inter-annotator agreement when the same `audit_id` carries
labels from two different `annotator` values in one merged file. If a second
person is available, have them label the same 150 rows independently into a
second copy, then concatenate the two files before scoring. If not, say in the
paper that the audit is single-annotator — do not leave it implied.

## What this audit does and does not establish

It estimates the **precision of accepted links on a stratified sample**, with
Wilson 95% intervals, per scene and per evidence tier. It does not estimate
recall, it does not audit the material class, and it is not a claim about
independently reconstructed geometry.
