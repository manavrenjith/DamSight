"""Data ingestion and preprocessing module (DEM, land cover, exposure)."""

from damsight.data.dem import (
    TerrainChangeLog,
    TerrainConditioningResult,
    condition_and_save_dem,
    fill_depressions_priority_flood,
)
from damsight.data.exposure import ingest_population, ingest_vector_exposure
from damsight.data.ingest import MissingDatasetError, generate_synthetic_raw_data, run_ingestion
from damsight.data.landcover import generate_landcover_and_manning, load_manning_lookup

__all__ = [
    "MissingDatasetError",
    "TerrainChangeLog",
    "TerrainConditioningResult",
    "condition_and_save_dem",
    "fill_depressions_priority_flood",
    "generate_landcover_and_manning",
    "generate_synthetic_raw_data",
    "ingest_population",
    "ingest_vector_exposure",
    "load_manning_lookup",
    "run_ingestion",
]
