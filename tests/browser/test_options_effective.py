"""Every option must actually do something.

The recurring bug in this app is a control that looks live and is not. "Take it
at the earliest access age and feed it into Stocks & Shares ISAs" was read only
inside `if (o.takePcls ...)`, so on its own it changed nothing, silently, for
months. "Move pension to ISA over time" fed a comparison table and the ISA
tracker but never the projection, so ticking it moved no chart. Both looked
exactly like a working control.

So this walks every option in the app and proves it changes something
observable, in one of three ways:

  MODEL    toggling it changes the projection - the year-by-year household
           income and the balances behind it. Fingerprinted by running
           computeAll() and hashing householdFunding()'s output, which is the
           model rather than a picture of it.

  DISPLAY  toggling it changes what is drawn but not what is computed: an
           overlay, a units transform, an extra series. Fingerprinted from the
           chart pixels, because that is the only place the change exists.

  REPORT   toggling it changes a panel, table or tracker and nothing else, on
           purpose. The emergency fund is the clearest case - the code says it
           "is deliberately not subtracted from the plan", because telling
           someone they are short is useful and quietly removing the money from
           their retirement is not. Fingerprinted from the rendered text.

A control in none of the three fails the run. That is deliberate: adding an
option forces a decision about which kind it is and a test that it works,
rather than the question being noticed a release later.

Some model controls only bite when there is an amount for them to act on - a
bonus of zero moves nothing however it is toggled - so setup() gives the
household real figures first. A control that needs a parent switched on is
listed in NEEDS_PARENT and exercised with it on.
"""
import hashlib
import os
import pathlib

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

# Controls that must move the projection itself.
MODEL = [
    "levelOn",             # flexible draws instead of fixed %-drawdown rows
    "toMaxAge",            # horizon: life expectancy vs maximum modelled age
    "targetInflationOn",   # whether the target rises each year
    "stratIsaOn",          # pension -> tax-free wrapper transfers
    "stratRecycleOn",      # keep paying in after retiring (you)
    "stratSpouseContribOn",# ...and for a spouse
    "yourTakePcls",        # 25% tax-free lump sum
    "spouseTakePcls",
    "budgetOn",            # build the target from the budget instead of a band
    "spendPhasesOn",       # go-go / slow-go / no-go spending profile
    "careStayOn",          # care costed for a length of stay, not every year
    "bonusOn",             # bonus accrual into the pot
    "rsuOn",               # RSU vesting into savings
    "sayeOn",              # SAYE scheme proceeds
    "extraSaveOn",         # extra regular saving
    "yourIndexGrowth",     # pot growth follows the global index average
    "spouseIndexGrowth",
]

# Controls that drive a panel, table or tracker and deliberately nothing else.
REPORT = [
    "stratSaveOn",         # comparison-table row only
    "stratPclsOn",         # comparison-table row only
    "emergencyOn",         # a target reported against your cash, never deducted
]

# Controls that change the drawing only. Real, visible, and not model changes.
DISPLAY = [
    # householdFunding always draws on savings; smoothOn selects whether the
    # CHART reads that funded line or the raw income stack. So it changes the
    # picture and the shortfall count, not the projection - which is exactly
    # why taking a tax-free lump sum can look harmful with it off.
    "smoothOn",
    "showSurvival",        # survival overlay on its own axis
    "flatMoney",           # strip inflation-style growth from the numbers
    "balanceProperty",     # add the house to the balance chart total
]

# Depends on another control, so it is exercised with its parent switched on.
NEEDS_PARENT = {"pclsEarlyIsa": "yourTakePcls", "survivalWho": "showSurvival"}

SELECTS = {"survivalWho": ["either", "you", "spouse"]}

# Controls whose effect only shows from a particular starting state. Ticking
# "use the global index average" snaps the growth box to that average; the box
# already holds it by default, so the toggle has to start from a different rate
# or it is a no-op by design rather than a fault.
PRESET = {
    "yourIndexGrowth": ("yourPotGrowth", "3", False),
    "spouseIndexGrowth": ("spousePotGrowth", "3", False),
}

MODEL_FINGERPRINT = """() => {
  const m = computeAll();
  const f = householdFunding(m);
  const rows = f.years.map(y => {
    const r = f.byYear[y];
    const b = r.balances || {};
    return [y, Math.round(r.total), Math.round(r.target),
            Math.round(Object.values(b).reduce((s, v) => s + (typeof v === 'number' ? v : 0), 0))].join(':');
  });
  return rows.join('|');
}"""

PIXEL_FINGERPRINT = """() => {
  const out = [];
  for (const id of ['plannerChart', 'breakdownChart', 'balanceChart']) {
    const c = document.getElementById(id);
    if (!c || !c.width) { out.push(id + ':none'); continue; }
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let h = 0;
    for (let i = 0; i < d.length; i += 211) h = (h * 31 + d[i]) >>> 0;
    out.push(id + ':' + h);
  }
  return out.join('|');
}"""


REPORT_FINGERPRINT = """() => {
  const ids = ['strategyCompare', 'strategyIhtNote', 'emergencyTarget', 'emergencyCover',
               'emergencyNote', 'moveOutTradeoff', 'isaTracker'];
  return ids.map(id => { const e = document.getElementById(id);
    return id + ':' + (e ? e.textContent.replace(/\s+/g, ' ').trim() : 'none'); }).join('|');
}"""


def digest(s):
    return hashlib.sha1(s.encode()).hexdigest()[:12]


def settle(pg):
    pg.wait_for_timeout(450)


def main():
    errors = []
    failures = []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        pg = b.new_context(viewport={"width": 1500, "height": 1000}).new_page()
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(FILE)
        pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
        # Advanced view so every control exists, and a household with a spouse
        # and a real pot so the strategies have something to act on.
        pg.evaluate("""() => {
          localStorage.setItem('pensionPlanner.rememberChoice', 'advanced');
          experienceLevel = 'advanced'; applyLevel();
          activateTab('planner'); renderAll();
        }""")
        settle(pg)

        # Setup: a control with nothing to act on cannot be told apart from a
        # control that is not wired up, so give each of them a real figure and
        # put the spouse's pension in pot mode - a 25% lump sum out of a fixed
        # income is meaningless.
        pg.evaluate("""() => {
          const set = (id, v) => { const e = document.getElementById(id); if (e) e.value = v; };
          set('bonusAmount', '20,000'); set('rsuAmount', '15,000'); set('sayeMonthly', '250');
          set('extraSave', '5,000'); set('spousePot', '400,000'); set('spouseContribMonthly', '500');
          set('emergencyMonths', '6'); set('stratSaveAmt', '10,000'); set('stratIsaAmt', '20,000');
          spouseMode = 'pot';
          document.querySelectorAll('#spouseModeSeg button').forEach(
            b => b.classList.toggle('active', b.dataset.mode === 'pot'));
          document.getElementById('spousePotFields').style.display = '';
          document.getElementById('spouseIncomeFields').style.display = 'none';
          renderAll();
        }""")
        settle(pg)

        # Everything the user can toggle in the planner and strategy areas.
        found = pg.evaluate("""() => {
          const ids = new Set();
          document.querySelectorAll('.planner-options-fixed input, #tab-planner input, #tab-salary input, #tab-savings input')
            .forEach(e => { if ((e.type === 'checkbox') && e.id) ids.add(e.id); });
          return [...ids];
        }""")

        classified = set(MODEL) | set(DISPLAY) | set(REPORT) | set(NEEDS_PARENT)
        unclassified = sorted(i for i in found if i not in classified)
        if unclassified:
            failures.append(
                "Unclassified option controls - add each to MODEL, DISPLAY or REPORT in "
                "this test, with a test that it works: " + ", ".join(unclassified))

        def toggle_and_compare(cid, fingerprint, kind):
            el = pg.query_selector("#" + cid)
            if el is None:
                failures.append(f"{cid}: control not found")
                return
            pre = PRESET.get(cid)
            if pre:
                field, value, want = pre
                pg.evaluate(f"""() => {{
                  const cb = document.getElementById('{cid}');
                  if (cb.checked !== {str(want).lower()}) {{ cb.checked = {str(want).lower()};
                    cb.dispatchEvent(new Event('change', {{bubbles:true}})); }}
                  const f = document.getElementById('{field}');
                  f.readOnly = false; f.value = '{value}';
                  f.dispatchEvent(new Event('change', {{bubbles:true}}));
                }}""")
                settle(pg)
            parent = NEEDS_PARENT.get(cid)
            if parent:
                pg.evaluate(f"""() => {{ const p = document.getElementById('{parent}');
                    if (!p.checked) {{ p.checked = true; p.dispatchEvent(new Event('change', {{bubbles:true}})); }} }}""")
                settle(pg)
            before = pg.evaluate(fingerprint)
            if cid in SELECTS:
                # step through every option, not just the first alternative
                seen = {}
                for val in SELECTS[cid]:
                    pg.select_option("#" + cid, val)
                    settle(pg)
                    seen[val] = digest(pg.evaluate(fingerprint))
                if len(set(seen.values())) < len(seen):
                    failures.append(f"{cid} ({kind}): options do not all differ -> {seen}")
                else:
                    print(f"  ok  {cid:22s} {kind:7s} {len(seen)} distinct states")
                return
            pg.evaluate(f"""() => {{ const e = document.getElementById('{cid}');
                e.checked = !e.checked; e.dispatchEvent(new Event('change', {{bubbles:true}})); }}""")
            settle(pg)
            after = pg.evaluate(fingerprint)
            # put it back so each control is judged from the same baseline
            pg.evaluate(f"""() => {{ const e = document.getElementById('{cid}');
                e.checked = !e.checked; e.dispatchEvent(new Event('change', {{bubbles:true}})); }}""")
            settle(pg)
            if digest(before) == digest(after):
                failures.append(
                    f"{cid} ({kind}): toggling it changed nothing. Either it is not wired "
                    f"to anything, or it belongs in the other list.")
            else:
                print(f"  ok  {cid:22s} {kind:7s} {digest(before)} -> {digest(after)}")

        print("MODEL controls - must change the projection")
        for cid in MODEL:
            toggle_and_compare(cid, MODEL_FINGERPRINT, "model")

        print("\nDISPLAY controls - must change what is drawn")
        for cid in DISPLAY:
            toggle_and_compare(cid, PIXEL_FINGERPRINT, "display")

        print("\nREPORT controls - must change a panel, and deliberately not the plan")
        for cid in REPORT:
            toggle_and_compare(cid, REPORT_FINGERPRINT, "report")

        print("\nDependent controls - exercised with their parent on")
        for cid in NEEDS_PARENT:
            fp = PIXEL_FINGERPRINT if cid in ("survivalWho",) else MODEL_FINGERPRINT
            toggle_and_compare(cid, fp, "dependent")

        b.close()

    if errors:
        failures.append("console/page errors: " + "; ".join(sorted(set(errors))[:5]))
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("\nALL OPTIONS EFFECTIVE, no console/page errors")


if __name__ == "__main__":
    main()
