"""Turn the raw inputs in raw/ into the small, geopandas-free files the app reads.

Run from the repo root:  uv run --group precompute python scripts/precompute.py

Writes:
  data/lsoa.geojson   LSOA polygons, simplified, feature id = row position
  data/mini_data.npz  names, demand, IMD decile and the two travel matrices
  data/sites.csv      the 18 sites (4 existing + 14 candidates)
"""

import json
from pathlib import Path

import geopandas
import numpy as np
import pandas as pd

RAW, OUT = Path("raw"), Path("data")
# Unreachable by public transport is stored as 9999 - cap it so colour scales stay readable
UNREACHABLE_CAP = 180.0
IMD_COL = "Index of Multiple Deprivation (IMD) Decile (where 1 is most deprived 10% of LSOA"

sites = pd.read_csv(RAW / "devon_cdcs.csv")
sites["Longitude"] = sites["Longitude"].astype(str).str.strip().astype(float)
sites["Existing"] = sites["Existing"].eq("Yes")

geo = geopandas.read_file(RAW / "LSOA_Devon_2021_EW_BSC_V4.gpkg")[["LSOA21NM", "geometry"]]
geo = geo.to_crs(4326)
names = geo["LSOA21NM"].tolist()

demand = pd.read_csv(RAW / "demand_MF_50_84.csv").set_index("LSOA 2021 Name")["MF50-84"]
imd = pd.read_csv(RAW / "devon_imd_2025_2021_LSOAs.csv").set_index("LSOA name (2021)")[IMD_COL]


def load_matrix(file):
    m = pd.read_csv(RAW / file).set_index("from_id")
    m = m.loc[names, sites["Facility_Name"]]
    return m.fillna(UNREACHABLE_CAP).clip(upper=UNREACHABLE_CAP).to_numpy(dtype="float32")


np.savez_compressed(
    OUT / "mini_data.npz",
    names=np.array(names),
    demand=demand.loc[names].to_numpy(dtype="float32"),
    imd=imd.loc[names].to_numpy(dtype="int8"),
    car=load_matrix("travel_matrix_car.csv"),
    pt=load_matrix("travel_matrix_public_transport.csv"),
)
sites.to_csv(OUT / "sites.csv", index=False)

# ~50 m simplification is invisible at county zoom and keeps the payload small
geo["geometry"] = geo.to_crs(27700).simplify(60, preserve_topology=True).to_crs(4326)
features = json.loads(geo[["geometry"]].to_json(drop_id=True, na="null", show_bbox=False))
for i, f in enumerate(features["features"]):
    f["id"] = i
    f["properties"] = {}
(OUT / "lsoa.geojson").write_text(json.dumps(features, separators=(",", ":")))
print("done", {p.name: p.stat().st_size // 1024 for p in OUT.iterdir()}, "KB")
