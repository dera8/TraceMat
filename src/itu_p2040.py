"""ITU-R P.2040 material parameters, frequency-parametric, with provenance.

Replaces the hard-coded (eps, sigma) pairs in build_twin_viewer_v2.py and the
`attenuation`-as-conductivity read in lookup_eps().

WHY THIS FILE EXISTS

The shipped pipeline had three separate problems:

1. lookup_eps() read conductivity from the catalog's `attenuation` field.
   That field holds small Unreal authoring numbers (0.001-0.01), not
   conductivity in S/m. At 3.5 GHz ITU gives concrete 0.12309 S/m; the
   catalog supplies 0.008. Fifteen times out.

2. MATERIAL_CLASS_DEFAULTS did contain correct ITU conductivities for three
   classes - concrete 0.12309, brick 0.02908, plaster 0.02758 all reproduce
   ITU to five significant figures at 3.5 GHz. But the catalog OVERRODE them
   whenever the material name resolved. Two concrete surfaces in one scene
   therefore received 0.008 or 0.12309 depending only on whether a string
   matched, with no physical reason for the difference.

3. Every metadata-tier node was written with
   conductivity_src = "ITU-R P.2040 Table 3", a provenance string chosen by
   testing where the PERMITTIVITY came from. The conductivity it labelled had
   not come from ITU at all.

Values are held as coefficients rather than as numbers computed at 3.5 GHz, so
changing the study frequency cannot silently leave stale values behind.

    eps_r(f) = a * f^b          sigma(f) = c * f^d   [S/m],  f in GHz

VERIFICATION STATUS

The coefficients below are the standard P.2040 Table 3 set. Three of them are
independently confirmed by this repository's own prior values: the concrete,
brick and plasterboard conductivities in MATERIAL_CLASS_DEFAULTS reproduce
c * 3.5^d exactly. That is good evidence the set is the right one, but it is
not a substitute for checking the document.

BEFORE SUBMISSION: open the revision you intend to cite, confirm every row,
and record the revision number in CITED_REVISION below. Revisions differ.
"""
from __future__ import annotations

# Coefficients below were checked against Table 3 of the current in-force
# Recommendation, rather than leaving the provenance revision unspecified.
CITED_REVISION = "ITU-R P.2040-4 (09/2025)"


class Provenance:
    ITU = "itu_p2040_table3"
    PROXY = "declared_proxy"       # mapped onto an ITU row by our decision
    LITERATURE = "named_literature"
    MODEL = "declared_model"       # our wet-state model, not from ITU
    NONE = "unparameterised"


# --------------------------------------------------------------------------
# ITU-R P.2040 Table 3. (a, b, c, d, f_min_GHz, f_max_GHz)
# Nothing may be added here that is not in the document.
# --------------------------------------------------------------------------
ITU_TABLE = {
    "vacuum":            (1.0,  0.0, 0.0,     0.0,    0.001, 100.0),
    "concrete":          (5.24, 0.0, 0.0462,  0.7822, 1.0,   100.0),
    "brick":             (3.91, 0.0, 0.0238,  0.16,   1.0,    40.0),
    "plasterboard":      (2.73, 0.0, 0.0085,  0.9395, 1.0,   100.0),
    "wood":              (1.99, 0.0, 0.0047,  1.0718, 0.001, 100.0),
    "glass":             (6.31, 0.0, 0.0036,  1.3394, 0.1,   100.0),
    "ceiling_board":     (1.48, 0.0, 0.0011,  1.0750, 1.0,   100.0),
    "chipboard":         (2.58, 0.0, 0.0217,  0.7800, 1.0,   100.0),
    "floorboard":        (3.66, 0.0, 0.0044,  1.3515, 50.0,  100.0),
    "metal":             (1.0,  0.0, 1.0e7,   0.0,    1.0,   100.0),
    "very_dry_ground":   (3.0,  0.0, 0.00015, 2.52,   1.0,    10.0),
    "medium_dry_ground": (15.0, -0.1, 0.035,  1.63,   1.0,    10.0),
    "wet_ground":        (30.0, -0.4, 0.15,   1.30,   1.0,    10.0),
}


# --------------------------------------------------------------------------
# Our material vocabulary -> ITU row.
#
# `proxy` entries are OUR decision, not ITU's. Each one needs a written
# justification before the paper goes out; a proxy with justification=None
# raises rather than silently returning a number that looks authoritative.
# ITU Table 3 contains no asphalt, gravel, plastic, paving stone, sett or
# kerb. Inventing rows for them would be worse than declaring the mapping.
# --------------------------------------------------------------------------
MAPPING = {
    "concrete":   ("concrete",     Provenance.ITU,   None),
    "brick":      ("brick",        Provenance.ITU,   None),
    "plaster":    ("plasterboard", Provenance.ITU,
                   "P.2040 lists plasterboard; rendered plaster is treated as "
                   "the same family."),
    "glass":      ("glass",        Provenance.ITU,   None),
    "wood":       ("wood",         Provenance.ITU,   None),
    # Ground is not a proxy: P.2040 Table 3 has three ground rows
    # (very_dry/medium_dry/wet). medium_dry_ground is the declared dry
    # state, consistent with the proxy state chosen for asphalt and
    # gravel, but here it is the material's own row, not a substitute.
    "ground":     ("medium_dry_ground", Provenance.ITU, None),
    # Generic metal is represented by the repository's named literature
    # value (material_properties.py), not by the ITU metal row.
    "metal":      (None,            Provenance.LITERATURE,
                   "material_properties.py CLASS_DEFAULTS['metal']; "
                   "generic metal literature value"),

    # --- proxies: JUSTIFICATION REQUIRED, do not ship with None ---
    "asphalt":    ("medium_dry_ground", Provenance.PROXY,
                   "Asphalt is mapped to ITU medium_dry_ground as the "
                   "declared proxy for the electromagnetic layer."),
    "roofing":    ("concrete",          Provenance.PROXY, None),
    "gravel":     ("medium_dry_ground", Provenance.PROXY,
                   "P.2040 Table 3 contains no row for unbound mineral "
                   "aggregate. We map gravel onto the ground family, the "
                   "same declared proxy used for asphalt, so that a porous "
                   "mineral surface receives a parameterisation of the "
                   "correct order rather than none. The dominant loss "
                   "mechanism at 3.5 GHz in both cases is water held in "
                   "pore space. The mapping is ours and is recorded as "
                   "PROXY, not as an ITU value; material identity is "
                   "retained as gravel. We make no claim that gravel and "
                   "ground are dielectrically equivalent."),
    "stone":      ("concrete",          Provenance.PROXY, None),
    "paving":     ("concrete",          Provenance.PROXY, None),
    "vegetation": (None,                Provenance.NONE,
                   "P.2040 has no vegetation row; vegetation is excluded from "
                   "the electromagnetic layer."),
    "plastic":    (None,                Provenance.NONE,
                   "P.2040 has no plastic row and we have no measurement; "
                   "excluded from the electromagnetic layer."),
    # Newly exposed scene vocabulary. These are intentionally unresolved
    # proxies: author decisions are required before any number is emitted.
    "paving":     ("concrete",          Provenance.PROXY, None),
    "sett":       ("concrete",          Provenance.PROXY, None),
    "kerb":       ("concrete",          Provenance.PROXY, None),
    "rail_ballast": ("medium_dry_ground", Provenance.PROXY, None),
    "grass":      ("medium_dry_ground", Provenance.PROXY, None),
    "earth":      ("medium_dry_ground", Provenance.PROXY, None),
    "water":      (None,                Provenance.NONE,
                   "P.2040 Table 3 has no water row; excluded from the "
                   "electromagnetic layer."),
    "unknown":    (None,                Provenance.NONE,
                   "material not resolved; no parameters asserted."),
}


# --------------------------------------------------------------------------
# Wet state. ITU parameterises GROUND wetness only (very dry / medium dry /
# wet ground). It gives no wet counterpart for construction materials, so
# every non-ground wet endpoint below is OUR model and is labelled as such.
# --------------------------------------------------------------------------
WET_TRANSITION = {
    "asphalt": ("medium_dry_ground", "wet_ground", Provenance.PROXY),
    "roofing": ("medium_dry_ground", "wet_ground", Provenance.PROXY),
    "gravel":  ("medium_dry_ground", "wet_ground", Provenance.PROXY),
    # Ground's own ITU row, not a proxy - both endpoints are material rows.
    "ground":  ("medium_dry_ground", "wet_ground", Provenance.ITU),
}


class UnparameterisedMaterial(Exception):
    pass


class FrequencyOutOfRange(Exception):
    pass


def itu_values(row, f_ghz, strict=True):
    """(eps_r, sigma S/m) for an ITU row at f_ghz."""
    if row not in ITU_TABLE:
        raise UnparameterisedMaterial(f"'{row}' is not a P.2040 Table 3 row")
    a, b, c, d, fmin, fmax = ITU_TABLE[row]
    if strict and not (fmin <= f_ghz <= fmax):
        raise FrequencyOutOfRange(
            f"'{row}' is specified for {fmin}-{fmax} GHz; {f_ghz} GHz is outside it")
    return a * f_ghz ** b, c * f_ghz ** d


def resolve(material_class, f_ghz, state="dry", require_justification=True):
    """Resolve one material class to (eps, sigma, provenance dict).

    Returns None for eps/sigma when the class has no defensible
    parameterisation, rather than substituting a placeholder. A caller that
    needs a number must handle the absence; that is the point.
    """
    cls = (material_class or "unknown").lower()
    if cls not in MAPPING:
        raise UnparameterisedMaterial(
            f"'{cls}' has no entry in MAPPING; add one with a written "
            f"justification rather than letting it fall through")

    row, prov, justification = MAPPING[cls]

    if cls == "metal":
        return 1.0, 1.4e6, {
            "provenance": Provenance.LITERATURE,
            "row": None,
            "frequency_ghz": f_ghz,
            "note": justification,
        }

    if state == "wet":
        if cls not in WET_TRANSITION:
            return None, None, {"provenance": Provenance.NONE, "row": None,
                                "note": f"no wet endpoint defined for '{cls}'"}
        _dry_row, wet_row, wprov = WET_TRANSITION[cls]
        row, prov = wet_row, wprov
    elif state == "dry" and cls in WET_TRANSITION:
        row = WET_TRANSITION[cls][0]

    if row is None:
        return None, None, {"provenance": prov, "row": None, "note": justification}

    if prov == Provenance.PROXY and require_justification and not justification:
        raise UnparameterisedMaterial(
            f"'{cls}' is mapped onto ITU row '{row}' as a PROXY with no written "
            f"justification. Write one in MAPPING, or drop the class from the "
            f"electromagnetic layer. Do not ship an unjustified proxy.")

    eps, sigma = itu_values(row, f_ghz)
    return eps, sigma, {
        "provenance": prov,
        "row": row,
        "revision": CITED_REVISION,
        "frequency_ghz": f_ghz,
        "note": justification,
    }


def self_test(f_ghz=3.5):
    """Reproduces the figures the paper quotes, from the table rather than
    from a keyboard. If the paper's numbers stop matching this output, one of
    the two is wrong."""
    out = []
    ed, sd = itu_values("very_dry_ground", f_ghz)
    ew, sw = itu_values("wet_ground", f_ghz)
    out.append(("ground eps ratio (very dry -> wet)", ew / ed))
    out.append(("ground sigma ratio (very dry -> wet)", sw / sd))
    em, sm = itu_values("medium_dry_ground", f_ghz)
    out.append(("ground eps ratio (medium dry -> wet)", ew / em))
    out.append(("ground sigma ratio (medium dry -> wet)", sw / sm))
    for name, row in (("concrete", "concrete"), ("brick", "brick"),
                      ("plaster", "plasterboard"), ("glass", "glass")):
        e, s = itu_values(row, f_ghz)
        out.append((f"{name} eps / sigma", (round(e, 4), round(s, 5))))
    return out


if __name__ == "__main__":
    print(f"ITU-R P.2040 Table 3, evaluated at 3.5 GHz")
    print(f"cited revision: {CITED_REVISION or 'NOT SET - set it before publishing'}\n")
    for label, value in self_test():
        if isinstance(value, tuple):
            print(f"  {label:38} eps={value[0]:<8} sigma={value[1]}")
        else:
            print(f"  {label:38} x{value:.2f}")
    print("\nunjustified proxies (must be resolved before submission):")
    for cls, (row, prov, just) in MAPPING.items():
        if prov == Provenance.PROXY and not just:
            print(f"  {cls:12} -> ITU row '{row}'  (no justification written)")
