"""Where should the next diagnostic centre go? A one-page stand demo.

Tab 1: toggle new centres on a map of Devon and watch travel times change.
Tab 2: watch a computer try every combination, then see that the "best" answer
depends on what you ask it to optimise.
Tab 3: weigh several questions at once and see which options nothing else beats.
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
    n_tied,
    nearest_shares,
    nearest_time,
    rank_of,
    score_all_combinations,
    summarise,
)
import pareto
from animation import render_optimiser_animation
from mobile_nav import add_mobile_nav
from figures import (
    MAP_ZOOM_CONFIG,
    compare_map,
    diminishing_returns_chart,
    journey_chart,
    travel_map,
)

HSMA_URL = "https://hsma.co.uk"
FULL_PLAYGROUND_URL = "https://github.com/hsma-programme/geographic_or_ds_playground"
CODE_URL = "https://github.com/hsma-programme/geographic_playground_mini"

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
    "deprived": "Journey time for most deprived areas only",
    "gain": "Who gets a quicker journey",
    "nearest": "Closest centre",
}

# Tab 2's comparison maps: the tab 1 view that shows each optimiser question best
OBJECTIVE_VIEW = {
    "avg": "time",
    "beyond": "cutoff",
    "deprived": "deprived",
    "worst": "time",
}
_TIME_CAPTION = "Colours show the journey time to the nearest centre, from quick (teal) to slow (red)."
COMPARE_CAPTIONS = {
    "avg": _TIME_CAPTION,
    "beyond": "Red areas are more than {cutoff} minutes from the nearest centre.",
    "deprived": "Only the most deprived third of areas are coloured, from quick (teal) to slow (red).",
    "worst": _TIME_CAPTION
    + " The black outline marks the area with the longest journey.",
}
# Score under each comparison map, how much better the winner is, and the rounding for both
COMPARE_SCORES = {
    "avg": ("{:.1f} min average journey", "{:.1f} min shorter", 1),
    "beyond": ("{:,.0f} people over {cutoff} min away", "{:,.0f} fewer people", 0),
    "deprived": (
        "{:.1f} min average journey in the most deprived areas",
        "{:.1f} min shorter",
        1,
    ),
    "worst": ("{:.1f} min longest journey", "{:.1f} min shorter", 1),
}

# Tab 3's "How to read this chart" box: one step per numbered badge on the example chart
GUIDE_STEPS = {
    "radar": [
        (
            "<b>Each shape is one option.</b> Further from the centre is always better, "
            "even for questions where less is better, like fewer people far away."
        ),
        (
            "<b>A point shows how an option scores, and what it's best and worst at.</b> Option A reaches furthest on "
            "question 1 but is close to the centre on question 3. Option B is the opposite. "
            "Neither wins on everything: that's the trade-off."
        ),
        (
            "<b>Your pick is the yellow dashed shape.</b> Here it sits inside Option B's shape, "
            "so B is better on every question and your pick can be ruled out. A bigger shape "
            "isn't automatically better: only one that sits inside another is beaten."
        ),
    ],
    "lines": [
        (
            "<b>Each line is one option.</b> Higher up is always better, "
            "even for questions where less is better, like fewer people far away."
        ),
        (
            "<b>A peak shows what an option is best at.</b> Option A is top on question 1 "
            "but bottom on question 3. Option B is the opposite. "
            "Neither wins on everything: that's the trade-off."
        ),
        (
            "<b>Your pick is the yellow dashed line.</b> Here it is below Option B on every "
            "question, so your pick can be ruled out. The faint grey lines are the other "
            "options that can be ruled out."
        ),
    ],
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


def clear_sites():
    st.session_state.new_sites = []
    st.session_state.optimiser_ran = False


def go_to_tab(label):
    """Switch tab from a button; the new tab would otherwise open at the old scroll position."""
    st.session_state.page = label
    st.session_state.scroll_to_top = True


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


def rank_colour(rank, total):
    """Green for the best rank, through amber, to red for the worst."""
    frac = (rank - 1) / max(total - 1, 1)
    return f"hsl({120 * (1 - frac):.0f}, 70%, 55%)"


def other_options(n):
    return f"{n} other option{'s' if n > 1 else ''}"


def number_boxes(items):
    """A row of big numbers, each with a label underneath: [(number, label html), ...]."""
    boxes = "".join(
        f"<div class='result-line'><div class='big-number'>{n:,}</div>"
        f"<div class='big-number-label'>{text}</div></div>"
        for n, text in items
    )
    st.markdown(f"<div class='result-box'>{boxes}</div>", unsafe_allow_html=True)


def render_what_if(mode, cutoff, demand, view, n_chosen):
    """Diminishing returns: what each extra centre adds, on the measure the map is showing."""
    best = best_by_count(mode, float(cutoff), demand)
    st.subheader("Extra: how many centres would be enough?")
    if view == "cutoff" and best["beyond"][0] == 0:
        st.markdown("**What if the budget were bigger?**")
        st.caption(
            f"Nobody is more than {cutoff} minutes from a centre today, so extra centres "
            "can't help on this measure."
        )
        return
    if view == "cutoff":
        series = best["beyond"]
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
        whose = (
            "the average journey in the most deprived areas"
            if view == "deprived"
            else "the average journey"
        )
        say = lambda g: f"{whose} by {g:.1f} min"
        say_last = lambda g: f"it by a further {g:.1f} min"
    else:
        series = best["helped"]
        gains = [series[i] - series[i - 1] for i in range(1, len(series))]
        y_title = "Extra people helped"
        fmt = lambda g: f"{g / 1000:.0f}k"
        say = lambda g: f"{round(g, -2):,.0f} people a closer centre"
        say_last = lambda g: f"{round(g, -2):,.0f} more people a closer centre"

    verb = {
        "cutoff": "brings",
        "time": "cuts",
        "deprived": "cuts",
        "gain": "gives",
        "nearest": "gives",
    }[view]
    # Each bar compares the best k sites with the best k + 1, which needn't share any
    # sites, so the text talks about how many centres rather than which one to open next
    first = f"Adding one new centre, in the best place for this measure, {verb} {say(gains[0])}."
    nonzero = [i for i, g in enumerate(gains) if round(g, -2) > 0 and g >= 50]
    if view == "cutoff" and len(nonzero) < len(gains):
        k = nonzero[-1]
        no_benefit = (
            " After that, there is no benefit on this measure to adding more centres."
        )
        later = (
            f" Going from {k} to {k + 1} new centres {verb} {say_last(gains[k])}.{no_benefit}"
            if k
            else no_benefit
        )
    else:
        k = len(gains) - 1
        later = f" Going from {k} to {k + 1} new centres {verb} {say_last(gains[k])}."

    # Text beside the chart; the reflow_stack_ key stacks them on narrower screens
    text_col, chart_col = st.container(key="reflow_stack_what_if").columns(
        [2, 3], gap="large"
    )
    with text_col:
        st.markdown(
            "**What if the budget were bigger?** This steps back from the towns you picked. "
            f"For each number of new centres, from 1 to {len(gains)}, the computer found the "
            "best places for what the map is showing, and each bar is how much that extra "
            f"centre adds. Your budget covers {MAX_NEW_SITES} (the solid bars); the faded bars "
            "show what more money would buy."
        )
        st.markdown(
            "The bar outlined in yellow is where you are now: "
            f"**{n_chosen} new centre{'s' if n_chosen > 1 else ''}**."
            if n_chosen
            else "Pick some centres and the bar for how many you've chosen is outlined in yellow."
        )
        st.markdown(first + later)
    chart_col.plotly_chart(
        diminishing_returns_chart(gains, n_chosen, MAX_NEW_SITES, y_title, fmt),
        key="what_if",
        width="stretch",
        config={"displayModeBar": False},
    )
    chart_col.caption(
        "Each bar uses the best choice of sites for this measure, which may not be the towns you picked."
    )


def on_sites_change():
    st.session_state.optimiser_ran = False


# Map traces that can be tapped: possible new centres, and your new centres (outline and dot)
TAPPABLE_TRACES = {2, 3, 4}


def on_map_click(key):
    """Tapping a site on the map adds it, or removes it if already chosen."""
    # Read the map that was tapped: a quick second tap can land on the previous map
    # before the rerun replaces it, by which point map_taps has already moved on
    points = st.session_state[key].selection.points
    tapped = [p["customdata"] for p in points if p["curve_number"] in TAPPABLE_TRACES]
    st.session_state.map_taps += 1
    if not tapped:
        return
    site = tapped[0]
    sites = st.session_state.new_sites
    st.session_state.new_sites = (
        [s for s in sites if s != site] if site in sites else sites + [site]
    )
    st.session_state.optimiser_ran = False


def on_question_change(row):
    """Tab 3 allows MAX_QUESTIONS questions across all rows; a tap past that is undone."""
    state = st.session_state
    if sum(len(state[f"pareto_{r}"]) for r in pareto.ROWS) > pareto.MAX_QUESTIONS:
        state[f"pareto_{row}"] = state[f"pareto_prev_{row}"]
        st.toast(
            f"You can weigh up to {pareto.MAX_QUESTIONS} questions at once - untick one first.",
            icon="☝️",
        )
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

# Dropdown in place of the tab pills on narrower screens (shown by style.css)
add_mobile_nav()

# on_change="rerun" tracks the open tab, so the sidebar can be tab 1's alone
TAB_LABELS = ["1 · You choose", "2 · Watch the optimiser", "3 · Weigh it up"]
tab_build, tab_opt, tab_trade = st.tabs(
    TAB_LABELS,
    key="page",
    on_change="rerun",
)

# Controls are drawn first (they write session state), then the maps read it
with st.sidebar:
    # Mode, cutoff and demand only mean something on tab 1. Tab 3 follows them;
    # tab 2 ignores them (it is always car, a 45-minute cutoff and today's population).
    # persist_state keeps their values while they aren't drawn
    if tab_build.open:
        # NIHR logo, directly under the HSMA logo in the sidebar header
        # Keyed so style.css can hide the image's hover "fullscreen" button
        with st.container(key="nihr_logo"):
            st.image(
                "resources/NIHR_APPLIED_RESEARCH_COLLABORATION_Logo_Horizontal_RGB_WHITE.png",
                width="stretch",
                link="https://arc-sw.nihr.ac.uk/",
            )
        # Picking towns is the main action, so it comes first
        st.subheader("Your new centres")
        st.pills(
            f"Add up to {MAX_NEW_SITES} new centres",
            data.candidates,
            format_func=lambda i: data.short_names[i],
            selection_mode="multi",
            key="new_sites",
            on_change=on_sites_change,
            persist_state="page",
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

        st.divider()
        st.subheader("What the map shows")
        st.caption(
            "Each option colours the map with a different set of information. "
            "It doesn't change your centres."
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
            if (
                radio_mode == st.session_state.mode
                and st.session_state.view == "cutoff"
            ):
                st.slider(
                    "How long is too long to travel? (minutes)",
                    15,
                    120,
                    step=5,
                    key="cutoff",
                    persist_state="page",
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
            label_visibility="collapsed",
            persist_state="page",
        )
        st.caption(
            "This doesn't change the map colours. Use it together with the options above: "
            "it changes the numbers and the charts."
        )

# ---------------------------------------------------------------- tab 1
with tab_build:
    st.markdown(
        """
        ### Where should the next diagnostic centre go?

        In this imaginary version of Devon there are **4 community diagnostic centres**,
        and **you have budget for up to 3 more**.
        Commissioners have asked you to improve access for those aged 50-84 specifically,
        so those are the population numbers used.

        This is called *what-if analysis* - trying out options on a computer
        <span style="color:#ffe600;font-weight:700">to see what would happen before any decision is made</span>.
        """,
        unsafe_allow_html=True,
    )
    st.info(
        "Tap a grey dot on the map, or a town in the list on the left, to open a centre there, "
        'and watch the red "too far" areas shrink.',
        icon=":material/touch_app:",
    )

    # The town list is in the sidebar, so this column is just the results
    map_col, results_col = st.columns([3, 2], gap="large")

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

    with results_col:
        with st.container(key="headline"):
            st.metric(
                # Shorter ending in 2036 so the label still fits on one line
                f"{who} more than {cutoff} min "
                + ("away" if demand == "2036" else "from a centre"),
                f"{now['beyond']:,.0f}",
                **delta_kwargs(
                    now["beyond"] - today["beyond"],
                    " vs today's centres",
                    0,
                    has_new,
                    comma=True,
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
            st.caption(
                "Showing today's network. Tap a grey dot or a town on the left to add a centre."
            )

        st.markdown("**How long people travel**")
        st.plotly_chart(
            journey_chart(mode, today_times, now_times, people, cutoff, has_new),
            key="journey_chart",
            width="stretch",
            config={"displayModeBar": False},
        )
        st.caption(
            "Each point is people grouped by journey time, so the higher the line, the more people. "
            "The further to the left the area under the line sits, the better: it means shorter journeys. "
            f"The red part is over {cutoff} minutes."
            + (" The grey line is today's centres." if has_new else "")
        )

    with map_col:
        if view == "time":
            map_note = "Hover over an area to see its journey time."
        elif view == "deprived":
            map_note = "Only the most deprived third of areas are coloured. Hover to see a journey time."
        elif view == "gain":
            map_note = (
                "Darker areas gain more minutes from your new centres; uncoloured areas are no quicker."
                + ("" if has_new else " Add a centre to see who gains.")
            )
        elif view == "nearest":
            shares = nearest_shares(data, mode, new_sites, demand)
            busiest = max(shares, key=shares.get)
            map_note = (
                "Each colour is the area closest to one centre - warm colours are your new ones. "
                f"The busiest centre is {busiest}, with {shares[busiest]:.0%} of patients. "
                "Hover over an area to see which."
            )
        else:
            map_note = (
                f"Red areas are more than {cutoff} minutes from the nearest centre."
            )
        st.caption(map_note + " Click and drag to move the map.")
        map_key = f"main_map_{st.session_state.map_taps}"
        st.plotly_chart(
            travel_map(
                data,
                mode,
                tapped_sites,
                cutoff,
                view,
                selectable=True,
                demand=demand,
                legend=True,
            ),
            key=map_key,
            width="stretch",
            config=MAP_ZOOM_CONFIG,
            on_select=lambda key=map_key: on_map_click(key),
            selection_mode="points",
        )

    st.divider()
    # The main way on, so it comes straight after the results; the extra panel sits below it
    with st.container(key="next_step"):
        st.markdown(
            f"### Is {label(data, new_sites)} the best place?\nLet a computer try every option."
            if has_new
            else "### Pick a new centre on the map\nThen see if a computer can beat it."
        )
        st.button(
            "Watch the optimiser",
            key="go_to_optimiser",
            icon=":material/arrow_forward:",
            type="primary",
            disabled=not has_new,
            on_click=go_to_tab,
            args=(TAB_LABELS[1],),
        )
        st.caption(
            "Or scroll down for an extra: how many centres would be enough?",
        )

    st.divider()
    render_what_if(mode, cutoff, demand, view, len(new_sites))

# ---------------------------------------------------------------- tab 2
with tab_opt:
    if not has_new:
        st.info("Choose at least one new centre on the first tab, then come back here.")
    else:
        # Fixed, so the optimiser always asks the same simple question; tab 3 explores others
        opt_mode, opt_cutoff, opt_demand = "car", DEFAULT_CUTOFF["car"], "today"
        n_new = len(new_sites)
        scores = score_all_combinations(opt_mode, n_new, float(opt_cutoff), opt_demand)
        n_total = len(scores)
        st.markdown(
            f"You chose **{label(data, new_sites)}**. Is that the best place? "
            f"There are **{n_total:,}** ways to place {n_new} new "
            f"centre{'s' if n_new > 1 else ''} - a computer can try them all.\n\n"
            "This is called *location optimisation* - a computer "
            "<span style='color:#ffe600;font-weight:700'>checks every option and finds the best one "
            "for the goal you choose</span>.",
            unsafe_allow_html=True,
        )
        st.caption(
            f"Every option is scored on average journey time {pareto.MODE_NAME[opt_mode]} for "
            "people aged 50-84. Don't think that's the most important thing to score on? "
            "Don't worry - we'll explore alternatives later."
        )
        if st.button(
            "Run the optimiser", key="run_optimiser", icon=":material/rocket_launch:"
        ):
            st.session_state.optimiser_ran = True

        if st.session_state.get("optimiser_ran"):
            render_optimiser_animation(data, opt_mode, scores, "avg")

            st.subheader("But 'best' depends on what you ask")
            st.markdown(
                "The animation scored every option on *average journey time*. "
                "Ask a different question and a different place can win."
            )
            st.caption(f"All the questions and maps below use journey times {pareto.MODE_NAME[opt_mode]}.")
            keys = list(OBJECTIVES)
            # The cutoff only matters to the 'far away' question, so it is named only there
            titles = {k: OBJECTIVES[k][0] for k in keys} | {
                "beyond": f"Fewest people over {opt_cutoff} min away"
            }
            # The keyed containers here and below let style.css wrap these rows
            # onto more lines on narrower screens
            for col, key in zip(
                st.container(key="reflow_halves_questions").columns(len(keys)), keys
            ):
                title, blurb = titles[key], OBJECTIVES[key][2]
                winner = scores.loc[scores[key].idxmin()]
                yours = rank_of(scores, new_sites, key)
                # Ties are exact and common on the longest journey, so say so rather than pick one
                winner_ties = n_tied(scores, winner["sites"], key)
                with col.container(border=True):
                    st.caption(title)
                    st.markdown(
                        f"<div class='champion-name'>{label(data, winner['sites'])}</div>",
                        unsafe_allow_html=True,
                    )
                    if winner_ties:
                        st.caption(f"Tied for best with {other_options(winner_ties)}")
                    st.markdown(blurb)
                    your_ties = n_tied(scores, new_sites, key)
                    st.markdown(
                        f"Your pick: <b style='color:{rank_colour(yours, n_total)}'>"
                        f"{'joint ' if your_ties else ''}#{yours}</b> "
                        f"of {n_total:,}" + (" 🏆" if yours == 1 else ""),
                        unsafe_allow_html=True,
                    )
                    if your_ties:
                        st.caption(f"Tied with {other_options(your_ties)}")

            pick_key = (
                st.segmented_control(
                    "Compare your pick with the winner on...",
                    keys,
                    default="avg",
                    format_func=titles.get,
                )
                or "avg"
            )
            winner_sites = scores.loc[scores[pick_key].idxmin(), "sites"]
            # Both maps use the tab 1 view that shows the chosen question
            compare_view = OBJECTIVE_VIEW[pick_key]
            outline_worst = pick_key == "worst"
            st.caption(COMPARE_CAPTIONS[pick_key].format(cutoff=opt_cutoff))
            score_fmt, gain_fmt, decimals = COMPARE_SCORES[pick_key]
            your_score = scores.loc[
                [s == new_sites for s in scores["sites"]], pick_key
            ].iloc[0]
            win_score = scores[pick_key].min()
            gain = round(your_score - win_score, decimals)
            your_ties = n_tied(scores, new_sites, pick_key)
            if winner_sites == new_sites:
                vs_yours = "This is your pick 🏆"
            elif your_score == win_score:
                vs_yours = "Tied with your pick" + (
                    f" and {other_options(your_ties - 1)}" if your_ties > 1 else ""
                ) + " 🏆"
            elif gain == 0:
                vs_yours = "The same as your pick"
            else:
                vs_yours = gain_fmt.format(gain).capitalize() + " than your pick"
            # Score in bold, then one smaller line on each side, so the two maps stay level
            left, right = st.container(key="reflow_stack_compare_maps").columns(2)
            left.subheader("Your pick")
            left.markdown(f"**{score_fmt.format(your_score, cutoff=opt_cutoff)}**")
            left.caption(
                f"#{rank_of(scores, new_sites, pick_key)} of {n_total:,} on this question"
                + (f", tied with {other_options(your_ties)}" if your_ties else "")
            )
            left.plotly_chart(
                compare_map(
                    data, opt_mode, new_sites, compare_view, opt_cutoff, outline_worst
                ),
                key="map_yours",
                width="stretch",
                config={"displayModeBar": False},
            )
            title = titles[pick_key]
            # "Best for the most deprived areas" already starts with "Best for"
            right.subheader(
                title if title.startswith("Best for") else f"Best for: {title.lower()}"
            )
            right.markdown(f"**{score_fmt.format(win_score, cutoff=opt_cutoff)}**")
            right.caption(vs_yours)
            right.plotly_chart(
                compare_map(
                    data,
                    opt_mode,
                    winner_sites,
                    compare_view,
                    opt_cutoff,
                    outline_worst,
                ),
                key="map_winner",
                width="stretch",
                config={"displayModeBar": False},
            )

            st.subheader("Why computers?")
            n_cand = len(data.candidates)
            number_boxes(
                [
                    (
                        n_combinations(n_cand, 1),
                        f"ways to add 1 centre<br>from {n_cand} site options",
                    ),
                    (
                        n_combinations(n_cand, 2),
                        f"ways to add 2 centres<br>from {n_cand} site options",
                    ),
                    (
                        n_combinations(n_cand, 3),
                        f"ways to add 3 centres<br>from {n_cand} site options",
                    ),
                    (
                        n_combinations(100, 5),
                        "ways to add 5 centres<br>from 100 site options",
                    ),
                ]
            )
            st.caption(
                "Real location problems can be far bigger than this one, and can have many "
                "competing goals. Optimisation software searches them for you and shows "
                "the trade-offs."
            )
            st.divider()
            st.markdown(
                "**Real decisions weigh several questions at once.** "
                "See which options come out on top when you do."
            )
            st.button(
                "Weigh up the trade-offs",
                key="to_trade",
                on_click=go_to_tab,
                args=(TAB_LABELS[2],),
                icon=":material/arrow_forward:",
                type="primary",
            )

# ---------------------------------------------------------------- tab 3
with tab_trade:
    if not has_new:
        st.info("Choose at least one new centre on the first tab, then come back here.")
    else:
        st.markdown(
            """
            ### There's rarely one best answer

            Most ways of placing your centres can be ruled out, because another way does
            at least as well on every question you care about. The few left are trade-offs:
            to do better on one question, you'd have to do worse on another. Choosing between
            them is a judgement for people, not computers.
            """
        )
        qs = pareto.questions(cutoffs)
        n_default = sum(len(v) for v in pareto.DEFAULT_QUESTIONS.values())
        st.info(
            f"**Which questions matter to you?** Tap to pick up to {pareto.MAX_QUESTIONS}. "
            f"We've picked {n_default} to get you started, so you can look at the "
            "results below straight away, or swap in your own.",
            icon=":material/touch_app:",
        )
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
                f"<div class='big-number'>{n_front:,}<span class='big-number-of'> of {n_total:,} options "
                + ("can't be ruled out" if n_front == 1 else "are defensible choices")
                + " on the questions you picked</span></div>"
                + (
                    "<div class='front-meaning'>It's at least as good as every other option on "
                    "every question you picked, so it's the clear choice.</div>"
                    if n_front == 1
                    else "<div class='front-meaning'><b>None of them can be ruled out</b>: no other option "
                    "is <i>at least as good</i> on every question and <i>better on at least one</i>.</div>"
                )
                + (
                    f"<div class='pick-made'>...and your pick, {label(data, new_sites)}, "
                    "is one of them 🏆</div>"
                    if beater is None
                    else f"<div class='pick-missed'>...but your pick, {label(data, new_sites)}, "
                    "isn't one of them</div>"
                )
                + "</div></div>",
                unsafe_allow_html=True,
            )
            if beater is not None:
                verdict_col, table_col = st.container(key="reflow_stack_verdict").columns(
                    [2, 3], vertical_alignment="center"
                )
                verdict_col.warning(
                    f"**{beater}** is at least as good as your pick, {label(data, new_sites)}, "
                    "on every question you picked, and better on at least one."
                )
                table_col.table(pareto.compare_table(ss, keys, new_sites))

            st.markdown("### Compare the options question by question")
            st.markdown(
                "Ordinary charts struggle with this. A bar chart can show one question at a time, "
                "and a scatter plot two. Questions can also be measured in different ways - "
                "minutes, numbers of people, percentages - and over very different ranges. So these "
                "charts put every question side by side, each on its own scale from worst to best."
            )
            can_radar = len(keys) >= 3
            if can_radar:
                view = (
                    st.segmented_control(
                        "Show as",
                        ["Shapes", "Lines"],
                        default="Shapes",
                        key="pareto_view",
                    )
                    or "Shapes"
                )
            else:
                view = "Lines"
                st.caption(
                    "Shapes need at least three questions, so this is shown as lines."
                )
            kind = "radar" if view == "Shapes" else "lines"
            # Starts open; a presenter can close it once a visitor has the idea
            with st.expander(
                "How to read this chart", expanded=True, key="chart_guide", icon=":material/help:"
            ):
                example_col, steps_col = st.container(key="reflow_stack_guide").columns(
                    [4, 5], vertical_alignment="center"
                )
                example_col.plotly_chart(
                    pareto.guide_chart(kind),
                    key=f"guide_{kind}",
                    width="content",
                    config={"staticPlot": True},
                )
                example_col.caption("A made-up example with three questions.")
                steps_col.markdown(
                    "\n".join(
                        f"<div class='guide-step'><span class='guide-num'>{n}</span><div>{text}</div></div>"
                        for n, text in enumerate(GUIDE_STEPS[kind], start=1)
                    ),
                    unsafe_allow_html=True,
                )
            st.plotly_chart(
                pareto.trade_off_chart(ss, keys, new_sites, kind),
                key=f"pareto_{kind}",
                width="stretch",
                config={"displayModeBar": False},
            )
            # Under the key, which sits on the right of the chart
            st.columns([2, 1])[1].caption(
                "**Using the key:** it lists every option that can't be ruled out. To start with, only "
                "the ones that win on at least one of your questions are switched on (their names say "
                '"wins on ..."), plus your pick if it is one of them. Tap a name in the key to show or '
                "hide it, or double-tap one to see it on its own."
            )

            st.subheader("Too many to check by hand")
            n_new = len(new_sites)
            n_options = n_combinations(len(data.candidates), n_new)
            n_pairs = n_options * (n_options - 1) // 2
            number_boxes(
                [
                    (
                        n_options,
                        (
                            f"ways to add {n_new} centre{'s' if n_new > 1 else ''}"
                            f"<br>from {len(data.candidates)} site options"
                        ),
                    ),
                    (n_pairs, "pairs of options<br>to compare"),
                    (
                        n_pairs * len(keys),
                        f"comparisons for the<br>{len(keys)} questions you picked",
                    ),
                ]
            )
            st.markdown(
                "This is called *multi-objective optimisation*. With one question, a computer can simply "
                "put every option in order. With several there is no single order, so "
                "<span style='color:#ffe600;font-weight:700'>every option has to be checked against every "
                "other on every question</span> - easy for a computer, far too much to do by hand.",
                unsafe_allow_html=True,
            )
# ---------------------------------------------------------------- footer
st.divider()

footer_qr, footer_text = st.columns([1, 5], vertical_alignment="center")

footer_qr.image("resources/hsma_qr.png", width=130)

footer_text.markdown(
    f"""
    **Want to learn how to build tools like this?**

    The Health Service Modelling Associates (HSMA) programme trains people working in
    health and social care in modelling, geographic
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

if st.session_state.pop("scroll_to_top", False):
    st.html(
        "<script>setTimeout(function () {"
        "var m = document.querySelector('[data-testid=\"stMain\"]'); if (m) m.scrollTo(0, 0);"
        "window.scrollTo(0, 0);}, 100);</script>",
        unsafe_allow_javascript=True,
    )
