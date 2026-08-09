"""Explain-on-hover, and the boxes lining up in columns.

Two claims are tested here:

  1. Jargon anywhere on the page explains itself on hover and on keyboard
     focus, in Plain English on Simple and in financial language on Advanced,
     and the switch reaches an explanation that is already open.
  2. The input boxes on a page sit in real columns. Under the old flex rows
     each field took its own basis width, so "Value today" started at a
     different x on every asset row. A grid gives every row the same columns.
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
errors = []

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME)
    pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    pg.goto(FILE)
    pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
    pg.wait_for_timeout(900)

    # 1. The page tagged its own jargon, across more than one concept and more
    #    than one page.
    tags = pg.evaluate("""() => { const t = [...document.querySelectorAll('.def-term')];
      return { n: t.length, keys: [...new Set(t.map(x => x.dataset.def))].length,
               focusable: t.every(x => x.tabIndex === 0),
               words: t.slice(0, 6).map(x => x.textContent) }; }""")
    assert tags["n"] > 20 and tags["keys"] > 8, tags
    assert tags["focusable"], "a term was not reachable by keyboard"
    print(f"1. {tags['n']} terms tagged covering {tags['keys']} concepts, e.g. {tags['words']}")

    # 2. No term is tagged twice inside the same card - one dotted underline per
    #    concept per card, not a rash of them.
    dupes = pg.evaluate("""() => { const bad = [];
      document.querySelectorAll('.card').forEach(c => { const seen = {};
        c.querySelectorAll('.def-term').forEach(t => {
          if (t.closest('.card') !== c) return;
          seen[t.dataset.def] = (seen[t.dataset.def] || 0) + 1; });
        Object.entries(seen).forEach(([k, n]) => { if (n > 1) bad.push([c.id || c.className, k, n]); }); });
      return bad; }""")
    assert not dupes, dupes
    print("2. one underline per concept per card - no repeats")

    # 3. Hovering shows an explanation positioned near the word and inside the
    #    viewport.
    pg.evaluate("() => activateTab('planner')")
    pg.wait_for_timeout(900)
    pg.evaluate("""() => { const t = [...document.querySelectorAll('.def-term')]
      .find(x => x.offsetParent && x.getBoundingClientRect().width > 4);
      t.id = 'firstVisibleTerm'; t.scrollIntoView({ block: 'center' }); }""")
    pg.wait_for_timeout(250)
    pg.hover("#firstVisibleTerm")
    pg.wait_for_selector("#defPop.show", timeout=3000)
    box = pg.evaluate("""() => { const p = document.getElementById('defPop');
      const r = p.getBoundingClientRect();
      return { text: p.querySelector('p').textContent, head: p.querySelector('h4').textContent,
               inside: r.left >= 0 && r.top >= 0 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1,
               described: !!document.querySelector('.def-term[aria-describedby=defPop]') }; }""")
    assert box["inside"], "the explanation opened off-screen"
    assert len(box["text"]) > 40 and box["described"], box
    print(f"3. hover explains '{box['head']}': {box['text'][:70]}...")

    # 4. Moving away closes it.
    pg.mouse.move(5, 5)
    pg.wait_for_timeout(400)
    assert not pg.evaluate("() => document.getElementById('defPop').classList.contains('show')")
    print("4. moving off the word closes it")

    # 5. Simple gives plain English; Advanced gives the financial register. The
    #    same concept, two different texts, and the Advanced one is the one
    #    carrying the technical vocabulary.
    texts = {}
    for level in ["simple", "advanced"]:
        pg.evaluate("(l) => { experienceLevel = l; applyLevel(); renderAll(); }", level)
        pg.wait_for_timeout(700)
        texts[level] = pg.evaluate("""() => { const out = {};
          ['spa', 'pcls', 'annualAllowance', 'drawdown'].forEach(k => out[k] = definitionText(k));
          return out; }""")
    for k in texts["simple"]:
        assert texts["simple"][k] != texts["advanced"][k], k
        assert len(texts["advanced"][k]) > 40 and len(texts["simple"][k]) > 30, k
    jargon = ["crystallis", "uncrystallis", "statutory", "Act", "taper", "marginal", "HMRC",
              "allowance", "band", "relief", "annual", "Pension Commencement"]
    hits = {lvl: sum(any(j.lower() in t.lower() for j in jargon) for t in texts[lvl].values())
            for lvl in texts}
    assert hits["advanced"] >= hits["simple"], hits
    print(f"5. two registers: Simple '{texts['simple']['pcls'][:58]}...'")
    print(f"            Advanced '{texts['advanced']['pcls'][:58]}...'")

    # 6. Changing the register while an explanation is open rewrites it in
    #    place rather than leaving the wrong wording on screen.
    pg.evaluate("() => { experienceLevel = 'simple'; applyLevel(); renderAll(); }")
    pg.wait_for_timeout(700)
    pg.evaluate("""() => { const vis = [...document.querySelectorAll('.def-term')]
        .filter(x => x.offsetParent && x.getBoundingClientRect().width > 4);
      const t = vis.find(x => x.dataset.def === 'spa') || vis[0];
      t.scrollIntoView({ block: 'center' }); t.focus(); }""")
    pg.wait_for_selector("#defPop.show", timeout=3000)
    plain = pg.evaluate("() => document.querySelector('#defPop p').textContent")
    pg.evaluate("() => { experienceLevel = 'advanced'; applyLevel(); refreshDefPop(); }")
    pg.wait_for_timeout(300)
    expert = pg.evaluate("() => document.querySelector('#defPop p').textContent")
    assert plain != expert, (plain, expert)
    print("6. switching to Advanced rewrote the open explanation in place")

    # 7. Keyboard focus alone opens it - no mouse required - and Escape closes.
    assert pg.evaluate("() => document.getElementById('defPop').classList.contains('show')")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(250)
    assert not pg.evaluate("() => document.getElementById('defPop').classList.contains('show')")
    print("7. focus opens it, Escape closes it")

    # 8. Clicking a term that sits inside a label still works the label, rather
    #    than stealing the click to open a definition.
    pg.evaluate("() => { experienceLevel = 'advanced'; applyLevel(); activateTab('people'); renderAll(); }")
    pg.wait_for_timeout(900)
    toggled = pg.evaluate("""() => { const t = [...document.querySelectorAll('label .def-term')]
        .find(x => x.closest('label').querySelector('input[type=checkbox]'));
      if (!t) return 'none';
      const cb = t.closest('label').querySelector('input[type=checkbox]');
      const was = cb.checked; t.click(); const now = cb.checked;
      if (now !== was) cb.click();          // put it back
      return was !== now; }""")
    assert toggled is True or toggled == "none", toggled
    print(f"8. clicking a term inside a tick-box label still ticks the box ({toggled})")

    # 9. THE GRID CLAIM: within one asset list, the same column starts at the
    #    same x on every row. That is what "look inline correctly" means.
    # The savings and property lists live on the Savings page and the employer
    # pensions on Pensions - measuring them on a hidden panel would compare a
    # column of zeroes and prove nothing.
    # Give each list enough rows to compare against each other, including a DB
    # pension (which carries a whole-row note) next to a DC one (which does not)
    # - the mixed case is exactly where the flex version went ragged.
    pg.evaluate("""() => document.querySelectorAll('details').forEach(d => d.open = true)""")
    LISTS = {"savings": ("savings", "savingsList_you"),
             "savings2": ("property", "propertyList_you"),
             "salary": ("employerPensions", "employerPensionList_you")}
    cols, seen = [], []
    for tab, (kind, listId) in [("savings", LISTS["savings"]), ("savings", LISTS["savings2"]),
                                ("salary", LISTS["salary"])]:
        pg.evaluate("(t) => activateTab(t)", tab)
        pg.wait_for_timeout(600)
        for _ in range(2):
            pg.evaluate("(k) => document.querySelector(`.add-btn[data-add=\"${k}\"][data-owner=you]`).click()", kind)
            pg.wait_for_timeout(250)
        if kind == "employerPensions":
            pg.evaluate("""() => { const s = document.querySelector(
                '#employerPensionList_you .asset-row select[data-field=kind]');
              if (s) { s.value = 'DB'; s.dispatchEvent(new Event('change', { bubbles: true })); } }""")
            pg.wait_for_timeout(700)
        assert pg.evaluate("(id) => !!document.getElementById(id).offsetParent", listId), \
            f"{listId} is on a hidden panel - a column of zeroes proves nothing"
        got = pg.evaluate("""(id) => {
          const out = [];
          const rows = [...document.getElementById(id).querySelectorAll('.asset-row')];
          if (rows.length < 2) return out;
          const xs = rows.map(r => [...r.querySelectorAll(':scope > .field')]
            .map(f => Math.round(f.getBoundingClientRect().left)));
          const n = Math.min(...xs.map(a => a.length));
          for (let c = 0; c < n; c++) {
            const spread = Math.max(...xs.map(a => a[c])) - Math.min(...xs.map(a => a[c]));
            out.push({ list: id, col: c, spread });
          }
          return out; }""", listId)
        assert got, f"{listId} did not gain enough rows to compare"
        cols += got
        seen.append(listId)
    assert len(cols) >= 6, cols
    worst = max(c["spread"] for c in cols)
    assert worst <= 1, [c for c in cols if c["spread"] > 1]
    print(f"9. every column lines up across {len(cols)} column/row pairs in "
          f"{len(seen)} lists (worst drift {worst}px)")

    # 10. And the rows really are grids now, with whole-row notes spanning.
    grid = pg.evaluate("""() => { const r = document.querySelector('.asset-row');
      return { display: getComputedStyle(r).display,
               fieldRow: getComputedStyle(document.querySelector('.field-row')).display }; }""")
    assert grid["display"] == "grid" and grid["fieldRow"] == "grid", grid
    print("10. asset rows and field rows are both grids")

    # 11. Tagging is idempotent - three renders do not nest spans or multiply
    #     them, which is what would happen if the tagger re-tagged its own work.
    n1 = pg.evaluate("() => document.querySelectorAll('.def-term').length")
    for _ in range(3):
        pg.evaluate("() => renderAll()")
        pg.wait_for_timeout(350)
    pg.wait_for_timeout(400)
    n2 = pg.evaluate("() => document.querySelectorAll('.def-term').length")
    nested = pg.evaluate("() => document.querySelectorAll('.def-term .def-term').length")
    assert nested == 0, nested
    assert abs(n2 - n1) <= 2, (n1, n2)
    print(f"11. stable across re-renders: {n1} -> {n2} terms, 0 nested")

    if errors:
        raise SystemExit("CONSOLE/PAGE ERRORS:\n" + "\n".join(errors[:10]))
    print("\nALL DEFINITION + GRID TESTS PASSED, no console/page errors")
    b.close()
