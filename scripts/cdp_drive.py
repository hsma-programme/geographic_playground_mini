"""Tiny CDP driver: python cdp.py out_prefix step1 step2 ...
Steps: wait:SECONDS | click:TEXT (click element whose text matches) | tapsite:TEXT (mouse tap on a map marker) | tapxy:X,Y | shot:NAME | js:EXPR
"""
import asyncio, json, subprocess, sys, urllib.request, time, os
import websockets

OUT = sys.argv[1]
STEPS = sys.argv[2:]
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

async def main():
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--window-size=1500,2600", "--remote-debugging-port=9333", "--user-data-dir=" + OUT + "_profile", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json")); break
            except Exception:
                time.sleep(0.5)
        ws_url = [t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"]
        async with websockets.connect(ws_url, max_size=None) as ws:
            n = 0
            async def call(method, **params):
                nonlocal n
                n += 1; mid = n
                await ws.send(json.dumps({"id": mid, "method": method, "params": params}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == mid:
                        return msg.get("result", msg)
            await call("Page.enable")
            await call("Page.navigate", url="http://localhost:8599/")
            for step in STEPS:
                kind, _, arg = step.partition(":")
                if kind == "wait":
                    await asyncio.sleep(float(arg))
                elif kind == "shot":
                    r = await call("Page.captureScreenshot", format="png", captureBeyondViewport=True)
                    import base64
                    open(f"{OUT}_{arg}.png", "wb").write(base64.b64decode(r["data"]))
                elif kind == "click":
                    js = """(function(t){var els=[...document.querySelectorAll('button,[role=tab],[role=radio],label,[data-testid=stPills] *')];
                      var e=els.find(x=>x.innerText&&x.innerText.trim()===t)||els.find(x=>x.innerText&&x.innerText.includes(t)); if(!e) return 'not found: '+t; e.click(); return 'clicked '+t;})(%s)""" % json.dumps(arg)
                    r = await call("Runtime.evaluate", expression=js, returnByValue=True)
                    print(r["result"].get("value"))
                elif kind in ("tapsite", "tapxy"):
                    if kind == "tapxy":
                        xy = [float(v) for v in arg.split(",")]
                    else:
                        # Real mouse press/release on a map marker whose hover text contains TEXT
                        js = """(function(t){for(const gd of document.querySelectorAll('.js-plotly-plot')){
                          const sub=gd._fullLayout&&gd._fullLayout.map&&gd._fullLayout.map._subplot; if(!sub) continue;
                          for(const tr of gd._fullData){ if(tr.type!=='scattermap'||!tr.hovertext) continue;
                            const i=[...tr.hovertext].findIndex(h=>String(h).includes(t)); if(i<0) continue;
                            const p=sub.map.project([tr.lon[i],tr.lat[i]]), r=sub.map.getCanvas().getBoundingClientRect();
                            return [r.left+p.x, r.top+p.y]; }}
                          return null;})(%s)""" % json.dumps(arg)
                        r = await call("Runtime.evaluate", expression=js, returnByValue=True)
                        xy = r["result"].get("value")
                        if not xy:
                            print("not found on map: " + arg)
                            continue
                    for typ in ("mouseMoved", "mousePressed", "mouseReleased"):
                        await call("Input.dispatchMouseEvent", type=typ, x=xy[0], y=xy[1],
                                   button="left" if typ != "mouseMoved" else "none", clickCount=1)
                        await asyncio.sleep(0.15)
                    print("tapped %s at %.0f,%.0f" % (arg, xy[0], xy[1]))
                elif kind == "js":
                    r = await call("Runtime.evaluate", expression=arg, returnByValue=True)
                    print(r["result"].get("value"))
    finally:
        proc.terminate()

asyncio.run(main())
