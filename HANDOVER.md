# Handover: geographic playground (mini)

## Context

A stand-friendly variant of the full geographic optimisation playground (`C:\geographic_or_ds_playground`,
a 45-minute, 20+ page teaching app for NHS decision makers). This one is meant for people walking up to a
stand who know nothing about the topic: 2-5 minutes, one page, two tabs, modelled on
`C:\Users\Sammi\des_playground_mini` (single page, presets, challenge feel, HSMA footer).

The two "wow" moments are (1) a map where you add centres and watch the red "too far" areas shrink, and
(2) the optimiser visibly trying every combination. The teaching point, condensed from the full app: the
"best" site depends on the question you ask, and a computer can show you that trade-off.

Audience framing is inherited from the full app's CLAUDE.md: NHS managers and leaders first, analysts and
clinicians second. Plain English, no jargon.

## Current state (first version, working, committed)

Verified by driving the real page in headless Chrome (see "Testing" below): both tabs, site toggling,
the animation advancing, the results section. Not verified: touch input, offline mode, narrow screens.

| File | Role |
|---|---|
| `streamlit_app.py` | The whole UI: tab 1 (build your network) and tab 2 (optimiser + results) |
| `core.py` | Data loading (`load_data`), scoring (`nearest_time`, `summarise`, `score_all_combinations`), objectives, ranking |
| `figures.py` | Plotly maps: interactive `travel_map`, compact `static_time_map` |
| `animation.py` | The optimiser animation: custom HTML + JS timer inside `components.html` |
| `scripts/precompute.py` | `raw/` to `data/` (simplified GeoJSON, npz of matrices/demand/IMD, sites.csv) |
| `scripts/cdp_drive.py` | Headless-Chrome driver for UI testing (see below) |
| `raw/` | Inputs copied from the full playground (see its LICENCE) |
| `data/` | Generated, committed so the app runs without geopandas |

Key design decisions:
- **No optimiser at runtime.** 4 existing + 14 candidate sites means at most 364 combinations (3 new sites);
  each is a `min()` over matrix columns plus a weighted mean. lokigi is not a dependency. If the story is ever
  "this is what lokigi does at scale", say so in copy; do not imply the app runs it.
- **Up to 3 new sites** (`MAX_NEW_SITES` in `core.py`); the animation length follows (14 / 91 / 364 frames).
- **Four objectives**, all lower-is-better, in `OBJECTIVES`: average journey, people beyond the cutoff,
  average for IMD deciles 1-3, longest journey. Winners differ for both car and public transport at 1 and 2
  sites (checked), which is the point of the demo.
- **Public transport** has 109 unreachable cells stored as 9999 in the source; `precompute.py` caps them at
  180 minutes. The cutoff default switches to 90 minutes for public transport (`DEFAULT_CUTOFF`).
- The metrics count **people aged 50-84** (the full app's demand definition). Copy says so on the headline.
- Wording note from the full app: IMD decile 1 = most deprived.

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
   plotly fades everything but the tapped dot; and the chart key carries a counter (`main_map_{map_taps}`)
   bumped on each tap, so the chart remounts with nothing selected. Without it a stale selection would swallow
   the next tap on the same trace position. The callback matches on `customdata` (site index) and only on
   traces 2-4 (possible new centres, then the chosen centres' dark outline and yellow dot), so taps on areas
   and existing centres do nothing. Map markers have no outline property, hence the separate outline trace;
   `animation.py` moves traces 3 and 4 together.

## Testing

No browser-automation framework is installed, but Chrome is, and headless Chrome plus the DevTools protocol
works. `scripts/cdp_drive.py` (needs the `websockets` package, already in the venv via streamlit) launches
Chrome, opens `http://localhost:8599/` and runs steps:

    uv run streamlit run streamlit_app.py --server.headless true --server.port 8599
    uv run python scripts/cdp_drive.py out/run1 wait:12 click:Barnstaple wait:3 click:Okehampton \
        click:"2 · Watch the optimiser" wait:2 click:"Run the optimiser" wait:8 shot:tall

Steps: `wait:SECONDS`, `click:TEXT` (exact then substring match on buttons/tabs/pills), `tapsite:TEXT` (real
mouse tap on the map marker whose hover text contains TEXT), `tapxy:X,Y` (mouse tap at a viewport position),
`shot:NAME`, `js:EXPR`.
It saves `out/run1_NAME.png`. Notes: `--virtual-time-budget` screenshots do NOT work (they capture only
Streamlit's loading skeleton); allow roughly 12 seconds for first load; the window is 1500 wide and 2600 tall so
the whole page shows. Chrome's path is hard-coded for Windows. `out/` and `*_profile/` are git-ignored.

Two quirks seen while doing the branding:
- Pass the output prefix as an absolute path (`C:/geographic_playground_mini/out/run1`). With a relative one,
  Chrome never opened its debugging port and the script failed with `UnboundLocalError: ... 'tabs'`.
- Screenshots often show the sidebar shifted left with its contents clipped. This is a capture artifact (the
  sidebar caught mid-transition): the DOM geometry is correct, later shots render it fine, and the DES mini shows
  the same thing. Don't "fix" it in CSS.

## Branding and layout (done)

Layout and theme copied from the DES mini so the two stand apps look like a pair: maroon sidebar with the
HSMA logo (`st.logo`), tabs restyled as a sticky navbar titled "Geographic Playground" in the HSMA Display font
(`resources/fonts/hsma-display/`, embedded as base64; its source and build scripts live in the DES mini repo),
Space Grotesk body at 18px weight 300, teal call-to-action button, muted-red `st.info`, and the QR + HSMA footer.
`style.css` is the DES mini's file with this app's rules at the bottom; keep the two in step where possible.

Travel mode, cutoff and map view moved to the sidebar (as the DES mini keeps its settings there). The town pills,
"Start again" / "Surprise me" and the metrics stay next to the map, because picking towns is the main action.

To confirm: the footer links in `streamlit_app.py` (`FULL_PLAYGROUND_URL`, `CODE_URL`) point at the Bergam0t
GitHub repos, since the full playground has no known deployed URL. The DES mini links to `hsma-programme/...`
instead; update both if these move.

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
