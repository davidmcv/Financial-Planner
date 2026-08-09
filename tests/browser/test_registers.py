"""Simple means plain English; Advanced means the professional register.

Not just in the popovers - in the page's own prose. The page is written once,
in the professional register, and the plain one is produced from it by swapping
the terms that carry the jargon. The swap has to be reversible: going back to
Advanced must restore exactly what was written, not a paraphrase of a
paraphrase, however many times you flip between them.
"""
import os
import pathlib
import re

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
errors = []

# Words a reader who ticked "Simple" should never be shown without help.
JARGON = ["decumulation", "accumulation phase", "crystallis", "uncrystallis",
          "marginal rate", "nil-rate band", "Potentially Exempt Transfer",
          "sequence risk", "sequence-of-returns", "salary sacrifice",
          "relief at source", "Pension Commencement Lump Sum", "equities",
          "concessional", "amortisation"]
TABS = ["people", "savings", "salary", "projection", "planner", "tax", "gifting"]

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME)
    pg = b.new_context(viewport={"width": 1500, "height": 1100}).new_page()
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    pg.goto(FILE)
    pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
    pg.evaluate("() => { experienceLevel = 'advanced'; applyLevel(); renderAll(); }")
    pg.wait_for_timeout(1200)

    def visible_text():
        return pg.evaluate("""() => [...document.querySelectorAll('.panel.active, .rail')]
          .map(el => el.innerText).join('\\n')""")

    def set_level(level):
        pg.evaluate("(l) => { experienceLevel = l; applyLevel(); renderAll(); }", level)
        pg.wait_for_timeout(1000)

    # 1. On Simple, none of the jargon survives anywhere on any page.
    set_level("simple")
    found = {}
    for tab in TABS:
        pg.evaluate("(t) => activateTab(t)", tab)
        pg.wait_for_timeout(900)
        text = visible_text()
        for j in JARGON:
            if re.search(j, text, re.I):
                found.setdefault(j, []).append(tab)
    assert not found, found
    print(f"1. Simple: none of {len(JARGON)} jargon terms appears on any of the {len(TABS)} pages")

    # 2. On Advanced the professional wording is back, and it is really there -
    #    a test that only checks the plain side would pass on a page that had
    #    quietly lost the technical register altogether.
    set_level("advanced")
    seen = set()
    for tab in TABS:
        pg.evaluate("(t) => activateTab(t)", tab)
        pg.wait_for_timeout(900)
        text = visible_text()
        for j in JARGON:
            if re.search(j, text, re.I):
                seen.add(j)
    assert len(seen) >= 5, seen
    print(f"2. Advanced: the professional wording is back ({', '.join(sorted(seen))})")

    # 3. Flipping repeatedly is lossless. Capture the Advanced text, go plain,
    #    come back, and it must be character-for-character what it was.
    #    Checked on the Pensions and Savings pages rather than the Planner: the
    #    Planner re-runs a Monte Carlo on every render, so its success rate
    #    moves by a point or two between renders for reasons that have nothing
    #    to do with wording.
    baselines = {}
    for tab in ["salary", "savings", "people"]:
        pg.evaluate("(t) => activateTab(t)", tab)
        pg.wait_for_timeout(900)
        baselines[tab] = visible_text()
    for _ in range(3):
        set_level("simple")
        set_level("advanced")
    for tab, baseline in baselines.items():
        pg.evaluate("(t) => activateTab(t)", tab)
        pg.wait_for_timeout(900)
        now = visible_text()
        if now != baseline:
            import difflib
            diff = "\n".join(list(difflib.unified_diff(
                baseline.split("\n"), now.split("\n"), lineterm=""))[:16])
            raise AssertionError(f"three round trips changed the Advanced wording on {tab}:\n{diff}")
    print(f"3. three round trips: the Advanced wording comes back exactly on "
          f"{', '.join(baselines)}")

    # 4. Simple is stable too - flipping does not accumulate swap spans, or
    #    re-swap inside its own replacements.
    set_level("simple")
    n1 = pg.evaluate("() => document.querySelectorAll('.reg-swap').length")
    plain1 = visible_text()
    for _ in range(3):
        pg.evaluate("() => renderAll()")
        pg.wait_for_timeout(400)
    pg.wait_for_timeout(500)
    n2 = pg.evaluate("() => document.querySelectorAll('.reg-swap').length")
    nested = pg.evaluate("() => document.querySelectorAll('.reg-swap .reg-swap').length")
    assert nested == 0, nested
    assert n1 == n2, (n1, n2)
    assert visible_text() == plain1, "re-rendering changed the plain wording"
    print(f"4. Simple is stable across re-renders: {n1} swaps, none nested")

    # 5. A swap keeps the sentence's capitalisation.
    caps = pg.evaluate("""() => [...document.querySelectorAll('.reg-swap')]
      .map(s => ({ src: s.dataset.regSrc, out: s.textContent }))
      .filter(x => x.src && x.src[0] === x.src[0].toUpperCase())""")
    for c in caps:
        assert c["out"][0].isupper(), c
    print(f"5. capitalisation preserved on {len(caps)} sentence-initial swaps")

    # 6. The panel headings are written twice by hand, because there the two
    #    registers say genuinely different things rather than swapping a word.
    heads = {}
    for level in ["simple", "advanced"]:
        set_level(level)
        pg.evaluate("() => activateTab('salary')")
        pg.wait_for_timeout(900)
        heads[level] = pg.evaluate("() => document.querySelector('#tab-salary .panel-head p').textContent")
    assert heads["simple"] != heads["advanced"], heads
    assert "annual allowance" in heads["advanced"].lower(), heads["advanced"]
    assert "government adds" in heads["simple"], heads["simple"]
    print(f"6. Pensions heading, Simple:   {heads['simple'][:74]}...")
    print(f"   Pensions heading, Advanced: {heads['advanced'][:74]}...")

    # 7. And the popovers follow the same control, on the same page state.
    set_level("simple")
    pg.evaluate("() => activateTab('planner')")
    pg.wait_for_timeout(1000)
    twoWays = pg.evaluate("""() => {
      const out = {};
      ['pcls', 'drawdown', 'annualAllowance'].forEach(k => out[k] = definitionText(k));
      return out; }""")
    set_level("advanced")
    other = pg.evaluate("""() => {
      const out = {};
      ['pcls', 'drawdown', 'annualAllowance'].forEach(k => out[k] = definitionText(k));
      return out; }""")
    for k in twoWays:
        assert twoWays[k] != other[k], k
    print("7. the explanations switch with the same control, not a separate one")

    if errors:
        raise SystemExit("CONSOLE/PAGE ERRORS:\n" + "\n".join(errors[:10]))
    print("\nALL REGISTER TESTS PASSED, no console/page errors")
    b.close()
