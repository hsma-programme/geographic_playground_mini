"""Tab 3: which options are worth weighing up, drawn with lokigi's trade-off charts.

Scoring stays in core.py (exhaustive numpy). lokigi is only used here to find the
options that no other option beats on every chosen question, and to draw them.
"""

import textwrap
from dataclasses import dataclass

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from lokigi.multiobjective import Metric
from lokigi.site_solutions import SiteSolutionSet

from core import Data, label, score_all_combinations

YOUR_PICK = "Your pick"
YOUR_COLOUR = "#ffe600"
MAX_QUESTIONS = 5

# Characters before a legend entry wraps; wide enough that most options sit on one line,
# since a long legend scrolls inside the chart
LEGEND_WRAP = 40


def _minutes(v):
    return f"{v:.1f} minutes"


def _people(v):
    return f"{v:,.0f}"


def _percent(v):
    return f"{v:.0%}"


@dataclass(frozen=True)
class Question:
    key: str
    column: str  # in the wide frame from question_scores()
    row: str  # which row of pills it sits in: car / pt / service
    pill: str  # what visitors tap
    chart: str  # lower-case axis name, which the radar prefixes with Minimising / Maximising
    wins: str  # what an option "wins on" in the legend
    higher_better: bool = False
    fmt: object = _minutes
    note: tuple = ()  # grey lines under the axis label, where the name alone needs explaining
    unit: str = "minutes"  # for differences; "percentage points" is the one measured as a share
    decimals: int = 1  # for differences

    def difference(self, yours, theirs) -> str:
        """Theirs minus yours, signed, in this question's own unit."""
        d = (theirs - yours) * (100 if self.unit == "percentage points" else 1)
        if round(abs(d), self.decimals) == 0:
            return "no difference"
        return f"{'+' if d > 0 else '−'}{abs(d):,.{self.decimals}f} {self.unit}"

    @property
    def lines_title(self):
        return self.chart[0].upper() + self.chart[1:]

    @property
    def radar_title(self):
        return f"{'Maximising' if self.higher_better else 'Minimising'} {self.chart}"


ROWS = {"car": "By car", "pt": "By public transport", "service": "How the service runs"}
MODE_NAME = {"car": "by car", "pt": "by public transport"}


def questions(cutoffs) -> dict:
    """Every question, in display order. The 'too far' wording names each mode's cutoff."""
    qs = []
    for mode, name in MODE_NAME.items():
        cut = f"{cutoffs[mode]:g}"
        qs += [
            Question(f"avg_{mode}", f"avg_{mode}", mode, "Shortest average journey",
                     f"average journey {name}", f"average journey {name}"),
            Question(f"beyond_{mode}", f"beyond_{mode}", mode, f"Fewest people over {cut} min away",
                     f"people over {cut} min away {name}", f"fewest people far away {name}", fmt=_people,
                     unit="people", decimals=0),
            Question(f"deprived_{mode}", f"deprived_{mode}", mode, "Best for the most deprived areas",
                     f"journey in most deprived areas {name}", f"most deprived areas {name}",
                     note=("average for the 30%", "most deprived areas")),
        ]
        if mode == "car":
            # By public transport some areas are unreachable and capped at 180, so the longest
            # journey never differs between options and can't be weighed
            qs.append(Question("worst_car", "worst_car", mode, "Shortest worst-case journey",
                               "longest journey by car", "longest journey by car", fmt=lambda v: f"{v:.0f} minutes", decimals=0))
        qs.append(Question(f"helped_{mode}", f"helped_{mode}", mode, "Most people helped",
                           f"people helped {name}", f"people helped {name}", higher_better=True, fmt=_people, unit="people", decimals=0,
                           note=("people whose nearest", "centre gets quicker")))
    qs.append(Question("busiest_car", "busiest_car", "service", "Most even workload",
                       "busiest centre's share of patients", "even workload", fmt=_percent, unit="percentage points",
                       note=("patients go to their", "nearest centre, by car")))
    return {q.key: q for q in qs}


DEFAULT_QUESTIONS = {"car": ["beyond_car", "helped_car"], "pt": ["beyond_pt"], "service": []}


def question_scores(data: Data, n_new: int, cutoffs, demand: str = "today") -> pd.DataFrame:
    """Every combination scored by car and by public transport side by side (columns end _car / _pt)."""
    frames = {m: score_all_combinations(m, n_new, float(cutoffs[m]), demand) for m in MODE_NAME}
    # Both enumerate combinations in the same order, which is what lets us line the rows up
    assert frames["car"]["sites"].tolist() == frames["pt"]["sites"].tolist()
    wide = pd.DataFrame({"sites": frames["car"]["sites"]})
    for mode, frame in frames.items():
        for col in ("avg", "beyond", "deprived", "worst", "helped", "busiest"):
            wide[f"{col}_{mode}"] = frame[col]
    return wide


def solution_set(data: Data, scores, keys, qs) -> SiteSolutionSet:
    """lokigi solution set for every scored combination, with the unbeaten ones flagged."""
    df = scores.copy().reset_index(drop=True)
    df["option_id"] = df.index + 1
    df["option_name"] = [label(data, s) for s in df["sites"]]
    df["site_names"] = [[data.short_names[i] for i in s] for s in df["sites"]]
    ss = SiteSolutionSet(df, site_problem=None, objectives="custom")
    metrics = [
        Metric(
            qs[k].column,
            "higher_better" if qs[k].higher_better else "lower_better",
            label=qs[k].lines_title,
        )
        for k in keys
    ]
    ss.compute_pareto_front(metrics, id_col="option_id")
    ss.questions = qs
    # Legend names: the options that are best on a question say so
    wins = {}
    for k in keys:
        wins.setdefault(_best_id(ss, qs[k]), []).append(qs[k].wins)
    ss.wins = wins
    ss.solution_df["option_label"] = [
        _with_wins(name, wins.get(i)) for i, name in zip(ss.solution_df["option_id"], ss.solution_df["option_name"])
    ]
    # lokigi styles unbeaten options in row order, turning to dashed lines once its ten
    # colours run out, so the winners (shown at first) go first to keep their lines solid.
    # Winners keep their own order, so _best_id still picks the same one among ties.
    is_winner = ss.solution_df["option_id"].isin(wins)
    ss.solution_df = pd.concat([ss.solution_df[is_winner], ss.solution_df[~is_winner]])
    return ss


def _with_wins(name, wins):
    return f"{name} (wins on {', '.join(wins)})" if wins else name


def _front(ss):
    return ss.solution_df[ss.solution_df["is_pareto_optimal"]]


def _pick_row(ss, your_sites):
    df = ss.solution_df
    return df[df["sites"] == tuple(sorted(your_sites))].iloc[0]


def _best_id(ss, q):
    """The unbeaten option that is best on one question (the first, if tied)."""
    front = _front(ss)
    col = front[q.column]
    return int(front.loc[col.idxmax() if q.higher_better else col.idxmin(), "option_id"])


def question_winners(ss, keys, your_sites=()):
    """Ids of the options to show at first: the best on each question, plus your pick if it survived."""
    ids = [_best_id(ss, ss.questions[k]) for k in keys]
    if len(your_sites):
        pick = _pick_row(ss, your_sites)
        if pick["is_pareto_optimal"]:
            ids.append(int(pick["option_id"]))
    return list(dict.fromkeys(ids))


def _beater_row(ss, keys, pick):
    """An unbeaten option that beats your pick: the one best on the first question, or None."""
    if pick["is_pareto_optimal"]:
        return None
    q = ss.questions[keys[0]]
    beaters = _front(ss)
    beaters = beaters[beaters["option_id"].isin(pick["dominated_by"])]
    return beaters.sort_values(q.column, ascending=not q.higher_better).iloc[0]


def verdict(ss, keys, your_sites):
    """(n_unbeaten, n_total, name of an option that beats your pick, or None)."""
    beater = _beater_row(ss, keys, _pick_row(ss, your_sites))
    return len(_front(ss)), len(ss.solution_df), None if beater is None else beater["option_name"]


def compare_table(ss, keys, your_sites):
    """Your pick beside the option that beats it, on each chosen question (None if nothing beats it)."""
    pick = _pick_row(ss, your_sites)
    beater = _beater_row(ss, keys, pick)
    if beater is None:
        return None
    rows = {}
    for k in keys:
        q = ss.questions[k]
        rows[q.lines_title] = [
            q.fmt(pick[q.column]),
            q.fmt(beater[q.column]),
            q.difference(pick[q.column], beater[q.column]),
        ]
    return pd.DataFrame(rows, index=["Your pick", beater["option_name"], "Difference"]).T


def _scaled(ss, q, value):
    """0-1 where 1 is the best of all options, as lokigi's scale_to='all'."""
    col = ss.solution_df[q.column]
    lo, hi = col.min(), col.max()
    frac = (value - lo) / ((hi - lo) or 1.0)
    return frac if q.higher_better else 1 - frac


def _axis_label(ss, q, kind="lines") -> str:
    """Spoke / axis label: the question, then its best and worst value across all options."""
    title, width = (q.radar_title, 26) if kind == "radar" else (q.lines_title, 20)
    col = ss.solution_df[q.column]
    best, worst = (col.max(), col.min()) if q.higher_better else (col.min(), col.max())
    # The line chart's columns are narrower, so the note breaks onto two lines there
    note = ("<br>" if kind == "lines" else " ").join(q.note) + "<br>" if q.note else ""
    return (
        textwrap.fill(title, width=width).replace("\n", "<br>")
        + "<br><span style='font-size:10px;color:gray'>"
        + note
        + f"best {q.fmt(best)}, worst {q.fmt(worst)}<br>of all {len(col):,} options</span>"
    )


# The made-up example in the "How to read this chart" box: 0 is worst, 1 is best.
# Your pick is below option B on every question, so B rules it out.
GUIDE_OPTIONS = {
    "Option A": ([0.95, 0.55, 0.15], "#1f77b4"),  # lokigi's first two colours (tab10)
    "Option B": ([0.3, 0.7, 0.9], "#ff7f0e"),
}
GUIDE_PICK = [0.2, 0.5, 0.7]
GUIDE_RULED_OUT = [[0.1, 0.25, 0.3], [0.45, 0.15, 0.05], [0.05, 0.1, 0.35]]
GUIDE_GREY = "#8a8a8a"


def _faint(colour):
    """A hex colour as a see-through fill, so shapes stay visible underneath each other."""
    r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},0.12)"


def guide_chart(kind="radar"):
    """Small annotated example of the radar ('radar') or lines ('lines') chart.

    Drawn on plain x/y axes, radar included, so the numbered badges can sit exactly
    where they point. The numbers match the steps written beside it.
    """
    radar = kind == "radar"
    angles = np.radians([90, 210, 330])  # question 1 at the top, like lokigi's radar

    def xy(values):
        if radar:
            v = np.append(values, values[0])
            a = np.append(angles, angles[0])
            return list(v * np.cos(a)), list(v * np.sin(a))
        return [0, 1, 2], list(values)

    fig = go.Figure()
    grid = dict(mode="lines", line=dict(color="rgba(255,255,255,0.25)", width=1), hoverinfo="skip")
    if radar:
        t = np.linspace(0, 2 * np.pi, 100)
        for r in (0.5, 1):
            fig.add_trace(go.Scatter(x=r * np.cos(t), y=r * np.sin(t), **grid))
        for a, i in zip(angles, range(3)):
            fig.add_trace(go.Scatter(x=[0, np.cos(a)], y=[0, np.sin(a)], **grid))
            fig.add_annotation(x=1.22 * np.cos(a), y=1.16 * np.sin(a), text=f"Question {i + 1}", showarrow=False)
    else:
        for i in range(3):
            fig.add_trace(go.Scatter(x=[i, i], y=[0, 1], **grid))
            fig.add_annotation(x=i, y=-0.13, text=f"Question {i + 1}", showarrow=False)
        for values in GUIDE_RULED_OUT:
            fig.add_trace(go.Scatter(x=[0, 1, 2], y=values, mode="lines",
                                     line=dict(color=GUIDE_GREY, width=1), opacity=0.6))

    # Which way is better: centre to edge on the radar, bottom to top on the lines
    tail, head, words = (
        ((0, -0.08), (0, -0.98), [((0, -1.12), "best"), ((0.2, -0.05), "worst")])
        if radar
        else ((-0.38, 0.02), (-0.38, 0.98), [((-0.38, 1.1), "best"), ((-0.38, -0.1), "worst")])
    )
    fig.add_annotation(x=head[0], y=head[1], ax=tail[0], ay=tail[1], xref="x", yref="y", axref="x", ayref="y",
                       text="", arrowhead=2, arrowsize=1.2, arrowwidth=2, arrowcolor="#cccccc")
    for (x, y), word in words:
        fig.add_annotation(x=x, y=y, text=word, showarrow=False, font=dict(color="#cccccc", size=14),
                           bgcolor="rgba(27,26,26,0.7)")

    for name, (values, colour) in GUIDE_OPTIONS.items():
        xs, ys = xy(values)
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers", line=dict(color=colour, width=3),
                                 marker=dict(size=7), fill="toself" if radar else None,
                                 fillcolor=_faint(colour)))
    xs, ys = xy(GUIDE_PICK)
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers", line=dict(color=YOUR_COLOUR, width=4, dash="dash"),
                             marker=dict(color=YOUR_COLOUR, size=8)))

    # Names beside each line, so the example needs no legend
    labels = (
        [((0.4, 0.6), "Option A", GUIDE_OPTIONS["Option A"][1]),
         ((0.36, -0.62), "Option B", GUIDE_OPTIONS["Option B"][1]),
         ((-0.62, 0.12), "Your pick", YOUR_COLOUR)]
        if radar
        else [((2.1, v[2]), name, c) for name, (v, c) in GUIDE_OPTIONS.items()]
        + [((2.1, GUIDE_PICK[2]), "Your pick", YOUR_COLOUR)]
    )
    for (x, y), text, colour in labels:
        fig.add_annotation(x=x, y=y, text=f"<b>{text}</b>", showarrow=False, xanchor="left" if not radar else "center",
                           font=dict(color=colour, size=14))

    # Numbered badges: (where the badge sits, what its arrow points at, or None)
    badges = (
        [((-0.32, -0.85), None), ((-0.28, 0.95), (-0.04, 0.95)), ((1.05, 0.05), (0.62, -0.33))]
        if radar
        else [((-0.62, 0.5), None), ((0.32, 1.08), (0.05, 0.97)), ((1.7, 0.45), (1.7, 0.61))]
    )
    for n, ((x, y), target) in enumerate(badges, start=1):
        if target:
            fig.add_annotation(x=target[0], y=target[1], ax=x, ay=y, xref="x", yref="y", axref="x", ayref="y",
                               text="", arrowhead=2, arrowwidth=1.5, arrowcolor="#ffffff", standoff=4, startstandoff=13)
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers+text", text=[f"<b>{n}</b>"],
                                 marker=dict(size=26, color="#ffffff"), textfont=dict(color="#1b1a1a", size=15)))

    axis = dict(visible=False, fixedrange=True)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Space Grotesk, sans-serif", size=14),
        showlegend=False,
        margin=dict(t=10, b=10, l=10, r=10),
        # A fixed size: the radar keeps its circle round by shrinking to fit, which could
        # leave the labels overlapping if the column was still narrow when it first drew
        width=580,
        height=420 if radar else 400,
        xaxis=axis | dict(range=[-1.35, 1.35] if radar else [-0.8, 2.7]),
        yaxis=axis | dict(range=[-1.2, 1.25] if radar else [-0.25, 1.2]),
    )
    if radar:
        fig.update_yaxes(scaleanchor="x")
    return fig


def trade_off_chart(ss, keys, your_sites, kind="radar"):
    """Interactive radar ('radar') or parallel-lines ('lines') chart, with your pick on top."""
    qs = [ss.questions[k] for k in keys]
    shown = question_winners(ss, keys, your_sites)
    common = dict(
        id_col="option_id",
        name_col="option_label",
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
    labels = [_axis_label(ss, q, kind) for q in qs]
    if kind == "radar":
        for trace in fig.data:
            if trace.theta is not None:
                trace.theta = labels + labels[:1]
            # lokigi also labels the filled area (name and sites), but plotly adds a
            # pale side box repeating the name, which reads as a ghost. namelength=0
            # still leaves a 6px strip of it, so label points only: they list the
            # sites too
            trace.hoveron = "points"
    else:
        # tickangle=0: plotly tilts crowded labels, which makes the multi-line ones unreadable
        fig.update_xaxes(ticktext=labels, tickangle=0)
        # lokigi's title says "Better ↑", which read as "bottom to top of the axis".
        # Worst and best match the words in the "How to read this chart" example.
        # plotly turns y-axis titles to read upwards, so → points up and Worst sits at the bottom
        fig.update_yaxes(title_text="Worst → Best")
        for trace in fig.data:
            if trace.showlegend is False:  # the one trace of ruled-out options
                trace.opacity = 0.3
            else:
                trace.line.width = 2.8

    pick = _pick_row(ss, your_sites)
    values = [_scaled(ss, q, pick[q.column]) for q in qs]
    n_total = len(ss.solution_df)

    def rank(q):
        col = ss.solution_df[q.column]
        n = int(((col > pick[q.column]) if q.higher_better else (col < pick[q.column])).sum()) + 1
        ties = int((col == pick[q.column]).sum()) - 1
        return f"{n} of {n_total:,}" + (
            f", tied with {ties} other option{'s' if ties > 1 else ''}" if ties else ""
        )

    pick_wins = ss.wins.get(int(pick["option_id"]))
    pick_name = _with_wins(pick["option_name"], pick_wins)
    # One set of brackets in the legend: "Your pick (A + B; wins on ...)"
    legend_name = f"{YOUR_PICK} ({pick['option_name']}" + (f"; wins on {', '.join(pick_wins)})" if pick_wins else ")")
    hover = [
        f"<b>{YOUR_PICK}: {pick_name}</b><br>{q.lines_title}: {q.fmt(pick[q.column])}<br>"
        f"Rank {rank(q)}"
        for q in qs
    ]
    style = dict(
        # Wrapped like lokigi's own legend entries (legend_wrap_at above)
        name="<br>".join(textwrap.wrap(legend_name, width=LEGEND_WRAP, break_long_words=False)),
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
        fig.add_trace(go.Scatter(x=list(range(len(qs))), y=values, text=hover, **style))

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
