"""Plotly figures: the interactive map and the optimiser animation."""

import os

import numpy as np
import plotly.graph_objects as go

from core import Data, nearest_site, nearest_time

# Basemap tiles need internet. Set MINI_OFFLINE=1 on a stand laptop with no wifi
# to fall back to a plain background (the area outlines still read fine).
MAP_STYLE = "white-bg" if os.environ.get("MINI_OFFLINE") else "carto-positron"
CENTRE = dict(lat=50.75, lon=-3.8)
ZOOM = 7.6

NEAR, FAR = "#2f80c9", "#e8453c"
NEW_SITE = "#ffe600"  # yellow stands out against both the blue/red and journey-time maps
TIME_COLORSCALE = [[0, "#1fb1b9"], [0.45, "#f6e8a4"], [1, "#b2182b"]]
# Colour scale tops out here so car and public transport maps each use their range
TIME_MAX = {"car": 60, "pt": 120}
# 'Closest site' view: cool colours for today's centres, warm for new ones, so the
# area a new centre takes over stands out (no red, which means "too far" elsewhere)
EXISTING_COLOURS = ["#4e79a7", "#59a14f", "#76b7b2", "#b07aa1"]
NEW_COLOURS = ["#f28e2b", "#edc948", "#ff9da7"]


def _site_traces(data: Data, new_sites, selectable=False):
    s = data.sites
    unchosen = [i for i in data.candidates if i not in new_sites]

    def trace(idx, name, colour, size, text=True, hover="{}"):
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
            customdata=idx,
            hovertext=[hover.format(data.short_names[i]) for i in idx],
            hoverinfo="text",
            # Tapping a site selects it; don't let plotly fade everything else
            selected=dict(marker=dict(opacity=1)),
            unselected=dict(marker=dict(opacity=1)),
        )

    remove_hover = "Tap to remove {}" if selectable else "{}"
    # Trace order matters: animation.py restyles traces 3-4 and the tap callback
    # in streamlit_app.py accepts taps on traces 2-4
    return [
        trace(data.existing, "Existing centre", "#0b2a6f", 18),
        trace(
            unchosen, "Possible new centre", "#7a7a7a", 16 if selectable else 11, text=False,
            hover="Tap to open a centre in {}" if selectable else "{}",
        ),
        # Map markers can't have an outline, so a larger dark dot sits underneath
        trace(new_sites, "Your new centre outline", "#111", 28, text=False, hover=remove_hover),
        trace(new_sites, "Your new centre", NEW_SITE, 22, hover=remove_hover),
    ]


def travel_map(data: Data, mode, new_sites, cutoff, view, height=640, selectable=False) -> go.Figure:
    """The interactive map: binary 'beyond the cutoff' view, a time gradient, or
    each area coloured by its closest centre.

    selectable=True sizes and labels the candidate sites for tapping.
    """
    times = nearest_time(data, mode, new_sites)
    if view == "nearest":
        sites = list(data.existing) + list(new_sites)
        colours = [EXISTING_COLOURS[i % len(EXISTING_COLOURS)] for i in range(len(data.existing))]
        colours += NEW_COLOURS[: len(new_sites)]
        # Step colour scale: each whole number z maps to one flat band of colour
        k = len(colours)
        scale = [[edge / k, c] for i, c in enumerate(colours) for edge in (i, i + 1)]
        nearest = nearest_site(data, mode, new_sites)
        names = np.array([data.short_names[i] for i in sites])[nearest]
        choropleth = go.Choroplethmap(
            geojson=data.geojson, locations=np.arange(len(nearest)), z=nearest,
            zmin=-0.5, zmax=k - 0.5, colorscale=scale, showscale=False,
            marker=dict(opacity=0.75, line_width=0),
            selected=dict(marker=dict(opacity=0.75)),
            unselected=dict(marker=dict(opacity=0.75)),
            customdata=np.column_stack([names, times.round(0).astype(int)]),
            hovertemplate="Closest centre: %{customdata[0]}<br>%{customdata[1]} minutes<extra></extra>",
        )
    elif view == "cutoff":
        z = (times > cutoff).astype(int)
        choropleth = go.Choroplethmap(
            geojson=data.geojson, locations=np.arange(len(z)), z=z,
            zmin=0, zmax=1, colorscale=[[0, NEAR], [1, FAR]], showscale=False,
            marker=dict(opacity=0.75, line_width=0),
            selected=dict(marker=dict(opacity=0.75)),
            unselected=dict(marker=dict(opacity=0.75)),
            customdata=times.round(0),
            hovertemplate="%{customdata:.0f} minutes to nearest centre<extra></extra>",
        )
    else:
        choropleth = go.Choroplethmap(
            geojson=data.geojson, locations=np.arange(len(times)), z=times.round(1),
            zmin=0, zmax=TIME_MAX[mode], colorscale=TIME_COLORSCALE,
            colorbar=dict(title="minutes", thickness=12, len=0.5, x=0.01, xanchor="left", y=0.2),
            marker=dict(opacity=0.75, line_width=0),
            selected=dict(marker=dict(opacity=0.75)),
            unselected=dict(marker=dict(opacity=0.75)),
            hovertemplate="%{z:.0f} minutes to nearest centre<extra></extra>",
        )
    fig = go.Figure([choropleth, *_site_traces(data, new_sites, selectable)])
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
