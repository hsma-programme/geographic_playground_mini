# Audience and purpose

- A one-page, three-tab demo for a conference stand, companion to the full geographic optimisation playground (`C:\geographic_or_ds_playground`, a 45-minute teaching app). Modelled on `C:\Users\Sammi\des_playground_mini`.
- Visitors are walk-ups, mostly NHS managers and leaders, who know nothing about location optimisation. A visit is 2-5 minutes, often with a presenter. Plain English, no jargon, large readable type, nothing that needs explaining before the first click.
- The two "wow" moments are the map where adding a centre shrinks the red "too far" areas, and the optimiser visibly trying every combination. The one teaching point: the best site depends on the question you ask. Keep new features in service of those, not of breadth.
- See `HANDOVER.md` for current state, open decisions and next steps.

# How the app works

- No optimiser runs at runtime. With 18 sites (4 existing, 14 candidates) every combination is scored directly in numpy in `core.py`. lokigi (>=0.10.0) is a dependency, but only `pareto.py` uses it, to find the unbeaten options and draw the radar/line charts on tab 3. Don't imply in copy that lokigi searches or optimises at runtime. It pulls in numba, geopandas and pysal, so installs are large and the first import is slow (about 18 s cold, 4 s warm on the dev laptop).
- `data/` is generated from `raw/` by `scripts/precompute.py` (`uv run --group precompute python scripts/precompute.py`) and committed, so the app runs without geopandas. Change inputs in `raw/`, then regenerate.
- Metrics are people aged 50-84. IMD decile 1 = most deprived.

# Git commit workflow

- Never run `git commit` unless the user explicitly asks for it that turn. Drafting a message and staging files is fine anytime; committing is not.
- Every commit must include a `Co-Authored-By: Claude <model-name> <noreply@anthropic.com>` trailer (via HEREDOC), even for a short "please commit this." If multiple models contributed this session, include a trailer for each.

# Fix scope

- If a bug report floats a bigger, speculative fix alongside a smaller one consistent with existing patterns, don't default to the bigger one just because it was mentioned last. Surface the choice explicitly before planning; the smaller fix usually wins.
- A same-sized adjacent bug found in passing is fine to fold in and flag in the summary. A structurally bigger one needs an explicit scope question first, even mid-task.

# Tests

Tests are not required. `scripts/cdp_drive.py` is the smoke test (see below).

# Deferred work

- When a fix needs a structural change and gets deferred, write a handover: context, a concrete repro, the proposed design and trade-offs, implementation notes, and testing guidance.

# Reporting

- State uncertainty plainly. Distinguish what's directly verified from what's inferred, e.g. "confirmed in a headless-Chrome screenshot, but not tested on a touchscreen".

# Environment gotchas

- **Verifying UI changes**: no browser-automation framework is installed, but Chrome is, and headless Chrome over the DevTools protocol works. Start the app on port 8599 (`uv run streamlit run streamlit_app.py --server.headless true --server.port 8599`), then run `scripts/cdp_drive.py` with steps such as `wait:12 click:Barnstaple shot:name` (it saves `<prefix>_<name>.png`; read the PNG to look at it). Allow about 12 seconds for first load. `--virtual-time-budget` screenshots do not work (they capture only Streamlit's loading skeleton). Check the Streamlit log for tracebacks as well as the screenshot, since a failed rerun can leave a stale page. Kill the server afterwards.
- **Plotly frame animations do not autoplay on map subplots.** The exported HTML starts `auto_play` in a `.then()` after `Plotly.newPlot` resolves, and on a map subplot that promise stalls until the basemap style loads. `animation.py` therefore uses one static figure plus a JS `setTimeout` loop calling `Plotly.restyle`. Don't return to `fig.frames` without testing in a real page.
- **The animation page must be loaded by URL, not as an iframe `srcdoc`** (which `components.html` uses): inline, the map stays blank though hover works. `animation.py` writes it to `static/` (`enableStaticServing` in `.streamlit/config.toml`) and redirects a tiny `srcdoc` stub to the relative `app/static/...`. Keep that address relative: Community Cloud serves the app under `/~/+/`, so `/app/static/...` 404s. Test the prefix locally with `--server.baseUrlPath=/~/+` (set `MSYS_NO_PATHCONV=1` in Git Bash).
- **Never hide `stToolbar` itself**: Streamlit draws the sidebar's expand button (and a header copy of the logo) inside it, so hiding it leaves a collapsed sidebar with no way back. Hide its parts (`stMainMenu`, `stHeaderLogo`, ...) instead; see the header rules in `style.css`.
- **`st.plotly_chart` needs an explicit `key=`** wherever two charts could be identical (e.g. your pick equals the winner), otherwise `StreamlitDuplicateElementId`.
- **`st.metric` deltas**: a change that rounds to zero must be neutral ("no change"); see `delta_kwargs` in `streamlit_app.py`.
- **Tabs are tracked, widgets can vanish**: `st.tabs(key=..., on_change="rerun")` gives each tab an `.open` property, used to draw the sidebar on tab 1 only. A keyed widget that isn't drawn loses its value unless it has `persist_state="page"`.
- **Bash tool quoting**: large heredocs mixing apostrophes and quotes can fail to parse. Use the Write tool for files containing prose or mixed quoting.
- **Internet dependence**: map tiles, Google Fonts and the plotly.js CDN all need internet. `MINI_OFFLINE=1` swaps to a plain map background, but fonts and plotly.js would still need vendoring for a genuinely offline stand (untested).
- **`TypeError: GZipResponder.__init__() missing ... 'thread_minimum_size'` on startup**: an upstream streamlit/starlette version mismatch, not this app's code. Fix with `uv lock --upgrade-package streamlit --upgrade-package starlette && uv sync`.
