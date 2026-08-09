"""No two flags on Key dates may ever sit on top of each other.

The old rule guessed from percentages - "if the next marker is within 13% of
the track, step it out a lane" - which cannot be right, because how wide a flag
is depends on its words, the text-size setting and how wide the card happens to
be. At the larger text sizes most flags are wider than 13% of the track, so
they overlapped.

They are now measured and then placed. This checks the result the only way
that means anything: by measuring the rectangles on screen and looking for any
two that intersect - across widths, text sizes, both scales, both people, and
with extra events crowding the near years.
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

OVERLAPS = """() => {
  const bad = [];
  document.querySelectorAll('.tl-track').forEach(tr => {
    const fs = [...tr.querySelectorAll('.tl-flag')].map(f => {
      const r = f.getBoundingClientRect();
      return { t: f.textContent.trim().slice(0, 30), l: r.left, r: r.right, tp: r.top, bt: r.bottom };
    });
    for (let i = 0; i < fs.length; i++) for (let j = i + 1; j < fs.length; j++) {
      const a = fs[i], b = fs[j];
      const ox = Math.min(a.r, b.r) - Math.max(a.l, b.l);
      const oy = Math.min(a.bt, b.bt) - Math.max(a.tp, b.tp);
      if (ox > 0.5 && oy > 0.5) bad.push([a.t, b.t, Math.round(ox), Math.round(oy)]);
    }
  });
  return bad;
}"""

# A flag must also stay inside the card it belongs to, and inside the track's
# own vertical space - pushing a flag out of the box is not a fix for overlap.
ESCAPES = """() => {
  const card = document.getElementById('timelineCard').getBoundingClientRect();
  const out = [];
  document.querySelectorAll('.tl-flag').forEach(f => {
    const r = f.getBoundingClientRect();
    if (r.top < card.top - 1 || r.bottom > card.bottom + 1) {
      out.push([f.textContent.trim().slice(0, 30), Math.round(r.top - card.top), Math.round(r.bottom - card.bottom)]);
    }
  });
  return out;
}"""

WIDTHS = [(1920, 1080), (1400, 1000), (1100, 900), (900, 800), (760, 900), (393, 852)]
SCALES = [1, 1.15, 1.3, 1.5]
checked = 0
failures = []

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME)
    for w, h in WIDTHS:
        for scale in SCALES:
            ctx = b.new_context(viewport={"width": w, "height": h},
                                is_mobile=(w < 500), has_touch=(w < 500))
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: failures.append(f"pageerror: {e}"))
            pg.goto(FILE)
            pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
            pg.evaluate("""(s) => { experienceLevel = 'advanced'; applyLevel();
                TEXT_SCALE = s; applyTextScale(); activateTab('people'); renderAll(); }""", scale)
            pg.wait_for_timeout(900)
            # Both people, and events packed into the near years where the
            # expanded scale spreads things out the most.
            pg.evaluate("""() => {
              if (!els('spouseSwitch').classList.contains('on')) els('spouseSwitch').click();
              const y = new Date().getFullYear();
              planEvents.length = 0;
              [1, 2, 3, 5].forEach((d, i) => planEvents.push(
                { label: 'Event ' + (i + 1), year: y + d, amount: 10000, dir: 'in' }));
              renderEventList(); renderAll(); }""")
            pg.wait_for_timeout(1100)
            for tlscale in ["power", "even"]:
                pg.evaluate("(s) => { timelineScale = s; renderTimeline(lastModel); }", tlscale)
                pg.wait_for_timeout(450)
                checked += 1
                where = f"{w}x{h} text={scale} {tlscale}"
                for x in pg.evaluate(OVERLAPS):
                    failures.append(f"[{where}] '{x[0]}' overlaps '{x[1]}' by {x[2]}x{x[3]}px")
                for x in pg.evaluate(ESCAPES):
                    failures.append(f"[{where}] '{x[0]}' escaped the card ({x[1]}, {x[2]})")
                # every flag must still be attached to its own marker's x
                drift = pg.evaluate("""() => { const bad = [];
                  document.querySelectorAll('.tl-marker').forEach(m => {
                    const f = m.querySelector('.tl-flag'); if (!f) return;
                    const mr = m.getBoundingClientRect(), fr = f.getBoundingClientRect();
                    const mid = (mr.left + mr.right) / 2;
                    if (fr.left - 2 > mid || fr.right + 2 < mid) bad.push(f.textContent.trim().slice(0, 24));
                  });
                  return bad; }""")
                for d in drift:
                    failures.append(f"[{where}] flag '{d}' floated away from its marker")
            ctx.close()
    b.close()

print(f"checked {checked} timeline states across {len(WIDTHS)} widths and {len(SCALES)} text sizes")
if failures:
    uniq = sorted(set(failures))
    print(f"\n{len(uniq)} problems:")
    for f in uniq[:30]:
        print("  " + f)
    raise SystemExit(1)
print("NO FLAGS OVERLAP, none escape the card, and each stays over its own marker")
