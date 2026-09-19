# ASSUMPTIONS.md — DamSight Assumption & Source Registry

> **Ground Rule 2:** Everything that is synthetic, approximate, or placeholder must be labelled as such in code, in outputs, and in the UI. Keep a running `ASSUMPTIONS.md` listing every assumption, source, and any number you could not verify.

This document tracks all physical constants, empirical coefficients, parameter ranges, and synthetic datasets used across DamSight.

---

## 1. Physical & Empirical Formulations

| Item | Formula / Value | Source / Citation | Verification Status | Notes |
|---|---|---|---|---|
| Froehlich (2008) Breach Width | $B_{\text{avg}} = 0.27 K_o V_w^{0.32} h_b^{0.04}$ | Froehlich, D. C. (2008). *Embankment dam breach parameters and their uncertainties*. J. Hydraul. Eng. | Sourced from paper | $K_o = 1.3$ (overtopping), $1.0$ (piping). SI units. |
| Froehlich (2008) Formation Time | $t_f = 63.2 \sqrt{\frac{V_w}{g h_b^2}}$ | Froehlich, D. C. (2008). | Sourced from paper | SI units ($t_f$ in seconds). |
| Froehlich (1995) Peak Outflow | $Q_p = 0.607 V_w^{0.295} h_w^{1.24}$ | Froehlich, D. C. (1995). *Peak outflow from breached embankment dam*. | Sourced from paper | SI units. Used as sanity upper bound on hydrograph peak. |
| Broad-Crested Weir Coefficient | $C_d \approx 1.7 \text{ m}^{1/2}/\text{s}$ | Standard open-channel hydraulics | General hydraulic assumption | Used for trapezoidal breach weir flow calculation. |

---

## 2. Roughness (Manning's n) Lookup

Manning's $n$ values will be mapped from ESA WorldCover 10m classes in `data/manning_lookup.csv`:

| WorldCover Class | Description | Assumed $n$ ($\text{s/m}^{1/3}$) | Source | Status |
|---|---|---|---|---|
| 10 | Tree cover | 0.120 | Chow (1959) / Arcement & Schneider (1989) | Standard literature estimate |
| 20 | Shrubland | 0.070 | Chow (1959) | Standard literature estimate |
| 30 | Grassland | 0.035 | Chow (1959) | Standard literature estimate |
| 40 | Cropland | 0.040 | Chow (1959) | Standard literature estimate |
| 50 | Built-up | 0.150 | Syme (2008) / Flood plain guidelines | Approximate macro-roughness |
| 60 | Bare / sparse vegetation | 0.030 | Chow (1959) | Standard literature estimate |
| 70 | Snow and ice | 0.020 | Chow (1959) | Standard literature estimate |
| 80 | Permanent water bodies | 0.025 | Standard river channel | Standard literature estimate |
| 90 | Herbaceous wetland | 0.060 | Chow (1959) | Standard literature estimate |
| 95 | Mangroves | 0.140 | Chow (1959) | Standard literature estimate |
| 100 | Moss and lichen | 0.030 | Chow (1959) | Standard literature estimate |

---

## 3. Site Parameters & Verification Status

### Site A (Candidate: Machhu-II Dam, Morbi, Gujarat)
- **Dam Height ($h_b$):** `TODO_VERIFY` (Pending verified entry from Central Water Commission / India-WRIS records).
- **Crest Elevation:** `TODO_VERIFY` (Pending official datum verification).
- **Reservoir Volume ($V_w$):** `TODO_VERIFY` (Pending official stage-storage documentation).
- **Breach Geometry:** Overtopping and piping scenarios modeled parametrically.
- **Topography:** Copernicus 30m Global DEM (GLO-30) assumed as base elevation. Coarse bathymetry assumed flat/interpolated.

### Site B (Natural Dam / Landslide: Rishiganga / Chamoli, Uttarakhand)
- **Elevation Model:** High-relief Himalayan valley; 30m DEM known to feature steep slope shadow artifacts and channel canyon narrowness.
- **Lake Volume:** Approximated from satellite water polygon area and contour depression bed.
- **Breach Mechanism:** Rapid overtopping erosion through unconsolidated debris.

### Site C (Cascade Failure)
- **Status:** Scoped hypothetical two-dam chain situated along Site A's reach.

---

## 4. Evacuation Modeling Assumptions

- **Walking Speed:** 4.0 km/h (flat terrain, unobstructed).
- **Vehicle Speed:** 30.0 km/h (rural secondary roads).
- **Road Closure Water Depth:** 0.3 meters (vehicles lose traction and stall; pedestrian wading threshold).
- **Safety Clearance Margin:** 10 minutes prior to flood wave arrival at any road link.
- **Safe Zone Definition:** Elevation $\ge$ P90 flood elevation $+ 1.0$m buffer, or areas with zero inundation probability.
- **Road Graph:** Derived from OpenStreetMap highway tags (`motorway`, `trunk`, `primary`, `secondary`, `tertiary`, `unclassified`, `residential`). Unmapped tracks or collapsed bridges are treated as impassable unless mapped.
