# DamSight Decisions & Open Items

**Reference:** `docs/SPEC.md` v2, Section 4

---

## 1. Frozen Decisions (Section 4.1)

| # | Topic | Decision | Notes |
|---|---|---|---|
| **D1** | Main demo site | Machhu-I / Machhu-II chain on the Machhu river, Morbi region, Gujarat. | Section 5 |
| **D2** | Cascade case | Real dam chain. A1 is a hindcast of the 1979 Machhu-II overtopping failure. A2 is a hypothetical upstream release or failure, labelled HYPOTHETICAL. | Ground Rule 7 |
| **D3** | Validation | Historical record for Site A (1979 event); Sentinel-1 for satellite-era events (Site C, Kerala 2018). | Section 7.10 |
| **D4** | Data honesty | All Machhu figures stay `verified: false` until reconciled. Public sources disagree. | Ground Rule 3 |
| **D5** | Earth Engine | Available. Non-commercial registration, Community quota tier (150 EECU-hours). Live detection enabled, cached fallback retained. | Section 7.9 |
| **D6** | Delft3D FM & Solver Baseline | Delft3D FM is DROPPED for the MVP demo (2026-09-27), given O1 hardware constraints (4 cores/8 threads, 7.6GB RAM, no CUDA GPU). ANUGA is the sole solver for Site A. Revisit only if hardware changes or Delft3D is confirmed to run on other infrastructure before the MVP freeze. | Section 7.4 |
| **D7** | Differentiators | Probabilistic maps, ML surrogate, evacuation feasibility, cascade failure, satellite-triggered natural-dam watch. | Section 1 |

---

## 2. Open Items (Section 4.2)

The following items are currently **OPEN** pending user confirmation. Defaults from `docs/SPEC.md` are documented below:

### Open Item O1: Target Execution Hardware
- **Status:** **RESOLVED**, with two fields pending benchmark (2026-09-23)
- **Answer (measured, not assumed):**
  - CPU: 11th Gen Intel Core i5-1135G7 @ 2.40GHz, 4 physical cores / 8 threads
  - RAM: 7.6 GB (as reported by Windows)
  - GPU: none for compute. Intel Iris Xe integrated graphics only, no dedicated VRAM (shares system RAM). No NVIDIA/CUDA.
  - Free disk on D:: ~100 GB free of ~201 GB (measured 2026-09-23 via Get-Volume)
  - OS: Windows 11 Home
- **Measured via:** PowerShell Get-CimInstance / Get-Volume queries, 2026-09-23
- **Deviation from SPEC default (CPU-only, 8 cores, 16 GB):** YES. Half the cores, about half the RAM.
- **Consequences:**
  - Ensemble size (M8): **PENDING BENCHMARK.** Do not assume 100. Time one real Site A run at the chosen mesh, then set N = time budget / per-run time.
  - Mesh resolution ceiling: **PENDING BENCHMARK.** Memory is the binding limit. Set from measured wall time and peak RAM.
  - SPH near-field (M13): **DROPPED** (no CUDA GPU, 8 GB RAM).
  - ML surrogate: CPU-only training; keep models small.
  - Delft3D FM: decide after licence review. Likely to run elsewhere (heaviest RAM user). If run locally, it shares the disk budget below.
  - Disk budget: cap `outputs/` at 20 GB; keep only summary rasters (max depth, arrival, percentiles) for ensemble members, not per-timestep frames; keep at least 20 GB free.
  - Workflow: close heavy apps during runs; use `-m "not slow"` for routine test runs.

---

### Open Item O2: Reference Dataset for 1979 Inundation Validation
- **Status:** **RESOLVED (2026-09-27): no georeferenced 1979 inundation extent found via search. Qualitative checkpoints only, both verified: false:**
  - **Checkpoint 1 (Depth):** reported flood depth at Morbi 3.7-9.1 m (12-30 ft)  
    *source:* "Wikipedia, '1979 Machchhu dam failure'" (`verified: false`).  
    *M3b Simulated Outcome (120m):* Simulated depth in Machhu channel reach at Morbi is 7.7-10.5 m (thalweg 9.93 m, reach average 5.11 m), which closely encompasses the 3.7-9.1 m inquiry range. **CONSISTENT**.
  - **Checkpoint 2 (Arrival Time & Distance):** floodwater reached Morbi industrial area (~5 km below dam) within approximately 20 minutes of dam collapse, around 3:30 PM on 11 Aug 1979  
    *source:* "Wikipedia, '1979 Machchhu dam failure'" (`verified: false`). Note: morbionline.in cites ~9 km upstream distance from dam to Morbi historic city center; these describe two distinct points (nearer southern industrial outskirts at ~5 km vs. central urban core at ~9 km along the river channel).  
    *M3b Simulated Outcome (120m):*
      - At 5 km point (industrial outskirts `[689371, 2522880]`): Simulated arrival is **76.7 minutes** post breach-start (wave transit time from dam toe is **52.2 minutes**).
      - At 9 km point (Morbi city center `[689161, 2524709]`): Simulated arrival is **101.5 minutes** post breach-start (wave transit time from dam toe is **77.1 minutes**).
    *Discrepancy Assessment:* A genuine discrepancy remains between the simulated 76.7 min (or 52.2 min transit) and the historical ~20-minute account at 5 km. This is primarily attributed to: (a) simulation timing starting at overtopping inception ($t=0$, where Froehlich breach formation ramps up gradually over 2.5 hours) versus historical accounts timing from the sudden catastrophic flank collapse; and (b) 120m mesh resolution averaging narrow channel geometry and increasing early channel storage dampening.
- **Consequence:** Validation is a qualitative sanity check only, against documented checkpoints (reported flood depths, arrival timing at Morbi). No IoU/F1 is computed or displayed. The validation panel carries the label "Qualitative check, no reference extent". Sourced citations must not be softened or combined into unverified ranges.