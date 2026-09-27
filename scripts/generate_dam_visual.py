import rasterio
import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from pathlib import Path

# Load data
with rasterio.open("cache/site_a/dem.tif") as src:
    dem = src.read(1)
    transform = src.transform
    inv_t = ~transform
    bounds = src.bounds
    res = src.res

with rasterio.open("cache/site_a/landcover.tif") as lc_src:
    lc = lc_src.read(1)
    water_mask = (lc == 80)

places = gpd.read_file("cache/site_a/places.geojson")
roads = gpd.read_file("cache/site_a/roads.geojson")

morbi_x, morbi_y = 688605.56, 2524469.49

# Dam coordinates:
dam_crossing_x = 691350.0
dam_crossing_y = 2518500.0
c_cross, r_cross = inv_t * (dam_crossing_x, dam_crossing_y)
c_cross, r_cross = int(c_cross), int(r_cross)
elev_channel = dem[r_cross, c_cross]

# Crest pixel on west embankment shoulder adjacent to breach/channel:
crest_x = 691270.0
crest_y = 2518200.0
c_crest, r_crest = inv_t * (crest_x, crest_y)
c_crest, r_crest = int(c_crest), int(r_crest)
elev_crest = dem[r_crest, c_crest]

print(f"Dam river channel crossing: ({dam_crossing_x:.1f}, {dam_crossing_y:.1f}) | Pixel [row={r_cross}, col={c_cross}] | Elev={elev_channel:.2f}m")
print(f"Embankment crest shoulder: ({crest_x:.1f}, {crest_y:.1f}) | Pixel [row={r_crest}, col={c_crest}] | Elev={elev_crest:.2f}m")

# West abutment to East abutment:
west_abutment = (689800.0, 2516680.0)
east_abutment = (693300.0, 2518960.0)

# Create figure with 2 panels: Map Overview & Dam Detail with Elevation Profile
fig = plt.figure(figsize=(16, 9), dpi=200)
gs = fig.add_gridspec(2, 2, width_ratios=[1.2, 1.0], height_ratios=[1.0, 1.0])

ax_map = fig.add_subplot(gs[:, 0])
ax_zoom = fig.add_subplot(gs[0, 1])
ax_prof = fig.add_subplot(gs[1, 1])

# 1. Full AOI hillshade on ax_map
ls = LightSource(azdeg=315, altdeg=45)
hs_full = ls.hillshade(dem, vert_exag=4, dx=30.0, dy=30.0)

ax_map.imshow(hs_full, cmap="gray", extent=[bounds.left, bounds.right, bounds.bottom, bounds.top], origin="upper")
water_rgba = np.zeros((*water_mask.shape, 4))
water_rgba[water_mask] = [0.0, 0.45, 0.9, 0.55]
ax_map.imshow(water_rgba, extent=[bounds.left, bounds.right, bounds.bottom, bounds.top], origin="upper")

# Overlay roads
roads.plot(ax=ax_map, color="tan", linewidth=0.5, alpha=0.6)

# Markers on full map
ax_map.plot(morbi_x, morbi_y, "r*", markersize=14, label="Morbi City Center (Anchor)")
ax_map.text(morbi_x + 300, morbi_y, "Morbi", color="red", fontweight="bold", fontsize=10)

ax_map.plot(dam_crossing_x, dam_crossing_y, "mo", markersize=10, label="Identified Machhu-II Dam")
ax_map.text(dam_crossing_x - 3200, dam_crossing_y - 800, "Machhu-II Dam", color="magenta", fontweight="bold", fontsize=10)

# Draw line from Dam to Morbi with distance label
ax_map.plot([dam_crossing_x, morbi_x], [dam_crossing_y, morbi_y], "r--", linewidth=1.5, alpha=0.8)
dist_straight = np.sqrt((dam_crossing_x - morbi_x)**2 + (dam_crossing_y - morbi_y)**2) / 1000.0
ax_map.text((dam_crossing_x + morbi_x)/2 + 200, (dam_crossing_y + morbi_y)/2, f"6.6 km straight\n~9 km channel", color="red", fontsize=9, fontweight="bold")

# Box showing zoom area
zoom_extent = [688500.0, 694000.0, 2515500.0, 2520500.0]
rect_x = [zoom_extent[0], zoom_extent[1], zoom_extent[1], zoom_extent[0], zoom_extent[0]]
rect_y = [zoom_extent[2], zoom_extent[2], zoom_extent[3], zoom_extent[3], zoom_extent[2]]
ax_map.plot(rect_x, rect_y, "c-", linewidth=2.0, label="Dam Area Zoom")

ax_map.set_title("Site A DEM Overview (Morbi Reach & Machhu River)", fontsize=12, fontweight="bold")
ax_map.set_xlabel("UTM Easting (m)")
ax_map.set_ylabel("UTM Northing (m)")
ax_map.legend(loc="lower right", fontsize=8)
ax_map.grid(True, linestyle=":", alpha=0.4)

# 2. Zoomed-in Dam Hillshade on ax_zoom
c_z1, r_z1 = inv_t * (zoom_extent[0], zoom_extent[3])
c_z2, r_z2 = inv_t * (zoom_extent[1], zoom_extent[2])
cz_min, cz_max = int(min(c_z1, c_z2)), int(max(c_z1, c_z2))
rz_min, rz_max = int(min(r_z1, r_z2)), int(max(r_z1, r_z2))

sub_dem = dem[rz_min:rz_max, cz_min:cz_max]
sub_water = water_mask[rz_min:rz_max, cz_min:cz_max]
sub_hs = ls.hillshade(sub_dem, vert_exag=3.5, dx=30.0, dy=30.0)

ax_zoom.imshow(sub_hs, cmap="gray", extent=zoom_extent, origin="upper")
sub_water_rgba = np.zeros((*sub_water.shape, 4))
sub_water_rgba[sub_water] = [0.0, 0.45, 0.9, 0.6]
ax_zoom.imshow(sub_water_rgba, extent=zoom_extent, origin="upper")

# Contours on zoom
cs = ax_zoom.contour(sub_dem, levels=np.arange(38, 70, 2), extent=zoom_extent, origin="upper",
                     colors="orange", linewidths=0.6, alpha=0.8)
ax_zoom.clabel(cs, inline=True, fontsize=6, fmt="%.0fm")

# Draw full embankment crest line
ax_zoom.plot([west_abutment[0], 691300.0], [west_abutment[1], 2518240.0], "y-", linewidth=3.0, label="West Embankment (~2.27 km)")
ax_zoom.plot([691800.0, east_abutment[0]], [2518840.0, east_abutment[1]], "y-", linewidth=3.0, label="East Embankment (~1.51 km)")
ax_zoom.plot(dam_crossing_x, dam_crossing_y, "mo", markersize=10, label="Channel Crossing (Breach/Spillway)")
ax_zoom.plot(crest_x, crest_y, "r^", markersize=9, label=f"Crest Shoulder (Elev={elev_crest:.1f}m)")

ax_zoom.text(dam_crossing_x + 100, dam_crossing_y + 150, "Crossing\n(691350, 2518500)", color="magenta", fontweight="bold", fontsize=8)
ax_zoom.text(crest_x - 1200, crest_y - 200, f"Crest ~{elev_crest:.1f}m", color="red", fontweight="bold", fontsize=8)

ax_zoom.set_title("Identified Machhu-II Embankment & Spillway Alignment", fontsize=11, fontweight="bold")
ax_zoom.set_xlabel("UTM Easting (m)")
ax_zoom.set_ylabel("UTM Northing (m)")
ax_zoom.legend(loc="upper left", fontsize=7)
ax_zoom.grid(True, linestyle=":", alpha=0.4)

# 3. Elevation Profile across the Embankment on ax_prof
# Profile 1: Along the river channel (South to North from reservoir pool across dam to downstream toe)
y_prof = np.arange(2517000.0, 2520000.0, 15.0)
prof_river = []
for y in y_prof:
    c, r = inv_t * (dam_crossing_x, y)
    prof_river.append(dem[int(r), int(c)])

# Profile 2: Along the embankment crest axis (West to East)
x_prof = np.arange(689500.0, 693500.0, 20.0)
# interpolate Y along the crest line:
# from (689800, 2516680) to (693300, 2518960)
y_interp = 2516680.0 + (x_prof - 689800.0) * (2518960.0 - 2516680.0) / (693300.0 - 689800.0)
prof_crest = []
for x, y in zip(x_prof, y_interp):
    c, r = inv_t * (x, y)
    prof_crest.append(dem[int(r), int(c)])

ax_prof.plot((x_prof - 689500.0)/1000.0, prof_crest, "y-", linewidth=2.0, label="Embankment Crest Profile (W to E)")
ax_prof.axhline(elev_crest, color="r", linestyle="--", alpha=0.7, label=f"Sampled Crest Elev = {elev_crest:.1f}m")
ax_prof.axhline(elev_channel, color="b", linestyle=":", alpha=0.7, label=f"Channel Bed Elev = {elev_channel:.1f}m")

# Annotate structural height
ax_prof.annotate(f"Dam Height ≈ {elev_crest - elev_channel:.1f}m\n(CWC/ASDSO Inquiry: 22.56m)",
                 xy=(1.85, (elev_crest + elev_channel)/2),
                 xytext=(2.3, 45.0),
                 arrowprops=dict(facecolor="black", arrowstyle="->", lw=1.2),
                 fontweight="bold", fontsize=8)

ax_prof.set_title("Elevation Profiles: Embankment Crest & Channel Section", fontsize=11, fontweight="bold")
ax_prof.set_xlabel("Distance along Dam Axis from West (km)")
ax_prof.set_ylabel("Elevation (m above MSL)")
ax_prof.legend(loc="lower right", fontsize=8)
ax_prof.grid(True, linestyle=":", alpha=0.4)
ax_prof.set_ylim(35, 70)

plt.tight_layout()
Path("docs/SLIDE_FIGURES").mkdir(parents=True, exist_ok=True)
out1 = "cache/site_a/machhu2_dam_location_identified.png"
out2 = "docs/SLIDE_FIGURES/machhu2_dam_location_identified.png"
plt.savefig(out1)
plt.savefig(out2)
print(f"Saved {out1} and {out2}")
