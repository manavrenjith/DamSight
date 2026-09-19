# AGENTS.md — Guidelines for Coding Agents (DamSight v2)

## 1. Specification & Section References (v2)
All milestone and section references in code, commits, and plans strictly follow `docs/SPEC.md` v2:
- **Ground Rules:** Section 0
- **PS Requirements:** Section 1
- **Demo Story:** Section 2
- **Scope Tiers:** Section 3
- **Decisions & Open Items:** Section 4 (D1–D7, O1–O2)
- **Demo Sites:** Section 5 (Site A: Machhu chain, Site B: Chamoli, Site C: Periyar)
- **Config Schema:** Section 6 (`configs/sites/<site_id>.yaml`)
- **Modules (Section 7):**
  - Data Ingestion: Section 7.2
  - Breach Model: Section 7.3
  - Solver Adapters: Section 7.4
  - Ensemble & Uncertainty: Section 7.5
  - ML Surrogate: Section 7.6
  - Cascade Module: Section 7.7
  - Evacuation Feasibility: Section 7.8
  - Satellite Watch: Section 7.9
  - Validation: Section 7.10
  - Export Engine: Section 7.11
  - API Backend: Section 7.12
  - Dashboard Frontend: Section 7.13
- **Data Contracts:** Section 8 (`demo_data/<site_id>/`)
- **Milestones:** Section 9 (M0 through M15)
- **Hardening & Deployment:** Section 10
- **Fallbacks:** Section 11 (`BLOCKERS.md`)

---

## 2. Testing Discipline & Rules
1. **Argument Swap Sensitivity:** Every test must include a case that would fail if two same-typed arguments were swapped (e.g., breach height $h_b$ vs. water depth $h_w$ in empirical breach functions).
2. **Never Weaken a Test:** Do not loosen assertion tolerances or delete assertions to make failing tests pass.
3. **Pre-Set Thresholds:** Test thresholds (e.g., convergence tolerances, error bounds) are set *before* running and must not be loosened afterwards without an explicit rationale entered into `ASSUMPTIONS.md`.
4. **Offline Purity:** Tests must run in seconds using tiny synthetic fixtures without internet access.

---

## 3. Ground Rules & Hygiene
1. **Never Invent Physical Numbers:** Use `TODO_VERIFY` until officially sourced and verified.
2. **Labeling:** Label all synthetic, approximate, defaulted, or unverified outputs with `data_status`.
3. **Secrets Hygiene:** Never hard-code or commit credentials, private keys, service accounts, or cloud project identifiers. Read from environment variables (`.env`).
4. **Log Everything:** Assumptions in `ASSUMPTIONS.md`, blockers and fallbacks in `BLOCKERS.md`.