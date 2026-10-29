"""Where should the next diagnostic centre go? A one-page stand demo.

Tab 1: toggle new centres on a map of Devon and watch travel times change.
Tab 2: watch a computer try every combination, then see that the "best" answer
depends on what you ask it to optimise.
"""

import random
from pathlib import Path

import streamlit as st

from core import (
    MAX_NEW_SITES,
    MODES,
    OBJECTIVES,
    label,
    load_data,
    n_combinations,
    nearest_time,
    rank_of,
    score_all_combinations,
    summarise,
)
from animation import render_optimiser_animation
from figures import static_time_map, travel_map

st.set_page_config(page_title="Where should the next centre go?", layout="wide")
st.markdown(f"<style>{Path('style.css').read_text()}</style>", unsafe_allow_html=True)

data = load_data()
DEFAULT_CUTOFF = {"car": 45, "pt": 90}

st.session_state.setdefault("mode", "car")
st.session_state.setdefault("cutoff", DEFAULT_CUTOFF["car"])
st.session_state.setdefault("view", "cutoff")
st.session_state.setdefault("new_sites", [])


def on_mode_change():
    st.session_state.cutoff = DEFAULT_CUTOFF[st.session_state.mode or "car"]
    st.session_state.optimiser_ran = False


def clear_sites():
    st.session_state.new_sites = []
    st.session_state.optimiser_ran = False


def surprise_me():
    st.session_state.new_sites = [random.choice(data.candidates)]
    st.session_state.optimiser_ran = False


def delta_kwargs(diff, unit, decimals, show, comma=False):
    """st.metric delta arguments where lower is better; a zero change reads as neutral."""
    if not show:
        return {}
    if round(diff, decimals) == 0:
        return {"delta": "no change", "delta_color": "off"}
    fmt = f"{{:+{',' if comma else ''}.{decimals}f}}"
    return {"delta": fmt.format(diff) + unit, "delta_color": "inverse"}


def on_sites_change():
    st.session_state.optimiser_ran = False


st.title("Where should the next diagnostic centre go?")
st.markdown(
    "Devon has **4 community diagnostic centres**. You have budget for more. "
    "Pick where they go, and see who still has a long journey."
)

tab_build, tab_opt = st.tabs(["1 · You choose", "2 · Watch the optimiser"])

# ---------------------------------------------------------------- tab 1
with tab_build:
    map_col, ctrl_col = st.columns([3, 2], gap="large")

    # Controls are drawn first (they write session state), then the map reads it
    with ctrl_col:
        st.segmented_control(
            "How do people travel?",
            list(MODES),
            format_func=MODES.get,
            key="mode",
            on_change=on_mode_change,
            selection_mode="single",
        )
        st.pills(
            f"Add up to {MAX_NEW_SITES} new centres",
            data.candidates,
            format_func=lambda i: data.short_names[i],
            selection_mode="multi",
            key="new_sites",
            on_change=on_sites_change,
        )
        if len(st.session_state.new_sites) > MAX_NEW_SITES:
            st.warning(
                f"The budget stretches to {MAX_NEW_SITES} new centres - untick one to swap."
            )
        b1, b2 = st.columns(2)
        b1.button(
            "Start again", on_click=clear_sites, width="stretch", icon=":material/restart_alt:"
        )
        b2.button(
            "Surprise me", on_click=surprise_me, width="stretch", icon=":material/casino:"
        )

        st.slider("How long is too long to travel? (minutes)", 15, 120, step=5, key="cutoff")
        st.segmented_control(
            "Map shows",
            ["cutoff", "time"],
            key="view",
            selection_mode="single",
            format_func={"cutoff": "Who is too far", "time": "Journey time"}.get,
        )

    mode = st.session_state.mode or "car"
    cutoff = st.session_state.cutoff
    view = st.session_state.view or "cutoff"
    new_sites = tuple(sorted(st.session_state.new_sites[:MAX_NEW_SITES]))
    has_new = bool(new_sites)

    today = summarise(data, nearest_time(data, mode), cutoff)
    now = summarise(data, nearest_time(data, mode, new_sites), cutoff)

    with ctrl_col:
        with st.container(key="headline"):
            st.metric(
                f"People aged 50-84 more than {cutoff} min from a centre",
                f"{now['beyond']:,.0f}",
                **delta_kwargs(now["beyond"] - today["beyond"], " vs today", 0, has_new, comma=True),
            )
        m1, m2 = st.columns(2)
        m1.metric(
            "Average journey",
            f"{now['avg']:.1f} min",
            **delta_kwargs(now["avg"] - today["avg"], " min", 1, has_new),
        )
        m2.metric(
            "Longest journey",
            f"{now['worst']:.0f} min",
            **delta_kwargs(now["worst"] - today["worst"], " min", 0, has_new),
        )
        if not has_new:
            st.caption("Showing today's network. Tap a town above to add a centre.")

    with map_col:
        st.plotly_chart(
            travel_map(data, mode, new_sites, cutoff, view),
            key="main_map",
            width="stretch",
            config={"displayModeBar": False},
        )
        if view == "time":
            st.caption("Hover over an area to see its journey time.")
        else:
            st.caption(f"Red areas are more than {cutoff} minutes from the nearest centre.")

# ---------------------------------------------------------------- tab 2
with tab_opt:
    if not has_new:
        st.info("Choose at least one new centre on the first tab, then come back here.")
    else:
        n_new = len(new_sites)
        scores = score_all_combinations(mode, n_new, float(cutoff))
        n_total = len(scores)
        st.markdown(
            f"You chose **{label(data, new_sites)}**. Is that the best place? "
            f"There are **{n_total:,}** ways to place {n_new} new "
            f"centre{'s' if n_new > 1 else ''} - a computer can try them all."
        )
        if st.button("Run the optimiser", icon=":material/rocket_launch:", type="primary"):
            st.session_state.optimiser_ran = True

        if st.session_state.get("optimiser_ran"):
            render_optimiser_animation(data, mode, scores, "avg")

            st.subheader("But 'best' depends on what you ask")
            st.markdown(
                "The animation scored every option on *average journey time*. "
                "Ask a different question and a different place can win."
            )
            keys = list(OBJECTIVES)
            for col, key in zip(st.columns(len(keys)), keys):
                title, _unit, blurb = OBJECTIVES[key]
                winner = scores.loc[scores[key].idxmin()]
                yours = rank_of(scores, new_sites, key)
                with col.container(border=True):
                    st.caption(title)
                    st.markdown(
                        f"<div class='champion-name'>{label(data, winner['sites'])}</div>",
                        unsafe_allow_html=True,
                    )
                    st.markdown(blurb)
                    st.markdown(
                        f"Your pick: **#{yours}** of {n_total:,}" + (" 🏆" if yours == 1 else "")
                    )

            pick_key = (
                st.segmented_control(
                    "Compare your pick with the winner on...",
                    keys,
                    default="avg",
                    format_func=lambda k: OBJECTIVES[k][0],
                )
                or "avg"
            )
            winner_sites = scores.loc[scores[pick_key].idxmin(), "sites"]
            left, right = st.columns(2)
            left.subheader("Your pick")
            left.plotly_chart(
                static_time_map(data, mode, new_sites),
                key="map_yours",
                width="stretch",
                config={"displayModeBar": False},
            )
            right.subheader(f"Best for: {OBJECTIVES[pick_key][0].lower()}")
            right.plotly_chart(
                static_time_map(data, mode, winner_sites),
                key="map_winner",
                width="stretch",
                config={"displayModeBar": False},
            )

            st.subheader("Why computers?")
            n_cand = len(data.candidates)
            for col, (n, text) in zip(
                st.columns(4),
                [
                    (n_combinations(n_cand, 1), "ways to add 1 centre"),
                    (n_combinations(n_cand, 2), "ways to add 2"),
                    (n_combinations(n_cand, 3), "ways to add 3"),
                    (n_combinations(100, 5), "ways to pick 5 from 100 sites"),
                ],
            ):
                col.markdown(
                    f"<div class='big-number'>{n:,}</div>"
                    f"<div class='big-number-label'>{text}</div>",
                    unsafe_allow_html=True,
                )
            st.caption(
                "Real location problems are far bigger than this one, and have many "
                "competing goals. Optimisation software searches them for you and shows "
                "the trade-offs."
            )
