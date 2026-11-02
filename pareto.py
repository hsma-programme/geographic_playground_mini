"""Tab 3: which options are worth weighing up, drawn with lokigi's trade-off charts.

Scoring stays in core.py (exhaustive numpy). lokigi is only used here to find the
options that no other option beats on every chosen question, and to draw them.
"""

import textwrap

import plotly.graph_objects as go
from lokigi.multiobjective import Metric
from lokigi.site_solutions import SiteSolutionSet

from core import Data, label

YOUR_PICK = "Your pick"
YOUR_COLOUR = "#ffe600"

def make_metrics(cutoff) -> dict:
    """Short spoke / axis names; all four questions are "lower is better".
    The 'too far' label names the cutoff, since it changes with the slider."""
    return {
        "avg": Metric("avg", "lower_better", label="Average journey", unit="min", decimals=1),
        "beyond": Metric(
            "beyond", "lower_better", label=f"People over {cutoff:g} min away", unit="people", decimals=0
        ),
        "deprived": Metric("deprived", "lower_better", label="Most deprived areas", unit="min", decimals=1),
        "worst": Metric("worst", "lower_better", label="Longest journey", unit="min", decimals=0),
    }


def solution_set(data: Data, scores, keys, cutoff) -> SiteSolutionSet:
    """lokigi solution set for every scored combination, with the unbeaten ones flagged."""
    metrics = make_metrics(cutoff)
    df = scores.copy().reset_index(drop=True)
    df["option_id"] = df.index + 1
    df["option_name"] = [label(data, s) for s in df["sites"]]
    df["site_names"] = [[data.short_names[i] for i in s] for s in df["sites"]]
    ss = SiteSolutionSet(df, site_problem=None, objectives="custom")
    ss.compute_pareto_front([metrics[k] for k in keys], id_col="option_id")
    ss.metric_by_key = metrics
    return ss


def _front(ss):
    return ss.solution_df[ss.solution_df["is_pareto_optimal"]]


def _pick_row(ss, your_sites):
    df = ss.solution_df
    return df[df["sites"] == tuple(sorted(your_sites))].iloc[0]


def question_winners(ss, keys, your_sites=()):
    """Ids of the options to show at first: the best on each question, plus your pick if it survived."""
    front = _front(ss)
    ids = [int(front.loc[front[k].idxmin(), "option_id"]) for k in keys]
    if len(your_sites):
        pick = _pick_row(ss, your_sites)
        if pick["is_pareto_optimal"]:
            ids.append(int(pick["option_id"]))
    return list(dict.fromkeys(ids))


def verdict(ss, keys, your_sites):
    """(n_unbeaten, n_total, name of an option that beats your pick, or None)."""
    front = _front(ss)
    pick = _pick_row(ss, your_sites)
    beater = None
    if not pick["is_pareto_optimal"]:
        beaters = front[front["option_id"].isin(pick["dominated_by"])]
        beater = beaters.sort_values(keys[0]).iloc[0]["option_name"]
    return len(front), len(ss.solution_df), beater


def _scaled(ss, key, value):
    """0-1 where 1 is the best of all options, as lokigi's scale_to='all'."""
    col = ss.solution_df[key]
    lo, hi = col.min(), col.max()
    return 1 - (value - lo) / ((hi - lo) or 1.0)


# Extra grey line under an axis label, where the name alone needs explaining
NOTES = {"deprived": ("average for the 30%", "most deprived areas")}


# Characters before a legend entry wraps; wide enough that most options sit on one line,
# since a long legend scrolls inside the chart
LEGEND_WRAP = 40

# Radar spokes say what is being minimised, since the shape reads as "bigger is better"
RADAR_TITLES = {"deprived": "Minimising journey in most deprived areas"}


def _axis_label(ss, key, kind="lines") -> str:
    """Spoke / axis label: the question, then its best and worst value across all options."""
    metric = ss.metric_by_key[key]
    title, width = metric.label, 20
    if kind == "radar":
        title = RADAR_TITLES.get(key) or f"Minimising {title[0].lower()}{title[1:]}"
        width = 26
    col = ss.solution_df[key]
    # All questions are lower-is-better, so the best is the smallest
    fmt = (lambda v: f"{v:,.0f}") if key == "beyond" else (lambda v: f"{v:.1f} minutes")
    # The line chart's columns are narrower, so the note breaks onto two lines there
    note = ("<br>" if kind == "lines" else " ").join(NOTES[key]) + "<br>" if key in NOTES else ""
    return (
        textwrap.fill(title, width=width).replace("\n", "<br>")
        + "<br><span style='font-size:10px;color:gray'>"
        + note
        + f"best {fmt(col.min())}, worst {fmt(col.max())}<br>of all {len(col):,} options</span>"
    )


def trade_off_chart(ss, keys, your_sites, kind="radar"):
    """Interactive radar ('radar') or parallel-lines ('lines') chart, with your pick on top."""
    shown = question_winners(ss, keys, your_sites)
    common = dict(
        id_col="option_id",
        name_col="option_name",
        interactive=True,
        initially_shown=shown,
        legend_wrap_at=LEGEND_WRAP,
        title="",
        caption="",
    )
    fig = (
        ss.plot_pareto_radar(**common)
        if kind == "radar"
        else ss.plot_pareto_summary(**common)
    )

    # lokigi's own best/worst text has no units and 2dp, so write the axis labels here
    labels = [_axis_label(ss, k, kind) for k in keys]
    if kind == "radar":
        for trace in fig.data:
            if trace.theta is not None:
                trace.theta = labels + labels[:1]
    else:
        # tickangle=0: plotly tilts crowded labels, which makes the multi-line ones unreadable
        fig.update_xaxes(ticktext=labels, tickangle=0)
        for trace in fig.data:
            if trace.showlegend is False:  # the one trace of ruled-out options
                trace.opacity = 0.3
            else:
                trace.line.width = 2.8

    pick = _pick_row(ss, your_sites)
    values = [_scaled(ss, k, pick[k]) for k in keys]
    n_total = len(ss.solution_df)
    hover = [
        f"<b>{YOUR_PICK}: {pick['option_name']}</b><br>{ss.metric_by_key[k].label}: "
        f"{ss.metric_by_key[k].format_value(pick[k])}<br>"
        f"Rank {int((ss.solution_df[k] < pick[k]).sum()) + 1} of {n_total:,}"
        for k in keys
    ]
    style = dict(
        # Wrapped like lokigi's own legend entries (legend_wrap_at above)
        name="<br>".join(
            textwrap.wrap(f"{YOUR_PICK} ({pick['option_name']})", width=LEGEND_WRAP, break_long_words=False)
        ),
        legendrank=0,
        mode="lines+markers",
        line=dict(color=YOUR_COLOUR, width=4, dash="dash"),
        marker=dict(color=YOUR_COLOUR, size=9),
        hovertemplate="%{text}<extra></extra>",
    )
    if kind == "radar":
        fig.add_trace(
            go.Scatterpolar(r=values + values[:1], theta=labels + labels[:1], text=hover + hover[:1], **style)
        )
    else:
        fig.add_trace(go.Scatter(x=list(range(len(keys))), y=values, text=hover, **style))

    # Right margin follows the longest legend line, counting the pick (added after lokigi sized it)
    longest = max(len(line) for t in fig.data if t.showlegend is not False for line in t.name.split("<br>"))
    radar = kind == "radar"
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Space Grotesk, sans-serif", size=16),
        legend=dict(font=dict(size=14)),
        annotations=[],
        title=None,
        # Radar spoke labels are taller and wider, so they need more room all round
        margin=dict(t=40 if radar else 20, b=125 if radar else 40, l=60, r=int(7.5 * longest) + 50),
        height=570,
    )
    if radar:
        fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", domain=dict(x=[0.22, 0.72], y=[0.0, 0.8])))
    return fig
