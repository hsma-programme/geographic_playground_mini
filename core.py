"""Data loading and scoring for the mini playground.

Everything here is plain numpy: with 729 areas and 18 sites, scoring any
combination of sites takes a fraction of a millisecond, so the app never needs
to run a real optimiser at runtime. The heavyweight lokigi runs that the full
playground uses are replaced by exhaustive scoring of every combination.
"""

import itertools
import json
from dataclasses import dataclass
from math import comb
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent / "data"

# Most-deprived group for the "fairness" objective: IMD deciles 1-3 (1 = most deprived)
DEPRIVED_MAX_DECILE = 3
MAX_NEW_SITES = 3

EXISTING_SHORT_NAMES = {
    "Bideford Community Hospital": "Bideford",
    "NHS Nightingale Exeter": "Exeter",
    "Colin Campbell Court, Plymouth": "Plymouth",
    "Torbay & South Devon Community Diagnostic Centre": "Torbay",
}

MODES = {"car": "By car", "pt": "By public transport"}
# Demand scenarios; "2036" is an illustrative projection made for teaching, not an ONS forecast
DEMANDS = {"today": "Today", "2036": "In 10 years (2036, projected)"}

# What each objective asks, in the plain English shown to visitors. All are
# "lower is better" so a single sort handles every one of them.
OBJECTIVES = {
    "avg": ("Shortest average journey", "minutes", "The best place if you care about the typical person's journey."),
    "beyond": ("Fewest people left far away", "people", "The best place if you care about people who are furthest away."),
    "deprived": ("Best for the most deprived areas", "minutes", "The best place if you care most about the most deprived third of areas."),
    "worst": ("Shortest worst-case journey", "minutes", "The best place if you care about the single longest journey."),
}


@dataclass(frozen=True)
class Data:
    demand: dict  # scenario -> people aged 50-84 in each area
    imd: np.ndarray  # IMD decile, 1 = most deprived
    matrices: dict  # mode -> (n_areas, n_sites) travel minutes
    sites: pd.DataFrame
    geojson: dict
    short_names: list
    existing: list  # column indices of the existing centres
    candidates: list  # column indices of the candidate sites


@st.cache_resource
def load_data() -> Data:
    arrays = np.load(DATA_DIR / "mini_data.npz")
    sites = pd.read_csv(DATA_DIR / "sites.csv")
    short = [
        EXISTING_SHORT_NAMES.get(name, name.split(" - ")[0])
        for name in sites["Facility_Name"]
    ]
    return Data(
        demand={"today": arrays["demand"], "2036": arrays["demand_2036"]},
        imd=arrays["imd"],
        matrices={"car": arrays["car"], "pt": arrays["pt"]},
        sites=sites,
        geojson=json.loads((DATA_DIR / "lsoa.geojson").read_text()),
        short_names=short,
        existing=sites.index[sites["Existing"]].tolist(),
        candidates=sites.index[~sites["Existing"]].tolist(),
    )


def nearest_time(data: Data, mode: str, new_sites=()) -> np.ndarray:
    """Minutes from each area to its nearest centre (existing + any new ones)."""
    cols = list(data.existing) + list(new_sites)
    return data.matrices[mode][:, cols].min(axis=1)


def nearest_site(data: Data, mode: str, new_sites=()) -> np.ndarray:
    """Position in existing + new_sites of each area's nearest centre."""
    cols = list(data.existing) + list(new_sites)
    return data.matrices[mode][:, cols].argmin(axis=1)


def summarise(data: Data, times: np.ndarray, cutoff: float, demand: str = "today") -> dict:
    w = data.demand[demand]
    deprived = data.imd <= DEPRIVED_MAX_DECILE
    return {
        "avg": float((times * w).sum() / w.sum()),
        "beyond": float(w[times > cutoff].sum()),
        "deprived": float((times[deprived] * w[deprived]).sum() / w[deprived].sum()),
        "worst": float(times.max()),
    }


@st.cache_data(show_spinner=False)
def score_all_combinations(mode: str, n_new: int, cutoff: float, demand: str = "today") -> pd.DataFrame:
    """Score every way of adding `n_new` candidate sites to today's network."""
    data = load_data()
    rows = []
    for combo in itertools.combinations(data.candidates, n_new):
        times = nearest_time(data, mode, combo)
        rows.append({"sites": combo, **summarise(data, times, cutoff, demand)})
    return pd.DataFrame(rows)


def label(data: Data, sites) -> str:
    return " + ".join(data.short_names[i] for i in sites)


def rank_of(scores: pd.DataFrame, sites, objective: str) -> int:
    """1-based rank of a combination on one objective (1 = best)."""
    ordered = scores.sort_values(objective, kind="stable")["sites"].tolist()
    return ordered.index(tuple(sorted(sites))) + 1


def n_combinations(n_candidates: int, n_new: int) -> int:
    return comb(n_candidates, n_new)
