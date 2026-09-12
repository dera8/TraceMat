#!/usr/bin/env python3
"""Export a UE GLB to a Mitsuba/Sionna scene whose shapes join the graph exactly.

Why this exists
---------------
`siemensstadt4_final_valid_SIONNA_ABS.xml` was exported from the LOD2 asset
(`Siemenstaddtlod2ue.glb`, 517 meshes) while the graph was built from the full
UE asset (`Siemenstaddt_ue.glb`, 588 meshes). Only 203 of the XML's meshes have
a `source_mesh_name` in the graph, so a run against that XML configures 39% of
the scene from the property layer and leaves the rest on whatever material the
XML happened to carry — a comparison that looks like it worked and is not one.

This regenerates the scene from the asset the graph actually describes, writing
one PLY per addressable mesh under an opaque ASCII token, plus
`object_to_source_mesh.json` mapping each token to its `source_mesh_name`. The
join XML object -> mapping -> graph surface -> EM parameters is then exact by
construction and independent of filesystem encoding. The exporter refuses to
finish unless the mapping is a bijection onto the graph's surface names.

Conventions copied from the existing working XML: world-baked geometry (no
per-shape transform), `<shape type="ply">` with a `<ref>` to an
`itu-radio-material` BSDF, scene version 2.1.0. Sionna overrides the BSDF per
object at run time, so the placeholder only has to load.

Coordinate system
-----------------
glTF is Y-up; Sionna scenes are authored Z-up (the transmitter heights in the
existing scripts are z values). `--up z` (default) applies the standard
Y-up -> Z-up rotation. The reported bounding box is the check: with `--up z`
the z extent should look like building heights, not city width. If it does not,
re-run with `--up y`.

    python tools/export_glb_to_mitsuba.py --probe
    python tools/export_glb_to_mitsuba.py
"""
from __future__ import annotations

import argparse
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import trimesh

DEFAULT_GLB = Path("Siemenstaddt_ue.glb")
DEFAULT_GRAPH = Path("data/graphs/Siemensstadt_graph.json")

# glTF Y-up -> Z-up: x stays, glTF z becomes -y, glTF y becomes z.
Y_TO_Z_UP = np.array([[1, 0, 0, 0],
                      [0, 0, -1, 0],
                      [0, 1, 0, 0],
                      [0, 0, 0, 1]], dtype=np.float64)


def graph_mesh_names(graph_path: Path) -> set[str]:
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    return {n["source_mesh_name"] for n in graph["nodes"]
            if n.get("kind") == "surface" and n.get("source_mesh_name")}


def load_scene(glb_path: Path) -> trimesh.Scene:
    print(f"loading {glb_path} ({glb_path.stat().st_size / 1e6:.0f} MB) ...", flush=True)
    scene = trimesh.load(str(glb_path), process=False, force="scene")
    print(f"  {len(scene.graph.nodes_geometry)} geometry nodes", flush=True)
    return scene


def world_meshes(scene: trimesh.Scene, rotate: bool):
    """Yield (node_name, mesh_in_world_coordinates) for every geometry node."""
    for node in scene.graph.nodes_geometry:
        transform, geom_name = scene.graph[node]
        geometry = scene.geometry.get(geom_name)
        if geometry is None or not hasattr(geometry, "vertices") or len(geometry.vertices) == 0:
            continue
        mesh = geometry.copy()
        mesh.apply_transform(transform)
        if rotate:
            mesh.apply_transform(Y_TO_Z_UP)
        yield node, mesh


def object_token(index: int) -> str:
    """An ASCII, filesystem- and XML-safe identifier for one mesh.

    An earlier version named each PLY after its `source_mesh_name` so the join
    could read the basename. Three Siemensstadt names contain 'ß'
    (Großsiedlung, Geißlerpfad, Goebelstraße) and Mitsuba fails to open the
    resulting paths — verified locally, and it would have failed identically on
    Colab. Rather than transliterate, which would break the exact join, the
    scene uses opaque tokens and carries the mapping to `source_mesh_name` in a
    sidecar JSON. Nothing then depends on filesystem encoding.
    """
    return f"elm_{index:04d}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--glb", type=Path, default=DEFAULT_GLB)
    ap.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    ap.add_argument("--out-dir", type=Path, default=Path("sionna_siemensstadt_ue"))
    ap.add_argument("--up", choices=["y", "z"], default="z",
                    help="target up axis; 'z' rotates from glTF Y-up (default)")
    ap.add_argument("--probe", action="store_true",
                    help="report the join and the bounding box, write nothing")
    args = ap.parse_args()

    names = graph_mesh_names(args.graph)
    scene = load_scene(args.glb)
    rotate = args.up == "z"

    found, bounds = {}, []
    for node, mesh in world_meshes(scene, rotate):
        if node not in names:
            continue
        found[node] = mesh
        bounds.append(mesh.bounds)

    missing = names - set(found)
    print(f"\ngraph surfaces          : {len(names)}")
    print(f"matched in the GLB      : {len(found)}")
    print(f"missing from the GLB    : {len(missing)}")
    non_ascii = [n for n in found if not n.isascii()]
    print(f"non-ASCII names (mapped): {len(non_ascii)}")
    if missing:
        print(f"  examples: {sorted(missing)[:6]}")

    if bounds:
        low = np.min([b[0] for b in bounds], axis=0)
        high = np.max([b[1] for b in bounds], axis=0)
        extent = high - low
        print(f"\nbounding box ({args.up}-up): "
              f"x {low[0]:.1f}..{high[0]:.1f}  y {low[1]:.1f}..{high[1]:.1f}  z {low[2]:.1f}..{high[2]:.1f}")
        print(f"extent: {extent[0]:.1f} x {extent[1]:.1f} x {extent[2]:.1f} m")
        up_extent = extent[2] if rotate else extent[1]
        print(f"  up-axis extent {up_extent:.1f} m — "
              f"{'plausible as building height' if up_extent < 300 else 'SUSPICIOUS: looks like a horizontal span, try --up y'}")

    if args.probe:
        print("\nprobe only; nothing written")
        return

    if missing:
        raise SystemExit(
            f"\nrefusing to write an incomplete scene: {len(missing)} graph surfaces have no "
            f"mesh. The join must be total, or the experiment silently covers part of the "
            f"scene — which is the defect this script exists to remove.")

    mesh_dir = args.out_dir / "meshes"
    if mesh_dir.exists():
        shutil.rmtree(mesh_dir)
    mesh_dir.mkdir(parents=True)

    root = ET.Element("scene", version="2.1.0")
    # The itu-radio-material plugin requires a `type` property naming an ITU
    # material; without it the scene fails to instantiate. Concrete is the
    # placeholder because it is also the homogeneous baseline, but the value is
    # immaterial: the runner replaces every object's radio material from the
    # property layer before solving.
    placeholder = ET.SubElement(root, "bsdf", type="itu-radio-material", id="mat-placeholder")
    ET.SubElement(placeholder, "string", name="type", value="concrete")

    mapping = {}
    for i, (name, mesh) in enumerate(sorted(found.items())):
        token = object_token(i)
        ply_path = mesh_dir / f"{token}.ply"
        mesh.export(ply_path, file_type="ply")
        mapping[token] = name
        shape = ET.SubElement(root, "shape", type="ply", id=token, name=token)
        ET.SubElement(shape, "string", name="filename", value=str(ply_path.resolve()).replace("\\", "/"))
        ET.SubElement(shape, "ref", id="mat-placeholder", name="bsdf")
        if (i + 1) % 100 == 0:
            print(f"  written {i + 1}/{len(found)}", flush=True)

    xml_path = args.out_dir / "siemensstadt_ue_SIONNA_ABS.xml"
    ET.indent(root, space=" ")
    ET.ElementTree(root).write(xml_path, encoding="utf-8", xml_declaration=True)

    map_path = args.out_dir / "object_to_source_mesh.json"
    map_path.write_text(json.dumps(mapping, indent=1, ensure_ascii=False), encoding="utf-8")

    written = {p.stem for p in mesh_dir.glob("*.ply")}
    if written != set(mapping):
        raise SystemExit("post-check failed: PLY files and mapping keys disagree")
    if set(mapping.values()) != names:
        raise SystemExit("post-check failed: the mapping is not a bijection onto the graph")

    total_mb = sum(p.stat().st_size for p in mesh_dir.glob("*.ply")) / 1e6
    print(f"\nwrote {xml_path}")
    print(f"      {len(written)} PLY files in {mesh_dir} ({total_mb:.0f} MB)")
    print(f"      {map_path} ({len(mapping)} entries)")
    print("join verified: mapping is a bijection onto the graph's source_mesh_name set")


if __name__ == "__main__":
    main()
