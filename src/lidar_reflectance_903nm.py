"""External UR-MAT dry/wet LiDAR reflectance priors at 903.9 nm.

This module is a read-only property layer. It never attaches catalog values to
G0 nodes and it never creates a wet value from a dry value implicitly.
"""
from __future__ import annotations
from dataclasses import dataclass
import json, math, random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "data" / "properties" / "lidar_reflectance_903nm.json"
TAXONOMY = ("Brick", "Glass", "Steel", "Tiles", "Limestone", "Plaster", "Concrete",
            "Wood", "Cobblestone", "Slate", "Asphalt", "Plastic", "Gravel", "Unknown")
DRY_TIERS = {"dry_sample_backed", "dry_sample_proxy", "dry_engineering_prior"}
WET_TIERS = {"wet_literature_prior", "wet_engineering_interval"}
GRAPH_CLASS_TO_LIBRARY = {
    "brick":"Brick", "glass":"Glass", "metal":"Steel", "roofing":"Tiles",
    "stone":"Limestone", "plaster":"Plaster", "concrete":"Concrete", "wood":"Wood",
    "paving":"Cobblestone", "sett":"Cobblestone", "asphalt":"Asphalt", "plastic":"Plastic",
    "gravel":"Gravel", "slate":"Slate", "unknown":"Unknown",
}
CLAIM = "Dry material-level spectral-reflectance prior at 903.9 nm; not calibrated Velodyne intensity or return probability."
WET_CLAIM = "Wet-surface prior; low confidence; first-order literature/engineering model; not calibrated sensor response."

def _round_half_up(value):
    return math.floor(value + 0.5)

@dataclass(frozen=True)
class LidarPrior:
    material_class: str
    state: str
    reflectance_mean: float
    reflectance_std: float
    reflectance_min: float
    reflectance_max: float
    n_samples: int
    provenance_tier: str
    derivation: str
    confidence: str
    source_ids: tuple[str, ...]
    sample_ids: tuple[str, ...]
    simulation_initialization_0_255: int
    surface_model: str
    reflectance_multiplier: float | None = None
    measured_for_urmat_class: bool = False
    calibrated_sensor_response: bool = False
    quantitative_use: bool = False

    @property
    def is_measured_or_sample_backed(self):
        return self.provenance_tier in {"dry_sample_backed", "dry_sample_proxy"}
    @property
    def is_engineering_prior(self):
        return self.provenance_tier in {"dry_engineering_prior", "wet_engineering_interval"}
    @property
    def is_supported_wet_prior(self):
        return self.state == "wet_surface" and self.provenance_tier in WET_TIERS
    def as_dict(self):
        return {
            "material_class": self.material_class, "state": self.state, "wavelength_nm": 903.9,
            "reflectance_mean": self.reflectance_mean, "reflectance_std": self.reflectance_std,
            "reflectance_min": self.reflectance_min, "reflectance_max": self.reflectance_max,
            "n_samples": self.n_samples, "provenance_tier": self.provenance_tier,
            "derivation": self.derivation, "confidence": self.confidence,
            "source_ids": list(self.source_ids), "sample_ids": list(self.sample_ids),
            "simulation_initialization_0_255": self.simulation_initialization_0_255,
            "is_measured_or_sample_backed": self.is_measured_or_sample_backed,
            "is_engineering_prior": self.is_engineering_prior,
            "is_supported_wet_prior": self.is_supported_wet_prior,
            "surface_model": self.surface_model, "reflectance_multiplier": self.reflectance_multiplier,
            "measured_for_urmat_class": self.measured_for_urmat_class,
            "calibrated_sensor_response": self.calibrated_sensor_response,
            "quantitative_use": self.quantitative_use,
            "claim": WET_CLAIM if self.state == "wet_surface" else CLAIM,
        }

def _num(x, label):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x): raise ValueError(f"{label} must be finite")
    return float(x)

def validate_catalog(data):
    if data.get("schema_version") != "2.0": raise ValueError("schema_version must be 2.0")
    if data.get("target_wavelength_nm") != 903 or data.get("measurement_wavelength_nm") != 903.9: raise ValueError("wavelength mismatch")
    c = data.get("conditions", {})
    if c.get("supported_surface_states") != ["dry", "wet_surface"] or c.get("wet_values_included") is not True: raise ValueError("invalid state model")
    if c.get("wet_values_type") != "first_order_literature_and_engineering_priors": raise ValueError("invalid wet type")
    if set(data.get("materials", {})) != set(TAXONOMY): raise ValueError("catalog must contain exactly 14 classes")
    for name in TAXONOMY:
        mat=data["materials"][name]; dry=mat["dry_state"]; wet=mat["wet_surface_state"]
        for state, rec in (("dry", dry["reflectance_903nm"]),("wet_surface", wet["reflectance_903nm_prior"])):
            lo,mean,hi=(_num(rec[k],f"{name}.{state}.{k}") for k in ("min","mean","max"))
            if not 0 <= lo <= mean <= hi <= 1: raise ValueError(f"invalid {name} {state} interval")
            if _num(rec.get("std",0),f"{name}.{state}.std") < 0: raise ValueError(f"invalid {name} {state} std")
        mult=wet["reflectance_multiplier"]
        if not 0 <= mult["min"] <= mult["mean"] <= mult["max"]: raise ValueError(f"invalid wet multiplier {name}")
        if abs(wet["reflectance_903nm_prior"]["mean"] - dry["reflectance_903nm"]["mean"]*mult["mean"]) > 1e-4: raise ValueError(f"wet mean mismatch {name}")
        if dry["linear_intensity_prior_0_255"] != _round_half_up(dry["reflectance_903nm"]["mean"]*255): raise ValueError(f"dry intensity mismatch {name}")
        if wet["linear_intensity_prior_0_255"] != _round_half_up(wet["reflectance_903nm_prior"]["mean"]*255): raise ValueError(f"wet intensity mismatch {name}")
        for rec in (dry, wet):
            if rec["calibrated_sensor_response"] is not False: raise ValueError(f"calibrated response claimed for {name}")
        if name == "Unknown" and wet["mean_provenance_tier"] != "fallback_excluded": raise ValueError("Unknown wet fallback must be excluded")
    return True

def load_catalog(path=DEFAULT_PATH):
    data=json.loads(Path(path).read_text(encoding="utf-8")); validate_catalog(data); return data

def graph_to_library_class(material_class, allow_unknown=False):
    name=GRAPH_CLASS_TO_LIBRARY.get(str(material_class or "").strip().lower())
    if name == "Unknown" and not allow_unknown: return None
    return name

def lookup(material_class, state="dry", *, allow_unknown=False, catalog=None):
    if state not in {"dry", "wet_surface"}: raise ValueError("state must be dry or wet_surface")
    catalog=catalog or load_catalog(); name=graph_to_library_class(material_class, allow_unknown=allow_unknown)
    if name is None: return None
    mat=catalog["materials"][name]; rec=mat["dry_state"] if state=="dry" else mat["wet_surface_state"]
    rr=rec["reflectance_903nm"] if state=="dry" else rec["reflectance_903nm_prior"]
    tier=rec.get("provenance_tier") if state=="dry" else rec.get("mean_provenance_tier")
    samples=tuple(rec.get("sample_ids", [])); sources=tuple(s["id"] for s in catalog.get("sources", []))
    return LidarPrior(name,state,rr["mean"],rr.get("std",0.0),rr["min"],rr["max"],rr.get("n_samples",0),tier,
        rec.get("derivation", ""),rec.get("confidence", ""),sources,samples,rec["linear_intensity_prior_0_255"],mat.get("surface_model", "unknown"),
        mat["wet_surface_state"]["reflectance_multiplier"]["mean"] if state=="wet_surface" else None,
        rec.get("measured_for_urmat_class",False),rec.get("calibrated_sensor_response",False),rec.get("quantitative_use",False))

def sample_reflectance_prior(material_class, rng, n, *, state="dry", allow_engineering_prior=False, allow_unknown=False, catalog=None):
    if not isinstance(n,int) or n<0: raise ValueError("n must be a non-negative integer")
    p=lookup(material_class,state,allow_unknown=allow_unknown,catalog=catalog)
    if p is None: raise ValueError(f"no {state} prior for {material_class!r}")
    if (p.state == "wet_surface" or p.is_engineering_prior or p.provenance_tier=="fallback_excluded") and not (allow_engineering_prior or allow_unknown): raise ValueError("engineering/literature prior disabled by default")
    if p.reflectance_std == 0: return [p.reflectance_mean]*n
    out=[]
    while len(out)<n:
        x=rng.gauss(p.reflectance_mean,p.reflectance_std)
        if math.isfinite(x) and p.reflectance_min<=x<=p.reflectance_max: out.append(x)
    return out
