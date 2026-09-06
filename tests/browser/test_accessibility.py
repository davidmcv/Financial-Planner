"""WCAG 2.2 AA, on every page, in every mode, at every size.

The app is used in the UK, the US, France and Australia, and each of those
places has a law that points at the same technical standard:

    UK          Equality Act 2010; the public sector accessibility regulations
                cite WCAG 2.2 AA
    US          the ADA (DOJ's 2024 Title II rule adopts WCAG 2.1 AA) and
                Section 508, which incorporates WCAG 2.0 AA
    EU          the European Accessibility Act, in force since June 2025, via
                EN 301 549, which incorporates WCAG 2.1 AA - this is what
                France, Italy and Spain enforce
    Australia   the Disability Discrimination Act 1992; the Digital Service
                Standard requires WCAG 2.1 AA
    Canada      the Accessible Canada Act, and Ontario's AODA, WCAG 2.0 AA

They differ in who they bind and how they are enforced, but not in what they
ask for. Testing against the strictest of them - WCAG 2.2 AA - covers the lot,
so that is what this does, using axe-core.

What this test is NOT: a certificate. Automated checks catch somewhere around
a third of WCAG failures. They cannot judge whether alt text is meaningful,
whether a heading describes what follows, or whether the tab order makes
sense to a person. Passing means the machine-checkable failures are absent,
which is the floor, not the ceiling. Anything that matters legally needs a
human audit, ideally with assistive-technology users.

axe-core is vendored in tests/browser/vendor rather than fetched, so the suite
runs offline and always against a known version.

The coverage matrix matters as much as the rules: contrast failures hide in
the theme nobody tested, and keyboard traps hide in the panel nobody opened.
Every tab, both themes, both detail levels, phone and desktop, the modals, and
the largest text setting.
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
FILE = (ROOT / "pension-planner.html").as_uri()
AXE = pathlib.Path(__file__).resolve().parent / "vendor" / "axe.min.js"
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

TABS = ["people", "savings", "salary", "projection", "planner", "tax", "gifting", "relocate"]

# WCAG 2.2 AA and everything it builds on.
RUN = """async () => await axe.run(document, {
  runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] },
  resultTypes: ['violations'] })"""


def main():
    if not AXE.exists():
        print(f"axe-core is missing: {AXE}")
        raise SystemExit(1)
    axe_src = AXE.read_text()
    findings, errors = {}, []
    checked = 0

    def record(res, where):
        for v in res["violations"]:
            e = findings.setdefault(v["id"], {"impact": v["impact"], "help": v["help"],
                                              "where": set(), "nodes": []})
            e["where"].add(where)
            for n in v["nodes"][:2]:
                line = n["target"][0][:100] + "  ||  " + n["failureSummary"].replace("\n", " ")[:170]
                if line not in e["nodes"] and len(e["nodes"]) < 6:
                    e["nodes"].append(line)

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)

        def audit_context(viewport, touch, label, theme, level, tabs, text_scale=1):
            nonlocal checked
            ctx = b.new_context(viewport=viewport, has_touch=touch)
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            pg.goto(FILE)
            pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
            pg.evaluate("""(a) => {
              localStorage.setItem('pensionPlanner.rememberChoice', a.level);
              experienceLevel = a.level; applyLevel();
              appTheme = a.theme; applyAppTheme();
              if (a.scale !== 1) { TEXT_SCALE = a.scale; applyTextScale(); }
              activateTab(a.level === 'simple' ? 'simple' : 'people'); renderAll();
            }""", {"level": level, "theme": theme, "scale": text_scale})
            pg.wait_for_timeout(800)
            pg.add_script_tag(content=axe_src)
            for t in tabs:
                pg.evaluate("(t) => activateTab(t)", t)
                pg.wait_for_timeout(500)
                record(pg.evaluate(RUN), f"{label}/{theme}/{level}/{t}")
                checked += 1
            # Dialogs are where focus handling and contrast go wrong unnoticed.
            for mid, opener in (("settingsModal", None), ("saveFileModal", "profileExportBtn")):
                if opener:
                    pg.evaluate("(o) => document.getElementById(o).click()", opener)
                else:
                    pg.evaluate("(m) => document.getElementById(m).classList.add('open')", mid)
                pg.wait_for_timeout(600)
                record(pg.evaluate(RUN), f"{label}/{theme}/{level}/{mid}")
                checked += 1
                pg.evaluate("(m) => document.getElementById(m).classList.remove('open')", mid)
            ctx.close()

        for viewport, touch, label in (({"width": 1400, "height": 1000}, False, "desktop"),
                                       ({"width": 393, "height": 852}, True, "phone")):
            for theme in ("night", "day"):
                for level in ("advanced", "simple"):
                    audit_context(viewport, touch, label, theme, level,
                                  TABS if level == "advanced" else ["simple"])

        # Largest text setting: reflow and contrast both change under it.
        for theme in ("night", "day"):
            audit_context({"width": 1400, "height": 1000}, False, "text-1.5x", theme,
                          "advanced", ["planner", "tax"], text_scale=1.5)

        # ---- what axe cannot check ------------------------------------------
        # Keyboard operation is judged by trying it, not by inspecting markup.
        # These are WCAG 2.1.1 (Keyboard), 2.1.2 (No Keyboard Trap) and
        # 2.4.7 (Focus Visible) - all Level A or AA, all invisible to a static
        # scan, and all things a keyboard-only user hits within seconds.
        ctx = b.new_context(viewport={"width": 1400, "height": 1000})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.goto(FILE)
        pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
        pg.evaluate("""() => { localStorage.setItem('pensionPlanner.rememberChoice','advanced');
          experienceLevel = 'advanced'; applyLevel(); activateTab('planner'); renderAll(); }""")
        pg.wait_for_timeout(800)

        # 1. Tab reaches a real spread of controls and never gets stuck.
        pg.evaluate("() => document.body.focus()")
        seen, repeats = [], 0
        for _ in range(90):
            pg.keyboard.press("Tab")
            el = pg.evaluate("""() => { const a = document.activeElement;
              if (!a || a === document.body) return null;
              return a.tagName.toLowerCase() + (a.id ? '#' + a.id : '') +
                     (a.className && typeof a.className === 'string' ? '.' + a.className.split(' ')[0] : ''); }""")
            if el is None:
                repeats += 1
                if repeats > 3:
                    break
                continue
            repeats = 0
            seen.append(el)
        unique = len(set(seen))
        if unique < 15:
            findings["keyboard-reach"] = {
                "impact": "critical", "help": "Tab must reach the page's controls",
                "where": {"planner"},
                "nodes": [f"only {unique} distinct controls reached in 90 presses: {sorted(set(seen))[:8]}"]}
        else:
            print(f"keyboard: Tab reached {unique} distinct controls without sticking")

        # 2. Focus has to be visible when it lands.
        invisible = pg.evaluate("""() => {
          const out = [];
          const cand = [...document.querySelectorAll('button, a[href], select, input, [tabindex="0"]')]
            .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
            .slice(0, 40);
          for (const e of cand) {
            e.focus();
            const s = getComputedStyle(e);
            const ring = (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0)
              || s.boxShadow !== 'none'
              || parseFloat(s.borderWidth) > 0;
            if (!ring) out.push(e.tagName.toLowerCase() + (e.id ? '#' + e.id : ''));
          }
          return out; }""")
        if invisible:
            findings["focus-visible"] = {
                "impact": "serious", "help": "Focus must be visible (WCAG 2.4.7)",
                "where": {"planner"}, "nodes": [", ".join(invisible[:8])]}
        else:
            print("focus: every sampled control shows a visible focus indicator")

        # 3. A dialog must be escapable from the keyboard, or it is a trap.
        for mid, opener in (("settingsModal", "openSettings"), ("saveFileModal", "profileExportBtn"),
                            ("planModal", "openPlansMobile")):
            pg.evaluate("(o) => { const b = document.getElementById(o); if (b) b.click(); }", opener)
            pg.wait_for_timeout(400)
            if not pg.evaluate("(m) => document.getElementById(m).classList.contains('open')", mid):
                continue
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(300)
            still = pg.evaluate("(m) => document.getElementById(m).classList.contains('open')", mid)
            if still:
                findings.setdefault("keyboard-trap", {
                    "impact": "critical", "help": "Escape must close a dialog (WCAG 2.1.2)",
                    "where": set(), "nodes": []})
                findings["keyboard-trap"]["where"].add(mid)
                findings["keyboard-trap"]["nodes"].append(f"{mid} stayed open after Escape")
                pg.evaluate("(m) => document.getElementById(m).classList.remove('open')", mid)
        if "keyboard-trap" not in findings:
            print("dialogs: Escape closes every dialog")
        ctx.close()

        b.close()

    print(f"axe-core WCAG 2.2 AA, {checked} page states audited")
    if errors:
        print("\npage errors during the audit:")
        for e in sorted(set(errors))[:5]:
            print("  -", e)
    if findings:
        order = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3}
        print(f"\n{len(findings)} violation type(s):\n")
        for k, v in sorted(findings.items(), key=lambda kv: order.get(kv[1]["impact"], 9)):
            print(f"[{v['impact']}] {k}: {v['help']}")
            print(f"    in {len(v['where'])} state(s), e.g. {sorted(v['where'])[:3]}")
            for n in v["nodes"][:4]:
                print(f"      - {n}")
            print()
        raise SystemExit(1)
    if errors:
        raise SystemExit(1)
    print("NO WCAG 2.2 AA VIOLATIONS in any state")
    print("Automated checks find roughly a third of WCAG failures. This is the floor,")
    print("not a certificate: judgement calls still need a human audit.")


if __name__ == "__main__":
    main()
