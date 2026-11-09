# Geographic playground (mini)

A one-page, stand-friendly demo of location optimisation: where should the next
diagnostic centres in Devon go? Companion to the full 45-minute playground.

- **Tab 1 · You choose** - add up to 3 new centres by tapping the map or a town, and watch
  journeys change. The sidebar switches between car and public transport, picks what the map
  shows (journey time, who is too far, the most deprived areas, who gets a quicker journey, or
  each area's closest centre), sets the "too far" cutoff, and switches between today's population
  and a projected 2036 one. A journey-time chart and a "what if the budget were bigger?" panel sit
  alongside, and a button at the bottom moves on to tab 2.
- **Tab 2 · Watch the optimiser** - an animated map tries every way of placing the same number of
  centres (scored on average journey time by car, today's population), then shows that a different
  question picks a different winner, and compares your pick with each winner side by side.
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
