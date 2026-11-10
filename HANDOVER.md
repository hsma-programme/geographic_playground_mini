# Handover: geographic playground (mini)

## Context

A stand-friendly variant of the full geographic optimisation playground (`C:\geographic_or_ds_playground`,
a 45-minute, 20+ page teaching app for NHS decision makers). This one is meant for people walking up to a
stand who know nothing about the topic: 2-5 minutes, one page, three tabs, modelled on
`C:\Users\Sammi\des_playground_mini` (single page, presets, challenge feel, HSMA footer).

The two "wow" moments are (1) a map where you add centres and watch the red "too far" areas shrink, and
(2) the optimiser visibly trying every combination. The teaching point, condensed from the full app: the
"best" site depends on the question you ask, and a computer can show you that trade-off.

Audience framing is inherited from the full app's CLAUDE.md: NHS managers and leaders first, analysts and
clinicians second. Plain English, no jargon.

## Current state (first version, working, committed)

Verified by driving the real page in headless Chrome (see "Testing" below): all three tabs, site toggling,
the animation advancing, the results section. Not verified: touch input, offline mode, narrow screens.

| File | Role |
|---|---|
| `streamlit_app.py` | The whole UI: tab 1 (build your network), tab 2 (optimiser + results), tab 3 (weigh it up) |
| `core.py` | Data loading (`load_data`), scoring (`nearest_time`, `summarise`, `score_all_combinations`), objectives, ranking |
| `figures.py` | Plotly maps: interactive `travel_map`, compact `static_time_map` |
| `pareto.py` | Tab 3 ("Weigh it up"): builds a lokigi `SiteSolutionSet` from `score_all_combinations`, finds the options no other beats on every chosen question, draws lokigi's interactive radar / parallel-lines chart plus a yellow dashed "Your pick" trace |
| `animation.py` | The optimiser animation: custom HTML + JS timer, written to `static/` and embedded by URL (see gotcha 7) |
| `scripts/precompute.py` | `raw/` to `data/` (simplified GeoJSON, npz of matrices/demand/IMD, sites.csv) |
| `scripts/cdp_drive.py` | Headless-Chrome driver for UI testing (see below) |
| `raw/` | Inputs copied from the full playground (see its LICENCE) |
| `data/` | Generated, committed so the app runs without geopandas |

Key design decisions:
- **No optimiser at runtime.** 4 existing + 14 candidate sites means at most 364 combinations (3 new sites);
  each is a `min()` over matrix columns plus a weighted mean. lokigi is a dependency, but only for tab 3's
  unbeaten-options logic and charts (`pareto.py`); do not imply in copy that it searches or optimises.
- **Up to 3 new sites** (`MAX_NEW_SITES` in `core.py`); the animation length follows (14 / 91 / 364 frames).
- **Four objectives**, all lower-is-better, in `OBJECTIVES`: average journey, people beyond the cutoff,
  average for IMD deciles 1-3, longest journey. Winners differ for both car and public transport at 1 and 2
  sites (checked), which is the point of the demo.
- **Public transport** has 109 unreachable cells stored as 9999 in the source; `precompute.py` caps them at
  180 minutes. The cutoff default switches to 90 minutes for public transport (`DEFAULT_CUTOFF`).
- The metrics count **people aged 50-84** (the full app's demand definition). Copy says so on the headline.
- Wording note from the full app: IMD decile 1 = most deprived.

## Tab 3: "Weigh it up"

Visitors pick up to 5 of 10 questions (at least 2), in three rows of pills: by car (average journey, people
over the cutoff, most deprived areas, longest journey, people helped), by public transport (the same minus
longest journey) and "How the service runs" (most even workload: smallest share of patients going to the
busiest centre, by car). The registry is `questions()` in `pareto.py`; `score_all_combinations` in `core.py`
supplies the `helped` and `busiest` columns. The page shows how many options are not beaten on every chosen
question, whether their pick is one of them, and a lokigi interactive radar ("Shapes", needs 3+ questions) or
parallel-lines chart ("Lines"). The chart opens with only the best option per question plus the visitor's pick
visible; the rest are greyed in the legend, which scrolls when there are many (up to 83 unbeaten options with 5
questions and 3 centres). Options that are best on a question say so in the legend ("wins on ..."). Higher-is-
better questions (people helped) are rescaled so further out is still better, and the radar says "Maximising".
Each mode has its own cutoff: tab 1's slider for the mode it shows, `DEFAULT_CUTOFF` for the other.

Deliberately left out: longest journey by public transport (unreachable areas are capped at 180, so it never
differs), a fairness gap between deprived and other areas (in Devon deprived areas are already closer under every
network, so "smallest gap" rewards helping richer rural areas), and 2036 journeys (correlate 0.98 with today's).
lokigi is a runtime dependency (`lokigi>=0.10.0`); see CLAUDE.md for the install-size and import-time cost.
Visitor copy avoids the words "Pareto" and "dominated".

The sidebar (new centres, travel mode, map view, cutoff, "Looking ahead") is drawn only on tab 1, using `st.tabs(key="page",
on_change="rerun")` and `tab_build.open`; tab 2 carries a one-line caption of what it is scoring. Every widget
that can stop being drawn needs `persist_state="page"`, or its value is lost.

Verified in headless Chrome: all three tabs with 3 centres by car; the sidebar present only on tab 1; picks and
mode kept across tabs; public transport (tab 2 caption and tab 3 cutoffs); the cap of 5 (the sixth tap is undone
with a toast); radar and lines with 4 and 5 questions. Not verified: the cutoff slider moved away from its
default (only the default cutoffs were exercised), "Most even workload" and the deprived
questions on the final layout, hover and legend taps (static screenshots only), touch, narrow screens, and load
time on a stand laptop.

## Journey-time chart (tab 1)

Under the metrics on tab 1, `journey_chart` in `figures.py` draws how many people (aged 50-84, for the chosen
demand) live at each journey time, in 5-minute groups that line up with the cutoff slider's steps. The filled
area is the current network: blue up to the cutoff, red beyond it, with a dashed line at the cutoff. Once a
centre is added, today's network shows behind it as a grey line, so the red tail and the hump visibly shrink and
move. The top is a rounded line through the groups, not a density estimate (which would smear the public transport
pile-up at the 180-minute cap). Fixed x-axis per mode (car 0-65, public transport 0-180); no legend, zoom disabled.

The chart is labelled directly rather than explained in a caption (`_label_journey_chart`): "Within N min" and
"Over N min" with people counts (the same split as the headline metric, so the red number matches it), "Grey line =
today's centres" on the grey line (two lines), "N min limit" on the cutoff line, and "more people" for the unlabelled height. Placement
is rule-based: the red label goes inside the red area when it is wide and tall (low cutoffs, public transport),
otherwise above it with an arrow; near the right edge it and the cutoff label move left of the line. The grey label
goes where the grey line sits clearest above the fill, preferring the blue side so it stays clear of the red label.
The x-axis title is "Minutes to the nearest centre", short enough not to clip at phone width.
Checked by eye in standalone renders (car at 20/30/45/60/70 min, public transport at 60/90/120, with and without
new centres) and in the app at desktop and 390 px phone width. Public transport is busier because its curve is lumpy.

Verified in headless Chrome: car with no centres and with two, public transport with two centres,
no tracebacks. Not verified: hover text, touch, cutoff slider away from its default (car cutoffs above 65 minutes
omit the red part and cutoff line by design, untested visually). Known wart: public transport is lumpy because the
underlying times are, and the pile-up at 180 draws as a thin spike at the right edge.

## Map views and tab 3 questions

Each tab 3 question now has a matching picture on tab 1 (`travel_map` in `figures.py`, `view` argument):

| Tab 3 question | Tab 1 map view |
|---|---|
| Shortest average journey | `time`: journey-time gradient |
| Fewest people over N min away | `cutoff`: blue/red split |
| Best for the most deprived areas | `deprived`: the same gradient, only IMD deciles 1-3 coloured |
| Most people helped | `gain`: only areas with a quicker nearest centre, coloured teal by minutes saved |
| Most even workload | `nearest`: catchments, with each centre's share of patients in the hover and caption (`nearest_shares` in `core.py`) |

`gain` is blank until a centre is added (the caption says so). Its colour scale tops out at `GAIN_MAX` (45 min by
car, 120 by public transport), set from the biggest single-centre saving (48 and 139). Colour-scale legends come
from `_colorbar`: kept inside the map's bottom-left corner, in black text. Map captions sit above the map, so
the map starts slightly lower than the town pills beside it.

Verified in headless Chrome: car `gain`, `deprived` and `nearest` with two centres; public transport `gain`
with two centres; car journey-time legend placement; no tracebacks. Not verified: public transport `deprived`
and the empty `gain` screenshots (taken, not looked at), the `gain` legend's new placement, hover text,
the what-if sentences for the new views on public transport, cross-checking a share
against tab 3's `busiest_car`, touch, narrow screens. Known weak spot: `deprived` colours small urban patches, so
at full-Devon zoom they read as faint specks. Check it on the stand screen; options are outlining those areas
or zooming in. The sidebar now has ten map options (five per mode), which is the limit for a walk-up audience.

## Gotchas learned the hard way

1. **Plotly frame animations do not autoplay on map subplots.** Exported HTML only adds frames and starts
   `auto_play` in a `.then()` after `Plotly.newPlot` resolves, and for a map subplot that promise stalls until
   the basemap style loads (and in a `file://` page it never does). `fig.frames` + `auto_play` rendered the first
   frame and froze. `animation.py` avoids frames entirely: one static figure plus a JS `setTimeout` loop calling
   `Plotly.restyle`. Do not go back to `fig.frames` without testing in a real page.
2. **`st.plotly_chart` needs explicit `key=`s** where two charts can be identical (your pick == the winner
   raised `StreamlitDuplicateElementId`).
3. **`st.metric` deltas**: a rounded-zero change must be neutral ("no change"), else it shows a red +0
   (`delta_kwargs` in `streamlit_app.py`).
4. **Pills overflow sideways by default**; `style.css` forces `stButtonGroup` to wrap.
5. **Bash tool quoting**: large heredocs mixing apostrophes and quotes failed to parse. Use the Write tool for
   files with prose.
6. **Tapping a site on the map** uses `st.plotly_chart(on_select=on_map_click, selection_mode="points")`, which
   does work on `Scattermap` traces. Two things it needs: every trace sets `selected`/`unselected` opacity, or
   plotly fades everything but the tapped dot; and the chart key carries a counter (`main_map_{sites_version}`)
   bumped on each tap, so the chart remounts with nothing selected. Without it a stale selection would swallow
   the next tap on the same trace position. The sidebar pills share that counter (`site_pills_{sites_version}`)
   and only mirror the plain `new_sites` key: if the pills were keyed `new_sites` themselves, a second tap sent
   before the first tap's rerun reached the browser would carry the browser's out-of-date pills value, which
   Streamlit treats as a fresh pill change, so the first site was swapped out. "Start again" and "Surprise me"
   bump the counter too. The callback matches on `customdata` (site index) and only on
   traces 2-4 (possible new centres, then the chosen centres' dark outline and yellow dot), so taps on areas
   and existing centres do nothing. Map markers have no outline property, hence the separate outline trace;
   `animation.py` moves traces 3 and 4 together.
7. **The animation must be loaded by URL, not inline.** In an iframe `srcdoc` (what `components.html` and
   `st.iframe("<html>")` produce) the map's tiles and areas never finish loading: hover works, but the map is
   blank. A URL-loaded iframe draws fine. The root cause in maplibre is unknown. So `animation.py` writes the
   page to `static/optimiser_<hash>.html` (served via `enableStaticServing` in `.streamlit/config.toml`) and
   embeds a one-line `srcdoc` stub that does `location.replace("app/static/...")`. The address must stay
   relative, with no leading slash: Community Cloud serves the app under `/~/+/`, and `/app/static/...` returned
   Not Found there. To test locally under the same prefix, run with `--server.baseUrlPath=/~/+` (in Git Bash set
   `MSYS_NO_PATHCONV=1`, or `~` is expanded to the home folder). The app needs write access to `static/`; the
   generated files are gitignored. Note that a running server does not pick up edits to `animation.py`; restart it.

## Testing

No browser-automation framework is installed, but Chrome is, and headless Chrome plus the DevTools protocol
works. `scripts/cdp_drive.py` (needs the `websockets` package, already in the venv via streamlit) launches
Chrome, opens `http://localhost:8599/` and runs steps:

    uv run streamlit run streamlit_app.py --server.headless true --server.port 8599
    uv run python scripts/cdp_drive.py out/run1 wait:12 click:Barnstaple wait:3 click:Okehampton \
        click:"2 · Watch the optimiser" wait:2 click:"Run the optimiser" wait:8 shot:tall

Steps: `size:W,H` (window size; `mobile` emulation below 768px wide; leading `size:` steps apply before the
page loads), `wait:SECONDS`, `click:TEXT` (exact then substring match on buttons/tabs/pills), `tapsite:TEXT` (real
mouse tap on the map marker whose hover text contains TEXT), `tapxy:X,Y` (mouse tap at a viewport position),
`shot:NAME` (full page), `shotv:NAME` (visible window only), `js:EXPR`. Run one driver at a time: they all
use debugging port 9333, so two at once share a browser and mix up their window sizes.
It saves `out/run1_NAME.png`. Notes: `--virtual-time-budget` screenshots do NOT work (they capture only
Streamlit's loading skeleton); allow roughly 12 seconds for first load; the window is 1500 wide and 2600 tall so
the whole page shows. Chrome's path is hard-coded for Windows. `out/` and `*_profile/` are git-ignored.

Two quirks seen while doing the branding:
- Pass the output prefix as an absolute path (`C:/geographic_playground_mini/out/run1`). With a relative one,
  Chrome never opened its debugging port and the script failed with `UnboundLocalError: ... 'tabs'`.
- Screenshots often show the sidebar shifted left with its contents clipped. This is a capture artifact (the
  sidebar caught mid-transition): the DOM geometry is correct, later shots render it fine, and the DES mini shows
  the same thing. Don't "fix" it in CSS. At phone sizes it happens on every `shot:`. The likely cause is that a
  full-page capture resizes the page and restarts the sidebar's slide-in; use `shotv:` there, which renders
  it correctly.

## Branding and layout (done)

Layout and theme copied from the DES mini so the two stand apps look like a pair: maroon sidebar with the
HSMA logo (`st.logo`), tabs restyled as a sticky navbar titled "Geographic Playground" in the HSMA Display font
(`resources/fonts/hsma-display/`, embedded as base64; its source and build scripts live in the DES mini repo),
Space Grotesk body at 18px weight 300, teal call-to-action button, muted-red `st.info`, and the QR + HSMA footer.
`style.css` is the DES mini's file with this app's rules at the bottom; keep the two in step where possible.

Travel mode, cutoff and map view moved to the sidebar (as the DES mini keeps its settings there). Mode and view
are two five-option radios under "By car" and "By public transport" subheaders ("Journey time by car", "Who
is too far by public transport", "Most deprived areas by car", "Who gets a quicker journey by car", "Closest
centre by car", ...); choosing in one clears the other. "Closest centre" colours each area by its nearest centre: cool colours for the existing four, warm for new
ones, in the order they were tapped (the map gets the unsorted `tapped_sites`). The public transport subheader's help hover
notes that public transport is buses and walking only, no trains. Changing mode resets the cutoff to that mode's
default; changing only the view keeps it. The cutoff slider shows only in the "too far" views, but its value is
kept while hidden (the headline metric and optimiser still use it).

Following review feedback ("put all the inputs in one place"), the town pills and "Start again" / "Surprise me"
are also in the sidebar, as its first section ("Your new centres", above "What the map shows" and "Looking ahead"),
so tab 1's right-hand column is only results: metrics and the journey chart. The sidebar is 24rem wide (the
DES mini's is narrower) and the sidebar pills are slightly compact (`style.css`), so the 14 towns fit 3 to a row
(5 rows). The cost is height: the "By car" map options start about 830px down (measured in a 1500px-wide
window), so on a 1080px stand screen they are near the fold and the public transport and demand options need a
scroll. Metric labels wrap instead of ending in "..." because the results column is narrower; below the
1070px container query the navbar swaps its pills for a dropdown (see "Small screens" below; seen at 1500px
wide with the sidebar open, not at 1920).
Note: the sidebar width rule used to target `[aria-expanded="true"]`, which this Streamlit never sets, so the
sidebar was Streamlit's default 300px until this change; it now targets `[data-collapsed="false"]`. The DES
mini's `style.css` has the same dead selector.

### The 2036 projection ("Looking ahead" and tab 2's fast forward)

The 2036 population is the full playground's projection (`raw/demand_MF_50_84_projected_2036.csv`, copied from
its `data/generate_projected_demand.py` output): synthetic, made for teaching, with extra growth around
Kingsbridge; the help hover and footer say so. It used to be a "Demand" radio at the bottom of the sidebar that
switched tab 1's and tab 3's numbers but not the map, and tab 2 ignored it, so it felt like an afterthought.
Now **every number on tabs 1 and 3 uses today's population**, and 2036 appears in two deliberate places:

- **Tab 1, "Looking ahead" sidebar section**: one radio option, "Where need grows by 2036" (`view="growth"` in
  `travel_map`: % growth in people aged 50-84, purple, since red and teal already mean "too far" and
  "quicker"). It is a third radio group beside car and public transport (`MAP_GROUPS`, `on_map_choice_change`);
  choosing it keeps the current travel mode and cutoff, which its caption uses: "If nothing changes, 10,600 more
  people will live more than 45 minutes from a centre" (car; 34,100 over 90 min by public transport), plus "With
  your new centres, that rise is ..." once centres are chosen (6,300 with Kingsbridge alone). The caption's
  "around Kingsbridge in the South Hams" is static text; `GROWTH_TOP` (42%) is computed. The what-if panel treats
  this view as "who is too far". Because the sidebar's car and public transport options are cleared in this view, a "By car / By public transport" switch (`growth_mode`, `on_growth_mode_change`) sits above the metrics, shown only here; it resets the cutoff like the sidebar. Verified in headless Chrome: car to public transport and back, then leaving the view hides it. In this view the metric cards show 2036 figures for the centres on the map, each arrow comparing with 2026 for the same centres (a caption under the switch says so): e.g. 62,789 people over 45 min, +10,644; with Kingsbridge 47,055, +6,316, matching the map caption. "People helped" and "Average time saved" use `delta_kwargs(..., higher_better=True)`. The longest journey always reads "no change" (it ignores population; its help hover says so). Other views keep the usual cards, compared with today's centres. A yellow `st.warning` under the map (this view only) says the 2036 population is an illustrative projection for teaching purposes only. The "Average journey" card has a help hover in every view saying it is weighted by people aged 50-84, plus, in this view, why that makes it change by 2036.
- **Tab 2, "Will it still be best in 10 years?"** (`render_fast_forward`), between the compare maps and "Why
  computers?": the do-nothing number, then a "Fast forward to 2036" button. It shows the growth map and two cards
  (shortest average journey, fewest people over 45 min): the 2026 and 2036 winners, a verdict ("Still the best in
  2036: a choice that lasts" or "Changes by 2036: Kingsbridge comes in, Okehampton drops out"), and your pick's rank
  in both years. `st.session_state.fast_forward` stores the centres it was run for, so other centres hide it.

What the data gives (car, 45 min): the 50-84 population grows 14% overall, ~40% in the South Hams, ~3% in Plymouth,
and faster where people are already far from a centre (20% vs 13%). Winners: with 1 centre nothing changes
(Barnstaple, Okehampton); with 2, both questions change (Barnstaple + Kingsbridge; Okehampton + Kingsbridge, where
sticking with 2026's answer leaves 2,170 more people too far); with 3, only the average journey changes (Kingsbridge
for Newton Abbot). The average-journey margins are 0.02-0.06 min, so the card shows no minutes, only ranks.
Public transport winners never change, which is one reason tab 2 stays on car. Not added: 2036 questions on tab 3
(journeys correlate 0.98 with today's, so they add few new trade-offs).

Verified in headless Chrome: tab 1's growth view by car with no centres and with Kingsbridge (10,600 / 6,300), and
by public transport (34,100, mode and 90-min cutoff kept); tab 2 with Barnstaple ("still the best" on both cards)
and Okehampton + Barnstaple (both change, 2,170 shown); the section going back to just the button after adding a
centre and re-running; tab 3 unaffected; no tracebacks. Numbers match a scratch exhaustive run. Not verified: 3
centres on tab 2, hover text on the growth map, phone width (the cards and map sit in a `reflow_stack_future`
row, so they should stack like the compare maps), touch.

Tab 1 ends with the "Watch the optimiser" button, in an outlined box right after the map and results (`next_step`
container; the button is bigger than the other call-to-action buttons, with a teal glow), with a muted line
pointing to an optional extra further down. That extra, "Extra: how many centres would be enough?", sits below
the box behind a divider, with text on the left and the chart on the right (they stack under 1300px via
`reflow_stack_what_if`). It used to sit under the map, beside the results, and a reviewer read it as tied to their
own picks ("I've chosen one centre but it talks about 8", "what is the yellow bar?"). A later version outlined the
visitor's current number of centres in yellow ("you" under the tick) while warning the bars "may not be the towns
you picked", which read as contradictory. So the panel now never mentions the visitor's picks (it doesn't depend on
them): its text says each bar uses the best sites, and it ends with a prompt to try a different option under "What
the map shows" (also shown on the "nobody is too far" message). The budget is marked on the chart itself rather
than in the text, and a line under the chart asks whether each extra centre is worth its cost. The panel
(`render_what_if` in `streamlit_app.py`, `best_by_count` in `core.py`, `diminishing_returns_chart` in `figures.py`)
shows what the best 1st to 8th extra
centre adds, on the measure the sidebar map is showing: people within the cutoff ("too far" view), minutes cut from
the average journey ("journey time"), minutes cut from the average in the most deprived areas ("most deprived";
`best_by_count` has a `deprived` series for it), or people with a closer centre ("closest centre" and "quicker journey",
the same measure worded to match each map). "Quicker journey" adds a second chart: the average minutes saved per
person helped (`best_by_count`'s `saved` series), for the combination that helps the most people. That one is a
level, not a gain, because it can dip as centres are added (car at 4, public transport at 3), which would give
negative bars. Each count uses its own
best combination for that measure, so the bars always fall. Bars within the 3-centre budget are solid; the rest
are faded on a shaded background behind a dashed line, under "Within budget" / "Over budget" labels. The "1".."8"
x labels look numeric, so plotly makes the axis linear (bar k at x = k), which is what the line's position assumes.
Deliberately left out: the
visitor's own per-centre gains in tap order (they can rise, which muddies the message). Verified in headless
Chrome for car and public transport in all three views, with the sentence numbers matching a scratch exhaustive
run. The new layout was checked in headless Chrome at 1500, 1000 and 390 wide, with 0, 1 and 3 centres, and with
a 115-minute car cutoff (the "nobody is too far" message). Not verified: touch. At 390 wide
the chart's y-axis title looked clipped by a character at the left edge; not yet checked whether that predates the
move.

### Small screens (ported from the DES mini's `shorten-animation` branch)

- **Sidebar expand button.** Streamlit draws the expand button (and a copy of the logo) inside `stToolbar`,
  which `style.css` used to hide, so once the sidebar was collapsed there was no way to reopen it at any width.
  Streamlit also appears to remember the collapsed state in the browser (read from its JS bundle, not
  tested), so on the stand it could have stayed shut after a reload. The toolbar now stays, click-through
  except for the button, with the menu and header-logo copy hidden. The button is moved down level with the
  navbar title, and the title is indented to clear it. The collapse button stays visible at every width,
  unlike the DES mini, which hides it on desktop.
- **Page dropdown.** `mobile_nav.py` (`add_mobile_nav`, called just before `st.tabs`) adds a `<select>` to the
  navbar. It is shown in place of the pills when the navbar is under 1070px wide (the same container query
  that used to put the title on its own row). The DES mini uses a 1320px viewport query instead. Its
  container and that container's layout wrapper are hidden; the wrapper would otherwise take an 18px flex gap
  and push the navbar down.
- **Reflow, 640-1300px.** Rows inside `reflow_stack_*` / `reflow_halves_*` keyed containers wrap: tab 2's "best
  place" cards go two per line, and tab 2's compare maps and tab 3's verdict and chart-guide rows stack. Tab 1's
  map and results deliberately stay side by side, so the numbers stay in view while tapping.
- **Phones (under 768px).** The sidebar drops the 24rem `min-width` so Streamlit's own cap (about 90% of the
  screen) applies; at 24rem it ran off a phone. Smaller navbar title (1.25rem, to fit beside the expand button at
  360px) and dropdown text, and 1rem text on the big call-to-action buttons.
- Not ported: unpinned dataframe index (no `st.dataframe` here), the animation-gap fix (this animation has no
  zoom-to-fit script), preset label wrapping (no presets), the Streamlit 1.63.0 pin (not a screen-size fix).
- Verified in headless Chrome at 1920, 1500, 1000, 390 and 360 wide. Not tried on a real phone, tablet or
  touchscreen, or with the native `<select>` picker that phones show.


## Suggested next steps

Decisions the user has not made yet:
1. **Reveal order on tab 2.** The "best depends on what you ask" cards and maps appear immediately under the
   animation, spoiling it. Options: show them only after the animation's final frame (post a message from the
   iframe is awkward; simplest is a "Show me the results" button), or leave as is for presenter-led use.
2. ~~Branding~~ done, see above.
3. **Attract mode.** Idle screen that loops the animation to draw people in from across the room.

Ideas from the original plan that were left out (see the earlier suggestions): a live "what did other visitors
choose" tally (local CSV on the stand laptop), a "who benefits" overlay by deprivation, presets
("biggest town", "fill the biggest gap"), closing an existing centre (genuine losers, but politically
sensitive in an NHS setting, so probably presenter-only), and a collapsed presenter cheat-sheet.

Technical follow-ups:
- Sites can now be tapped on the plotly map (see gotcha 6), but each tap is a full rerun and redraw. A
  Leaflet/MapLibre Streamlit custom component would give instant client-side map updates.
  Tapping is only verified with headless-Chrome mouse events, not on a real touchscreen; check the grey dots
  (16 px) are easy enough to hit with a finger on the stand hardware.
  The current plotly map re-sends about 480 KB of GeoJSON on every rerun; it feels fine locally, untested on
  conference wifi. Simplifying geometry further in `precompute.py` (tolerance is 60 m) is the cheap lever.
- Offline stand: `MINI_OFFLINE=1` swaps to a plain background but is untested; the Google Fonts and Plotly
  CDN links in `animation.py`, `style.css` and `config.toml` also need internet, so a truly offline stand needs
  those vendored.
- Touch: check pill and button sizes on the real stand screen; the slider is the likely weak spot.
- Narrow screens and the large-type/readability pass for viewing at a distance have not been done.
- No tests (consistent with the full app's stance); the CDP script is the smoke test.

## Conventions carried over from the full app

- Commits only when the user asks, with a `Co-Authored-By: Claude <model-name> <noreply@anthropic.com>`
  trailer, added via heredoc.
- Report what was directly verified versus inferred.
- A same-sized adjacent bug found in passing can be folded in and flagged; anything structurally bigger needs
  a scope question first.
