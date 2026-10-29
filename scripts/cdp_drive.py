"""Tiny CDP driver: python cdp.py out_prefix step1 step2 ...
Steps: wait:SECONDS | click:TEXT (click element whose text matches) | shot:NAME | js:EXPR
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
                elif kind == "js":
                    r = await call("Runtime.evaluate", expression=arg, returnByValue=True)
                    print(r["result"].get("value"))
    finally:
        proc.terminate()

asyncio.run(main())
