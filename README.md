# Geographic playground (mini)

A one-page, stand-friendly demo of location optimisation: where should the next
diagnostic centres in Devon go? Companion to the full 45-minute playground.

- **Tab 1 · You choose** - add up to 3 new centres by tapping the map or a town, and watch
  journeys change. The sidebar switches between car and public transport, picks what the map
  shows (journey time, who is too far, the most deprived areas, who gets a quicker journey, or
  each area's closest centre), and sets the "too far" cutoff. A "Looking ahead" map shows where the
  population aged 50-84 grows most by 2036, and how many more people would be too far if nothing
  changes. A journey-time chart sits alongside the map, then a big button moves on
  to tab 2. Below that, an optional "how many centres would be enough?" panel shows what each extra
  centre would add if the budget were bigger.
- **Tab 2 · Watch the optimiser** - an animated map tries every way of placing the same number of
  centres (scored on average journey time by car, today's population), then shows that a different
  question picks a different winner, and compares your pick with each winner side by side. A
  "Fast forward to 2036" button then checks whether the winners, and your pick's rank, still hold
  with the projected 2036 population.
- **Tab 3 · Weigh it up** - pick up to 5 questions and see which options no other option beats on
  all of them, on a radar or parallel-lines chart.

All figures are for people aged 50-84.

## Run

    uv sync
    uv run streamlit run streamlit_app.py

Set `MINI_OFFLINE=1` to use a plain background instead of online map tiles. Fonts and plotly.js
still load from the internet.

The tab 2 animation is written to `static/` at runtime and served by Streamlit's static file
serving (`enableStaticServing` in `.streamlit/config.toml`), so the app needs write access to that
folder.

## Screen size

The page names in the top bar show as three buttons when there is room. When the bar is narrower
than about 1070px, they become a dropdown instead. On tab 1 the sidebar takes 24rem (432px), so the
browser window needs to be about 1500px wide for the buttons.

Windows display scaling reduces the width the browser sees. On a 1920x1080 screen, 100% scaling gives
1920px, 125% gives 1536px (the buttons should just fit), and 150% gives 1280px (you get the dropdown).
For the stand, set scaling to 100%, or zoom the browser out (Ctrl and minus; 80% at 150% scaling
gives 1600px). Everything still works with the dropdown; it just takes one more tap to change page.

## Regenerate the data

`raw/` holds the inputs copied from the full playground. The app reads the small files in `data/`:

    uv run --group precompute python scripts/precompute.py

No optimiser runs at runtime: with 18 sites, every combination is scored directly in numpy (`core.py`).
[lokigi](https://github.com/hsma-tools/lokigi) is used only on tab 3, to find the options nothing
else beats and to draw the charts. It is a large install, so the first start-up is slow.

## In-browser version (stlite)

The same app also runs entirely in the visitor's browser, with no server, using
[stlite](https://github.com/whitphx/stlite) (Streamlit on Pyodide). It is built from this source, which
is not changed, by `stlite/build.py`:

    uv run python stlite/build.py --serve   # builds _site/, then serves http://localhost:8599/

`--serve` builds and starts a plain static server (`--port` changes the port; Ctrl+C stops it). Or do it in
two steps: `uv run python stlite/build.py`, then `python -m http.server 8599 -d _site`.

Testing locally:
- Open it over `http://localhost`, not by double-clicking `index.html`: a `file://` page can't load the app's files.
- The first load takes 20-60 seconds while the browser downloads Python and the packages. It needs internet
  (stlite and Pyodide come from jsDelivr, as do map tiles and fonts).
- After changing an app file, stop the server, rebuild, then hard-refresh (Ctrl+Shift+R) so the browser doesn't reuse cached files.
- There is no server log. If the page stays blank, open the browser's DevTools (F12) and read the Console for
  the Python traceback; `HANDOVER.md` lists the known causes.

`.github/workflows/stlite-pages.yml` builds and publishes it to GitHub Pages on every push to `main`
(set Settings, Pages, Source to "GitHub Actions" once). The first load downloads tens of MB and takes
20-60 seconds; after that the browser caches it.

### Limitations of the in-browser build

- **It needs internet.** stlite and Python (Pyodide) load from jsDelivr, and the map tiles, Google Fonts and the
  plotly.js script in the optimiser animation are fetched too. It is not an offline stand build; vendoring those
  would be a separate job.
- **The first load is slow.** The browser downloads Python, Streamlit, pandas, pyarrow, plotly, matplotlib and
  seaborn (tens of MB, 20-60 seconds), then caches them.
- **lokigi is imported with stand-ins.** lokigi loads mapping and spatial packages (geopandas, pysal, osmium,
  folium and others) that tab 3 never uses and Python in the browser can't supply, so `stlite/stlite_shims.py`
  replaces them with empty modules. If lokigi adds another import like that, the page fails at `import pareto`
  with `ModuleNotFoundError`: add the module name to `STUBBED` in that file.
- **The stand-ins hide real modules too.** `requests`, `tqdm` and `joblib` exist in the browser's Python but are
  stubbed as well, for the whole session. Nothing in the app needs them and nothing broke in testing, but a new
  Streamlit feature that used them would get an empty class and fail confusingly.
- **The build edits copies with exact-text matches.** The optimiser animation's page name (`animation.py`, the
  `name = f"optimiser_..."` line) is rewritten in the copy, because a content hash can't match between the build
  and the browser. If that line changes, the build stops with an assertion naming `HASH_NAME` in
  `stlite/build.py`; update it there. The sidebar width rules are appended in the same way (`SIDEBAR_CSS`),
  because stlite's Streamlit (1.65) marks an open sidebar differently from the pinned 1.66.1.
- **Only three animation pages exist.** Tab 2 always runs by car, with the default cutoff, for today's
  population, so the build pre-renders one page for 1, 2 and 3 new centres. A new variant needs its own page.
- **It runs a different Streamlit.** stlite bundles its own fork (currently 1.65.0), not the pinned 1.66.1.
  After changing `STLITE_VERSION` in `stlite/build.py`, check all three tabs, the sidebar, the navbar and the
  page dropdown again.
