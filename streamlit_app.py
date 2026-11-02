"""Where should the next diagnostic centre go? A one-page stand demo.

Tab 1: toggle new centres on a map of Devon and watch travel times change.
Tab 2: watch a computer try every combination, then see that the "best" answer
depends on what you ask it to optimise.
"""

import base64
import random
from pathlib import Path

import streamlit as st

from core import (
    DEMANDS,
    MAX_NEW_SITES,
    OBJECTIVES,
    best_by_count,
    label,
    load_data,
    n_combinations,
    nearest_shares,
    nearest_time,
    rank_of,
    score_all_combinations,
    summarise,
)
import pareto
from animation import render_optimiser_animation
from figures import diminishing_returns_chart, journey_chart, static_time_map, travel_map

HSMA_URL = "https://hsma.co.uk"
FULL_PLAYGROUND_URL = "https://github.com/Bergam0t/geographic_or_ds_playground"
CODE_URL = "https://github.com/Bergam0t/geographic_playground_mini"

st.set_page_config(
    page_title="Geographic Playground",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.logo(
    "resources/Chalky HSMA-07-wide white logo tall with tagline - new tagline.png",
    size="large",
    link=HSMA_URL,
)
st.markdown(f"<style>{Path('style.css').read_text()}</style>", unsafe_allow_html=True)

# HSMA display font for the navbar title and big button. Embedded as base64 so it
# loads without needing static file serving.
font_b64 = base64.b64encode(
    Path("resources/fonts/hsma-display/HSMADisplay-Regular.woff2").read_bytes()
).decode()
st.markdown(
    f"""<style>
    @font-face {{
        font-family: "HSMA Display";
        src: url(data:font/woff2;base64,{font_b64}) format("woff2");
    }}
    </style>""",
    unsafe_allow_html=True,
)

data = load_data()
DEFAULT_CUTOFF = {"car": 45, "pt": 90}
# map view -> sidebar label (the travel mode is in the heading above each radio)
MAP_VIEWS = {
    "time": "Journey time",
    "cutoff": "Who is too far",
    "deprived": "Most deprived areas",
    "gain": "Who gets a quicker journey",
    "nearest": "Closest centre",
}

st.session_state.setdefault("mode", "car")
st.session_state.setdefault("cutoff", DEFAULT_CUTOFF["car"])
st.session_state.setdefault("view", "cutoff")
# One radio per travel mode; choosing in one clears the other
st.session_state.setdefault("map_choice_car", ("cutoff", "car"))
st.session_state.setdefault("map_choice_pt", None)
st.session_state.setdefault("demand", "today")
st.session_state.setdefault("new_sites", [])
# Bumped after each map tap so the chart remounts with no point left selected
st.session_state.setdefault("map_taps", 0)


def on_map_choice_change(mode):
    """Switching travel mode resets the cutoff; switching only the map view keeps it."""
    other = "pt" if mode == "car" else "car"
    st.session_state[f"map_choice_{other}"] = None
    view, _ = st.session_state[f"map_choice_{mode}"]
    st.session_state.view = view
    if mode != st.session_state.mode:
        st.session_state.mode = mode
        st.session_state.cutoff = DEFAULT_CUTOFF[mode]
        st.session_state.optimiser_ran = False


def clear_sites():
    st.session_state.new_sites = []
    st.session_state.optimiser_ran = False


def surprise_me():
    n = random.randint(1, MAX_NEW_SITES)
    st.session_state.new_sites = random.sample(list(data.candidates), n)
    st.session_state.optimiser_ran = False


def delta_kwargs(diff, unit, decimals, show, comma=False):
    """st.metric delta arguments where lower is better; a zero change reads as neutral."""
    if not show:
        return {}
    if round(diff, decimals) == 0:
        return {"delta": "no change", "delta_color": "off", "delta_arrow": "off"}
    fmt = f"{{:+{',' if comma else ''}.{decimals}f}}"
    return {"delta": fmt.format(diff) + unit, "delta_color": "inverse"}


ORDINALS = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"]


def render_what_if(mode, cutoff, demand, view, n_chosen):
    """Diminishing returns: what each extra centre adds, on the measure the map is showing."""
    best = best_by_count(mode, float(cutoff), demand)
    st.subheader("What if the budget were bigger?")
    if view == "cutoff":
        series = best["beyond"]
        if series[0] == 0:
            st.caption(
                f"Nobody is more than {cutoff} minutes from a centre today, so extra centres "
                "can't help on this measure."
            )
            return
        gains = [series[i - 1] - series[i] for i in range(1, len(series))]
        y_title = f"Extra people within {cutoff} min"
        fmt = lambda g: f"{g / 1000:.1f}k" if g >= 50 else "0"
        say = lambda g: f"{round(g, -2):,.0f} more people within {cutoff} min"
        say_last = say
    elif view in ("time", "deprived"):
        series = best["deprived" if view == "deprived" else "avg"]
        gains = [series[i - 1] - series[i] for i in range(1, len(series))]
        y_title = "Minutes cut from average"
        fmt = lambda g: f"{g:.1f}"
        whose = "the average journey in the most deprived areas" if view == "deprived" else "the average journey"
        say = lambda g: f"{whose} by {g:.1f} min"
        say_last = say
    else:
        series = best["helped"]
        gains = [series[i] - series[i - 1] for i in range(1, len(series))]
        y_title = "Extra people helped"
        fmt = lambda g: f"{g / 1000:.0f}k"
        say = lambda g: f"{round(g, -2):,.0f} people a closer centre"
        say_last = say

    verb = {"cutoff": "brings", "time": "cuts", "deprived": "cuts", "gain": "gives", "nearest": "gives"}[view]
    first = f"The best 1st new centre {verb} {say(gains[0])}."
    nonzero = [i for i, g in enumerate(gains) if round(g, -2) > 0 and g >= 50]
    if view == "cutoff" and len(nonzero) < len(gains):
        k = nonzero[-1]
        no_benefit = " After that, there is no benefit on this measure to adding more centres."
        later = f" The {ORDINALS[k]} {verb} {say_last(gains[k])}.{no_benefit}" if k else no_benefit
    else:
        later = f" The {ORDINALS[-1]} {verb} {say_last(gains[-1])}."
    st.markdown(first + later)
    st.plotly_chart(
        diminishing_returns_chart(gains, n_chosen, MAX_NEW_SITES, y_title, fmt),
        key="what_if",
        width="stretch",
        config={"displayModeBar": False},
    )
    st.caption("Each bar uses the best choice of sites for this measure.")


def on_sites_change():
    st.session_state.optimiser_ran = False


# Map traces that can be tapped: possible new centres, and your new centres (outline and dot)
TAPPABLE_TRACES = {2, 3, 4}


def on_map_click():
    """Tapping a site on the map adds it, or removes it if already chosen."""
    points = st.session_state[f"main_map_{st.session_state.map_taps}"].selection.points
    tapped = [p["customdata"] for p in points if p["curve_number"] in TAPPABLE_TRACES]
    st.session_state.map_taps += 1
    if not tapped:
        return
    site = tapped[0]
    sites = st.session_state.new_sites
    st.session_state.new_sites = [s for s in sites if s != site] if site in sites else sites + [site]
    st.session_state.optimiser_ran = False


def on_question_change(row):
    """Tab 3 allows MAX_QUESTIONS questions across all rows; a tap past that is undone."""
    state = st.session_state
    if sum(len(state[f"pareto_{r}"]) for r in pareto.ROWS) > pareto.MAX_QUESTIONS:
        state[f"pareto_{row}"] = state[f"pareto_prev_{row}"]
        st.toast(f"You can weigh up to {pareto.MAX_QUESTIONS} questions at once - untick one first.", icon="☝️")
    for r in pareto.ROWS:
        state[f"pareto_prev_{r}"] = list(state[f"pareto_{r}"])


for r, default in pareto.DEFAULT_QUESTIONS.items():
    st.session_state.setdefault(f"pareto_{r}", list(default))
    st.session_state.setdefault(f"pareto_prev_{r}", list(default))

# What every tab reads (the sidebar and tab 1's widgets write it)
mode = st.session_state.mode
cutoff = st.session_state.cutoff
view = st.session_state.view
demand = st.session_state.get("demand", "today")
# Each mode has its own cutoff: tab 1's slider for the mode it is showing, the default for the other
cutoffs = {m: DEFAULT_CUTOFF[m] for m in DEFAULT_CUTOFF} | {mode: cutoff}
who = "People aged 50-84" + (" in 2036" if demand == "2036" else "")
# Tap order sets each new centre's colour on the 'closest site' map; sorted for everything else
tapped_sites = tuple(st.session_state.new_sites[:MAX_NEW_SITES])
new_sites = tuple(sorted(tapped_sites))
has_new = bool(new_sites)

# on_change="rerun" tracks the open tab, so the sidebar can be tab 1's alone
tab_build, tab_opt, tab_trade = st.tabs(
    ["1 · You choose", "2 · Watch the optimiser", "3 · Weigh it up"],
    key="page",
    on_change="rerun",
)

# Controls are drawn first (they write session state), then the maps read it
with st.sidebar:
    # Mode, cutoff and demand only mean something on tab 1; tabs 2 and 3 follow them.
    # persist_state keeps their values while they aren't drawn
    if tab_build.open:
        st.caption(
            "**Choose what the map shows.** Each option colours the map with a different "
            "set of information. Changing this will not affect the centres you have chosen."
        )
        st.space("xsmall")
        for radio_mode, heading, heading_help in [
            ("car", "By car", None),
            (
                "pt",
                "By public transport",
                "Public transport means buses and walking only - trains are not included in the data.",
            ),
        ]:
            if radio_mode == "pt":
                st.divider()
            st.subheader(heading, help=heading_help)
            st.radio(
                f"Map shows ({heading.lower()})",
                [(v, radio_mode) for v in MAP_VIEWS],
                format_func=lambda c: MAP_VIEWS[c[0]],
                key=f"map_choice_{radio_mode}",
                on_change=on_map_choice_change,
                args=(radio_mode,),
                label_visibility="collapsed",
                persist_state="page",
            )
            # The slider sits under the travel mode it applies to, in the "too far" views only
            if radio_mode == st.session_state.mode and st.session_state.view == "cutoff":
                st.slider(
                    "How long is too long to travel? (minutes)", 15, 120, step=5, key="cutoff", persist_state="page"
                )

        st.divider()
        st.subheader(
            "Demand",
            help=(
                "Today uses ONS population estimates. The 2036 figures are an illustrative projection "
                "made for teaching, not an official forecast: rural and coastal areas age faster than "
                "the cities, especially in the South Hams."
            ),
        )
        st.radio(
            "Whose journeys count",
            list(DEMANDS),
            format_func=DEMANDS.get,
            key="demand",
            on_change=on_sites_change,
            label_visibility="collapsed",
            persist_state="page",
        )
        st.caption(
            "This doesn't change the map colours. Use it together with the options above: "
            "it changes the numbers, the chart and the optimiser."
        )

# ---------------------------------------------------------------- tab 1
with tab_build:
    st.markdown(
        """
        ### Where should the next diagnostic centre go?

        Devon has **4 community diagnostic centres**, and **you have budget for up to 3 more**.
        Tap a grey dot on the map, or a town in the list, to open a centre there,
        and watch the red "too far" areas shrink.

        This is called *location optimisation* - using a computer to
        <span style="color:#ffe600;font-weight:700">test where a service should go before anything is built</span>.
        """,
        unsafe_allow_html=True,
    )

    map_col, ctrl_col = st.columns([3, 2], gap="large")

    with ctrl_col:
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
            "Start again",
            key="quick_clear",
            on_click=clear_sites,
            width="stretch",
            icon=":material/restart_alt:",
        )
        b2.button(
            "Surprise me",
            key="quick_surprise",
            on_click=surprise_me,
            width="stretch",
            icon=":material/casino:",
        )

    today_times = nearest_time(data, mode)
    now_times = nearest_time(data, mode, new_sites)
    people = data.demand[demand]
    today = summarise(data, today_times, cutoff, demand)
    now = summarise(data, now_times, cutoff, demand)
    # Anyone whose nearest centre is now quicker, whatever the time limit
    quicker = now_times < today_times
    improved = float(people[quicker].sum())
    saved = (today_times - now_times)[quicker]
    avg_saved = float((saved * people[quicker]).sum() / improved) if improved else 0.0

    with ctrl_col:
        with st.container(key="headline"):
            st.metric(
                # Shorter ending in 2036 so the label still fits on one line
                f"{who} more than {cutoff} min " + ("away" if demand == "2036" else "from a centre"),
                f"{now['beyond']:,.0f}",
                **delta_kwargs(
                    now["beyond"] - today["beyond"], " vs today's centres", 0, has_new, comma=True
                ),
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
        if has_new:
            m3, m4 = st.columns(2)
            m3.metric(
                "People helped",
                f"{improved:,.0f}",
                delta=f"{improved / people.sum():.1%} of everyone",
                delta_color="off",
                delta_arrow="off",
                help=(
                    f"{who} whose nearest centre is now quicker to reach, by any amount, "
                    "and what share of everyone aged 50-84 that is."
                ),
            )
            m4.metric(
                "Average time saved",
                f"{avg_saved:.1f} min",
                help="Average minutes saved, counting only the people helped.",
            )
        else:
            st.caption("Showing today's network. Tap a grey dot or a town to add a centre.")

        st.markdown("**How long people travel**")
        st.plotly_chart(
            journey_chart(mode, today_times, now_times, people, cutoff, has_new),
            key="journey_chart",
            width="stretch",
            config={"displayModeBar": False},
        )
        st.caption(
            "Each point is people grouped by journey time, so the higher the line, the more people. "
            f"The red part is over {cutoff} minutes."
            + (" The grey line is today's centres." if has_new else "")
        )

    with map_col:
        if view == "time":
            st.caption(
                "Hover over an area to see its journey time. "
                "Tap a dot to add or remove a centre, or use the buttons on the right."
            )
        elif view == "deprived":
            st.caption(
                "Only the most deprived third of areas are coloured. Hover to see a journey time. "
                "Tap a dot to add or remove a centre, or use the buttons on the right."
            )
        elif view == "gain":
            st.caption(
                "Darker areas gain more minutes from your new centres; uncoloured areas are no quicker. "
                "Tap a dot to add or remove a centre, or use the buttons on the right."
                + ("" if has_new else " Add a centre to see who gains.")
            )
        elif view == "nearest":
            shares = nearest_shares(data, mode, new_sites, demand)
            busiest = max(shares, key=shares.get)
            st.caption(
                "Each colour is the area closest to one centre - warm colours are your new ones. "
                f"The busiest centre is {busiest}, with {shares[busiest]:.0%} of patients. "
                "Hover over an area to see which. "
                "Tap a dot to add or remove a centre, or use the buttons on the right."
            )
        else:
            st.caption(
                f"Red areas are more than {cutoff} minutes from the nearest centre. "
                "Tap a dot to add or remove a centre, or use the buttons on the right."
            )
        st.plotly_chart(
            travel_map(data, mode, tapped_sites, cutoff, view, selectable=True, demand=demand),
            key=f"main_map_{st.session_state.map_taps}",
            width="stretch",
            config={"displayModeBar": False},
            on_select=on_map_click,
            selection_mode="points",
        )

    st.divider()
    render_what_if(mode, cutoff, demand, view, len(new_sites))

# ---------------------------------------------------------------- tab 2
with tab_opt:
    if not has_new:
        st.info("Choose at least one new centre on the first tab, then come back here.")
    else:
        n_new = len(new_sites)
        scores = score_all_combinations(mode, n_new, float(cutoff), demand)
        n_total = len(scores)
        st.markdown(
            f"You chose **{label(data, new_sites)}**. Is that the best place? "
            f"There are **{n_total:,}** ways to place {n_new} new "
            f"centre{'s' if n_new > 1 else ''} - a computer can try them all."
        )
        st.caption(
            f"Scored on journeys {pareto.MODE_NAME[mode]} for {who.lower()}, with more than "
            f"{cutoff} minutes counted as too far. You can change these on the first tab."
        )
        if st.button("Run the optimiser", key="run_optimiser", icon=":material/rocket_launch:"):
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
            boxes = "".join(
                f"<div class='result-line'><div class='big-number'>{n:,}</div>"
                f"<div class='big-number-label'>{text}</div></div>"
                for n, text in [
                    (n_combinations(n_cand, 1), "ways to add 1 centre"),
                    (n_combinations(n_cand, 2), "ways to add 2"),
                    (n_combinations(n_cand, 3), "ways to add 3"),
                    (n_combinations(100, 5), "ways to pick 5 from 100 sites"),
                ]
            )
            st.markdown(f"<div class='result-box'>{boxes}</div>", unsafe_allow_html=True)
            st.caption(
                "Real location problems are far bigger than this one, and have many "
                "competing goals. Optimisation software searches them for you and shows "
                "the trade-offs."
            )

# ---------------------------------------------------------------- tab 3
with tab_trade:
    if not has_new:
        st.info("Choose at least one new centre on the first tab, then come back here.")
    else:
        st.markdown(
            """
            ### There's rarely one best answer

            Most ways of placing your centres can be ruled out, because another way is
            better on **every** question you care about. The few left each win on
            something, so choosing between them is a judgement for people, not computers.
            """
        )
        qs = pareto.questions(cutoffs)
        st.markdown(f"**Which questions matter to you?** Pick up to {pareto.MAX_QUESTIONS}.")
        for row, row_title in pareto.ROWS.items():
            st.pills(
                row_title,
                [k for k, q in qs.items() if q.row == row],
                format_func=lambda k: qs[k].pill,
                selection_mode="multi",
                key=f"pareto_{row}",
                on_change=on_question_change,
                args=(row,),
                persist_state="page",
            )
        # In the order of the list above, not the order they were tapped
        chosen = {k for row in pareto.ROWS for k in st.session_state[f"pareto_{row}"]}
        keys = [k for k in qs if k in chosen]
        if len(keys) < 2:
            st.warning("Pick at least two questions to weigh them against each other.")
        else:
            trade_scores = pareto.question_scores(data, len(new_sites), cutoffs, demand)
            ss = pareto.solution_set(data, trade_scores, keys, qs)
            n_front, n_total, beater = pareto.verdict(ss, keys, new_sites)
            st.markdown(
                f"<div class='result-box'><div class='result-line'>"
                f"<div class='big-number'>{n_front:,}</div>"
                f"<div class='big-number-label'>of {n_total:,} options are not beaten on every "
                f"question you picked</div></div></div>",
                unsafe_allow_html=True,
            )
            if beater is None:
                st.success(f"Your pick, {label(data, new_sites)}, is one of them. 🏆")
            else:
                verdict_col, table_col = st.columns([2, 3], vertical_alignment="center")
                verdict_col.warning(
                    f"**{beater}** beats your pick, {label(data, new_sites)}, "
                    "on every question you picked."
                )
                table_col.table(pareto.compare_table(ss, keys, new_sites))

            can_radar = len(keys) >= 3
            if can_radar:
                view = st.segmented_control(
                    "Show as", ["Shapes", "Lines"], default="Shapes", key="pareto_view"
                ) or "Shapes"
            else:
                view = "Lines"
                st.caption("Shapes need at least three questions, so this is shown as lines.")
            kind = "radar" if view == "Shapes" else "lines"
            st.caption(
                ("Further from the centre" if kind == "radar" else "Higher up")
                + " is always better. Each colour is an option nothing else beats on every "
                "question; the yellow dashed line is your pick. A bigger shape is not "
                "automatically better, so compare question by question."
            )
            st.caption(
                "**Using the key:** it lists every option nothing else beats. To start with, only "
                "the ones that win on at least one of your questions are switched on (their names say "
                '"wins on ..."), plus your pick if it is one of them. Tap a name in the key to show or '
                "hide it, or double-tap one to see it on its own."
            )
            st.plotly_chart(
                pareto.trade_off_chart(ss, keys, new_sites, kind),
                key=f"pareto_{kind}",
                width="stretch",
                config={"displayModeBar": False},
            )
# ---------------------------------------------------------------- footer
st.divider()

footer_qr, footer_text = st.columns([1, 5], vertical_alignment="center")

footer_qr.image("resources/hsma_qr.png", width=130)

footer_text.markdown(
    f"""
    **Want to learn how to build tools like this?**

    HSMA trains people working in health and social care in modelling, geographic
    analysis and data science. Scan the code or visit the
    [HSMA website]({HSMA_URL}) to find out more, try the
    [full geographic playground]({FULL_PLAYGROUND_URL}), or
    [explore the code for this app]({CODE_URL}).
    """
)
footer_text.caption(
    "Population and deprivation data from the ONS (Open Government Licence); "
    "the 2036 population is an illustrative projection made for teaching. "
    "Travel times calculated from OpenStreetMap data (© OpenStreetMap contributors). "
    "Trade-off charts drawn with [lokigi](https://github.com/hsma-tools/lokigi), "
    "HSMA's open-source location package."
)
