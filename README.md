# DamSight

> **Dam Break Inundation Modelling & Decision Support System**  
> Smart India Hackathon 2026 | Problem Statement #161 (NTRO)

DamSight is an end-to-end hydrodynamic simulation, risk exposure mapping, and emergency evacuation planning platform for dam failure scenarios.

---

## Key Features

- **Automated Ingestion:** Terrain (Copernicus 30m / SRTM DEM), land cover (ESA WorldCover), population (WorldPop), and infrastructure (OpenStreetMap).
- **Physical Breach Hydrograph:** Froehlich (1995/2008) empirical breach parameters coupled with stage-storage level pool reservoir routing.
- **2D Hydrodynamic Modeling:** Standardized solver abstraction with ANUGA shallow water solver, plus Delft3D FM / PySPH near-field adapters.
- **Probabilistic Ensemble:** Latin Hypercube sampling over geotechnical uncertainties producing spatial flood probabilities ($P_{\text{flood}}$) and arrival-time percentiles ($P_{10}$, $P_{50}$).
- **Instant ML Surrogate:** Sub-second what-if exploration via spatial PCA and gradient boosting regression with out-of-distribution parameter guards.
- **Dynamic Evacuation Feasibility:** Time-dependent road closure routing identifying cut-off points and classifying settlements (`can_evacuate`, `tight`, `trapped`).
- **Satellite Lake Watch:** Optical and SAR satellite monitoring (Sentinel-1 / Sentinel-2) for high-altitude glacial and natural blockage breach risks.
- **GIS Export & Reporting:** Direct export to Shapefile (`.shp`), Keyhole Markup (`.kml`), and GeoTIFF formats.

---

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd Dam

# Set up environment using Conda
conda env create -f environment.yml
conda activate damsight

# Or install editable package via pip
pip install -e .
```

### Running Tests

```bash
pytest tests/
# or
make test
```

### Launching the Demo

```bash
make demo
```

---

## Documentation

- [`docs/SPEC.md`](docs/SPEC.md) - Full project build specification.
- [`docs/PLAN.md`](docs/PLAN.md) - Engineering plan, milestone definitions, and risk analysis.
- [`ASSUMPTIONS.md`](ASSUMPTIONS.md) - Registry of all assumptions, parameters, and unverified data sources.
- [`BLOCKERS.md`](BLOCKERS.md) - Registry of blockers encountered and applied fallbacks.
