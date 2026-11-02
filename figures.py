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


def diminishing_returns_chart(gains, n_chosen, budget, y_title, fmt, height=280) -> go.Figure:
    """Bars of what each extra centre adds (best possible choice each time).

    Bars within the budget are solid, the rest faded; the bar for the number of
    centres the visitor has chosen so far is outlined in yellow.
    """
    n = len(gains)
    fig = go.Figure(
        go.Bar(
            x=[f"{i}" for i in range(1, n + 1)],
            y=gains,
            text=[fmt(g) for g in gains],
            textposition="outside",
            textfont=dict(size=14),
            cliponaxis=False,
            marker=dict(
                color=["#1fb1b9" if i < budget else "rgba(31,177,185,0.35)" for i in range(n)],
                line=dict(
                    color=[NEW_SITE if i == n_chosen - 1 else "rgba(0,0,0,0)" for i in range(n)],
                    width=4,
                ),
            ),
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=24, b=0), showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            title="Extra centre (faded = over budget)", tickfont=dict(size=14), fixedrange=True,
            tickmode="array", tickvals=[f"{i}" for i in range(1, n + 1)],
        ),
        yaxis=dict(title=y_title, tickfont=dict(size=12), fixedrange=True, rangemode="tozero"),
        bargap=0.25,
    )
    return fig


def static_time_map(data: Data, mode, new_sites, height=440) -> go.Figure:
    """Compact gradient map used to compare 'your pick' with 'the optimiser's pick'."""
    fig = travel_map(data, mode, new_sites, cutoff=0, view="time", height=height)
    fig.update_traces(showscale=False, selector=dict(type="choroplethmap"))
    return fig


# Journey-time chart: 5-minute groups line up with the cutoff slider's 5-minute steps
HIST_BIN = 5
HIST_MAX = {"car": 65, "pt": 180}  # public transport is capped at 180 (unreachable areas)
GREY = "#b8b8b8"


def _people_by_time(times, weights, mode):
    """(group mid-points, people in each 5-minute group); anything at or over the top lands in the last."""
    top = HIST_MAX[mode]
    edges = np.arange(0, top + HIST_BIN, HIST_BIN)
    counts, _ = np.histogram(np.minimum(times, top - 1e-6), bins=edges, weights=weights)
    return (edges[:-1] + edges[1:]) / 2, counts


def journey_chart(mode, today_times, now_times, weights, cutoff, show_today, height=260) -> go.Figure:
    """People at each journey time as a filled area: blue up to the cutoff, red beyond it.

    With new centres chosen, today's network is drawn behind as a grey line. The top is
    a rounded line through the 5-minute groups (not a density estimate, which would smear
    the public transport pile-up at the 180-minute cap).
    """
    top = HIST_MAX[mode]
    mids, now = _people_by_time(now_times, weights, mode)
    _, today = _people_by_time(today_times, weights, mode)
    lo = mids - HIST_BIN / 2
    hover = [f"{a:.0f}-{a + HIST_BIN:.0f} minutes: {n:,.0f} people" for a, n in zip(lo, now)]
    if mode == "pt":
        hover[-1] = f"About {top / 60:.0f} hours or more, or no bus route: {now[-1]:,.0f} people"

    def area(mask, colour, extra_x, extra_y, extra_at_start):
        xs, ys, text = list(mids[mask]), list(now[mask]), [h for h, m in zip(hover, mask) if m]
        if extra_at_start:
            xs, ys, text = [extra_x, *xs], [extra_y, *ys], ["", *text]
        else:
            xs, ys, text = [*xs, extra_x], [*ys, extra_y], [*text, ""]
        return go.Scatter(
            x=xs, y=ys, text=text, mode="lines", fill="tozeroy",
            line=dict(color=colour, width=3, shape="spline", smoothing=0.6),
            fillcolor=f"rgba({int(colour[1:3], 16)},{int(colour[3:5], 16)},{int(colour[5:7], 16)},0.5)",
            hovertemplate="%{text}<extra></extra>",
        )

    fig = go.Figure()
    if show_today:
        fig.add_trace(go.Scatter(
            x=mids, y=today, mode="lines", hoverinfo="skip",
            line=dict(color=GREY, width=2.5, shape="spline", smoothing=0.6),
        ))
    # Height at the cutoff, so the blue and red fills meet without a gap
    at_cut = float(np.interp(cutoff, mids, now))
    fig.add_trace(area(mids < cutoff, NEAR, min(cutoff, top), at_cut, extra_at_start=False))
    if cutoff < top:
        fig.add_trace(area(mids > cutoff, FAR, cutoff, at_cut, extra_at_start=True))
        fig.add_vline(
            x=cutoff, line=dict(color="#ffffff", width=1.5, dash="dash"),
            annotation_text=f"{cutoff:g} min", annotation_position="top right",
            annotation_font=dict(size=14),
        )
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Space Grotesk, sans-serif", size=14),
        showlegend=False, dragmode=False, hovermode="closest",
        margin=dict(l=10, r=10, t=10, b=40), height=height,
    )
    fig.update_xaxes(
        range=[0, top], title_text="Journey time to the nearest centre (minutes)", fixedrange=True,
    )
    fig.update_yaxes(rangemode="tozero", showticklabels=False, showgrid=False, fixedrange=True)
    return fig
