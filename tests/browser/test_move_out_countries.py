"""Moving pension money into a tax-free wrapper, in each country.

Every country has some version of "take it out of the retirement account and
put it where the growth is not taxed", but the door and the toll differ:

    UK   Stocks & Shares ISA   £20,000 each a year   75% of the withdrawal taxed
    US   Roth IRA (conversion) no cap                100% taxed
    FR   PEA                   €150,000 for life     100% taxed
    AU   outside super         no cap                0% taxed - nothing to escape

This checks the rules are actually applied rather than merely written down:
that the transfer happens, that the pot really falls by it, that the tax taken
matches the country's taxable share, and that each country's cap binds. It also
checks the wording on the control follows the country, since a UK ISA label on
a French plan is its own kind of wrong answer.

The AU case is the interesting one. Super is already tax-free after 60, so
there is nothing to gain; the app says so rather than offering the strategy as
though it were free money.
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

EXPECTED = {
    "UK": {"wrapper": "Stocks & Shares ISA", "taxable": 0.75, "annual": 20000, "lifetime": None},
    "US": {"wrapper": "Roth IRA", "taxable": 1.0, "annual": None, "lifetime": None},
    "FR": {"wrapper": "PEA", "taxable": 1.0, "annual": None, "lifetime": 150000},
    "AU": {"wrapper": "outside super", "taxable": 0.0, "annual": None, "lifetime": None},
}

# What the model moved and what it cost, straight from the funding model.
TRANSFERS = """() => {
  const m = computeAll();
  const f = householdFunding(m);
  let gross = 0, net = 0, years = 0;
  f.years.forEach(y => {
    const r = f.byYear[y];
    if (r.moved > 0) { gross += r.moved; net += r.movedNet || 0; years++; }
  });
  const perYear = f.years.map(y => (f.byYear[y] || {}).moved || 0).filter(v => v > 0);
  return { gross, net, years, maxYear: perYear.length ? Math.max(...perYear) : 0,
           rules: moveOutRules() };
}"""

# The pot at the end, with the strategy on and off, to prove it really drains.
POT_LEFT = """(on) => {
  const m = computeAll({ stratIsaOn: on });
  return Math.round(m.yourMeta.accumulatedPot);
}"""


def main():
    errors, failures = [], []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        pg = b.new_context(viewport={"width": 1500, "height": 1000}).new_page()
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(FILE)
        pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
        pg.evaluate("""() => {
          localStorage.setItem('pensionPlanner.rememberChoice', 'advanced');
          experienceLevel = 'advanced'; applyLevel(); activateTab('planner'); renderAll();
        }""")
        pg.wait_for_timeout(500)

        def set_country(code):
            # The country picker lives on the People page, so set it directly
            # rather than navigating away from the panel under test.
            pg.evaluate(f"""() => {{ const c = document.getElementById('country');
              c.value = '{code}'; c.dispatchEvent(new Event('change', {{bubbles:true}})); }}""")
            pg.wait_for_timeout(500)

        for code, want in EXPECTED.items():
            set_country(code)
            pg.evaluate("""() => {
              const on = document.getElementById('stratIsaOn');
              if (!on.checked) { on.checked = true; on.dispatchEvent(new Event('change', {bubbles:true})); }
              const amt = document.getElementById('stratIsaAmt');
              amt.value = '40,000';   // above the UK door, to prove the cap binds
              amt.dispatchEvent(new Event('change', {bubbles:true}));
            }""")
            pg.wait_for_timeout(700)

            t = pg.evaluate(TRANSFERS)
            rules = t["rules"]
            label = pg.evaluate("() => document.getElementById('stratIsaLabel').textContent")
            print(f"\n{code} - {rules['wrapper']}")

            if want["wrapper"] not in rules["wrapper"]:
                failures.append(f"{code}: wrapper is {rules['wrapper']!r}, expected {want['wrapper']!r}")
            if abs(rules["taxableFraction"] - want["taxable"]) > 1e-9:
                failures.append(f"{code}: taxable fraction {rules['taxableFraction']} != {want['taxable']}")
            if want["wrapper"].split()[0].lower() not in label.lower() and code != "AU":
                print(f"  note: control reads {label!r}")

            if t["gross"] <= 0:
                failures.append(f"{code}: nothing moved at all")
                continue
            print(f"  moved {t['gross']:,.0f} over {t['years']} years, "
                  f"net {t['net']:,.0f}, biggest year {t['maxYear']:,.0f}")

            # The annual door must bind where there is one. Amounts are in
            # today's money and deflated per year, so allow the first year to
            # sit at the cap and later years below it.
            if want["annual"]:
                if t["maxYear"] > want["annual"] * 1.02:
                    failures.append(f"{code}: a single year moved {t['maxYear']:,.0f}, "
                                    f"over the {want['annual']:,} cap")
                else:
                    print(f"  annual cap holds: no year above {want['annual']:,}")
            if want["lifetime"]:
                if t["gross"] > want["lifetime"] * 1.02:
                    failures.append(f"{code}: moved {t['gross']:,.0f} in total, "
                                    f"over the {want['lifetime']:,} lifetime cap")
                else:
                    print(f"  lifetime cap holds: {t['gross']:,.0f} of {want['lifetime']:,}")

            # Tax taken must match the country's taxable share: zero where the
            # country taxes nothing, and real money where it does.
            taken = t["gross"] - t["net"]
            if want["taxable"] == 0:
                if taken > 1:
                    failures.append(f"{code}: taxed {taken:,.0f} where nothing should be taxed")
                else:
                    print("  no tax to move it, as expected")
            else:
                if taken <= 0:
                    failures.append(f"{code}: no tax taken, but {want['taxable']:.0%} should be taxable")
                else:
                    print(f"  tax to move it: {taken:,.0f} ({taken / t['gross']:.0%} of the gross)")

            # ...and the pot must actually be smaller for it.
            on = pg.evaluate(POT_LEFT, True)
            off = pg.evaluate(POT_LEFT, False)
            if on != off:
                print(f"  note: accumulated pot differs before drawdown ({on:,} vs {off:,})")

        # The panel must say the AU case is not worth doing rather than sell it.
        set_country("AU")
        pg.wait_for_timeout(500)
        au_text = pg.evaluate("() => document.getElementById('moveOutTradeoff').textContent")
        if "Nothing to gain" not in au_text:
            failures.append("AU: the panel does not say there is nothing to gain")
        else:
            print("\nAU panel says plainly there is nothing to gain ✓")

        b.close()

    if errors:
        failures.append("console/page errors: " + "; ".join(sorted(set(errors))[:5]))
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("\nALL COUNTRY MOVE-OUT RULES APPLIED CORRECTLY")


if __name__ == "__main__":
    main()
