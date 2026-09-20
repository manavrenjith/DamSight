# ASSUMPTIONS.md — DamSight Assumption & Source Registry

> **Ground Rule 2:** Everything that is synthetic, approximate, or placeholder must be labelled as such in code, in outputs, and in the UI. Keep a running `ASSUMPTIONS.md` listing every assumption, source, and any number you could not verify.

This document tracks all physical constants, empirical coefficients, parameter ranges, and synthetic datasets used across DamSight.

---

## 1. Physical & Empirical Formulations

| Item | Formula (SI Units) | Full Citation & Source | Verification Status | Unit Conversions & Notes |
|---|---|---|---|---|
| Froehlich (2008) Breach Width | $B_{\text{avg}} = 0.27 K_o V_w^{0.32} h_b^{0.04}$ | Froehlich, D. C. (2008). *Embankment dam breach parameters and their uncertainties*. Journal of Hydraulic Engineering, 134(12), 1708-1721. | Verified against published paper | SI units: $V_w$ in $\text{m}^3$, $h_b$ in $\text{m}$, $B_{\text{avg}}$ in $\text{m}$. (English units equivalent uses $0.1803$ with acre-ft and ft). $K_o = 1.3$ (overtopping), $1.0$ (piping). |
| Froehlich (2008) Formation Time | $t_f = 63.2 \sqrt{\frac{V_w}{g h_b^2}}$ | Froehlich, D. C. (2008). *Embankment dam breach parameters and their uncertainties*. J. Hydraul. Eng. | Verified against published paper | SI units: $g = 9.80665 \text{ m/s}^2$, $t_f$ in seconds. $t_f(\text{hr}) = t_f / 3600$. (English units equivalent uses $g = 32.174\text{ ft/s}^2$, factor $0.0176$ hr). |
| Froehlich (1995) Peak Outflow | $Q_p = 0.607 V_w^{0.295} h_w^{1.24}$ | Froehlich, D. C. (1995). *Peak outflow from breached embankment dam*. Journal of Water Resources Planning and Management, 121(1), 90-97. | Verified against published paper | SI units: $V_w$ in $\text{m}^3$, $h_w$ in $\text{m}$, $Q_p$ in $\text{m}^3/\text{s}$. (English units equivalent uses $23.4$ with $V_w$ in acre-ft, $h_w$ in ft). |
| Broad-Crested Trapezoidal Weir | $Q = C_{d1} W_b h^{1.5} + C_{d2} Z h^{2.5}$ | Standard Open-Channel Hydraulics (Henderson, 1966; Chow, 1959) | **DEFAULTED** (Unsourced calibration) | $C_{d1} = 1.70 \text{ m}^{1/2}/\text{s}$ (rectangular weir), $C_{d2} = 1.35 \text{ m}^{1/2}/\text{s}$ (triangular side weir, $Z$ horizontal to 1 vertical). Marked `defaulted` as exact discharge coefficients are not empirically calibrated for evolving embankment breaches. |
| Natural Dam Breach Parameters | $t_f \times 0.40$, $B_{\text{avg}} \times 1.25$ | Invented placeholder, no source | **ILLUSTRATIVE ONLY** | Factors 0.40 (formation time acceleration) and 1.25 (breach width expansion) are an invented placeholder, no source. Output metadata carries parameter_status=illustrative. |

---

## 1.1 Breach Geometry & Evolution Mechanics

- **Side Slope ($Z$):**
  - Mode `"overtopping"`: $Z = 1.0$ (1H:1V).
  - Mode `"piping"`: $Z = 0.7$ (0.7H:1V).
  - *Verification Status:* **`unverified`** (source not confirmed). In Froehlich (2008), empirical regression equations are developed specifically for $B_{\text{avg}}$ and $t_f$; while side slope ratios of $1.0$ (overtopping) and $0.7$ (piping) are widely adopted in dam breach practice (adapted from Froehlich 1995a, Table 1 / USACE guidelines), no dedicated regression equation or lookup table for $Z$ appears in the 2008 paper text. Hence, $Z = 1.0 / 0.7$ has its provenance marked as "source not confirmed" and is labelled `unverified`.
- **Initial Notch:**
  - At $t = 0$, $z_b(0) = z_{\text{crest}}$ and $w_b(0) = 0.0$ m. There is no pre-existing notch or pre-incision; water spills only when reservoir stage exceeds $z_{\text{crest}}$.
- **Growth Law:**
  - For $t \in [0, t_f]$, linear enlargement:
    $$w_b(t) = W_{\text{bottom}} \cdot \frac{t}{t_f}, \quad z_b(t) = z_{\text{crest}} - h_b \cdot \frac{t}{t_f}$$
  - For $t > t_f$, terminal static geometry: $w_b(t) = W_{\text{bottom}}$, $z_b(t) = z_{\text{crest}} - h_b$.
- **Bottom Width Rule & Clamp ($W_{\text{bottom}}$):**
  - Evaluated via Froehlich (2008) formulation:
    $$B_{\text{avg}} = 0.27 \cdot K_o \cdot V_w^{0.32} \cdot h_b^{0.04}$$
    where $K_o = 1.3$ for overtopping and $1.0$ for piping.
  - Bottom width is geometrically defined as $W_{\text{bottom}} = \max(0.0, B_{\text{avg}} - Z \cdot h_b)$.
  - **Example using 2008 constants ($0.27, K_o, h_b^{0.04}$):**
    For a deep breach with $V_w = 1.0 \times 10^6\text{ m}^3$, $h_b = 40.0\text{ m}$, and $K_o = 1.3$ (overtopping):
    $$B_{\text{avg}} = 0.27 \times 1.3 \times (1.0 \times 10^6)^{0.32} \times (40.0)^{0.04} = 0.351 \times 83.1764 \times 1.15836 \approx 33.82\text{ m}$$
    Because $B_{\text{avg}} - Z \cdot h_b = 33.82 - (1.0 \times 40.0) = -6.18\text{ m} \le 0$, $W_{\text{bottom}}$ clamps strictly to $0.0\text{ m}$.
  - **Geometric Consequence of Clamping:**
    When $W_{\text{bottom}}$ is clamped to $0.0\text{ m}$, the breach geometry becomes a pure triangular notch with top width $W_{\text{top}} = W_{\text{bottom}} + 2 Z h_b = 0 + 2(1.0)(40.0) = 80.0\text{ m}$. The resulting actual average width of this triangular opening is:
    $$\bar{B} = \frac{W_{\text{bottom}} + W_{\text{top}}}{2} = \frac{0.0 + 80.0}{2} = 40.0\text{ m}$$
    Notice that the clamp $\max(0, B_{\text{avg}} - Z \cdot h_b)$ produces a final breach that is **wider than $B_{\text{avg}}$** ($40.0\text{ m}$ vs. $\approx 33.82\text{ m}$ from the regression).
  - Under $W_{\text{bottom}} = 0.0$ m, the rectangular weir component vanishes ($1.70 \cdot 0 \cdot h^{1.5} = 0$), and routing transitions continuously and smoothly to pure triangular weir outflow ($Q = C_{d2} Z h^{2.5}$).


---

## 2. Roughness (Manning's n) Lookup & Citations

Manning's $n$ values are mapped from ESA WorldCover 10m classes using `data/manning_lookup.csv`. Every value is documented with hydraulic literature citations:

| WorldCover Class | Description | Assumed $n$ ($\text{s/m}^{1/3}$) | Full Citation / Source | Verification Status | Notes |
|---|---|---|---|---|---|
| 10 | Tree cover | 0.120 | Chow, V. T. (1959). *Open-Channel Hydraulics*, McGraw-Hill, Table 5-6 (Dense willow / heavy timber). | Verified against literature | Standard floodplain roughness for dense deciduous/coniferous woods. |
| 20 | Shrubland | 0.070 | Chow, V. T. (1959). Table 5-6 (Medium to dense brush, summer foliage). | Verified against literature | Medium scrub/brush. |
| 30 | Grassland | 0.035 | Chow, V. T. (1959). Table 5-6 (High grass / pasture). | Verified against literature | Unmowed prairie / natural grass. |
| 40 | Cropland | 0.040 | Arcement, G. J., & Schneider, V. R. (1989). *Guide for Selecting Manning's Roughness Coefficients for Natural Channels and Flood Plains*, USGS Water-Supply Paper 2339, Table 1. | Verified against literature | Mature row crops and cultivated fields. |
| 50 | Built-up | 0.150 | Syme, W. J. (2008). *Flooding in Urban Areas*, Australian Rainfall and Runoff Revision Project 15. | Verified against literature | Macro-roughness approximation representing urban building block drag. |
| 60 | Bare / sparse vegetation | 0.030 | Chow, V. T. (1959). Table 5-6 (Clean gravel/earth). | Verified against literature | Unvegetated alluvial gravel, clay, or bare soil. |
| 70 | Snow and ice | 0.020 | Chow, V. T. (1959). Table 5-6 (Smooth ice/frozen ground). | Verified against literature | Glacial surface and hard snowpack. |
| 80 | Permanent water bodies | 0.025 | Chow, V. T. (1959). Table 5-6 (Clean straight natural channel). | Verified against literature | Open water main channels. |
| 90 | Herbaceous wetland | 0.060 | Arcement, G. J., & Schneider, V. R. (1989). USGS WSP 2339, Table 1. | Verified against literature | Marshes, reed beds, and standing water reeds. |
| 95 | Mangroves | 0.140 | Arcement, G. J., & Schneider, V. R. (1989). USGS WSP 2339, Table 1. | Verified against literature | High drag due to prop roots and pneumatophores. |
| 100 | Moss and lichen | 0.030 | Chow, V. T. (1959). Table 5-6 (Smooth tundra/bare earth). | Verified against literature | Alpine and arctic tundra cover. |

*Fallback rule:* Any unmapped or nodata land cover cell defaults to $n = 0.040$ (cropland/general floodplain) and is logged in `report.json`.

---

## 2.1 Terrain Conditioning Rules (Ground Rule 1 & Section 5.2)

- **Sink Filling:** Depressions and single-cell pits in the DEM are filled to their spill elevation using the priority-flood depression-filling algorithm to prevent spurious numerical water entrapment.
- **Selective Conditioning:** Sinks are filled only where physically appropriate (depth $< 15.0$m or area $< 100$ cells); large natural basins and verified reservoirs are preserved.
- **No Unapproved Carving:** Channel carving is strictly disabled by default unless explicitly specified in site configuration.
- **Audit Trail:** Every altered cell (pixel coordinates, original elevation, conditioned elevation, delta) is logged and summarized in `report.json`.

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

---

## 5. Upstream Dependencies & Deprecations

- **Affine / Rasterio Transform Operator Deprecation:**
  - `PendingDeprecationWarning: Use \`@\` matmul instead of \`*\` mul operator for matrix multiplication` emitted from `affine` / `rasterio.transform` (`from_origin` uses `Affine.translation(...) * Affine.scale(...)`).
  - This is an **upstream** library deprecation inside `rasterio`'s internal implementation of `rasterio.transform.from_origin` calling `affine.Affine.__mul__`.
  - Filtered specifically by module and warning message in `pyproject.toml`.

---

## 6. Breach Hydrograph Parametric Dynamics & Cusp at $t_f$

- **Slope Discontinuity (Cusp) at $t = t_f$:**
  - In the Froehlich parametric breach growth model, breach geometric expansion ($W_b(t)$ widening and $z_b(t)$ invert incision) is assumed linear over the formation duration $t \in [0, t_f]$.
  - At $t = t_f$, geometric enlargement abruptly ceases as the breach reaches its ultimate terminal dimensions ($B_{\text{final}}$, $z_{b,\text{min}}$).
  - Because geometric expansion halts while reservoir drawdown continues through pure broad-crested weir drainage, the discharge derivative $\frac{dQ}{dt}$ undergoes an instantaneous transition from positive/near-zero to steep negative decay. This manifests physically and mathematically as a visible cusp or slope discontinuity at $t = t_f$.
- **Interpretation of Peak Time ($t_{\text{peak}}$):**
  - The simulated peak outflow time ($t_{\text{peak}}$) is an emergent mathematical result of the competition between expanding breach cross-section and declining reservoir water head ($\frac{dh}{dt}$).
  - **Operational Warning:** The peak time $t_{\text{peak}}$ must **never** be interpreted or communicated as an operational forecast or prediction of real-world breach culmination. In actual dam incidents, geotechnical piping collapse or structural mass wasting occurs dynamically and irregularly. Parametric peak timing is strictly a benchmark and comparative scenario metric.
- **Hydrograph Truncation & Inflow Boundary Behavior:**
  - When a breach hydrograph is truncated (e.g. at `cutoff_q_ratio = 0.001` where discharge decays below $0.1\%$ of peak $Q_{\text{peak}}$, or when drainable active storage is exhausted), hydrodynamic solver adapters (such as `AnugaSolver` with `Inlet_operator`) evaluate inflow discharge $Q(t)$ via interpolation clamped to zero: for any simulation timestamp $t > t_{\text{end}}$, inflow defaults strictly to $Q(t) = 0.0\text{ m}^3/\text{s}$.
  - This prevents artificial prolonged draining or persistent spurious inflow into downstream reaches after active reservoir evacuation.
