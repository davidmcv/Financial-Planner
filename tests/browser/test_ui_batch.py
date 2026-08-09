"""The timeline scale, the Major Events option row, the People page density,
and the rule that moving any slider updates everything that depends on it.
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
errors = []


def watch(pg):
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME)
    pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    watch(pg)
    pg.goto(FILE)
    pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
    pg.evaluate('() => { experienceLevel = "advanced"; applyLevel(); activateTab("people"); renderAll(); }')
    pg.wait_for_timeout(900)

    # 1. The timeline scale spreads the milestones out instead of crushing the
    #    near ones against the left edge. Today, retirement, pension access,
    #    State Pension and life expectancy must all be separable by eye.
    marks = pg.evaluate("""() => [...document.querySelectorAll('.tl-track[data-owner=you] .tl-marker')]
      .map(m => ({ name: m.querySelector('b').textContent, x: parseFloat(m.style.left) }))
      .sort((a, b) => a.x - b.x)""")
    assert len(marks) >= 4, marks
    assert marks[0]["name"] == "Today" and marks[0]["x"] == 0, marks
    # the last milestone reaches the far end of the track
    assert marks[-1]["x"] > 80, marks
    # and no two DISTINCT dates land on top of each other
    xs = sorted({round(m["x"], 1) for m in marks})
    assert all(b - a > 3 for a, b in zip(xs, xs[1:])), xs
    print("1. timeline spreads milestones: " + ", ".join(f"{m['name']} {m['x']:.0f}%" for m in marks))

    # 2. It genuinely differs from a linear scale - the near years get more of
    #    the track than their share of the years.
    both = {}
    for scale in ["power", "even"]:
        pg.evaluate("(s) => { timelineScale = s; renderTimeline(lastModel); }", scale)
        pg.wait_for_timeout(300)
        both[scale] = pg.evaluate("""() => { const m = [...document.querySelectorAll('.tl-track[data-owner=you] .tl-marker')]
          .map(x => parseFloat(x.style.left)).sort((a, b) => a - b); return m[1]; }""")
    assert both["power"] > both["even"] + 5, both
    print(f"2. the second milestone sits at {both['power']:.0f}% on the expanded scale "
          f"vs {both['even']:.0f}% linear - that is the crowding it fixes")

    # 3. Both scales keep the milestones in true date order.
    for scale in ["power", "even"]:
        pg.evaluate("(s) => { timelineScale = s; renderTimeline(lastModel); }", scale)
        pg.wait_for_timeout(250)
        seq = pg.evaluate("""() => [...document.querySelectorAll('.tl-track[data-owner=you] .tl-marker')]
          .map(m => ({ x: parseFloat(m.style.left),
                       y: +m.querySelector('.tl-sub').textContent.match(/(\\d{4})/)[1] }))""")
        ordered = sorted(seq, key=lambda s: s["x"])
        years = [s["y"] for s in ordered]
        assert years == sorted(years), (scale, seq)
    pg.evaluate("() => { timelineScale = 'power'; renderTimeline(lastModel); }")
    print("3. both scales keep the dates in order - only the spacing changes")

    # 4. Axis labels never print on top of each other.
    gaps = pg.evaluate("""() => { const s = [...document.querySelectorAll('.tl-axis span')]
      .map(x => parseFloat(x.style.left)).sort((a, b) => a - b);
      return s.slice(1).map((v, i) => +(v - s[i]).toFixed(1)); }""")
    assert gaps and min(gaps) >= 6.9, gaps
    print(f"4. axis labels stay {min(gaps):.1f}%+ apart on the compressed scale")

    # 5. Planned retirement shows the AGE as well as the date, for both people.
    ages = pg.evaluate("() => [els('retireAgeP').textContent, els('spouseRetireAgeP').textContent]")
    assert all("age" in a for a in ages), ages
    print(f"5. planned retirement shows the age for both: {ages[0].strip()} / {ages[1].strip()}")

    # 6. THE propagation rule: move one slider, everything that depends on it
    #    updates - on this page and on pages not currently visible.
    before = pg.evaluate("""() => ({
      age: els('retireAgeP').textContent, date: els('retireDate').value,
      card: document.querySelector('#ageCards .stat:nth-child(2) .value').textContent,
      marker: document.querySelector('.tl-marker.tl-move').style.left,
      planner: els('retireSlider').value })""")
    pg.evaluate("""() => { const r = els('retireSliderP');
      r.value = String(+r.value + 6); r.dispatchEvent(new Event('input', { bubbles: true })); }""")
    pg.wait_for_timeout(600)
    after = pg.evaluate("""() => ({
      age: els('retireAgeP').textContent, date: els('retireDate').value,
      card: document.querySelector('#ageCards .stat:nth-child(2) .value').textContent,
      marker: document.querySelector('.tl-marker.tl-move').style.left,
      planner: els('retireSlider').value })""")
    for k in before:
        assert before[k] != after[k], (k, before[k], after[k])
    print(f"6. one slider moved {before['age'].strip()} -> {after['age'].strip()}: the label, the date field, "
          f"the Key Dates card, the timeline marker and the Planner slider all followed")

    # 7. The Tax page - never visited during that edit - reflects it too.
    pg.evaluate("() => activateTab('tax')")
    pg.wait_for_timeout(800)
    taxYear = pg.evaluate("""() => { const c = [...document.querySelectorAll('#taxCards .person-card')]
      .find(x => x.querySelector('h2').textContent.trim() === 'You');
      return c.querySelectorAll('.tax-section-head .when')[0].textContent.trim(); }""")
    assert after["date"][:4] in taxYear, (taxYear, after["date"])
    print(f"7. the Tax page picked it up without being visited: '{taxYear}'")

    # 8. Major Events options: one flowing row, each taking its own width, and
    #    the survival tick-box last.
    pg.evaluate("() => activateTab('planner')")
    pg.wait_for_timeout(1200)
    row = pg.evaluate("""() => {
      const box = document.querySelector('.check-row');
      const items = [...box.querySelectorAll('.check-inline')];
      const r = box.getBoundingClientRect();
      return { ids: items.map(i => i.querySelector('input').id),
               display: getComputedStyle(box).display, wrap: getComputedStyle(box).flexWrap,
               inside: items.every(i => i.getBoundingClientRect().right <= r.right + 1),
               // each takes its own width, not an equal share of a grid
               widths: items.map(i => Math.round(i.getBoundingClientRect().width)) }; }""")
    assert row["display"] == "flex" and row["wrap"] == "wrap", row
    assert row["ids"][-1] == "showSurvival", row["ids"]
    assert row["inside"], "an option overflowed the row"
    assert len(set(row["widths"])) > 1, row["widths"]     # not forced to equal columns
    print(f"8. options flow and wrap ({row['widths']}), survival tick-box last")

    # 9. The rail's four chart-mode buttons fit without being clipped - the bug
    #    that showed "Deca" and "Numb".
    rail = pg.evaluate("""() => [...document.querySelectorAll('.rail .chartmode-seg button')]
      .map(b => ({ t: b.textContent, clipped: b.scrollWidth - b.clientWidth > 1,
                   inside: b.getBoundingClientRect().right <=
                     document.querySelector('.rail').getBoundingClientRect().right + 1 }))""")
    assert rail and all(not r["clipped"] and r["inside"] for r in rail), rail
    assert [r["t"] for r in rail] == ["Full", "Zoom", "Decades", "Numbers"], rail
    print("9. rail chart-mode buttons all fit: " + ", ".join(r["t"] for r in rail))

    # 10. The age/date line under each event flag uses the higher-contrast
    #     tone. It was --ink-faint, which on the Night theme is grey on dark
    #     and barely there. Checked as CONTRAST against the chart background,
    #     not raw brightness: on the Day theme the readable tone is the DARKER
    #     one, so comparing luminance would assert the wrong thing on one of
    #     the two themes.
    for theme in ["night", "day"]:
        pg.evaluate("(t) => { appTheme = t; applyAppTheme(); }", theme)
        pg.wait_for_timeout(400)
        ratio = pg.evaluate("""() => {
          const lum = c => {
            const m = c.trim().match(/^#(\\w\\w)(\\w\\w)(\\w\\w)$/);
            const v = m.slice(1).map(h => {
              const x = parseInt(h, 16) / 255;
              return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
            });
            return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
          };
          const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
            return (x + 0.05) / (y + 0.05); };
          const bg = themeColor('--surface-2', '#000');
          return { muted: +ratio(themeColor('--ink-muted', ''), bg).toFixed(2),
                   faint: +ratio(themeColor('--ink-faint', ''), bg).toFixed(2) }; }""")
        assert ratio["muted"] > ratio["faint"], (theme, ratio)
        print(f"10{'nd'[['night', 'day'].index(theme)]}. {theme}: flag sub-lines now at "
              f"{ratio['muted']}:1 contrast, up from {ratio['faint']}:1")
    pg.evaluate("() => { appTheme = 'night'; applyAppTheme(); }")

    # 11. The People page fits in fewer screens than it used to (2.51 at
    #     1280x900 before the two-column pass).
    pg.evaluate("() => activateTab('people')")
    pg.wait_for_timeout(700)
    for w, h, limit in [(1280, 900, 2.35), (1600, 1000, 1.85)]:
        pg.set_viewport_size({"width": w, "height": h})
        pg.wait_for_timeout(600)
        screens = pg.evaluate("() => document.documentElement.scrollHeight / window.innerHeight")
        assert screens < limit, (w, h, screens, limit)
        print(f"11{'ab'[[1280, 1600].index(w)]}. People at {w}x{h}: {screens:.2f} screens (under {limit})")

    if errors:
        raise SystemExit("CONSOLE/PAGE ERRORS:\n" + "\n".join(errors[:10]))
    print("\nALL UI BATCH TESTS PASSED, no console/page errors")
    b.close()
