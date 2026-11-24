"""Build the stlite (in-browser) version of the app into a static folder.

    uv run python stlite/build.py [--out _site]
    python -m http.server 8599 -d _site

The Community Cloud app is not touched: this copies its files, patches only the copy
(an import of the stubs at the top of streamlit_app.py) and pre-renders the
optimiser animation pages that the server would otherwise write at runtime.
"""

import argparse
import importlib.metadata as md
import json
import shutil
import sys
import tomllib
from pathlib import Path

STLITE_VERSION = "1.12.3"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

APP_PY = ["streamlit_app.py", "core.py", "figures.py", "pareto.py", "animation.py", "mobile_nav.py"]
APP_DIRS = ["data", "resources"]
APP_FILES = ["style.css"]  # config.toml goes in via streamlitConfig instead


def copy_tree(src: Path, dst: Path):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def vendor(package: str, out: Path):
    """Copy an installed pure-Python package and its licence file(s) into the site."""
    dist = md.distribution(package)
    copy_tree(Path(dist.locate_file(package)), out / package)
    for f in dist.files or []:
        if "licen" in f.name.lower() and "dist-info" in str(f):
            (out / "licences").mkdir(exist_ok=True)
            shutil.copy(dist.locate_file(f), out / "licences" / f"{package}-{f.name}")


def flatten(d: dict, prefix="") -> dict:
    flat = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        flat.update(flatten(v, key + ".") if isinstance(v, dict) else {key: v})
    return flat


HASH_NAME = 'name = f"optimiser_{hashlib.md5(html.encode()).hexdigest()[:12]}.html"'
# The hash differs between CPython (build) and Pyodide (browser), so the page would 404.
# Tab 2 only ever asks for 3 pages, which differ in how many options they show.
COUNT_NAME = 'name = f"optimiser_{len(scores)}.html"'


# stlite's Streamlit fork (1.65) marks an open sidebar with aria-expanded="true"; the app's
# style.css targets the data-collapsed="false" that 1.66.1 uses, so its sidebar width rules never match.
# These copies of those two rules are appended to the built style.css only. The phone rule
# comes second so it still wins on narrow screens.
SIDEBAR_CSS = """
/* stlite build: the sidebar rules above, for the older markup */
section[data-testid="stSidebar"][aria-expanded="true"] {
	width: 24rem !important;
	min-width: 24rem !important;
}
@media (max-width: 767.98px) {
	section[data-testid="stSidebar"][aria-expanded="true"] {
		min-width: 0 !important;
	}
}
/* stlite build: ":yellow[**...**]" text in an info box (see TEXT_PATCHES), in the app's own yellow.
   Streamlit's :yellow is paler, and style.css forces strong in info boxes to near-white. */
[data-testid="stAlertContentInfo"] .stMarkdownColoredText,
[data-testid="stAlertContentInfo"] .stMarkdownColoredText strong {
	color: #ffe600 !important;
}
"""


# Wording tweaks that apply to the stlite build only (exact text in the copied streamlit_app.py)
TEXT_PATCHES = [
    ('"Tap a grey dot on the map, or a town', '":yellow[**Tap a grey dot on the map**], or a town'),
]


def prerender_animations(out: Path):
    """The 3 pages tab 2 can ask for (1-3 new centres, by car, default cutoff).

    Uses the patched copy of animation.py in the site, so the browser asks for the same names.
    """
    sys.path.insert(0, str(out))
    import animation
    from core import MAX_NEW_SITES, load_data, score_all_combinations

    animation.STATIC_DIR = out / "app" / "static"
    animation.STATIC_DIR.parent.mkdir(parents=True, exist_ok=True)
    data = load_data()
    for n in range(1, MAX_NEW_SITES + 1):
        # 45 is DEFAULT_CUTOFF["car"] in streamlit_app.py
        scores = score_all_combinations("car", n, 45.0, "today")
        animation.render_optimiser_animation(data, "car", scores, "avg")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "_site"))
    ap.add_argument("--serve", action="store_true", help="after building, serve the site locally (Ctrl+C to stop)")
    ap.add_argument("--port", type=int, default=8599)
    args = ap.parse_args()
    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    for name in APP_PY:
        shutil.copy(ROOT / name, out / name)
    for name in APP_FILES:
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / name, out / name)
    for name in APP_DIRS:
        copy_tree(ROOT / name, out / name)

    # Only the copies are patched (the app's own files stay as they are)
    css = out / "style.css"
    css.write_text(css.read_text(encoding="utf8") + SIDEBAR_CSS, encoding="utf8")
    anim = out / "animation.py"
    src = anim.read_text(encoding="utf8")
    assert HASH_NAME in src, "animation.py changed: update HASH_NAME in stlite/build.py"
    anim.write_text(src.replace(HASH_NAME, COUNT_NAME), encoding="utf8")
    # The stubs must be in place before lokigi is imported
    shutil.copy(ROOT / "stlite" / "stlite_shims.py", out / "stlite_shims.py")
    entry = out / "streamlit_app.py"
    app_src = entry.read_text(encoding="utf8")
    for old, new in TEXT_PATCHES:
        assert old in app_src, f"streamlit_app.py changed: update TEXT_PATCHES in stlite/build.py ({old!r})"
        app_src = app_src.replace(old, new)
    entry.write_text("import stlite_shims  # noqa: F401  (stlite build only)\n" + app_src, encoding="utf8")

    vendor("lokigi", out)
    vendor("sweetpareto", out)
    prerender_animations(out)

    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    config = flatten(tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf8")))
    # stlite 1.12.3 crashes (react-helmet) on a theme.font that carries a font URL. style.css
    # already applies the family, so only the download is needed: load it from index.html.
    font = config.pop("theme.font", "")
    font_url = font.split(":", 1)[1].rsplit(",", 1)[0].strip() if ":http" in font else ""
    options = {
        "entrypoint": "streamlit_app.py",
        "files": {f: {"url": f} for f in files},
        "requirements": [f"plotly=={md.version('plotly')}", f"seaborn=={md.version('seaborn')}"],
        "streamlitConfig": config,
    }
    html = (ROOT / "stlite" / "index.html").read_text(encoding="utf8")
    html = html.replace("__STLITE_VERSION__", STLITE_VERSION).replace("__MOUNT_OPTIONS__", json.dumps(options, indent=2))
    html = html.replace("__FONT_LINK__", f'<link rel="stylesheet" href="{font_url}" />' if font_url else "")
    (out / "index.html").write_text(html, encoding="utf8")
    (out / ".nojekyll").write_text("")
    print(f"Built {len(files)} files into {out}")
    print(f"Preview: python -m http.server {args.port} -d {out}")
    if args.serve:
        serve(out, args.port)



def serve(out: Path, port: int):
    """Plain static server, as stlitepack's preview does. stlite can't run from file://."""
    import functools
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(out))
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"Serving http://localhost:{port}/ (first load takes 20-60 s; Ctrl+C to stop)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Stopped")


if __name__ == "__main__":
    main()
