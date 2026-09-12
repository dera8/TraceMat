# Closed query schema

The graph is queried through a closed schema of 14 typed
operations, plus an explicit `unsupported` escape. A query is rejected
before execution if it names an operation outside this list, a field
outside that operation, or a value of the wrong type. Execution is
deterministic and exact: the same query on an unchanged graph returns
the same rows in the same order, and no operation ranks, retrieves
approximately, or interpolates.

Every example below was executed against `data/graphs/Maradona_graph.json` when this file was generated,
and the reported result shape is what came back. Regenerate with:

```bash
python tools/generate_query_docs.py --scene Maradona
```

## Fields accepted by each operation

| Operation | Accepted fields |
|---|---|
| `coverage` | *(none)* |
| `cross_modal` | `material_class`, `return` |
| `distribution` | `attribute` |
| `filter` | `has_wet_state`, `material_class`, `material_contains`, `surface`, `wettable` |
| `grid` | `cell_m`, `min_surfaces` |
| `lidar_pseudoreflectance` | `sort`, `surface` |
| `nearest_street` | `street_name` |
| `provenance` | `osm_id`, `surface_scope` |
| `provenance_filter` | `evidence_tier`, `surface_scope` |
| `quality` | `max_confidence` |
| `radio_materials` | `frequency_ghz`, `material_contains`, `state`, `surface` |
| `radio_state_change` | `frequency_ghz`, `surface_scope` |
| `score` | `top` |
| `state_change` | `state` |

## Worked examples

### `filter`

*Which glass surfaces are in the scene?*

```json
{"op": "filter", "material_class": "glass"}
```

Returns: 2 rows; fields: `id`, `name`, `material`, `surface`, `osm_id`, `link_source`, `permittivity_dry`, `permittivity_src`, … (45 fields).

### `filter`

*Which road surfaces are marked wettable by the rain-exposure model?*

```json
{"op": "filter", "surface": "road", "wettable": true}
```

Returns: 148 rows; fields: `id`, `name`, `material`, `surface`, `osm_id`, `link_source`, `permittivity_dry`, `permittivity_src`, … (49 fields).

### `provenance`

*What does the graph record about this OSM building, including its components and neighbours?*

```json
{"op": "provenance", "osm_id": "915551373"}
```

Returns: one record; fields: `found`, `osm_id`, `n_parts`, `parts`, `entity_kind`, `entity_surface`, `reported_kind`, `direct_component`.

### `state_change`

*Which surfaces are affected by the modelled wet state?*

```json
{"op": "state_change", "state": "wet"}
```

Returns: 137 rows; fields: `id`, `node_id`, `osm_id`, `surface`, `material_class`, `changed_fields`, `dry_values`, `wet_values`, … (13 fields).

### `quality`

*Show all surfaces whose property confidence is at most 0.5.*

```json
{"op": "quality", "max_confidence": 0.5}
```

Returns: 6 rows; fields: `id`, `name`, `material`, `surface`, `osm_id`, `link_source`, `permittivity_dry`, `permittivity_src`, … (49 fields).

### `cross_modal`

*Which permittivity and conductivity values are recorded for glass surfaces?*

```json
{"op": "cross_modal", "material_class": "glass", "return": ["permittivity", "conductivity"]}
```

Returns: 2 rows; fields: `id`, `osm_id`, `material_class`, `surface`, `permittivity_dry`, `permittivity_wet`, `conductivity_dry`, `conductivity_wet`.

### `grid`

*Which 100 m cells contain the highest density of surfaces with a modelled dry-wet state change?*

```json
{"op": "grid", "cell_m": 100.0, "min_surfaces": 10}
```

Returns: 17 rows; fields: `cell_x`, `cell_z`, `n_surfaces`, `n_wettable`, `sum_delta_sigma`, `n_high_heat_capacity`, `wet_fraction`.

### `score`

*Rank the entities whose electromagnetic signature changes most when it rains.*

```json
{"op": "score", "top": 5}
```

Returns: 5 rows; fields: `osm_id`, `n_surfaces`, `n_wettable`, `score`.

### `distribution`

*How are surface types distributed across the scene?*

```json
{"op": "distribution", "attribute": "surface"}
```

Returns: 7 rows; fields: `value`, `count`, `pct`.

### `coverage`

*For how many surfaces does the permittivity come from the scene catalogue rather than a class default?*

```json
{"op": "coverage"}
```

Returns: one record; fields: `total`, `measured`, `estimated`, `unresolved`, `out_of_scope`, `link_source_distribution`, `confidence_distribution`.

### `radio_materials`

*Return the dry-state radio-material parameters for plastered walls at 2.4 GHz.*

```json
{"op": "radio_materials", "surface": "wall", "material_contains": "plaster", "frequency_ghz": 2.4}
```

Returns: 65 rows; fields: `id`, `node_id`, `mesh_id`, `osm_id`, `surface`, `material_class`, `itu_family`, `state`, … (16 fields).

### `radio_state_change`

*Which roof or road surfaces change their radio-material parameters between dry and wet?*

```json
{"op": "radio_state_change", "surface_scope": ["roof", "road"]}
```

Returns: 137 rows; fields: `id`, `node_id`, `osm_id`, `surface`, `material_class`, `changed_fields`, `dry_values`, `wet_values`, … (11 fields).

### `lidar_pseudoreflectance`

*Show roof surfaces ordered by material-derived LiDAR pseudo-reflectance, lowest first.*

```json
{"op": "lidar_pseudoreflectance", "surface": "roof", "sort": "ascending"}
```

Returns: 70 rows; fields: `material_class`, `state`, `wavelength_nm`, `reflectance_mean`, `reflectance_std`, `reflectance_min`, `reflectance_max`, `n_samples`, … (35 fields).

### `provenance_filter`

*Which evaluated roof and road surfaces have a label-supported parent link?*

```json
{"op": "provenance_filter", "surface_scope": ["roof", "road"], "evidence_tier": "label_supported"}
```

Returns: 280 rows; fields: `id`, `node_id`, `osm_id`, `surface`, `material_class`, `evidence_tier`, `parent_validation_status`, `parent_validation_source`, … (9 fields).

### `nearest_street`

*What does the graph hold for the surfaces nearest a named street?*

```json
{"op": "nearest_street", "street_name": "node_186"}
```

Returns: one record; fields: `found`, `street_name`, `matched_street`, `matched_meshes`, `nearest_street`, `nearest_mesh_id`, `nearest_mesh_name`, `distance_m`.

### `unsupported`

*Which surfaces show cracks in the most recent photograph?*

```json
{"op": "unsupported", "reason": "The graph has no real-world imagery or damage-state attribute.", "missing_concepts": ["real_world_observation"]}
```

Returns no rows, and names the concept the graph does not represent. Questions of this kind are answered by declining, not by returning a plausible answer.
