# PERFORMANCE.md — Solver Validation & Benchmark Performance

This document records hydrodynamic solver benchmarks, numerical accuracy metrics, convergence rates, and execution runtimes for DamSight.

---

## 1. Environment & Hydrodynamic Solver Specification

- **Solver:** ANUGA Hydrodynamic Model (Australian National University & Geoscience Australia)
- **Package Version:** `anuga 4.0.0` (`py311hf5321a7_0`)
- **Installation Channel:** `conda-forge` (binary wheel compiled for Windows 64-bit AMD64)
- **Python Runtime:** Python 3.11.16 64-bit
- **Architecture:** Shallow Water 2D Finite-Volume Formulation with discontinuous Galerkin / Godunov flux limiter
- **Execution Mode:** Sequential (`mpi4py` disabled/sequential interface active)

---

## 2. Analytical Dam-Break Benchmarks (SPEC Section 7.4 / M3a)

All benchmark simulations were executed strictly **through the solver adapter** (`AnugaSolver.prepare()`, `AnugaSolver.run()`, `AnugaSolver.collect()`), not by ad-hoc calls to internal ANUGA methods.

### Benchmark Setup & Execution Parameters (B2):
- **Geometry:** 1D Rectangular Frictionless Channel ($L = 1000.0$ m, $W = 20.0$ m)
- **Dam Location:** $x_0 = 500.0$ m
- **Initial Reservoir Depth ($h_0$ / $h_L$):** $10.0$ m
- **Downstream Depth ($h_R$):** $0.0$ m (Ritter dry bed) | $2.0$ m (Stoker wet bed)
- **Bed & Roughness:** Flat horizontal bed ($z = 0.0$ m), frictionless Manning $n = 0.0\text{ s/m}^{1/3}$
- **Boundary Types:** Top & Bottom: `Reflective_boundary`; Left & Right: `Transmissive_boundary`
- **Output Yieldstep:** $\Delta t_{\text{yield}} = 1.0$ s (simulation duration $16.0$ s)
- **Mesh Resolutions & Triangle Counts:**
  - Coarse ($\Delta x = 20$ m): 200 triangles ($nx = 50, ny = 1$)
  - Fine ($\Delta x = 10$ m): 800 triangles ($nx = 100, ny = 2$)
  - Superfine ($\Delta x = 5$ m): 3200 triangles ($nx = 200, ny = 4$)
- **Sampling Grid:** Centroid coordinates $x_c$ of triangles extracted directly from simulation SWW NetCDF output, guaranteeing zero spatial interpolation artifacts.

### Metric Definitions, Code Criteria & Gates:

#### 1. Front Definition & Exact Code
For dry bed (Ritter), water depth starts at $0.0\text{ m}$, so the front threshold is $0.01 \cdot h_0 = 0.10\text{ m}$.
For wet bed (Stoker), downstream water depth is already $h_R = 2.0\text{ m}$. Hence the shock front threshold is placed $1\%$ above the ambient pool:
$$h_{\text{thresh, Stoker}} = h_R + 0.01 \cdot (h_m - h_R)$$

**Exact code in `scripts/benchmarks/run_benchmarks.py`:**
```python
if b_key == "ritter":
    h_exact, _, meta = ritter_solution(xc_sim, t=t_eval, x0=x0, h0=h0, g=g)
    exact_front_tip = meta["x_front"]
    thresh = 0.01 * h0
    sim_wet = xc_sim[h_sim > thresh]
    exact_wet = xc_sim[h_exact > thresh]
else:
    h_exact, _, meta = stoker_solution(xc_sim, t=t_eval, x0=x0, hL=h0, hR=h_right, g=g)
    exact_front_tip = meta["x_shock"]
    thresh = h_right + 0.01 * (meta["hm"] - h_right)
    sim_wet = xc_sim[h_sim > thresh]
    exact_wet = xc_sim[h_exact > thresh]

x_sim_front = float(np.max(sim_wet)) if len(sim_wet) > 0 else x0
x_exact_thresh = float(np.max(exact_wet)) if len(exact_wet) > 0 else x0
```

#### 2. Shock Arrival Criterion & Exact Code
In `tests/test_solvers.py::test_stoker_arrival_time_shock_speed`, arrival is defined by a $20\%$ rise above the ambient downstream pool:
$$h_{\text{arrival, thresh}} = h_R + 0.20 \cdot (h_m - h_R)$$

**Exact code in `tests/test_solvers.py`:**
```python
# Arrival threshold: 20% elevation above downstream pool hR
arrival_thresh = hR + 0.2 * (hm - hR)
# Simulated arrival evaluated per triangle:
for i in range(len(xc)):
    hits = np.where(depth_c[:, i] > arrival_thresh)[0]
    if len(hits) > 0:
        arrival_sim[i] = time_arr[hits[0]]
# Exact analytical shock arrival:
arr_exact_wet = (xc_wet - x0) / s
```

#### 3. Error Metrics & G1 Verification Gates
- **Dual Front Error:**
  - Position % (**Gate: $\le 5.0\%$ at finest mesh $\Delta x = 5$ m**): $\frac{|x_{\text{sim}} - x_{\text{exact, thresh}}|}{x_{\text{exact, thresh}}} \times 100\%$
  - Distance Travelled % (**Strict Metric**, reported in JSON & tables): $\frac{|x_{\text{sim}} - x_{\text{exact, thresh}}|}{|x_{\text{exact, thresh}} - x_0|} \times 100\%$
  - Error vs Analytical Tip ($h=0$) (*info*): $|x_{\text{sim}} - x_{\text{tip}}|$
  - **Regression Guard (G1-d):** Front error at $\Delta x = 5$ m $\le 3 \text{ cells}$ ($3 \cdot \Delta x = 15.0\text{ m}$) at all timestamps.
- **$L_1$ Depth Error Regions:**
  - **Symmetric Region:** $|x - x_0| \le c_0 t$ ($L_{\text{disturbed}} = 2 c_0 t$).
  - **True Disturbed Region (Ritter):** $[x_0 - c_0 t, x_0 + 2 c_0 t]$, encompassing the entire rarefaction wave and advancing tip ($L_{\text{true}} = 3 c_0 t$).
  - **Gate:** $L_1$ depth error $\le 5.0\%$ at $\Delta x = 5$ m across all evaluation timestamps.
- **Spatial Convergence Gate:** Monotonically non-increasing error from $\Delta x = 20\text{ m} \to 10\text{ m} \to 5\text{ m}$ at each timestamp ($5$s, $10$s, $15$s) for both front and $L_1$ error.

---

### Benchmark 1: Ritter (1892) Dry Bed Dam-Break ($h_0 = 10.0\text{ m}, h_R = 0.0\text{ m}$)

| Resolution ($\Delta x$) | Time ($t$) | Exact Thresh | Sim Front | Front Error | Front Pos % [Gate $\le 5\%$] | Travelled % (*strict*) | Error vs Tip (*info*) | $L_1$ Sym [Gate $\le 5\%$] | $L_1$ True [Gate $\le 5\%$] | $L_1$ Whole (*info*) | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **20 m** (200 tri) | 5.0 s | 583.33 m | 563.33 m | 20.00 m | 3.43% (*info*) | 24.00% | 35.70 m | 8.12% (*info*) | 5.95% (*info*) | 0.92% | 0.19 s |
| **20 m** (200 tri) | 10.0 s | 663.33 m | 636.67 m | 26.67 m | 4.02% (*info*) | 16.33% | 61.39 m | 4.15% (*info*) | 3.23% (*info*) | 1.00% | 0.19 s |
| **20 m** (200 tri) | 15.0 s | 750.00 m | 716.67 m | 33.33 m | 4.44% (*info*) | 13.33% | 80.42 m | 2.90% (*info*) | 2.21% (*info*) | 1.04% | 0.19 s |
| **10 m** (800 tri) | 5.0 s | 581.67 m | 568.33 m | 13.33 m | 2.29% (*info*) | 16.33% | 30.70 m | 4.17% (*info*) | 3.23% (*info*) | 0.50% | 0.24 s |
| **10 m** (800 tri) | 10.0 s | 668.33 m | 648.33 m | 20.00 m | 2.99% (*info*) | 11.88% | 49.72 m | 2.24% (*info*) | 1.75% (*info*) | 0.54% | 0.24 s |
| **10 m** (800 tri) | 15.0 s | 751.67 m | 735.00 m | 16.67 m | 2.22% (*info*) | 6.62% | 62.09 m | 1.55% (*info*) | 1.21% (*info*) | 0.56% | 0.24 s |
| **5 m** (3200 tri) | 5.0 s | 584.17 m | 574.17 m | 10.00 m | **1.71%** (PASS) | 11.88% | 24.86 m | **2.24%** (PASS) | **1.75%** (PASS) | 0.27% | 0.62 s |
| **5 m** (3200 tri) | 10.0 s | 667.50 m | 657.50 m | 10.00 m | **1.50%** (PASS) | 5.97% | 40.56 m | **1.19%** (PASS) | **0.92%** (PASS) | 0.29% | 0.62 s |
| **5 m** (3200 tri) | 15.0 s | 752.50 m | 745.83 m | 6.67 m | **0.89%** (PASS) | 2.64% | 51.25 m | **0.83%** (PASS) | **0.64%** (PASS) | 0.30% | 0.62 s |

**Ritter Convergence Audit:**
- $t = 5.0$ s: Front Error $20.00 \to 13.33 \to 10.00$ m (Monotonic: True); $L_1$ True $5.95\% \to 3.23\% \to 1.75\%$ (Monotonic: True); Observed Order $p = 0.90$ [**PASS**]
- $t = 10.0$ s: Front Error $26.67 \to 20.00 \to 10.00$ m (Monotonic: True); $L_1$ True $3.23\% \to 1.75\% \to 0.92\%$ (Monotonic: True); Observed Order $p = 0.91$ [**PASS**]
- $t = 15.0$ s: Front Error $33.33 \to 16.67 \to 6.67$ m (Monotonic: True); $L_1$ True $2.21\% \to 1.21\% \to 0.64\%$ (Monotonic: True); Observed Order $p = 0.90$ [**PASS**]

---

### Benchmark 2: Stoker (1957) Wet Bed Dam-Break ($h_0 = 10.0\text{ m}, h_R = 2.0\text{ m}$)

| Resolution ($\Delta x$) | Time ($t$) | Exact Shock | Sim Shock | Shock Error | Shock Pos % [Gate $\le 5\%$] | Travelled % (*strict*) | Error vs Tip (*info*) | $L_1$ Disturbed [Gate $\le 5\%$] | $L_1$ Whole (*info*) | Runtime |
|---|---|---|---|---|---|---|---|---|---|---|
| **20 m** (200 tri) | 5.0 s | 543.33 m | 563.33 m | 20.00 m | 3.68% (*info*) | 46.15% | 16.39 m | 4.87% (*info*) | 0.72% | 0.19 s |
| **20 m** (200 tri) | 10.0 s | 590.00 m | 610.00 m | 20.00 m | 3.39% (*info*) | 22.22% | 16.12 m | 3.10% (*info*) | 0.69% | 0.19 s |
| **20 m** (200 tri) | 15.0 s | 636.67 m | 656.67 m | 20.00 m | 3.14% (*info*) | 14.63% | 15.84 m | 2.11% (*info*) | 0.73% | 0.19 s |
| **10 m** (800 tri) | 5.0 s | 545.00 m | 555.00 m | 10.00 m | 1.83% (*info*) | 22.22% | 8.06 m | 3.12% (*info*) | 0.35% | 0.24 s |
| **10 m** (800 tri) | 10.0 s | 591.67 m | 601.67 m | 10.00 m | 1.69% (*info*) | 10.91% | 7.78 m | 1.97% (*info*) | 0.41% | 0.24 s |
| **10 m** (800 tri) | 15.0 s | 638.33 m | 648.33 m | 10.00 m | 1.57% (*info*) | 7.23% | 7.51 m | 1.29% (*info*) | 0.40% | 0.24 s |
| **5 m** (3200 tri) | 5.0 s | 545.83 m | 550.83 m | 5.00 m | **0.92%** (PASS) | 10.91% | 3.89 m | **1.97%** (PASS) | 0.21% | 0.53 s |
| **5 m** (3200 tri) | 10.0 s | 592.50 m | 597.50 m | 5.00 m | **0.84%** (PASS) | 5.41% | 3.62 m | **0.99%** (PASS) | 0.20% | 0.53 s |
| **5 m** (3200 tri) | 15.0 s | 639.17 m | 644.17 m | 5.00 m | **0.78%** (PASS) | 3.59% | 3.34 m | **0.72%** (PASS) | 0.22% | 0.53 s |

**Stoker Convergence Audit:**
- $t = 5.0$ s: Shock Error $20.00 \to 10.00 \to 5.00$ m (Monotonic: True); $L_1$ $4.87\% \to 3.12\% \to 1.97\%$ (Monotonic: True); Observed Order $p = 0.66$ [**PASS**]
- $t = 10.0$ s: Shock Error $20.00 \to 10.00 \to 5.00$ m (Monotonic: True); $L_1$ $3.10\% \to 1.97\% \to 0.99\%$ (Monotonic: True); Observed Order $p = 0.99$ [**PASS**]
- $t = 15.0$ s: Shock Error $20.00 \to 10.00 \to 5.00$ m (Monotonic: True); $L_1$ $2.11\% \to 1.29\% \to 0.72\%$ (Monotonic: True); Observed Order $p = 0.84$ [**PASS**]

---

## 3. Summary of Verification Gates & Regression Guards

| Gate ID | Specification & Formula | Target Threshold | Ritter Result | Stoker Result | Overall Status |
|---|---|---|---|---|---|
| **G1-a** | Front Position Error at finest mesh ($\Delta x = 5$ m) | $\le 5.0\%$ at all 3 times | $1.71\%, 1.50\%, 0.89\%$ | $0.92\%, 0.84\%, 0.78\%$ | **PASS** |
| **G1-b** | $L_1$ Depth Error (disturbed / true disturbed) | $\le 5.0\%$ at $\Delta x = 5$ m | True: $1.75\%, 0.92\%, 0.64\%$<br>Sym: $2.24\%, 1.19\%, 0.83\%$ | $1.97\%, 0.99\%, 0.72\%$ | **PASS** |
| **G1-c** | Spatial Convergence: Error($\Delta x/2$) $\le$ Error($\Delta x$) | Monotonic reduction for front & $L_1$ | Monotonic at all times ($p \approx 0.90$) | Monotonic at all times ($p \approx 0.83$) | **PASS** |
| **G1-d** | **Regression Guard:** Front error at $\Delta x = 5$ m | $\le 3 \text{ cells}$ ($15.0\text{ m}$) at all times | Max $10.0\text{ m} \le 15.0\text{ m}$ ($2 \cdot \Delta x$) | Max $5.0\text{ m} \le 15.0\text{ m}$ ($1 \cdot \Delta x$) | **PASS** |
| **G2** | Boundary Type specification | Required argument (no default) | Verified transmissive | Verified transmissive | **PASS** |
| **G2-Flux** | Outlet outflow volume vs SWW x-momentum integral | Within $2.0\%$ | N/A (tested in channel) | Rel diff: $0.7187\% \le 2\%$ | **PASS** |
| **C4-Guard** | **Regression Guard:** `arrival_time.tif` max diff vs shock | $\le 2 \cdot \Delta t_{\text{yield}} = 1.0\text{ s}$ | N/A | $0.8584\text{ s} \le 1.0\text{ s}$ | **PASS** |

---

## 4. Deviations & Methodological Notes

1. **Departure from Contract "depth > 0.1 m" for Wet-Bed Benchmark:**
   - In wet-bed dam-break (Stoker), the downstream channel is initially flooded to $h_R = 2.0\text{ m}$. Applying the dry-bed contract arrival threshold $h > 0.1\text{ m}$ would yield $t_{\text{arrival}} = 0.0\text{ s}$ everywhere downstream.
   - Consequently, for the benchmark front tracking in `run_benchmarks.py`, the front threshold is defined as $h_R + 0.01 \cdot (h_m - h_R)$ ($1\%$ above the ambient downstream pool).
   - For the shock arrival test in `tests/test_solvers.py::test_stoker_arrival_time_shock_speed`, the arrival threshold is defined as $h_R + 0.20 \cdot (h_m - h_R)$ ($20\%$ above downstream pool), which filters out minor numerical pre-shock acoustic waves and accurately isolates the shock front arrival.
   - The adapter's default arrival threshold for real terrain / dry-bed simulations remains strictly $0.1\text{ m}$; any overridden threshold is written into `run_meta.json`.

---

## 5. Artifact Deliverables

- **Benchmark Results JSON:** `demo_data/benchmarks/ritter_stoker_results.json`
- **Validation Comparison Figure:** `docs/SLIDE_FIGURES/benchmark_ritter_stoker.png` and `demo_data/benchmarks/ritter_stoker_comparison.png`


