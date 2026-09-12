"""The interface must not depend on which glyphs a platform happens to have.

Two faults, both reported from a Windows PC, both the same underlying mistake:
asking the operating system for a picture instead of drawing one.

  Flags showed as two-letter codes - "GB United Kingdom", "IT Italy". A flag
  emoji is a pair of regional indicator letters that the font is supposed to
  combine into a flag, and Microsoft has never shipped flag glyphs in Segoe UI
  Emoji. With nothing to combine them into, the browser draws the two letters
  it was given.

  The navigation icons came out as a jumble. Some of those characters - the
  bank, the scales, the map, the up arrow - are "text presentation by
  default": without a variation selector the browser may draw them from an
  ordinary text font, monochrome and at text weight, while the ones beside
  them arrive from the colour emoji font at emoji size. Four coloured pictures
  and four small black symbols, in one row.

Neither is fixable in CSS, because both are font-selection decisions. Both are
drawn as inline SVG now. This test guards the ways that could quietly come
undone:

  * someone reintroduces an emoji flag or an emoji icon, which will look right
    on the machine they test it on and wrong on every Windows PC
  * a country or a page is added and its artwork is missed, which shows as
    nothing at all rather than as an error

It also checks the details that bit during the change: the map is keyed by the
app's own country codes (the UK is "UK" here, not the ISO "GB", and keying it
wrongly silently produced an empty flag), and the flags carry no element ids -
the first attempt gave every flag a <clipPath id>, which put the same id on
the page seven times over.
"""
import os
import pathlib
import re

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
SRC = pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html"
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")


def main():
    errors, failures = [], []

    def check(cond, msg):
        if not cond:
            failures.append(msg)
        return cond

    # ---- 1. no flag emoji anywhere in the source ---------------------------
    # Both spellings: literal regional indicators, and the numeric entities
    # they are often written as (127462-127487).
    text = SRC.read_text(encoding="utf-8")
    literal = re.findall(r"[\U0001F1E6-\U0001F1FF]{2}", text)
    entities = re.findall(r"&#(1274[6-9][0-9]|12748[0-7]);\s*&#(1274[6-9][0-9]|12748[0-7]);", text)
    check(not literal, f"literal flag emoji in the source: {sorted(set(literal))} - "
                       f"these render as letters on Windows")
    check(not entities, f"flag emoji as numeric entities in the source: {entities[:4]} - "
                        f"these render as letters on Windows")
    print(f"1. no flag emoji in the source (checked {len(text):,} characters)")

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        pg = b.new_context(viewport={"width": 1400, "height": 1100}).new_page()
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(FILE)
        pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
        pg.evaluate("""() => { localStorage.setItem('pensionPlanner.rememberChoice','advanced');
          experienceLevel = 'advanced'; applyLevel(); activateTab('relocate'); renderAll(); }""")
        pg.wait_for_timeout(1300)

        # ---- 2. every country in the comparison has artwork ----------------
        # flagSvg() never returns nothing - it falls back to printing the
        # two-letter code, which is exactly the failure this whole suite
        # exists to prevent. So the check has to be on the artwork itself,
        # not on whether the function returned a string. A country added
        # without a flag used to pass this line silently.
        missing = pg.evaluate("""() => Object.keys(RELOCATE)
          .filter(c => !FLAG_SVG[c] || FLAG_SVG[c].length < 40)""")
        check(not missing, f"these countries would render as a bare country code: {missing}")
        fallback = pg.evaluate("""() => Object.keys(RELOCATE)
          .filter(c => flagSvg(c).includes('flag-code'))""")
        check(not fallback,
              f"these countries fall back to the two-letter code on screen: {fallback}")
        codes = pg.evaluate("() => Object.keys(RELOCATE)")
        print(f"2. all {len(codes)} countries have artwork: {', '.join(codes)}")

        # ---- 3. ...and it actually reaches the page -------------------------
        rows = pg.evaluate("""() => [...document.querySelectorAll('#relocTable tbody tr')].map(tr => {
          const cell = tr.querySelector('td');
          return { text: cell.innerText.split('\\n')[0].trim(),
                   svg: !!cell.querySelector('svg.flag'),
                   painted: cell.querySelectorAll('svg.flag rect, svg.flag path, svg.flag circle').length }; })""")
        check(len(rows) >= 7, f"expected every country in the table, got {len(rows)} rows")
        for r in rows:
            check(r["svg"], f"{r['text']!r} has no flag in the comparison table")
            # an empty <svg> would satisfy the check above and show nothing
            check(r["painted"] >= 2,
                  f"{r['text']!r} has a flag element with only {r['painted']} shape(s) in it")
        print(f"3. all {len(rows)} table rows carry a drawn flag "
              f"({min(r['painted'] for r in rows)}-{max(r['painted'] for r in rows)} shapes each)")

        # ---- 4. the UK is the case that broke ------------------------------
        # RELOCATE keys the UK as "UK"; keying the artwork "GB" produced an
        # empty string and a silently flagless row.
        uk = pg.evaluate("""() => { const t = flagSvg('UK');
          return { has: !!t, len: t.length, blue: t.includes('012169') }; }""")
        check(uk["has"] and uk["blue"],
              f"the UK flag is missing or wrong - flagSvg('UK') gave {uk}")
        print(f"4. flagSvg('UK') returns real artwork ({uk['len']} chars)")

        # ---- 5. no ids inside the flags ------------------------------------
        # Seven flags each carrying <clipPath id="..."> would put the same id
        # on the page seven times.
        ids = pg.evaluate("""() => [...document.querySelectorAll('svg.flag [id], svg.flag[id]')]
          .map(e => e.getAttribute('id'))""")
        check(not ids, f"flag artwork contains element ids, which repeat per flag: {ids[:5]}")
        dupes = pg.evaluate("""() => { const c = {};
          document.querySelectorAll('[id]').forEach(e => c[e.id] = (c[e.id] || 0) + 1);
          return Object.entries(c).filter(([k, v]) => v > 1); }""")
        check(not dupes, f"duplicate element ids on the page: {dupes}")
        print("5. flags carry no ids, and the page has no duplicate ids")

        # ---- 6. they are decorative, and the name is the label --------------
        # A flag beside a country name that is also announced would have a
        # screen reader read the country twice.
        exposed = pg.evaluate("""() => [...document.querySelectorAll('svg.flag')]
          .filter(s => s.getAttribute('aria-hidden') !== 'true').length""")
        check(exposed == 0, f"{exposed} flags are not marked aria-hidden - "
                            f"a screen reader would read the country name twice")
        print("6. flags are aria-hidden; the country name carries the meaning")

        # ---- 7. sized with the text, not fixed ------------------------------
        small = pg.evaluate("""() => document.querySelector('#relocTable svg.flag')
          .getBoundingClientRect().width""")
        pg.evaluate("() => { TEXT_SCALE = 1.5; applyTextScale(); renderAll(); }")
        pg.wait_for_timeout(900)
        big = pg.evaluate("""() => document.querySelector('#relocTable svg.flag')
          .getBoundingClientRect().width""")
        check(big > small * 1.2,
              f"flags do not grow with the text setting: {small:.0f}px -> {big:.0f}px")
        print(f"7. flags scale with the text setting: {small:.0f}px -> {big:.0f}px at 1.5x")

        # ---- 8. every navigation icon is drawn, in both navs ----------------
        pg.evaluate("() => { TEXT_SCALE = 1; applyTextScale(); renderAll(); }")
        pg.wait_for_timeout(700)
        navs = pg.evaluate("""() => {
          const read = sel => [...document.querySelectorAll(sel + ' .tab-btn')].map(b => ({
            tab: b.dataset.tab,
            drawn: !!b.querySelector('.icon svg.ic'),
            shapes: b.querySelectorAll('.icon svg.ic path, .icon svg.ic circle, .icon svg.ic rect, .icon svg.ic ellipse').length }));
          return { rail: read('.rail'), bottom: read('.bottomnav') }; }""")
        for where, items in navs.items():
            check(items, f"no tab buttons found in the {where} navigation")
            for it in items:
                check(it["drawn"], f"{where}: the {it['tab']!r} tab has no drawn icon")
                check(it["shapes"] >= 1, f"{where}: the {it['tab']!r} icon is an empty <svg>")
        print(f"8. every tab icon drawn in both navs "
              f"({len(navs['rail'])} in the rail, {len(navs['bottom'])} in the bottom bar)")

        # ---- 9. one weight, one size ---------------------------------------
        # The original fault was not that the icons were missing but that they
        # did not match each other. Visible icons must all be the same size.
        widths = pg.evaluate("""() => [...document.querySelectorAll('.rail .tab-btn .icon svg.ic')]
          .map(s => s.getBoundingClientRect().width).filter(w => w > 0)
          .map(w => Math.round(w * 10) / 10)""")
        check(len(set(widths)) == 1,
              f"rail icons are not all the same size: {sorted(set(widths))}")
        strokes = pg.evaluate("""() => [...new Set([...document.querySelectorAll('.rail svg.ic')]
          .map(s => getComputedStyle(s).strokeWidth))]""")
        check(len(strokes) == 1, f"rail icons are drawn at different stroke weights: {strokes}")
        print(f"9. all rail icons are {widths[0]}px at stroke {strokes[0]} - one visual family")

        # ---- 10. they take the theme's colour, not a fixed one --------------
        colours = {}
        for theme in ("night", "day"):
            pg.evaluate("(t) => { appTheme = t; applyAppTheme(); }", theme)
            pg.wait_for_timeout(400)
            colours[theme] = pg.evaluate("""() => getComputedStyle(
              document.querySelector('.rail .tab-btn .icon svg.ic')).stroke""")
        check(colours["night"] != colours["day"],
              f"icons keep the same colour in both themes ({colours}) - they are not "
              f"inheriting currentColor, so one theme will have them nearly invisible")
        print(f"10. icons follow the theme: {colours['night']} on Night, {colours['day']} on Day")

        # ---- 11. no emoji left in the chrome --------------------------------
        # Anything above the Latin range in the rail or the bottom bar is a
        # glyph whose appearance belongs to the platform rather than to us.
        left = pg.evaluate(r"""() => {
          const out = [];
          for (const sel of ['.rail', '.bottomnav', '.mobilebar']) {
            const el = document.querySelector(sel);
            if (!el) continue;
            for (const ch of (el.innerText || '')) {
              const c = ch.codePointAt(0);
              // punctuation the app uses deliberately: dashes, ellipsis, quotes
              if (c > 0x2000 && ![0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2026].includes(c)) {
                out.push(sel + ': U+' + c.toString(16).toUpperCase());
              }
            }
          }
          return [...new Set(out)]; }""")
        check(not left, f"emoji or symbol characters remain in the navigation: {left}")
        print("11. no platform-drawn glyphs left in the rail, bottom bar or top bar")

        b.close()

    if errors:
        failures.append("console/page errors: " + "; ".join(sorted(set(errors))[:5]))
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("\nFLAGS AND ICONS ARE DRAWN IN THE PAGE, NOT LEFT TO THE PLATFORM")


if __name__ == "__main__":
    main()
