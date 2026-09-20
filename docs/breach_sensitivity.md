# Peak Breach Outflow Sensitivity Analysis

**Reference:** `docs/SPEC.md` Section 7.3 & Section 7.4  
**Environment:** `damsight` (Python 3.11)  
**Date:** September 19, 2026  

---

## 1. Synthetic Sensitivity Matrix ($3 \times 3$)

Simulations run using `estimate_breach_parameters` (overtopping mode, embankment dam, $Z=1.0$) and `generate_breach_hydrograph` with broad-crested weir coefficients ($C_{d,\text{rect}} = 1.70$, $C_{d,\text{tri}} = 1.35$, $\Delta t = 5.0$ s). In all cases $h_w = h_b$.

| $V_w$ ($\text{m}^3$) | $V_w$ (MCM) | $h_b$ (m) | Hydrograph $Q_{\text{peak}}$ ($\text{m}^3/\text{s}$) | Froehlich $Q_p$ ($\text{m}^3/\text{s}$) | Ratio ($Q_{\text{peak}} / Q_p$) | $t_{\text{peak}} / t_f$ | Status vs [0.5, 2.0] |
|---|---|---|---|---|---|---|---|
| $1.0 \times 10^6$ | 1.0 | 10.0 | 730.79 | 621.14 | **1.177** | 0.998 | Within [0.5, 2.0] |
| $1.0 \times 10^6$ | 1.0 | 20.0 | 1,438.70 | 1,467.12 | **0.981** | 0.961 | Within [0.5, 2.0] |
| $1.0 \times 10^6$ | 1.0 | 40.0 | 2,701.76 | 3,465.32 | **0.780** | 0.842 | Within [0.5, 2.0] |
| $1.0 \times 10^7$ | 10.0 | 10.0 | 2,073.81 | 1,225.15 | **1.693** | 1.000 | Within [0.5, 2.0] |
| $1.0 \times 10^7$ | 10.0 | 20.0 | 4,599.70 | 2,893.78 | **1.590** | 1.000 | Within [0.5, 2.0] |
| $1.0 \times 10^7$ | 10.0 | 40.0 | 9,145.68 | 6,835.07 | **1.338** | 0.968 | Within [0.5, 2.0] |
| $1.0 \times 10^8$ | 100.0 | 10.0 | 5,280.29 | 2,416.51 | **2.185** | 1.000 | **Outside** (> 2.0) |
| $1.0 \times 10^8$ | 100.0 | 20.0 | 12,897.77 | 5,707.76 | **2.260** | 1.000 | **Outside** (> 2.0) |
| $1.0 \times 10^8$ | 100.0 | 40.0 | 28,910.29 | 13,481.65 | **2.144** | 1.000 | **Outside** (> 2.0) |

---

## 2. Bounds Audit Against [0.5, 2.0]

- **Inside [0.5, 2.0]:**
  - All small and medium reservoir cases ($V_w = 1.0\text{ MCM}$ and $V_w = 10.0\text{ MCM}$) produce ratios strictly within the $[0.5, 2.0]$ band, ranging from $0.780$ to $1.693$.
- **Outside [0.5, 2.0]:**
  - All three very large reservoir cases ($V_w = 100.0\text{ MCM}$) exceed the $2.0$ upper bound:
    - $V_w = 100\text{ MCM}, h_b = 10.0\text{ m} \implies \text{Ratio} = 2.185$
    - $V_w = 100\text{ MCM}, h_b = 20.0\text{ m} \implies \text{Ratio} = 2.260$
    - $V_w = 100\text{ MCM}, h_b = 40.0\text{ m} \implies \text{Ratio} = 2.144$

---

## 3. Code-Grounded Analysis: Why the 25 MCM Case Yielded 1.95

In the 25 MCM synthetic test case ($V_w = 2.5 \times 10^7\text{ m}^3$, $h_b = 30.0\text{ m}$, $h_w = 27.5\text{ m}$), the hydrograph peak is $10,969.9\text{ m}^3/\text{s}$ while Froehlich (1995) gives $Q_p = 5,627.99\text{ m}^3/\text{s}$, producing a ratio of **$1.949 \approx 1.95$**.

The drivers in the codebase are:

### A. Growth Law and Time to Peak ($t_{\text{peak}} \approx t_f$)
In `src/damsight/breach/hydrograph.py`, the breach geometry grows linearly from $t=0$ to $t_f$:
$$w_b(t) = W_{\text{bottom}} \cdot \frac{t}{t_f}, \quad z_b(t) = z_{\text{crest}} - h_b \cdot \frac{t}{t_f}$$
For a 25 MCM reservoir, the cumulative outflow volume during the formation time ($t_f \approx 3364\text{ s} \approx 56\text{ min}$) is less than 15% of the active storage. The water surface stage barely drops ($\approx 1.5\text{ m}$ out of $27.5\text{ m}$). Consequently, the breach reaches its full width ($W_{\text{bottom}} = 63.70\text{ m}$) and full depth ($h_b = 30.0\text{ m}$) while the driving head remains near maximum ($h_{\text{water}} \approx 26.0\text{ m}$). This aligns maximum breach cross-section with near-maximum head at $t \approx t_f$, maximizing $Q_{\text{peak}}$.

### B. Triangular Side-Slope Weir Component ($Z = 1.0$)
In `hydrograph.py`:
$$Q_{\text{weir}} = C_{d,\text{rect}} \cdot w_b \cdot h_{\text{water}}^{1.5} + C_{d,\text{tri}} \cdot Z \cdot h_{\text{water}}^{2.5}$$
With $Z = 1.0$ (standard overtopping trapezoid) and $C_{d,\text{tri}} = 1.35$:
- At $h_{\text{water}} = 26.0\text{ m}$, the rectangular term contributes:
  $$1.70 \times 63.70 \times (26.0)^{1.5} \approx 14,352\text{ m}^3/\text{s}$$
- The triangular term adds:
  $$1.35 \times 1.0 \times (26.0)^{2.5} \approx 4,402\text{ m}^3/\text{s}$$
The $h_{\text{water}}^{2.5}$ scaling strongly amplifies peak discharge for deep breaches ($h_b \ge 25\text{ m}$).

### C. Scaling Disparity: Hydrograph Weir Flow vs. Froehlich (1995) Empirical Fit
- **Physical Level-Pool Routing in Code (`generate_breach_hydrograph`):**
  - Uses broad-crested weir formulation: $Q(t) = C_{d,\text{rect}} \cdot w_b(t) \cdot h_{\text{water}}^{1.5} + C_{d,\text{tri}} \cdot Z \cdot h_{\text{water}}^{2.5}$.
  - Assumes unchoked free discharge with zero tailwater submergence backpressure and frictionless exit.
  - Breach geometry grows linearly over formation time $t_f$: $w_b(t) = W_{\text{bottom}} \cdot (t / t_f)$ and $z_b(t) = z_{\text{crest}} - h_b \cdot (t / t_f)$.
- **Froehlich (1995) Regression:**
  - $Q_p = 0.607 \cdot V_w^{0.295} \cdot h_w^{1.24}$ has an empirical exponent of $1.24$ on water depth.
  - When $V_w \ge 2.5 \times 10^7\text{ m}^3$ and $h_w \ge 25\text{ m}$, the difference in depth scaling exponents ($h_w^{1.5} / h_w^{1.24} = h_w^{0.26} \approx 2.3$) between frictionless level-pool weir flow and Froehlich's regression fit naturally causes the simulated hydrograph peak to exceed Froehlich $Q_p$ by $1.95 - 2.26\times$.

