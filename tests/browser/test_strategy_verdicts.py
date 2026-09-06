"""Strategy verdicts must be measured on money you can actually spend.

Every "is this worth doing?" panel runs the plan twice and subtracts. Three
things have to be true of that subtraction, and each of them was false at some
point in this file's history - each time producing a confident, large, wrong
number rather than an obvious crash.

  1. AFTER TAX.  Pension drawdown arrives with income tax still owing on it;
     an ISA draw, the tax-free lump sum and a downsize do not. Adding gross
     pension pounds to tax-free ISA pounds charges the ISA route for tax it
     never pays. "Move only what comes out tax-free" cost £0 in tax and was
     reported £320,264 BEHIND.

  2. COUNT WHAT IS LEFT IN THE PENSION.  Under the fixed %-drawdown rule the
     pot is never emptied - it pays a percentage of whatever remains. A plan
     that leaves money in the pension therefore ends holding a large balance
     that was never drawn, and it appeared in no total at all: not in income
     (never withdrawn), not in `balances.pot` (zero outside level mode). That
     hid £832,531 on the demo household.

  3. TIMING-NEUTRAL.  Two plans that spend the same money at different times
     cannot be compared by adding yearly figures up. Over fifty years at 8%,
     whichever plan spends least early wins on compounding alone, whatever the
     tax - so everything is discounted back to today at the growth rate the
     money would otherwise have earned.

The tax-free case is the sharp end of all three: moving money at a £0 tax cost
out of a pension whose withdrawals are 75% taxable, into a wrapper that is not
taxed at all, cannot leave the household worse off. If this test says it does,
the measure is wrong again - not the strategy.
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

# Run the plan with the strategy on and off and report both measures.
COMPARE = """(opts) => {
  const on  = planMeasure(computeAll(Object.assign({ stratIsaOn: true  }, opts)));
  const off = planMeasure(computeAll(Object.assign({ stratIsaOn: false }, opts)));
  return {
    spendDelta: on.spendable - off.spendable,
    grossDelta: on.lifetime - off.lifetime,
    taxDelta:   on.tax - off.tax,
    leftDelta:  on.left - off.left,
    totalDelta: (on.spendable - off.spendable) + (on.left - off.left),
    onResidue: on.residue, offResidue: off.residue,
    onTax: on.tax, offTax: off.tax,
  };
}"""


def main():
    errors, failures = [], []

    def check(cond, msg):
        if not cond:
            failures.append(msg)
        return cond

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        pg = b.new_context(viewport={"width": 1500, "height": 1000}).new_page()
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(FILE)
        pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
        pg.evaluate("""() => { localStorage.setItem('pensionPlanner.rememberChoice','advanced');
          experienceLevel = 'advanced'; applyLevel(); activateTab('planner'); renderAll(); }""")
        pg.wait_for_timeout(900)
        # A pot where there is real unused personal allowance to move into.
        pg.evaluate("""() => { const e = document.getElementById('yourPot');
          e.value = '250,000'; e.dispatchEvent(new Event('change', {bubbles:true})); }""")
        pg.evaluate("""() => { const on = document.getElementById('stratIsaOn');
          if (!on.checked) { on.checked = true; on.dispatchEvent(new Event('change', {bubbles:true})); } }""")
        pg.wait_for_timeout(700)

        def set_mode(m):
            pg.evaluate("""(m) => { const e = document.getElementById('moveOutMode');
              e.value = m; e.dispatchEvent(new Event('change', {bubbles:true})); }""", m)
            pg.wait_for_timeout(1000)

        # ---- 1. the measure exists and reports the parts separately ----------
        shape = pg.evaluate("() => { const m = planMeasure(computeAll()); return Object.keys(m); }")
        for key in ("spendable", "lifetime", "tax", "left", "residue", "shortfall"):
            check(key in shape, f"planMeasure has no '{key}' - the parts must stay separable")
        print(f"1. planMeasure reports: {', '.join(sorted(shape))}")

        # ---- 2. tax-free mode must not be reported as a loss -----------------
        set_mode("taxfree")
        moved = pg.evaluate("""() => { const m = computeAll(); const f = householdFunding(m);
          let g = 0, n = 0; f.years.forEach(y => { const r = f.byYear[y];
            g += r.moved || 0; n += r.movedNet || 0; }); return { gross: g, tax: g - n }; }""")
        c = pg.evaluate(COMPARE, {})
        check(moved["gross"] > 0, "tax-free mode moved nothing, so nothing is being tested")
        check(moved["tax"] < 1, f"tax-free mode charged {moved['tax']:,.0f} of tax to move")
        check(c["totalDelta"] > 0,
              f"moving money at ZERO tax cost is reported as {c['totalDelta']:,.0f} - "
              f"a free move cannot leave the household worse off; the measure is wrong")
        check(c["taxDelta"] < 0,
              f"tax-free transfers should cut lifetime tax, but tax moved by {c['taxDelta']:+,.0f}")
        print(f"2. tax-free: moved {moved['gross']:,.0f} for {moved['tax']:,.0f} tax -> "
              f"{c['totalDelta']:+,.0f} overall, lifetime tax {c['taxDelta']:+,.0f}")

        # ---- 3. after-tax and before-tax must actually differ ----------------
        # If they agree, income tax is not being taken off at all and bug #1
        # is back.
        check(abs(c["spendDelta"] - c["grossDelta"]) > 1,
              "before-tax and after-tax comparisons are identical - no tax is being deducted")
        check(c["onTax"] > 0 and c["offTax"] > 0,
              f"no income tax charged at all ({c['onTax']:,.0f} / {c['offTax']:,.0f})")
        print(f"3. after tax {c['spendDelta']:+,.0f} vs before tax {c['grossDelta']:+,.0f} "
              f"- the two differ, so tax is being taken off")

        # ---- 4. the pension residue is counted -------------------------------
        # Leaving money in the pot must show up as something left over. If the
        # "leave it alone" plan reports nothing left in the pension, bug #2 is
        # back and every comparison against it is scored on income alone.
        check(c["offResidue"] > 0,
              "the plan with the strategy off ends with nothing left in the pension - "
              "the untouched pot is not being counted")
        check(c["offResidue"] > c["onResidue"],
              f"moving money out did not reduce what is left in the pension "
              f"({c['offResidue']:,.0f} -> {c['onResidue']:,.0f})")
        print(f"4. left in the pension: {c['offResidue']:,.0f} leaving it alone, "
              f"{c['onResidue']:,.0f} after moving money out")

        # ---- 5. timing-neutral ----------------------------------------------
        # Present value at the growth rate. The test of it: the numbers stay
        # the size of a real decision instead of the size of fifty years of
        # compounding. A £250k pot cannot honestly produce a million-pound
        # verdict either way.
        for mode in ("taxfree", "basic", "fixed"):
            set_mode(mode)
            d = pg.evaluate(COMPARE, {})
            check(abs(d["totalDelta"]) < 1_000_000,
                  f"{mode}: verdict of {d['totalDelta']:+,.0f} on a £250k pot - "
                  f"figures are not discounted, so compounding dominates the answer")
            print(f"5. {mode:8s} -> {d['totalDelta']:+,.0f} (tax {d['taxDelta']:+,.0f})")

        # ---- 6. like-for-like spending: level mode ---------------------------
        # With spending held level, both plans buy the same life and the only
        # thing left to differ is tax - so a tax-free move must come out ahead.
        pg.evaluate("""() => { const e = document.getElementById('levelOn');
          if (!e.checked) { e.checked = true; e.dispatchEvent(new Event('change', {bubbles:true})); } }""")
        set_mode("taxfree")
        lvl = pg.evaluate(COMPARE, {"levelOn": True})
        check(lvl["totalDelta"] > 0,
              f"with spending held level a free transfer still reports {lvl['totalDelta']:+,.0f}")
        print(f"6. level income, tax-free move: {lvl['totalDelta']:+,.0f}")
        pg.evaluate("""() => { const e = document.getElementById('levelOn');
          if (e.checked) { e.checked = false; e.dispatchEvent(new Event('change', {bubbles:true})); } }""")
        pg.wait_for_timeout(600)

        # ---- 7. the panel says what it measured ------------------------------
        set_mode("taxfree")
        text = pg.evaluate("() => document.getElementById('moveOutTradeoff').innerText")
        for phrase in ("after income tax", "today's money"):
            check(phrase in text, f"the panel does not say it measures {phrase!r}")
        print("7. the panel states its basis: after income tax, in today's money")

        b.close()

    if errors:
        failures.append("console/page errors: " + "; ".join(sorted(set(errors))[:5]))
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("\nSTRATEGY VERDICTS MEASURED ON SPENDABLE MONEY")


if __name__ == "__main__":
    main()
