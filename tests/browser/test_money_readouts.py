"""The money figures on the Pensions page and the take-home line on the charts.

Three faults this pins down, all reported as "the number looks wrong":

  1. Take-home on the year-by-year breakdown. It counted every pound paid into
     a pension as tax, and - with smoothing on - read the whole pension
     drawdown as tax-FREE, because the funding stack calls it `pension` while
     the income stack calls it `private`. Both are checked here against an
     independent tax calculation written out longhand below.
  2. Rate (%) under pension contributions did nothing. Only `change` was
     listened for, and `change` waits for the box to lose focus, so typing a
     rate changed no figure on the page until you clicked somewhere else.
  3. The per-month figures, which have to be exactly a twelfth of the yearly
     ones in both entry modes.

The tax arithmetic here is written independently of the app rather than read
back out of it - a test that asks the app what the answer is cannot catch the
app being wrong.
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
errors = []

PA, BASIC_TO, HIGHER_TO = 12570.0, 50270.0, 125140.0
TAPER_FROM = 100000.0


def income_tax(gross):
    """UK 2025/26, England/Wales/NI bands, with the personal-allowance taper."""
    pa = max(0.0, PA - max(0.0, gross - TAPER_FROM) / 2)
    tax, lower = 0.0, pa
    for top, rate in ((BASIC_TO, 0.20), (HIGHER_TO, 0.40), (float("inf"), 0.45)):
        if gross <= lower:
            break
        tax += (min(gross, top) - lower) * rate
        lower = top
    return tax


def national_insurance(gross):
    ni = 0.0
    if gross > PA:
        ni += (min(gross, BASIC_TO) - PA) * 0.08
    if gross > BASIC_TO:
        ni += (gross - BASIC_TO) * 0.02
    return ni


def close(a, b, tol=2.0):
    return abs(a - b) <= tol


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME)
    pg = b.new_context(viewport={"width": 1500, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    pg.goto(FILE)
    pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
    pg.evaluate("() => { experienceLevel = 'advanced'; applyLevel(); activateTab('salary'); renderAll(); }")
    pg.wait_for_timeout(1000)

    def typed(field, value):
        """Type into a box the way a person does: an input event, no blur."""
        pg.evaluate("([f, v]) => { const e = els(f); e.value = v; "
                    "e.dispatchEvent(new Event('input', { bubbles: true })); }", [field, value])
        pg.wait_for_timeout(500)

    def readouts():
        return pg.evaluate("""() => ({
          goesIn: els('yourContributionAmount').textContent.trim(),
          relief: els('yourReliefAmount').textContent.trim(),
          note: els('reliefNote').style.display === 'none' ? '' : els('reliefNote').textContent,
          personalNet: lastModel.personalNet, personalGross: lastModel.personalGross,
          personalRelief: lastModel.personalRelief,
          yourContribution: lastModel.yourContribution,
          salary: lastModel.inp.yourSalary })""")

    typed("yourSalary", "60,000")

    # 1. Typing a rate changes the figures immediately - no blur, no tabbing
    #    away. This is the whole of the "Rate (%) doesn't work" report.
    before = readouts()
    typed("yourPersonalRate", "10")
    after = readouts()
    assert after["personalNet"] != before["personalNet"], (before, after)
    assert close(after["personalNet"], 6000), after
    print(f"1. typing 10% into Rate updated straight away: "
          f"{before['personalNet']} -> {after['personalNet']} a year")

    # 2. The employer rate does the same, and the two add up.
    typed("yourEmployerRate", "20")
    r = readouts()
    assert close(r["personalGross"], 7500), r          # 6,000 net + 20% relief at source
    assert close(r["personalRelief"], 1500), r
    assert close(r["yourContribution"], 12000 + 7500), r   # employer 20% of 60k + your gross
    print(f"2. employer 20% + your 10%: {r['goesIn']} (relief {r['relief']})")

    # 3. Per-month is exactly a twelfth of per-year, in the readout and in the
    #    note, in BOTH entry modes.
    def per_month_matches(label):
        vals = pg.evaluate("""() => { const num = s => { const m = [...String(s)
            .matchAll(/£([\\d,]+(?:\\.\\d+)?)/g)].map(x => parseFloat(x[1].replace(/,/g, '')));
            return m; };
          return { goesIn: num(els('yourContributionAmount').textContent),
                   note: num(els('reliefNote').textContent),
                   contribution: lastModel.yourContribution, net: lastModel.personalNet }; }""")
        yr, mo = vals["goesIn"][0], vals["goesIn"][1]
        assert close(yr, vals["contribution"], 0.51), (label, vals)
        assert close(mo, yr / 12, 0.02), (label, "per month is not a twelfth", vals)
        noteYr, noteMo = vals["note"][0], vals["note"][1]
        assert close(noteYr, vals["net"], 1.0), (label, vals)
        assert close(noteMo, noteYr / 12, 1.0), (label, "note per month wrong", vals)
        return yr, mo, noteYr, noteMo

    yr, mo, nYr, nMo = per_month_matches("percent mode")
    print(f"3a. % mode: £{yr:,.0f}/yr = £{mo:,.2f}/mo into the pot; "
          f"you pay £{nYr:,.0f}/yr = £{nMo:,.0f}/mo")

    pg.evaluate("() => document.querySelector('#yourPersonalModeSeg button[data-pmode=fixed]').click()")
    pg.wait_for_timeout(400)
    typed("yourPersonalMonthly", "500")
    yr2, mo2, nYr2, nMo2 = per_month_matches("fixed mode")
    # £500 a month entered as a fixed amount must mean the same as 10% of £60k
    assert close(nYr2, 6000), nYr2
    assert close(nMo2, 500, 1.0), nMo2
    assert close(yr2, yr, 1.0), (yr, yr2)
    print(f"3b. £/month mode agrees: £{nMo2:,.0f}/mo = £{nYr2:,.0f}/yr, same pot total £{yr2:,.0f}")
    pg.evaluate("() => document.querySelector('#yourPersonalModeSeg button[data-pmode=pct]').click()")
    pg.wait_for_timeout(400)

    # 4. TAKE-HOME WHILE WORKING. Independently: salary, less income tax and
    #    NI, less what you yourself pay into the pension. The employer's
    #    contribution is in the gross bar but was never yours to spend.
    pg.evaluate("() => activateTab('planner')")
    pg.wait_for_timeout(1600)
    d = pg.evaluate("""() => { const y = new Date().getFullYear(); const t = breakdownXform.tip(y);
      return { year: t.year, gross: t.total, taxBase: t.taxBase, tax: t.tax,
               contrib: t.contrib, net: t.net }; }""")
    salary = 60000.0
    expTax = income_tax(salary) + national_insurance(salary)
    assert close(d["taxBase"], salary), d
    assert close(d["tax"], expTax, 3), (d, expTax)
    assert close(d["contrib"], 6000), d
    assert close(d["net"], salary - expTax - 6000, 3), (d, salary - expTax - 6000)
    # and the old bug specifically: tax is NOT (gross - net)
    assert not close(d["tax"], d["gross"] - d["net"], 50), \
        "tax is being inferred from gross - net again"
    print(f"4. working take-home: £{salary:,.0f} pay - £{d['tax']:,.0f} tax & NI "
          f"- £{d['contrib']:,.0f} pension = £{d['net']:,.0f} (gross bar £{d['gross']:,.0f})")

    # 5. It UPDATES. Change the salary and every part of that sum moves.
    pg.evaluate("() => activateTab('salary')")
    pg.wait_for_timeout(400)
    typed("yourSalary", "90,000")
    pg.evaluate("() => activateTab('planner')")
    pg.wait_for_timeout(1600)
    d2 = pg.evaluate("""() => { const y = new Date().getFullYear(); const t = breakdownXform.tip(y);
      return { taxBase: t.taxBase, tax: t.tax, contrib: t.contrib, net: t.net }; }""")
    exp2 = income_tax(90000.0) + national_insurance(90000.0)
    assert close(d2["taxBase"], 90000), d2
    assert close(d2["tax"], exp2, 3), (d2, exp2)
    assert close(d2["contrib"], 9000), d2            # 10% of the new salary
    assert close(d2["net"], 90000 - exp2 - 9000, 3), d2
    assert d2["net"] != d["net"], "take-home did not move with the salary"
    print(f"5. salary £60k -> £90k: take-home £{d['net']:,.0f} -> £{d2['net']:,.0f}, "
          f"tax £{d['tax']:,.0f} -> £{d2['tax']:,.0f}")

    # 6. TAKE-HOME IN RETIREMENT must not depend on which income view is
    #    switched on. Smoothing renames the same money, and the take-home line
    #    used to read the renamed drawdown as tax-free.
    both = {}
    for smooth in [False, True]:
        pg.evaluate("(v) => { els('smoothOn').checked = v; "
                    "els('smoothOn').dispatchEvent(new Event('change', { bubbles: true })); }", smooth)
        pg.wait_for_timeout(1600)
        both[smooth] = pg.evaluate("""() => { const m = lastModel; const out = {};
          [1, 6, 12].forEach(k => { const y = m.yourMeta.decumStartDate.y + k;
            const t = breakdownXform.tip(y);
            if (t) out[y] = { tax: Math.round(t.tax), net: Math.round(t.net),
                              base: Math.round(t.taxBase) }; });
          return out; }""")
    common = set(both[False]) & set(both[True])
    assert len(common) >= 2, both
    for y in sorted(common):
        a, c = both[False][y], both[True][y]
        assert a["tax"] == c["tax"], (y, a, c)
        # the taxable income is the same in both views, so the tax must be too
        assert a["tax"] > 0, (y, a)
    print(f"6. retirement tax identical with smoothing on and off, for {sorted(common)}: "
          + ", ".join(f"{y}: £{both[False][y]['tax']:,}" for y in sorted(common)))

    # 7. And that retirement tax is right: 25% of a drawdown is tax-free, the
    #    rest is income, split across the household's allowances.
    pg.evaluate("() => { els('smoothOn').checked = false; "
                "els('smoothOn').dispatchEvent(new Event('change', { bubbles: true })); }")
    pg.wait_for_timeout(1500)
    check = pg.evaluate("""() => { const m = lastModel; const heads = m.spouse ? 2 : 1;
      const y = m.yourMeta.decumStartDate.y + 6; const t = breakdownXform.tip(y);
      if (!t) return null;
      const seg = k => { const s = t.segs.find(s => new RegExp(k, 'i').test(s.label)); return s ? s.amt : 0; };
      return { heads, year: y, tax: t.tax, net: t.net, base: t.taxBase,
               draw: seg('pension'), state: seg('State'), db: seg('DB') }; }""")
    assert check, "no retirement year to check"
    taxablePerHead = (check["draw"] * 0.75 + check["state"] + check["db"]) / check["heads"]
    expected = check["heads"] * income_tax(taxablePerHead)   # no NI on pension income
    assert close(check["tax"], expected, 3), (check, expected, taxablePerHead)
    print(f"7. retirement tax checks out: £{check['draw']:,.0f} drawdown, 25% tax-free, "
          f"{check['heads']} allowance(s) -> £{check['tax']:,.0f} (independently £{expected:,.0f})")

    # 8. Nothing above depended on blurring a field: prove the live path once
    #    more, on a box the charts read directly.
    pg.evaluate("() => activateTab('salary')")
    pg.wait_for_timeout(400)
    n0 = pg.evaluate("() => lastModel.yourContribution")
    pg.evaluate("() => { const e = els('yourEmployerRate'); e.focus(); e.value = '25'; "
                "e.dispatchEvent(new Event('input', { bubbles: true })); }")
    pg.wait_for_timeout(600)
    stillFocused = pg.evaluate("() => document.activeElement.id")
    n1 = pg.evaluate("() => lastModel.yourContribution")
    assert n1 != n0, (n0, n1)
    assert stillFocused == "yourEmployerRate", stillFocused
    print(f"8. recomputed while the box still had focus ({n0:,.0f} -> {n1:,.0f}) - "
          f"the caret stayed in {stillFocused}")

    if errors:
        raise SystemExit("CONSOLE/PAGE ERRORS:\n" + "\n".join(errors[:10]))
    print("\nALL MONEY READOUT TESTS PASSED, no console/page errors")
    b.close()
