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
    MAX_NEW_SITES,
    MODES,
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
# Biggest growth in any area's population aged 50-84 by 2036, in %. In this (fixed)
# projection it is around Kingsbridge, which the captions that use it name
GROWTH_TOP = float(100 * (data.demand["2036"] / data.demand["today"] - 1).max())
DEFAULT_CUTOFF = {"car": 45, "pt": 90}
# map view -> sidebar label (the travel mode is in the heading above each radio)
MAP_VIEWS = {
    "cutoff": "Who is too far",
    "time": "Journey time",
    "deprived": "Journey time for most deprived areas only",
    "gain": "Who gets a quicker journey",
    "nearest": "Closest centre",
}
# ("growth", "Where need grows by 2036") has its own "Looking ahead" radio in the sidebar

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
st.session_state.setdefault("map_choice_future", None)
st.session_state.setdefault("new_sites", [])
# Bumped after each map tap so the chart remounts with no point left selected
st.session_state.setdefault("map_taps", 0)

# Sidebar map radios: one per travel mode, plus "Looking ahead"; choosing in one clears the others
MAP_GROUPS = ["car", "pt", "future"]


def on_map_choice_change(group):
    """Switching travel mode resets the cutoff; switching only the map view keeps it.

    The "Looking ahead" view keeps whichever travel mode was last chosen.
    """
    for other in MAP_GROUPS:
        if other != group:
            st.session_state[f"map_choice_{other}"] = None
    view, _ = st.session_state[f"map_choice_{group}"]
    st.session_state.view = view
    if group in DEFAULT_CUTOFF and group != st.session_state.mode:
        st.session_state.mode = group
        st.session_state.cutoff = DEFAULT_CUTOFF[group]


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


def delta_kwargs(diff, unit, decimals, show, comma=False, higher_better=False):
    """st.metric delta arguments (lower is better unless higher_better); a zero change reads as neutral."""
    if not show:
        return {}
    if round(diff, decimals) == 0:
        return {"delta": "no change", "delta_color": "off", "delta_arrow": "off"}
    fmt = f"{{:+{',' if comma else ''}.{decimals}f}}"
    return {"delta": fmt.format(diff) + unit, "delta_color": "normal" if higher_better else "inverse"}


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


def render_what_if(mode, cutoff, view):
    """Diminishing returns: what each extra centre adds, on the measure the map is showing.

    Depends only on the sidebar's travel mode, map view and cutoff, never on the towns
    picked, so the text doesn't mention the visitor's picks. The 'where need grows' map
    has no measure of its own, so it uses 'who is too far', which its caption talks about.
    """
    measure = "what the map is showing"
    if view == "growth":
        view, measure = "cutoff", f"people more than {cutoff} minutes away"
    best = best_by_count(mode, float(cutoff))
    st.subheader("Extra: how many centres would be enough?")
    try_another = (
        "Try a different option under **What the map shows** on the left - car or public "
        "transport, another goal, or a different 'too far' time - and see how many centres "
        "each goal needs.\n\n:small[Your selected centres don't change this chart.]"
    )
    if view == "cutoff" and best["beyond"][0] == 0:
        st.markdown("**What if the budget were bigger?**")
        st.caption(
            f"Nobody is more than {cutoff} minutes from a centre today, so extra centres "
            "can't help on this measure."
        )
        st.info(try_another, icon=":material/tune:")
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
        y_title = (
            "Minutes cut from average<br>(most deprived areas only)"
            if view == "deprived"
            else "Minutes cut from average"
        )
        fmt = lambda g: f"{g:.1f}"
        whose = (
            "the average journey in the most deprived areas"
            if view == "deprived"
            else "the average journey"
        )
        say = lambda g: f"{whose} by {g:.1f} min"
        say_last = lambda g: f"it by a further {g:.1f} min"
    else:
        # The same measure (nearest centre now quicker), worded to match each map
        series = best["helped"]
        gains = [series[i] - series[i - 1] for i in range(1, len(series))]
        fmt = lambda g: f"{g / 1000:.0f}k"
        if view == "gain":
            y_title = "Extra people with<br>a quicker journey"
            say = lambda g: f"{round(g, -2):,.0f} people a quicker journey"
            say_last = lambda g: f"{round(g, -2):,.0f} more people a quicker journey"
        else:
            y_title = "Extra people with a<br>closer centre than before"
            say = lambda g: f"{round(g, -2):,.0f} people a closer centre than before"
            say_last = lambda g: f"{round(g, -2):,.0f} more people a closer centre than before"

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
    if view == "gain":
        saved = best["saved"][1:]
        later += (
            f" Those people save {saved[0]:.0f} minutes each on average with 1 new centre, "
            f"and {saved[-1]:.0f} minutes with {len(saved)}."
        )

    # Text beside the chart; the reflow_stack_ key stacks them on narrower screens
    text_col, chart_col = st.container(key="reflow_stack_what_if").columns(
        [2, 3], gap="large"
    )
    with text_col:
        st.markdown(
            "**What if the budget were bigger?** "
            f"For each number of new centres, from 1 to {len(gains)}, the computer found the "
            f"best places for {measure}, and each bar is how much that extra "
            "centre adds."
        )
        st.markdown(first + later)
        st.info(try_another, icon=":material/tune:")
    chart_col.plotly_chart(
        diminishing_returns_chart(gains, MAX_NEW_SITES, y_title, fmt),
        key="what_if",
        width="stretch",
        config={"displayModeBar": False},
    )
    if view == "gain":
        # A level, not a gain: what each extra centre adds can be negative (the extra
        # people helped may save less than the average so far)
        chart_col.markdown("**And how much quicker is it for them?**")
        chart_col.plotly_chart(
            diminishing_returns_chart(
                best["saved"][1:],
                MAX_NEW_SITES,
                "Average minutes saved<br>per person helped",
                lambda g: f"{g:.0f}",
            ),
            key="what_if_saved",
            width="stretch",
            config={"displayModeBar": False},
        )
        chart_col.caption(
            "Each bar is the average for that many new centres, in the places that help "
            "the most people, not what the extra centre adds."
        )
    chart_col.markdown(
        "**Is each extra centre worth what it costs?** There's rarely a clean yes or no. "
        "It depends on what a centre costs, how much each bar is worth to you, "
        "and what else that money could do."
    )


# Tab 2's fast forward re-asks these questions with the 2036 population. Not the deprived
# areas (they grow more slowly than elsewhere) or the longest journey (it ignores population)
FUTURE_QUESTIONS = ["avg", "beyond"]


def site_change(old, new):
    """'Kingsbridge comes in, Okehampton drops out' between two sets of sites."""
    came = [s for s in new if s not in old]
    went = [s for s in old if s not in new]
    names = lambda sites: " and ".join(data.short_names[i] for i in sites)
    parts = []
    if came:
        parts.append(f"{names(came)} come{'s' if len(came) == 1 else ''} in")
    if went:
        parts.append(f"{names(went)} drop{'s' if len(went) == 1 else ''} out")
    return ", ".join(parts)


def on_fast_forward(sites):
    # Remember which centres were fast-forwarded, so picking others hides the old answer
    st.session_state.fast_forward = sites


def card_title(text, mode):
    """A question's name as a tinted band across the top of its card, with the travel
    mode on a softer second line ("by car").

    Call first inside st.container(border=True, key="title_card_..."), which style.css
    needs to stretch the band to the card's edges.
    """
    st.markdown(
        f"<div class='card-title'>{text}<br><span class='by-mode'>{pareto.MODE_NAME[mode]}</span></div>",
        unsafe_allow_html=True,
    )


def render_fast_forward(scores, mode, cutoff, titles):
    """Tab 2: does the winner, and your pick's rank, hold up with the 2036 population?"""
    n_new = len(new_sites)
    today_times = nearest_time(data, mode)
    rise = summarise(data, today_times, cutoff, "2036")["beyond"] - summarise(
        data, today_times, cutoff
    )["beyond"]
    st.subheader("Will it still be best in 10 years?")
    st.markdown(
        "By 2036 there will be more people aged 50-84 in Devon, growing faster in some places "
        f"than others. If nothing changes, **{round(rise, -2):,.0f} more people** will live more "
        f"than {cutoff} minutes from a centre. Fast forward to see if the best place changes."
    )
    st.button(
        "Fast forward to 2036",
        key="fast_forward_button",
        icon=":material/fast_forward:",
        on_click=on_fast_forward,
        args=(new_sites,),
    )
    if st.session_state.get("fast_forward") != new_sites:
        return

    later = score_all_combinations(mode, n_new, float(cutoff), "2036")
    n_total = len(scores)
    map_col, cards_col = st.container(key="reflow_stack_future").columns(2, gap="large")
    with map_col:
        st.caption(
            "Darker areas will have more people aged 50-84 by 2036, "
            f"up to {GROWTH_TOP:.0f}% more around Kingsbridge."
        )
        st.plotly_chart(
            compare_map(data, mode, new_sites, view="growth"),
            key="map_growth",
            width="stretch",
            config={"displayModeBar": False},
        )
    with cards_col:
        for key in FUTURE_QUESTIONS:
            win_now = scores.loc[scores[key].idxmin(), "sites"]
            win_later = later.loc[later[key].idxmin(), "sites"]
            with st.container(border=True, key=f"title_card_ff_{key}"):
                card_title(titles[key], mode)
                st.markdown(
                    f"Best in 2026: **{label(data, win_now)}**  \n"
                    f"Best in 2036: **{label(data, win_later)}**"
                )
                if win_now == win_later:
                    st.markdown("✅ Still the best in 2036: a choice that lasts.")
                else:
                    verdict = f"🔄 Changes by 2036: {site_change(win_now, win_later)}."
                    # Minutes differences on the average are tiny, so only people are counted
                    if key == "beyond":
                        stay = [s == win_now for s in later["sites"]]
                        lost = later.loc[stay, key].iloc[0] - later[key].min()
                        if round(lost, -1) > 0:
                            verdict += (
                                f" Sticking with 2026's answer would leave {round(lost, -1):,.0f} "
                                "more people too far away in 2036."
                            )
                    st.markdown(verdict)
                r_now = rank_of(scores, new_sites, key)
                r_later = rank_of(later, new_sites, key)
                change = (
                    "no change"
                    if r_now == r_later
                    else f"up {r_now - r_later}"
                    if r_later < r_now
                    else f"down {r_later - r_now}"
                )
                st.markdown(
                    f"Your pick: <b style='color:{rank_colour(r_now, n_total)}'>#{r_now}</b> in 2026 → "
                    f"<b style='color:{rank_colour(r_later, n_total)}'>#{r_later}</b> in 2036 "
                    f"({change})" + (" 🏆" if r_later == 1 else ""),
                    unsafe_allow_html=True,
                )
    st.markdown(
        "Plans like this last for years, so "
        "<span style='color:#ffe600;font-weight:700'>it's worth checking that the answer still "
        "holds as the population changes</span>.",
        unsafe_allow_html=True,
    )


def on_growth_mode_change():
    """The 'where need grows' view's own car / public transport switch; resets the cutoff like the sidebar."""
    chosen = st.session_state.growth_mode
    if chosen != st.session_state.mode:
        st.session_state.mode = chosen
        st.session_state.cutoff = DEFAULT_CUTOFF[chosen]


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
# Each mode has its own cutoff: tab 1's slider for the mode it is showing, the default for the other
cutoffs = {m: DEFAULT_CUTOFF[m] for m in DEFAULT_CUTOFF} | {mode: cutoff}
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
    # Mode and cutoff only mean something on tab 1. Tab 3 follows them; tab 2 ignores
    # them (it is always car and a 45-minute cutoff). Every tab counts today's population;
    # 2036 appears only in the "Looking ahead" map and tab 2's fast forward.
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
            "Looking ahead",
            help=(
                "Today's numbers use ONS population estimates. The 2036 figures are an illustrative "
                "projection made for teaching, not an official forecast: rural and coastal areas age "
                "faster than the cities, especially in the South Hams."
            ),
        )
        st.radio(
            "Map shows (looking ahead)",
            [("growth", "future")],
            format_func=lambda c: "Where need grows by 2036",
            key="map_choice_future",
            on_change=on_map_choice_change,
            args=("future",),
            label_visibility="collapsed",
            persist_state="page",
        )

# ---------------------------------------------------------------- tab 1
with tab_build:
    st.markdown(
        """
        ### Where should the next diagnostic centre go?

        In this imaginary version of Devon there are **4 community diagnostic centres**,
        and you have budget for <span class="budget-pill">up to 3 more</span>.
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
    # Tab 1's numbers are for today's population, except the cards in the 'where need
    # grows' view, which show 2036 and compare each figure with 2026 for the same centres
    future = view == "growth"
    people = data.demand["today"]
    today = summarise(data, today_times, cutoff)
    now = summarise(data, now_times, cutoff)
    # Anyone whose nearest centre is now quicker, whatever the time limit
    quicker = now_times < today_times
    saved = (today_times - now_times)[quicker]

    def helped(weights):
        """(people helped, their average minutes saved) for one year's population."""
        n = float(weights[quicker].sum())
        return n, float((saved * weights[quicker]).sum() / n) if n else 0.0

    improved, avg_saved = helped(people)
    if future:
        later = summarise(data, now_times, cutoff, "2036")
        improved_later, avg_saved_later = helped(data.demand["2036"])
        # Cards: (value, what the arrow compares it with, label suffix, arrow text)
        shown, base, when, vs, show_delta = later, now, " in 2036", " vs 2026", True
    else:
        shown, base, when, vs, show_delta = now, today, "", " vs today's centres", has_new

    with results_col:
        # The growth map has no travel mode of its own (the sidebar's car and public transport
        # options are cleared), so say which one the numbers use, and let it be switched here
        if view == "growth":
            st.session_state.growth_mode = mode
            st.segmented_control(
                "Journeys",
                list(MODES),
                format_func=MODES.get,
                required=True,
                key="growth_mode",
                on_change=on_growth_mode_change,
                label_visibility="collapsed",
            )
            st.caption(
                "Fast-forwarded to 2036, for the centres on the map. "
                "The arrows show the change from 2026."
            )
        with st.container(key="headline"):
            st.metric(
                f"People aged 50-84 more than {cutoff} min from a centre{when}",
                f"{shown['beyond']:,.0f}",
                **delta_kwargs(
                    shown["beyond"] - base["beyond"], vs, 0, show_delta, comma=True
                ),
            )
        with st.container(key="stack_phone_journeys"):
            m1, m2 = st.columns(2)
        m1.metric(
            f"Average journey{when}",
            f"{shown['avg']:.1f} min",
            # No "vs 2026" here: it doesn't fit a half-width card, and the caption above says it
            **delta_kwargs(shown["avg"] - base["avg"], " min", 1, show_delta),
            # summarise() weights each area's journey by its people aged 50-84
            help="The average journey per person aged 50-84, so areas where more people live count for more."
            + (
                " That's why it changes by 2036: numbers grow fastest in areas with longer journeys."
                if future
                else ""
            ),
        )
        m2.metric(
            f"Longest journey{when}",
            f"{shown['worst']:.0f} min",
            **delta_kwargs(shown["worst"] - base["worst"], " min", 0, show_delta),
            # Only a change of centres can move it, so in 2036 it always reads "no change"
            help="The single longest journey doesn't depend on how many people live there."
            if future
            else None,
        )
        if has_new:
            with st.container(key="stack_phone_helped"):
                m3, m4 = st.columns(2)
            if future:
                m3.metric(
                    "People helped in 2036",
                    f"{improved_later:,.0f}",
                    **delta_kwargs(
                        improved_later - improved, vs, 0, True, comma=True, higher_better=True
                    ),
                    help="People aged 50-84 whose nearest centre is quicker to reach, by any amount.",
                )
                m4.metric(
                    "Average time saved in 2036",
                    f"{avg_saved_later:.1f} min",
                    **delta_kwargs(
                        avg_saved_later - avg_saved, " min", 1, True, higher_better=True
                    ),
                    help="Average minutes saved, counting only the people helped.",
                )
            else:
                m3.metric(
                    "People helped",
                    f"{improved:,.0f}",
                    delta=f"{improved / people.sum():.1%} of everyone",
                    delta_color="off",
                    delta_arrow="off",
                    help=(
                        "People aged 50-84 whose nearest centre is now quicker to reach, by any amount, "
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
        st.caption("The further left the hump sits, the shorter people's journeys.")

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
            shares = nearest_shares(data, mode, new_sites)
            busiest = max(shares, key=shares.get)
            map_note = (
                "Each colour is the area closest to one centre - warm colours are your new ones. "
                f"The busiest centre is {busiest}, with {shares[busiest]:.0%} of patients. "
                "Hover over an area to see which."
            )
        elif view == "growth":
            # People too far in 2036 minus today, for today's centres and then with the new ones
            rise = summarise(data, today_times, cutoff, "2036")["beyond"] - today["beyond"]
            rise_new = summarise(data, now_times, cutoff, "2036")["beyond"] - now["beyond"]
            map_note = (
                "Darker areas will have more people aged 50-84 by 2036, up to "
                f"{GROWTH_TOP:.0f}% more around Kingsbridge in the South Hams. "
            )
            if round(rise, -2) == 0:
                map_note += f"Even then, almost nobody would be more than {cutoff} minutes from a centre."
            else:
                map_note += (
                    f"If nothing changes, **{round(rise, -2):,.0f} more people** will live more than "
                    f"{cutoff} minutes from a centre."
                )
                if has_new:
                    map_note += (
                        f" With your new centres, that rise is **{round(rise_new, -2):,.0f}**."
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
                legend=True,
            ),
            key=map_key,
            width="stretch",
            config=MAP_ZOOM_CONFIG,
            on_select=lambda key=map_key: on_map_click(key),
            selection_mode="points",
        )
        if view == "growth":
            st.warning(
                "The 2036 population is an illustrative projection made for teaching purposes only, "
                "not an official forecast.",
                icon=":material/warning:",
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
    render_what_if(mode, cutoff, view)

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
                with col.container(border=True, key=f"title_card_q_{key}"):
                    # Mode repeated on each card: the intro above is easy to miss
                    card_title(title, opt_mode)
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
            # Shown as a pill like tab 1's metric changes: green only when the winner beats you
            vs_colour, vs_icon = "gray", None
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
                vs_colour, vs_icon = "green", ":material/arrow_downward:"
            # Score in bold, then one smaller line on each side, so the two maps stay level
            left, right = st.container(key="reflow_stack_compare_maps").columns(2)
            # Markdown headings on both sides (same spacing), so the right one can put the
            # travel mode on a softer second line
            left.markdown("### Your pick")
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
            heading = title if title.startswith("Best for") else f"Best for: {title.lower()}"
            right.markdown(
                f"### {heading}<br><span class='by-mode'>{pareto.MODE_NAME[opt_mode]}</span>",
                unsafe_allow_html=True,
            )
            right.markdown(f"**{score_fmt.format(win_score, cutoff=opt_cutoff)}**")
            right.badge(vs_yours, color=vs_colour, icon=vs_icon)
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

            render_fast_forward(scores, opt_mode, opt_cutoff, titles)

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
            # Styled like tab 1's "next_step" box, so the way on looks the same on both tabs.
            # Two ways on: tab 3, or back to tab 1 to rerun with a different number of centres
            with st.container(key="trade_step"):
                onward, again = st.container(key="reflow_stack_trade_step").columns(
                    2, gap="large"
                )
                onward.markdown(
                    "### Real decisions weigh several questions at once\n"
                    "See which options come out on top when you do."
                )
                onward.button(
                    "Weigh up the trade-offs",
                    key="to_trade",
                    on_click=go_to_tab,
                    args=(TAB_LABELS[2],),
                    icon=":material/arrow_forward:",
                    type="primary",
                )
                others = " or ".join(
                    str(k) for k in range(1, MAX_NEW_SITES + 1) if k != n_new
                )
                again.markdown(
                    "### Or try a different number of centres\n"
                    f"This time the computer placed **{n_new} new "
                    f"centre{'s' if n_new > 1 else ''}**. Go back and try **{others}** "
                    "to see if the best places change."
                )
                again.button(
                    "Change the number of centres",
                    key="back_to_build",
                    on_click=go_to_tab,
                    args=(TAB_LABELS[0],),
                    icon=":material/arrow_back:",
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
            trade_scores = pareto.question_scores(data, len(new_sites), cutoffs)
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
                    + ("is the clear choice" if n_front == 1 else "is one of the defensible options")
                    + " 🏆</div>"
                    if beater is None
                    else f"<div class='pick-missed'>...but your pick, {label(data, new_sites)}, "
                    + ("is not the clear choice" if n_front == 1 else "is not one of the defensible options")
                    + "</div>"
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
