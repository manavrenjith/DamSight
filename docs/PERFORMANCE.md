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

### Benchmark Setup:
- **Geometry:** 1D Rectangular Frictionless Channel ($L = 1000$ m, $W = 20$ m)
- **Dam Location:** $x_0 = 500.0$ m
- **Bed:** Flat horizontal bed ($z = 0$ m), frictionless ($n = 0.0\text{ s/m}^{1/3}$)
- **Resolutions:** Coarse ($\Delta x = 20$ m) and Fine ($\Delta x = 10$ m)
- **Evaluation Timestamps:** $t \in [5.0\text{ s}, 10.0\text{ s}, 15.0\text{ s}]$

---

### Benchmark 1: Ritter (1892) Dry Bed Dam-Break ($h_L = 10.0\text{ m}, h_R = 0.0\text{ m}$)

| Resolution ($\Delta x$) | Time ($t$) | Exact Front ($x_{\text{exact}}$) | Sim Front ($x_{\text{sim}}$) | Front Error ($|x_{\text{sim}} - x_{\text{exact}}|$) | $L_1$ Depth Error | Mass Balance Error | Run Time |
|---|---|---|---|---|---|---|---|
| **20 m** (coarse) | 5.0 s | 599.03 m | 570.00 m | 29.03 m | 0.0923 m | $1.44 \times 10^{-16}$ | 0.18 s |
| **20 m** (coarse) | 10.0 s | 698.06 m | 636.67 m | 61.39 m | 0.1004 m | $1.44 \times 10^{-16}$ | 0.18 s |
| **20 m** (coarse) | 15.0 s | 797.09 m | 716.67 m | 80.42 m | 0.1041 m | $1.44 \times 10^{-16}$ | 0.18 s |
| **10 m** (fine) | 5.0 s | 599.03 m | 568.33 m | 30.70 m | 0.0502 m | $1.45 \times 10^{-16}$ | 0.24 s |
| **10 m** (fine) | 10.0 s | 698.06 m | 651.67 m | 46.39 m | 0.0539 m | $1.45 \times 10^{-16}$ | 0.24 s |
| **10 m** (fine) | 15.0 s | 797.09 m | 738.33 m | 58.75 m | 0.0563 m | $1.45 \times 10^{-16}$ | 0.24 s |

*Observations:*
- Refining the mesh from $\Delta x = 20$ m to $10$ m cuts the $L_1$ depth profile error almost exactly in half (from $\sim 0.100$ m to $\sim 0.054$ m), demonstrating first-order spatial convergence $O(\Delta x)$.
- Front tip diffusion is characteristic of dry-bed Godunov schemes where wetting drying thresholds truncate the infinitesimal analytical tip.
- Volumetric mass balance is conserved to machine precision ($\approx 1.4 \times 10^{-16}$).

---

### Benchmark 2: Stoker (1957) Wet Bed Dam-Break ($h_L = 10.0\text{ m}, h_R = 2.0\text{ m}$)

| Resolution ($\Delta x$) | Time ($t$) | Exact Shock ($x_{\text{exact}}$) | Sim Shock ($x_{\text{sim}}$) | Shock Error ($|x_{\text{sim}} - x_{\text{exact}}|$) | $L_1$ Depth Error | Mass Balance Error | Run Time |
|---|---|---|---|---|---|---|---|
| **20 m** (coarse) | 5.0 s | 546.94 m | 556.67 m | 9.73 m | 0.0724 m | $1.20 \times 10^{-16}$ | 0.18 s |
| **20 m** (coarse) | 10.0 s | 593.88 m | 603.33 m | 9.45 m | 0.0685 m | $1.20 \times 10^{-16}$ | 0.18 s |
| **20 m** (coarse) | 15.0 s | 640.82 m | 650.00 m | 9.18 m | 0.0726 m | $1.20 \times 10^{-16}$ | 0.18 s |
| **10 m** (fine) | 5.0 s | 546.94 m | 551.67 m | 4.73 m | 0.0345 m | $2.41 \times 10^{-16}$ | 0.24 s |
| **10 m** (fine) | 10.0 s | 593.88 m | 598.33 m | 4.45 m | 0.0411 m | $2.41 \times 10^{-16}$ | 0.24 s |
| **10 m** (fine) | 15.0 s | 640.82 m | 645.00 m | 4.18 m | 0.0400 m | $2.41 \times 10^{-16}$ | 0.24 s |

*Observations:*
- In the wet-bed shock bore, the shock position error scales directly with cell size ($\Delta x / 2$): $\approx 9.5$ m at $\Delta x = 20$ m and $\approx 4.5$ m at $\Delta x = 10$ m.
- $L_1$ depth error drops from $\sim 0.071$ m to $\sim 0.038$ m, confirming monotonic grid convergence.
- Intermediate plateau depth ($h_m = 5.079$ m) and velocity ($u_m = 5.691$ m/s) match analytical Rankine-Hugoniot predictions across the bore.

---

## 3. Artifact Deliverables

- **Benchmark Results JSON:** `demo_data/benchmarks/ritter_stoker_results.json`
- **Validation Comparison Figure:** `docs/SLIDE_FIGURES/benchmark_ritter_stoker.png` and `demo_data/benchmarks/ritter_stoker_comparison.png`
