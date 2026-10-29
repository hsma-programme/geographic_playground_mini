"""Plotly figures: the interactive map and the optimiser animation."""

import os

import numpy as np
import plotly.graph_objects as go

from core import Data, nearest_time

# Basemap tiles need internet. Set MINI_OFFLINE=1 on a stand laptop with no wifi
# to fall back to a plain background (the area outlines still read fine).
MAP_STYLE = "white-bg" if os.environ.get("MINI_OFFLINE") else "carto-positron"
CENTRE = dict(lat=50.75, lon=-3.8)
ZOOM = 7.6

NEAR, FAR = "#2f80c9", "#e8453c"
TIME_COLORSCALE = [[0, "#1fb1b9"], [0.45, "#f6e8a4"], [1, "#b2182b"]]
# Colour scale tops out here so car and public transport maps each use their range
TIME_MAX = {"car": 60, "pt": 120}


def _site_traces(data: Data, new_sites):
    s = data.sites
    unchosen = [i for i in data.candidates if i not in new_sites]

    def trace(idx, name, colour, size, text=True):
        idx = list(idx)
        return go.Scattermap(
            lat=s.loc[idx, "Latitude"],
            lon=s.loc[idx, "Longitude"],
            mode="markers+text" if text else "markers",
            marker=dict(size=size, color=colour),
            text=[data.short_names[i] for i in idx] if text else None,
            textposition="top center",
            textfont=dict(size=13, color="#111"),
            name=name,
            hovertext=[data.short_names[i] for i in idx],
            hoverinfo="text",
        )

    return [
        trace(data.existing, "Existing centre", "#0b2a6f", 18),
        trace(unchosen, "Possible new centre", "#7a7a7a", 11, text=False),
        trace(new_sites, "Your new centre", "#21a354", 22),
    ]


def travel_map(data: Data, mode, new_sites, cutoff, view, height=640) -> go.Figure:
    """The interactive map: binary 'beyond the cutoff' view or a time gradient."""
    times = nearest_time(data, mode, new_sites)
    if view == "cutoff":
        z = (times > cutoff).astype(int)
        choropleth = go.Choroplethmap(
            geojson=data.geojson, locations=np.arange(len(z)), z=z,
            zmin=0, zmax=1, colorscale=[[0, NEAR], [1, FAR]], showscale=False,
            marker=dict(opacity=0.75, line_width=0),
            customdata=times.round(0),
            hovertemplate="%{customdata:.0f} minutes to nearest centre<extra></extra>",
        )
    else:
        choropleth = go.Choroplethmap(
            geojson=data.geojson, locations=np.arange(len(times)), z=times.round(1),
            zmin=0, zmax=TIME_MAX[mode], colorscale=TIME_COLORSCALE,
            colorbar=dict(title="minutes", thickness=12, len=0.5, x=0.01, xanchor="left", y=0.2),
            marker=dict(opacity=0.75, line_width=0),
            hovertemplate="%{z:.0f} minutes to nearest centre<extra></extra>",
        )
    fig = go.Figure([choropleth, *_site_traces(data, new_sites)])
    fig.update_layout(
        map=dict(style=MAP_STYLE, center=CENTRE, zoom=ZOOM),
        margin=dict(l=0, r=0, t=0, b=0), height=height, showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def static_time_map(data: Data, mode, new_sites, height=440) -> go.Figure:
    """Compact gradient map used to compare 'your pick' with 'the optimiser's pick'."""
    fig = travel_map(data, mode, new_sites, cutoff=0, view="time", height=height)
    fig.update_traces(showscale=False, selector=dict(type="choroplethmap"))
    return fig
