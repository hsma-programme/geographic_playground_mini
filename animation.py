"""The optimiser animation: a map that flicks through every combination of sites.

Plotly's own frame animation (fig.frames + auto_play) only starts once Plotly.newPlot
resolves, and on a map subplot that promise can stall until the basemap style has
loaded - so autoplay silently never started. Instead the figure is exported as a
single static map and a few lines of JS step through precomputed colours with
Plotly.restyle on a timer. That also lets us draw a proper header and progress bar.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import streamlit as st

from core import Data, label, nearest_time
from figures import travel_map

STATIC_DIR = Path(__file__).parent / "static"
MAP_HEIGHT = 560
HEADER_HEIGHT = 96
FOOTER_HEIGHT = 44


def _frame_duration_ms(n_frames: int) -> int:
    """Slow enough to read when there are few options, a blur when there are many."""
    if n_frames <= 20:
        return 700
    if n_frames <= 120:
        return 140
    return 55


def build_payload(data: Data, mode, scores, objective, seed=7) -> dict:
    """Everything the browser needs: per-frame area colours, marker positions, captions.

    Combinations are shown in random order (not listing order) so the "best so far"
    changes as the search goes - which is what watching a real search looks like.
    """
    order = np.random.default_rng(seed).permutation(len(scores))
    combos = [scores.iloc[i]["sites"] for i in order]
    values = scores[objective].to_numpy()[order]
    n = len(combos)

    z, lat, lon, trying, best_text, new_best = [], [], [], [], [], []
    best = 0
    for k, combo in enumerate(combos):
        if values[k] < values[best]:
            gain = values[best] - values[k]
            amount = f"{gain:.1f} min" if gain >= 0.05 else "under 0.1 min"
            new_best.append(f"New winner: {amount} quicker on average")
            best = k
        else:
            new_best.append(None)
        site = data.sites.loc[list(combo)]
        z.append(nearest_time(data, mode, combo).round(0).astype(int).tolist())
        lat.append(site["Latitude"].tolist())
        lon.append(site["Longitude"].tolist())
        trying.append(f"<b>Trying:</b> {label(data, combo)} <span class='dim'>option {k + 1} of {n}</span>")
        best_text.append(f"<b>Best so far:</b> {label(data, combos[best])} <span class='dim'>{values[best]:.1f} min average journey</span>")

    # Final frame lands on the overall winner
    winner = int(np.argmin(values))
    site = data.sites.loc[list(combos[winner])]
    z.append(z[winner])
    lat.append(site["Latitude"].tolist())
    lon.append(site["Longitude"].tolist())
    trying.append(f"<b>Done!</b> All {n} options tried")
    best_text.append(f"<b>Winner:</b> {label(data, combos[winner])} <span class='dim'>{values[winner]:.1f} min average journey</span>")
    new_best.append(None)

    return dict(z=z, lat=lat, lon=lon, trying=trying, best=best_text, new_best=new_best,
                duration=_frame_duration_ms(n))


PAGE_CSS = """
html,body{overflow:hidden;}
body{margin:0;background:transparent;color:#fff;font-family:'Space Grotesk',sans-serif;}
#hdr{height:%dpx;box-sizing:border-box;padding:6px 4px;font-size:21px;line-height:1.5;}
#hdr .dim{opacity:.65;font-size:16px;margin-left:8px;}
#bestrow{display:flex;align-items:center;gap:12px;white-space:nowrap;}
#best{overflow:hidden;text-overflow:ellipsis;}
#tag{flex-shrink:0;background:#2e9e4f;color:#fff;font-size:15px;font-weight:600;padding:2px 10px;border-radius:999px;
  opacity:0;transition:opacity .3s;}
#tag.show{opacity:1;}
#bar{height:6px;background:#333;border-radius:3px;margin:0 0 8px;}
#fill{height:100%%;width:0;background:#1fb1b9;border-radius:3px;}
#ctl{height:%dpx;}
button{background:#2b2b2b;color:#fff;border:1px solid #555;border-radius:6px;padding:6px 16px;font-size:16px;cursor:pointer;margin-right:8px;}
button.on{background:#1fb1b9;border-color:#1fb1b9;}
#toast{position:fixed;z-index:10;right:16px;bottom:%dpx;max-width:340px;padding:14px 18px;border-radius:8px;
  background:#262730;border-left:4px solid #1fb1b9;box-shadow:0 4px 16px rgba(0,0,0,.5);
  font-size:18px;line-height:1.4;opacity:0;transform:translateY(12px);transition:opacity .4s,transform .4s;pointer-events:none;}
#toast.show{opacity:1;transform:none;}
"""

# Placeholder tokens are swapped in with str.replace, so the JS can keep literal braces
PAGE_JS = """
var P = __PAYLOAD__;
var gd = document.getElementById('map');
var i = 0, playing = true, looping = false, timer = null, toastTimer = null;
var toggleBtn = document.getElementById('toggle'), loopBtn = document.getElementById('loop');
var toast = document.getElementById('toast');
var tag = document.getElementById('tag'), tagTimer = null;
function showToast() {
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function () { toast.classList.remove('show'); }, 8000);
}
function setPlaying(on) {
  playing = on;
  toggleBtn.textContent = playing ? 'Pause' : (i === 0 ? 'Play again' : 'Play');
  clearTimeout(timer);
  if (playing) { toast.classList.remove('show'); tick(); }
}
function show(k) {
  Plotly.restyle(gd, {z: [P.z[k]]}, [0]);
  Plotly.restyle(gd, {lat: [P.lat[k], P.lat[k]], lon: [P.lon[k], P.lon[k]]}, [3, 4]);  // outline + marker
  document.getElementById('trying').innerHTML = P.trying[k];
  document.getElementById('best').innerHTML = P.best[k];
  document.getElementById('fill').style.width = (100 * (k + 1) / P.z.length) + '%';
  if (P.new_best[k]) {
    // Held long enough to read even when frames fly by; a newer winner replaces it
    tag.textContent = P.new_best[k];
    tag.classList.add('show');
    clearTimeout(tagTimer);
    tagTimer = setTimeout(function () { tag.classList.remove('show'); }, Math.max(1500, 2 * P.duration));
  } else if (k === 0 || k === P.z.length - 1) {
    tag.classList.remove('show');
  }
}
function tick() {
  if (!gd.data || !gd._fullLayout) { timer = setTimeout(tick, 200); return; }  // not drawn yet
  show(i);
  var last = (i === P.z.length - 1);
  i = last ? 0 : i + 1;
  // Stops on the winner unless looping is on (for leaving it running on the stand)
  if (last && !looping) { setPlaying(false); showToast(); return; }
  if (playing) timer = setTimeout(tick, last ? 3500 : P.duration);
}
toggleBtn.onclick = function () { setPlaying(!playing); };
loopBtn.onclick = function () {
  looping = !looping;
  this.classList.toggle('on', looping);
  this.textContent = looping ? 'Loop: on' : 'Loop: off';
  if (looping && !playing) setPlaying(true);
};
tick();
"""


def render_optimiser_animation(data: Data, mode, scores, objective="avg"):
    payload = build_payload(data, mode, scores, objective)

    # Drawn with no chosen sites so every candidate keeps its grey dot throughout;
    # the first frame fills in the colours and the yellow marker.
    fig = travel_map(data, mode, (), cutoff=0, view="time", height=MAP_HEIGHT)
    fig.data[0].update(showscale=False, hovertemplate="%{z:.0f} min to nearest centre<extra></extra>")
    fig.data[4].update(mode="markers", text=None)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)")
    map_html = fig.to_html(
        full_html=False, include_plotlyjs="cdn", div_id="map",
        config={"displayModeBar": False, "responsive": True},
    )

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600&display=swap'>"
        f"<style>{PAGE_CSS % (HEADER_HEIGHT, FOOTER_HEIGHT, FOOTER_HEIGHT + 80)}</style></head><body>"
        "<div id='hdr'><div id='trying'></div>"
        "<div id='bestrow'><span id='best'></span><span id='tag'></span></div></div>"
        "<div id='bar'><div id='fill'></div></div>"
        f"{map_html}"
        "<div id='ctl'><button id='toggle'>Pause</button><button id='loop'>Loop: off</button></div>"
        "<div id='toast'><b>Done!</b> Scroll down to see how a different question "
        "can pick a different winner &darr;</div>"
        f"<script>{PAGE_JS.replace('__PAYLOAD__', json.dumps(payload))}</script>"
        "</body></html>"
    )

    # Embedded by URL, not inline: components.html uses an iframe srcdoc, in which the
    # map's tiles and areas never finish loading (the map stays blank). The file is
    # named by content hash so each combination of choices gets its own page.
    STATIC_DIR.mkdir(exist_ok=True)
    name = f"optimiser_{hashlib.md5(html.encode()).hexdigest()[:12]}.html"
    path = STATIC_DIR / name
    if not path.exists():
        path.write_text(html, encoding="utf8")
    # A tiny srcdoc page that loads the real one by a relative URL, so it resolves
    # against the app's own address. "/app/static/..." would miss the "/~/+/" prefix
    # the app is served under on Community Cloud.
    redirect = f"<script>location.replace({json.dumps('app/static/' + name)})</script>"
    st.iframe(redirect, height=HEADER_HEIGHT + MAP_HEIGHT + FOOTER_HEIGHT + 40)
    return html
