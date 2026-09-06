"""The market stress test at scale: the ladder, and not freezing the page.

The run count used to be a three-item dropdown (200/500/1000). It is now a
slider from 1,000 to 100,000, stepping 2,000 at a time. Two things had to be
true before that was safe, and both are easy to get wrong silently:

  * 100,000 runs must not lock the page. One blocking loop would leave the
    browser unresponsive for seconds with nothing on screen to explain why, so
    the work runs in slices between frames with progress and a cancel.

  * the longevity chart must not inherit the number. It runs its own
    simulation on EVERY redraw - tab switch, resize, theme change, any edit -
    so at 100,000 runs the whole app would stall each time anything moved. It
    is capped, and the cap has to hold however high the slider goes.

And one honesty check: more runs make the answer steadier, not more accurate
about markets. The page has to say so, with the actual margin of error, or the
slider invites people to believe a bigger number means a better forecast.
"""
import os
import pathlib
import time

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


def main():
    errors, failures = [], []

    def check(cond, msg):
        if not cond:
            failures.append(msg)
        return cond

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(FILE)
        pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
        pg.evaluate("""() => { localStorage.setItem('pensionPlanner.rememberChoice','advanced');
          experienceLevel = 'advanced'; applyLevel(); activateTab('planner'); renderAll();
          document.querySelector('.planner-subtab-btn[data-planner-tab="mc-stress"]').click(); }""")
        pg.wait_for_timeout(1100)

        def set_step(s):
            pg.evaluate("""(s) => { const e = document.getElementById('mcRunsSlider');
              e.value = String(s); e.dispatchEvent(new Event('input', {bubbles:true})); }""", s)
            pg.wait_for_timeout(180)

        # ---- 1. the ladder: 1,000 then 2,000 at a time, up to 100,000 -------
        ladder = pg.evaluate("() => Array.from({length: 51}, (_, i) => mcRunsForStep(i))")
        check(ladder[0] == 1000, f"the ladder starts at {ladder[0]}, not 1,000")
        check(ladder[-1] == 100000, f"the ladder ends at {ladder[-1]}, not 100,000")
        steps = {ladder[i + 1] - ladder[i] for i in range(len(ladder) - 2)}
        check(steps == {2000}, f"the steps below the top are not all 2,000: {sorted(steps)}")
        check(len(set(ladder)) == len(ladder), "the ladder repeats a value")
        print(f"1. ladder: {ladder[0]:,}, {ladder[1]:,}, {ladder[2]:,} ... {ladder[-2]:,}, {ladder[-1]:,}")

        # ---- 2. the slider drives the number the model reads ----------------
        for step, want in ((0, 1000), (1, 3000), (25, 51000), (50, 100000)):
            set_step(step)
            got = pg.evaluate("() => parseInt(document.getElementById('mcRuns').value, 10)")
            shown = pg.evaluate("() => document.getElementById('mcRunsVal').textContent")
            check(got == want, f"step {step} set {got:,} runs, expected {want:,}")
            check(shown.replace(",", "") == str(want), f"step {step} shows {shown!r}, expected {want:,}")
        print("2. the slider sets the run count and shows it")

        # ---- 3. old saved plans snap onto the ladder ------------------------
        # Plans saved before the slider existed carry 200 or 500.
        snapped = pg.evaluate("() => [200, 500, 1000, 4000, 100000, 999999].map(r => mcRunsForStep(mcStepForRuns(r)))")
        check(all(v in ladder for v in snapped),
              f"an old saved value did not snap onto the ladder: {snapped}")
        check(snapped[0] == 1000 and snapped[-1] == 100000,
              f"old values snapped oddly: 200 -> {snapped[0]}, 999999 -> {snapped[-1]}")
        print(f"3. old saved values snap onto the ladder: 200 -> {snapped[0]:,}, 999999 -> {snapped[-1]:,}")

        # ---- 4. a 100,000-run test actually runs 100,000 --------------------
        set_step(50)
        pg.evaluate("() => document.getElementById('runMcBtn').click()")
        pg.wait_for_function("() => !mcJob && lastMc && lastMc.runs === 100000", timeout=180000)
        res = pg.evaluate("() => ({ runs: lastMc.runs, pct: lastMc.successPct, bands: lastMc.bands.length })")
        check(res["runs"] == 100000, f"asked for 100,000 runs, got {res['runs']:,}")
        check(0 <= res["pct"] <= 100, f"success rate out of range: {res['pct']}")
        check(res["bands"] > 1, "the fan chart has no bands after the run")
        print(f"4. 100,000 runs completed: {res['pct']:.1f}% success, {res['bands']} bands drawn")

        # ---- 5. ...without blocking the page --------------------------------
        # Start a long run, then time a round trip to the page while it works.
        # A blocking loop would make this wait for the whole simulation.
        set_step(50)
        pg.evaluate("() => document.getElementById('runMcBtn').click()")
        worst = 0
        sampled = 0
        for _ in range(12):
            t0 = time.time()
            still = pg.evaluate("() => !!mcJob")
            dt = (time.time() - t0) * 1000
            if still:
                worst = max(worst, dt)
                sampled += 1
            else:
                break
        check(worst < 500,
              f"the page took {worst:.0f}ms to answer while simulating - the run is blocking the UI")
        pg.wait_for_function("() => !mcJob", timeout=180000)
        print(f"5. page stayed responsive during the run (worst round trip {worst:.0f}ms over {sampled} samples)")

        # ---- 6. progress and cancel -----------------------------------------
        set_step(50)
        pg.evaluate("() => document.getElementById('runMcBtn').click()")
        pg.wait_for_timeout(40)
        mid = pg.evaluate("""() => ({ running: !!mcJob,
          btn: document.getElementById('runMcBtn').textContent.trim(),
          prog: document.getElementById('mcProgress').textContent })""")
        if mid["running"]:
            check(mid["btn"] == "Cancel", f"the button reads {mid['btn']!r} during a run, not 'Cancel'")
            check("Running" in mid["prog"], f"no progress shown during a run: {mid['prog']!r}")
            pg.evaluate("() => document.getElementById('runMcBtn').click()")   # cancel
            pg.wait_for_timeout(300)
            after = pg.evaluate("""() => ({ running: !!mcJob,
              btn: document.getElementById('runMcBtn').textContent.trim() })""")
            check(not after["running"], "cancelling did not stop the run")
            check(after["btn"] == "Run stress test", f"the button stayed {after['btn']!r} after cancelling")
            print(f"6. progress shown ({mid['prog'].strip()}), and Cancel stops it")
        else:
            # Fast machine finished inside 40ms; the mechanism is still checked
            # by test 5, so this is not a failure.
            print("6. run finished too fast to sample progress on this machine (see test 5)")
        pg.wait_for_function("() => !mcJob", timeout=180000)

        # ---- 7. the longevity chart stays capped ----------------------------
        set_step(50)   # 100,000 on the stress test
        used = pg.evaluate("""() => {
          // read what longevityData actually asks mcSimulate for
          let asked = null;
          const real = window.mcSimulate;
          window.mcSimulate = (args) => { asked = args.runs; return real(args); };
          try { longevityData(lastModel); } finally { window.mcSimulate = real; }
          return { asked, cap: LONGEVITY_RUNS_CAP }; }""")
        check(used["asked"] is not None, "longevityData did not call mcSimulate at all")
        check(used["asked"] <= used["cap"],
              f"the longevity chart ran {used['asked']:,} simulations - it must stay at or under "
              f"{used['cap']:,}, because it redraws on every render")
        print(f"7. longevity chart used {used['asked']:,} runs with the slider at 100,000 (cap {used['cap']:,})")

        # ...and redrawing stays quick
        t = pg.evaluate("""() => { const t0 = performance.now();
          for (let i = 0; i < 3; i++) drawLongevityChart(lastModel);
          return performance.now() - t0; }""")
        check(t < 3000, f"three longevity redraws took {t:.0f}ms with the slider at 100,000")
        print(f"   three redraws in {t:.0f}ms")

        # ---- 8. it says what more runs buy ----------------------------------
        pg.evaluate("() => document.getElementById('runMcBtn').click()")
        pg.wait_for_function("() => !mcJob && lastMc", timeout=180000)
        hint = pg.evaluate("() => document.getElementById('mcRunsHint').innerText")
        cap = pg.evaluate("() => document.getElementById('mcCaption').innerText")
        check("steadier" in hint.lower(),
              f"the hint does not say more runs make the answer steadier: {hint[:120]!r}")
        check("percentage points" in hint.lower(), "the hint does not quote a margin of error")
        check("accurate to about" in cap.lower() and "points" in cap.lower(),
              f"the caption does not give the headline's margin of error: {cap[:140]!r}")
        # the margin must actually shrink as runs rise
        m1 = pg.evaluate("() => mcMarginPct(0.9, 1000)")
        m2 = pg.evaluate("() => mcMarginPct(0.9, 100000)")
        check(m1 > m2 * 5, f"the margin of error barely moves: {m1:.2f} at 1,000 vs {m2:.2f} at 100,000")
        print(f"8. margin of error quoted and real: ±{m1:.1f} points at 1,000, ±{m2:.1f} at 100,000")

        b.close()

    if errors:
        failures.append("console/page errors: " + "; ".join(sorted(set(errors))[:5]))
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("\nSTRESS TEST SCALES WITHOUT FREEZING THE PAGE")


if __name__ == "__main__":
    main()
