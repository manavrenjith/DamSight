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
| **D6** | Delft3D FM | Proceed. Time-boxed setup (M4), benchmark first; ANUGA remains guaranteed baseline solver. | Section 7.4 |
| **D7** | Differentiators | Probabilistic maps, ML surrogate, evacuation feasibility, cascade failure, satellite-triggered natural-dam watch. | Section 1 |

---

## 2. Open Items (Section 4.2)

The following items are currently **OPEN** pending user confirmation. Defaults from `docs/SPEC.md` are documented below:

### Open Item O1: Target Execution Hardware
- **Status:** **OPEN**
- **Question:** What hardware is available (CPU cores, RAM, NVIDIA GPU)?
- **Default if unanswered:** Assume CPU-only, 8 cores, 16 GB RAM. Ensemble limited to 100 members on a coarse mesh. SPH restricted to a tiny benchmark.
- **Affected Pipeline Stages:** Ensemble size (M8), SPH near-field scope (M13), mesh resolution.

---

### Open Item O2: Reference Dataset for 1979 Inundation Validation
- **Status:** **OPEN**
- **Question:** What is the authoritative source for the 1979 Machhu-II inundation reference extent (published study, GIS polygon, or historical survey map)?
- **Default if unanswered:** Do not invent an extent. Validate against documented qualitative checkpoints (reported maximum flood depths and arrival timing at Morbi) and label it a qualitative sanity check, not an empirical F1/IoU score.
- **Affected Pipeline Stages:** Validation panel (M6).
