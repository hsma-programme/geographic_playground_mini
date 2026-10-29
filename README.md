# Geographic playground (mini)

A one-page, stand-friendly demo of location optimisation: where should the next
diagnostic centre in Devon go? Companion to the full 45-minute playground.

- **Tab 1** - toggle new centres on a map, change the travel-time cutoff, switch car / public transport.
- **Tab 2** - watch a computer score every combination, then see that the "best" site depends on the question asked.

## Run

    uv sync
    uv run streamlit run streamlit_app.py

Set `MINI_OFFLINE=1` to use a plain background instead of online map tiles.

## Regenerate the data

`raw/` holds the inputs copied from the full playground. The app reads the small files in `data/`:

    uv run --group precompute python scripts/precompute.py

No optimiser runs at runtime: with 18 sites, every combination is scored directly in numpy (`core.py`).
