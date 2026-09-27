"""Utility to fetch real OSM data from Overpass API for site bounding box."""

import json
import logging
import time
import urllib.parse
import urllib.request
from pathlib import Path
import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("fetch_osm")

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]

def query_overpass(query: str, timeout_sec: int = 45) -> dict:
    encoded = query.strip().encode("utf-8")
    last_err = None
    for url in OVERPASS_URLS:
        try:
            logger.info(f"Querying Overpass endpoint: {url}...")
            req = urllib.request.Request(
                url,
                data=encoded,
                headers={"User-Agent": "DamSight-OSM-Fetcher/1.0 (dam-safety-research)"}
            )
            with urllib.request.urlopen(req, timeout=timeout_sec + 10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                logger.info(f"Received {len(data.get('elements', []))} elements from {url}")
                return data
        except Exception as e:
            logger.warning(f"Failed to query {url}: {e}")
            last_err = e
            time.sleep(2)
    raise RuntimeError(f"All Overpass endpoints failed: {last_err}")


def fetch_osm_for_bbox(min_lat: float, min_lon: float, max_lat: float, max_lon: float, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    bbox_str = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    logger.info(f"Fetching OSM data for bbox: {bbox_str}")

    # 1. Places
    places_out = out_dir / "raw_places.geojson"
    if not places_out.exists() or places_out.stat().st_size < 1000:
        places_query = f"""
        [out:json][timeout:60];
        node["place"~"city|town|village|hamlet|suburb"]({bbox_str});
        out body;
        """
        places_data = query_overpass(places_query)
        place_records = []
        for el in places_data.get("elements", []):
            tags = el.get("tags", {})
            place_records.append({
                "id": el.get("id"),
                "name": tags.get("name", tags.get("name:en", "Unnamed")),
                "type": tags.get("place", "place"),
                "geometry": Point(el["lon"], el["lat"])
            })
        places_gdf = gpd.GeoDataFrame(place_records, geometry="geometry", crs="EPSG:4326")
        places_gdf.to_file(places_out, driver="GeoJSON")
        logger.info(f"Saved {len(places_gdf)} places to {places_out}")
    else:
        places_gdf = gpd.read_file(places_out)
        logger.info(f"Loaded existing {len(places_gdf)} places from {places_out}")

    # 2. Roads
    roads_out = out_dir / "raw_roads.geojson"
    roads_query = f"""
    [out:json][timeout:60];
    way["highway"~"motorway|trunk|primary|secondary|tertiary|unclassified|residential"]({bbox_str});
    out geom 5000;
    """
    roads_data = query_overpass(roads_query)
    road_records = []
    for el in roads_data.get("elements", []):
        tags = el.get("tags", {})
        coords = [(pt["lon"], pt["lat"]) for pt in el.get("geometry", [])]
        if len(coords) >= 2:
            road_records.append({
                "id": el.get("id"),
                "name": tags.get("name", tags.get("name:en", "Unnamed Road")),
                "type": tags.get("highway", "road"),
                "geometry": LineString(coords)
            })
    roads_gdf = gpd.GeoDataFrame(road_records, geometry="geometry", crs="EPSG:4326")
    roads_out = out_dir / "raw_roads.geojson"
    roads_gdf.to_file(roads_out, driver="GeoJSON")
    logger.info(f"Saved {len(roads_gdf)} roads to {roads_out}")

    # 3. Buildings
    buildings_query = f"""
    [out:json][timeout:120];
    (
      way["building"]({bbox_str});
    );
    out geom 5000;
    """
    buildings_data = query_overpass(buildings_query)
    b_records = []
    for el in buildings_data.get("elements", []):
        tags = el.get("tags", {})
        geom_pts = el.get("geometry", [])
        if len(geom_pts) >= 3:
            coords = [(pt["lon"], pt["lat"]) for pt in geom_pts]
            # Ensure closed polygon
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            b_records.append({
                "id": el.get("id"),
                "name": tags.get("name", tags.get("name:en", "Building")),
                "type": tags.get("building", "yes"),
                "geometry": Polygon(coords)
            })
    buildings_gdf = gpd.GeoDataFrame(b_records, geometry="geometry", crs="EPSG:4326")
    buildings_out = out_dir / "raw_buildings.geojson"
    buildings_gdf.to_file(buildings_out, driver="GeoJSON")
    logger.info(f"Saved {len(buildings_gdf)} buildings to {buildings_out}")

    return len(places_gdf), len(roads_gdf), len(buildings_gdf)

if __name__ == "__main__":
    import sys
    out_dir = Path("cache/site_a/raw")
    # WGS84 bbox for Morbi AOI: [22.6801, 70.6899, 22.9095, 70.9363]
    fetch_osm_for_bbox(22.6801, 70.6899, 22.9095, 70.9363, out_dir)
