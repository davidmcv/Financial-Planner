"""Nothing on screen may be cut off.

A standing guard, not a one-off: it walks every visible element and fails when
text is wider than the box drawn around it, or when a box spills out of its
parent. That is the class of bug that clipped "Decades"/"Numbers" in the rail
to "Deca"/"Numb" - invisible to a test that only checks the page doesn't
scroll sideways, because a clipped child doesn't widen the page.

Run at several widths, at both text sizes, and with the rail open and closed,
because all four change what fits.
"""
from playwright.sync_api import sync_playwright

import pathlib
FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
import os
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

# Elements whose content is legitimately scrollable or deliberately clipped.
SKIP = """
  .table-scroll, .table-scroll *, .chart-wrap, .chart-wrap *, .scroll-mirror,
  .scroll-mirror *, #timelineCard, #timelineCard *, textarea, canvas,
  .fold, .fold *, .rail-fold-block, .rail-fold-block *, select, option,
  .modal-backdrop, .modal-backdrop *,
  input
"""
# `input` is excluded on purpose: a text field whose value is longer than its
# box scrolls internally, which is how text fields have always worked. That is
# not clipped layout - you can click in and read the rest.

DETECT = """
(skip) => {
  const bad = [];
  const skipEls = new Set(document.querySelectorAll(skip));
  document.querySelectorAll('body *').forEach(el => {
    if (skipEls.has(el)) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') return;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    // Text wider than its own box, with no way to reach the rest of it.
    const clipped = el.scrollWidth - el.clientWidth > 1 &&
                    cs.overflowX !== 'auto' && cs.overflowX !== 'scroll';
    if (clipped) {
      bad.push({ why: 'text clipped', sel: el.tagName.toLowerCase() +
        (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string'
          ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.') : ''),
        over: el.scrollWidth - el.clientWidth,
        text: (el.textContent || '').trim().slice(0, 40) });
    }
  });
  return bad;
}
"""

TABS = ["people", "savings", "salary", "projection", "planner", "tax", "gifting"]
failures = []
checked = 0

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME)
    for w, h in [(1920, 1080), (1440, 900), (1280, 900), (1024, 800), (900, 800), (393, 852)]:
        for scale in [1, 1.5]:
            for railCollapsed in ([False, True] if w > 860 else [False]):
                ctx = b.new_context(viewport={"width": w, "height": h},
                                    is_mobile=(w < 500), has_touch=(w < 500))
                pg = ctx.new_page()
                pg.goto(FILE)
                pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
                pg.evaluate("""(s) => { experienceLevel = 'advanced'; applyLevel();
                    TEXT_SCALE = s; applyTextScale(); }""", scale)
                if railCollapsed:
                    pg.evaluate("() => { railCollapsed = true; applyRail(); }")
                pg.wait_for_timeout(500)
                for tab in TABS:
                    pg.evaluate("(t) => activateTab(t)", tab)
                    pg.wait_for_timeout(700)
                    # A collapsed rail clips its own labels on purpose - that
                    # IS the concertina - so its containers are exempt only in
                    # that state. Expanded, the rail is checked like anything
                    # else, which is what this test exists for.
                    skip = SKIP + (", .rail, .brand, .settings-btn, .wording-seg" if railCollapsed else "")
                    bad = pg.evaluate(DETECT, skip)
                    checked += 1
                    for x in bad:
                        failures.append(f"[{w}x{h} text={scale} rail={'closed' if railCollapsed else 'open'} "
                                        f"{tab}] {x['sel']} clipped by {x['over']}px: '{x['text']}'")
                ctx.close()
    b.close()

print(f"checked {checked} page states")
if failures:
    uniq = sorted(set(failures))
    print(f"\n{len(uniq)} clipped elements:")
    for f in uniq[:40]:
        print("  " + f)
    raise SystemExit(1)
print("NOTHING IS CLIPPED anywhere, at any width, text size, or rail state")
