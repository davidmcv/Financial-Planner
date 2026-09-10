"""The front page claims nothing leaves your device. That has to stay true.

A privacy claim is the one kind of copy that can become a lie without anyone
touching it. Add a web font, a chart library from a CDN, an analytics snippet,
a map tile, an avatar image - all of them are one line, none of them looks
like a change to the privacy of the app, and every one of them would make the
sentence on the front page false.

So this does not read the claim and nod at it. It runs the app and watches
the network, twice, because the two ways it gets opened behave differently:

  FROM A FILE   exactly one request: the page itself. Nothing else at all,
                which is what makes it work with Wi-Fi off.

  OVER HTTP     the page, plus one request to its OWN address asking whether
                an optional account server is running there. On the published
                site there is none. That request is disclosed on the front
                page rather than glossed over - a claim the browser's network
                tab can contradict is worse than no claim.

Anything to a third-party host fails the test. So does an unvisited claim:
the note has to be on screen when the app opens, not buried.

The offline check is the real one. The page is loaded, the browser is then
cut off from everything, and the app is driven through every tab and a full
market simulation. If it still works, "run it with Wi-Fi off" is true.
"""
import functools
import http.server
import pathlib
import socketserver
import threading
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
PAGE = ROOT / "pension-planner.html"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
PORT = 8897

TABS = ["people", "savings", "salary", "projection", "planner", "tax", "gifting", "relocate"]


def drive(pg):
    """Use the app properly: every tab, and the heaviest thing it does."""
    pg.evaluate("""() => { localStorage.setItem('pensionPlanner.rememberChoice','advanced');
      experienceLevel = 'advanced'; applyLevel(); renderAll(); }""")
    pg.wait_for_timeout(900)
    for t in TABS:
        pg.evaluate("(t) => activateTab(t)", t)
        pg.wait_for_timeout(300)
    pg.evaluate("() => { const b = document.getElementById('runMcBtn'); if (b) b.click(); }")
    pg.wait_for_timeout(1500)


def main():
    failures, errors = [], []

    def check(cond, msg):
        if not cond:
            failures.append(msg)
        return cond

    class Silent(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):        # the 404 on /api/health is expected
            pass

    handler = functools.partial(Silent, directory=str(ROOT))

    class Quiet(socketserver.TCPServer):
        allow_reuse_address = True

        def handle_error(self, *a):
            pass

    srv = Quiet(("127.0.0.1", PORT), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.4)

    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME)

            # ---- 1. from a file: one request, and that request is itself ----
            reqs = []
            ctx = b.new_context(viewport={"width": 1400, "height": 1000})
            pg = ctx.new_page()
            pg.on("request", lambda r: reqs.append(r.url))
            pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            pg.goto(PAGE.as_uri())
            pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
            drive(pg)
            real = [u for u in reqs if not u.startswith(("data:", "blob:", "about:"))]
            check(len(real) == 1,
                  f"opened from a file the page made {len(real)} requests, not one: {real[:6]}")
            check(real and real[0].startswith("file://"),
                  f"the one request was not the page itself: {real[:2]}")
            print(f"1. from a file: {len(real)} request ({len(reqs)} counting data: URIs) - the page itself")
            ctx.close()

            # ---- 2. over http: only its own origin ---------------------------
            reqs2 = []
            ctx = b.new_context(viewport={"width": 1400, "height": 1000})
            pg = ctx.new_page()
            pg.on("request", lambda r: reqs2.append(r.url))
            pg.on("pageerror", lambda e: errors.append(f"pageerror(http): {e}"))
            pg.goto(f"http://127.0.0.1:{PORT}/pension-planner.html")
            pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
            drive(pg)
            real2 = [u for u in reqs2 if not u.startswith(("data:", "blob:", "about:"))]
            offsite = [u for u in real2 if f"127.0.0.1:{PORT}" not in u]
            check(not offsite,
                  f"the page contacted somewhere other than its own address: {offsite}")
            check(len(real2) <= 2,
                  f"served over http the page made {len(real2)} requests: {real2}")
            print(f"2. over http: {len(real2)} requests, all to its own address: "
                  f"{[u.split('127.0.0.1:%d' % PORT)[-1] for u in real2]}")

            # ...and that extra request is the one the note discloses
            note = pg.evaluate("() => document.getElementById('privacyNote').innerText")
            if len(real2) > 1:
                check("account server" in note.lower(),
                      "the page makes a request when served over http but the note does not say so")
            print("3. the note discloses the account-server probe when it happens")
            ctx.close()

            # ---- 4. the note is on the front page, unprompted -----------------
            ctx = b.new_context(viewport={"width": 1400, "height": 1000})
            pg = ctx.new_page()
            pg.goto(PAGE.as_uri())
            pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
            pg.wait_for_timeout(900)
            vis = pg.evaluate("""() => { const n = document.getElementById('privacyNote');
              if (!n) return null;
              const r = n.getBoundingClientRect();
              return { onStart: document.body.classList.contains('on-start'),
                       visible: r.width > 0 && r.height > 0,
                       text: n.innerText }; }""")
            check(vis, "there is no privacy note on the page")
            if vis:
                check(vis["onStart"], "the app did not open on the front page, so this proves nothing")
                check(vis["visible"], "the privacy note is on the front page but not visible")
                for phrase in ("leaves your device", "Wi-Fi turned off", "no analytics"):
                    check(phrase.lower() in vis["text"].lower(),
                          f"the note no longer says {phrase!r}")
            print("4. the note is on the front page and visible without doing anything")
            ctx.close()

            # ---- 5. it genuinely works with the network gone ------------------
            # Load, then cut everything off, then use the app in anger.
            ctx = b.new_context(viewport={"width": 1400, "height": 1000})
            pg = ctx.new_page()
            offline_errors = []
            pg.on("pageerror", lambda e: offline_errors.append(str(e)))
            pg.on("console", lambda m: offline_errors.append(m.text) if m.type == "error" else None)
            pg.goto(PAGE.as_uri())
            pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
            ctx.set_offline(True)
            # every route dies from here on, so anything it needs must be local
            pg.route("**/*", lambda route: route.abort())
            drive(pg)
            works = pg.evaluate("""() => {
              const m = computeAll();
              const f = householdFunding(m);
              return { years: f.years.length,
                       income: Math.round(f.byYear[f.years[0]].total),
                       mc: lastMc ? lastMc.runs : 0,
                       countries: Object.keys(RELOCATE).length }; }""")
            check(works["years"] > 10, f"the projection did not run offline: {works}")
            check(works["income"] > 0, f"no income computed offline: {works}")
            check(works["mc"] > 0, "the market stress test did not run offline")
            check(works["countries"] > 30, "the country comparison lost its data offline")
            check(not offline_errors,
                  f"errors while offline: {sorted(set(offline_errors))[:3]}")
            print(f"5. offline: {works['years']} years projected, first year "
                  f"£{works['income']:,}, {works['mc']:,} simulations, "
                  f"{works['countries']} countries - no errors")
            ctx.close()
            b.close()
    finally:
        srv.shutdown()
        srv.server_close()

    if errors:
        failures.append("page errors: " + "; ".join(sorted(set(errors))[:4]))
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("\nTHE PRIVACY CLAIM ON THE FRONT PAGE IS TRUE")


if __name__ == "__main__":
    main()
