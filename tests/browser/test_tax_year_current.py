"""The rates are for the CURRENT tax year, and drift is a silent failure.

This is the test the app most needed and did not have. Every other suite
checks that the arithmetic is consistent with the tables; none of them checked
that the tables are this year's. So the app sat on 2025/26 UK rates, 2025 US
brackets, a 2025 French barème and 2024-25 Australian rates while presenting
itself as current - and none of that breaks anything, it just quietly gives
everybody the wrong answer.

The figures below are written out longhand from the primary announcements
rather than read from the app, so when a rate changes this file fails and has
to be deliberately updated, which is the point.

Sources, all checked September 2026:
  UK      Personal allowance £12,570 and the higher-rate threshold £50,270,
          frozen to April 2031 (Autumn Budget 2025 extended the freeze by
          three years). Scottish starter and basic band limits rose 7.4% for
          2026/27 to £16,537 and £29,526; higher, advanced and top frozen.
          New State Pension £241.30/week. Dividend ordinary and upper rates
          rose two points to 10.75% and 35.75% on 6 April 2026. Property and
          savings income get their own 22/42/47% rates on 6 April 2027.
  US      Rev. Proc. 2025-32: single-filer brackets starting at $12,400,
          standard deduction $16,100, $2,050 more from 65, plus the OBBBA
          $6,000 senior deduction for 2025-2028 phasing out above $75,000.
  France  Loi de finances 2026 indexed the barème by 0.9%: 11,600 / 29,579 /
          84,577 / 181,917. The 10% pension deduction is capped at €4,399.
  Australia 2026-27: the second band fell from 16% to 15% on 1 July 2026 and
          falls again to 14% in 2027. Medicare levy phases in from $28,011.

What this does NOT do is assert that any of these are still right in a later
year - nothing can. It asserts that the app and this file agree, so that
updating one without the other is caught.
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
FILE = (ROOT / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)
    return cond


def bands_tax(taxable, bands):
    """The app's own banding rule, reimplemented so a bug in it is visible."""
    t = 0.0
    for i, (frm, rate) in enumerate(bands):
        to = bands[i + 1][0] if i + 1 < len(bands) else float("inf")
        if taxable > frm:
            t += (min(taxable, to) - frm) * rate
    return t


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        pg = b.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(FILE)
        pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
        pg.wait_for_timeout(500)

        # ---- 1. UK: the frozen thresholds, and the Scottish ones that moved --
        uk = pg.evaluate("() => TAXDATA.UK")
        check(uk["pa"] == 12570, f"UK personal allowance is {uk['pa']}, not £12,570")
        check(uk["paTaperFrom"] == 100000, f"the PA taper starts at {uk['paTaperFrom']}")
        check([b[0] for b in uk["bands"]] == [12570, 50270, 125140],
              f"UK band thresholds are {[b[0] for b in uk['bands']]}, "
              f"not 12,570 / 50,270 / 125,140")
        check([b[1] for b in uk["bands"]] == [0.20, 0.40, 0.45],
              f"UK rates are {[b[1] for b in uk['bands']]}")
        SCOT = [[12570, 0.19], [16537, 0.20], [29526, 0.21],
                [43662, 0.42], [75000, 0.45], [125140, 0.48]]
        check(uk["scotBands"] == SCOT,
              f"Scottish bands are {uk['scotBands']}, not the 2026/27 set {SCOT}. "
              f"The starter and basic limits rose 7.4% to £16,537 and £29,526.")
        check(uk["niBands"] == [[12570, 0.08], [50270, 0.02]],
              f"employee NI is {uk['niBands']}, not 8% then 2%")
        print("1. UK 2026/27: allowance, bands, NI and all six Scottish bands are current")

        # The 48% top rate and the 67.5% allowance-withdrawal band both exist,
        # and the app must be able to produce them rather than round them away.
        scot_check = pg.evaluate("""() => {
          const at = (g) => ukIncomeTax(g, true);
          const marg = g => (at(g + 100) - at(g)) / 100;
          // £80,000 is inside the advanced band but below the £100,000 where
          // the personal allowance starts being withdrawn - probing at
          // £100,000 measures the 67.5% allowance-withdrawal band instead,
          // which is a real rate but not this one.
          return { top: +marg(200000).toFixed(3), advanced: +marg(80000).toFixed(3),
                   withdrawal: +marg(110000).toFixed(3),
                   sixty: +((ukIncomeTax(110000,false)-ukIncomeTax(109900,false))/100).toFixed(3) }; }""")
        check(abs(scot_check["top"] - 0.48) < 0.001,
              f"the Scottish top rate came out at {scot_check['top']:.1%}, not 48%")
        check(abs(scot_check["advanced"] - 0.45) < 0.001,
              f"the Scottish advanced rate came out at {scot_check['advanced']:.1%}, not 45%")
        # 45% advanced plus the allowance being withdrawn at 50p in the pound:
        # the highest marginal rate anywhere in the UK, and it is not a typo.
        check(abs(scot_check["withdrawal"] - 0.675) < 0.001,
              f"the Scottish allowance-withdrawal band came out at "
              f"{scot_check['withdrawal']:.1%}, not 67.5%")
        check(abs(scot_check["sixty"] - 0.60) < 0.001,
              f"the 60% band (40% plus the withdrawn allowance) came out at "
              f"{scot_check['sixty']:.1%} - it is the single most misunderstood UK rate "
              f"and the app has to show it")
        print(f"   the 60% band emerges from the taper at {scot_check['sixty']:.0%}, "
              f"Scotland's advanced and top rates at "
              f"{scot_check['advanced']:.0%} / {scot_check['top']:.0%}, and its "
              f"allowance-withdrawal band at {scot_check['withdrawal']:.1%}")

        # State Pension: the figure in the box, and the one in the glossary.
        sp = pg.evaluate("""() => ({
          box: document.getElementById('statePensionWeekly').value,
          country: COUNTRIES.UK.spWeeklyDefault,
          gloss: DEFINITIONS.statePension ? DEFINITIONS.statePension.expert : '' })""")
        check(abs(float(sp["box"].replace(",", "")) - 241.30) < 0.01,
              f"the State Pension box says {sp['box']}, not the 2026/27 rate of £241.30")
        check(abs(sp["country"] - 241.30) < 0.01,
              f"COUNTRIES.UK.spWeeklyDefault is {sp['country']}, not 241.30")
        check("241.30" in sp["gloss"],
              f"the glossary still quotes an old State Pension rate: {sp['gloss'][:100]!r}")
        print(f"2. the new State Pension is £241.30/week in the input, the country table "
              f"and the glossary")

        # The freeze runs to 2031 now, not 2028.
        freeze = pg.evaluate("""() => ({
          uk: RELOCATE.UK.risks.join(' '),
          note: COUNTRIES.UK.note })""")
        check("2031" in freeze["uk"],
              f"the UK risk note still gives the old freeze end date: {freeze['uk'][:140]!r}")
        check("2031" in freeze["note"],
              f"the UK tax note does not mention the freeze to 2031: {freeze['note'][:140]!r}")
        print("   the threshold freeze is stated as running to April 2031, not 2028")

        # ---- 3. US 2026 -----------------------------------------------------
        us = pg.evaluate("() => TAXDATA.US")
        US_BANDS = [[0, 0.10], [12400, 0.12], [50400, 0.22], [105700, 0.24],
                    [201775, 0.32], [256225, 0.35], [640600, 0.37]]
        check(us["bands"] == US_BANDS,
              f"US brackets are {us['bands']}, not the 2026 set from Rev. Proc. 2025-32")
        check(us["stdDeduction"] == 16100,
              f"the US standard deduction is {us['stdDeduction']}, not $16,100 for 2026")
        check(us["age65Extra"] == 2050,
              f"the extra standard deduction at 65 is {us.get('age65Extra')}, not $2,050")
        check(us["seniorDeduction"] == 6000 and us["seniorPhaseFrom"] == 75000,
              f"the OBBBA senior deduction is not modelled as $6,000 phasing from $75,000: {us}")
        # And it actually reaches the answer: a 68-year-old on $60,000 pays
        # less than a 50-year-old on the same money, by a knowable amount.
        age_gap = pg.evaluate("""() => ({
          young: Math.round(usIncomeTax(60000, 50)),
          old: Math.round(usIncomeTax(60000, 68)),
          ded: Math.round(usDeduction(60000, 68)) })""")
        want_ded = 16100 + 2050 + max(0, 6000 - max(0, 60000 - 75000) * 0.06)
        check(age_gap["ded"] == round(want_ded),
              f"the deduction at 68 on $60,000 is ${age_gap['ded']:,}, expected ${round(want_ded):,}")
        check(age_gap["old"] < age_gap["young"],
              f"age 65+ made no difference to US tax: {age_gap}")
        # Above the phase-out it tapers away rather than cutting off.
        taper = pg.evaluate("""() => [75000, 100000, 150000].map(g =>
          Math.round(usDeduction(g, 68) - 16100 - 2050))""")
        check(taper == [6000, 4500, 1500],
              f"the senior deduction taper is {taper}, expected 6,000 / 4,500 / 1,500 "
              f"at 6% of income above $75,000")
        print(f"3. US 2026: brackets from $12,400, ${us['stdDeduction']:,} standard deduction, "
              f"and the 65+ additions worth ${age_gap['ded'] - 16100:,} at $60,000")

        # ---- 4. France 2026 -------------------------------------------------
        fr = pg.evaluate("() => TAXDATA.FR")
        FR_BANDS = [[11600, 0.11], [29579, 0.30], [84577, 0.41], [181917, 0.45]]
        check(fr["bands"] == FR_BANDS,
              f"the French barème is {fr['bands']}, not the 2026 set {FR_BANDS} "
              f"(the 2025 thresholds indexed by 0.9%)")
        check(fr["pensionDeductionCap"] == 4399,
              f"the 10% pension deduction cap is {fr.get('pensionDeductionCap')}, not €4,399")
        # The cap is the point: above ~€44,000 of pension the deduction stops.
        ded = pg.evaluate("""() => [10000, 44000, 80000, 200000].map(x =>
          Math.round(frPensionDeduction(x)))""")
        check(ded == [1000, 4399, 4399, 4399],
              f"the pension deduction is {ded}; it should be 10% up to the €4,399 cap and "
              f"then flat, which is what makes a large French pension worse than a small one")
        print(f"4. France 2026: barème indexed to 11,600 / 29,579 / 84,577 / 181,917, "
              f"and the 10% pension deduction caps at €4,399")

        # ---- 5. Australia 2026-27 -------------------------------------------
        au = pg.evaluate("() => TAXDATA.AU")
        AU_BANDS = [[18200, 0.15], [45000, 0.30], [135000, 0.37], [190000, 0.45]]
        check(au["bands"] == AU_BANDS,
              f"Australian bands are {au['bands']}, not the 2026-27 set. The second band "
              f"fell from 16% to 15% on 1 July 2026.")
        check(au["medicareFrom"] == 28011,
              f"the Medicare levy threshold is {au['medicareFrom']}, not $28,011 for 2026-27")
        second = pg.evaluate("""() => +((auIncomeTax(40000) - auIncomeTax(39000)) / 1000).toFixed(3)""")
        check(abs(second - 0.17) < 0.001,
              f"the marginal rate in the second band is {second:.1%}, expected 15% plus the "
              f"2% Medicare levy")
        print(f"5. Australia 2026-27: second band at 15% (17% with the levy), "
              f"Medicare from ${au['medicareFrom']:,}")

        # ---- 6. UK dividend, property and savings rate changes --------------
        prop = pg.evaluate("() => PROP")
        check(abs(prop["divBasic"] - 0.1075) < 1e-9 and abs(prop["divHigher"] - 0.3575) < 1e-9,
              f"dividend rates are {prop['divBasic']}/{prop['divHigher']}, not the "
              f"10.75%/35.75% in force since 6 April 2026")
        check(abs(prop["divAddl"] - 0.3935) < 1e-9,
              f"the additional dividend rate is {prop['divAddl']}, and it did not change")
        check(abs(prop["propBasic"] - 0.22) < 1e-9 and abs(prop["propHigher"] - 0.42) < 1e-9
              and abs(prop["propAddl"] - 0.47) < 1e-9,
              f"the April 2027 property income rates are not 22/42/47: {prop}")
        check(abs(prop["s24Credit"] - 0.20) < 1e-9,
              "the Section 24 credit must stay at 20% when the rates rise - that is exactly "
              "what makes the 2027 change bite a geared landlord harder than two points")
        check(prop["cgtAEA"] == 3000 and abs(prop["cgtBasic"] - 0.18) < 1e-9
              and abs(prop["cgtHigher"] - 0.24) < 1e-9,
              f"CGT on residential property should still be 18/24 with a £3,000 allowance: {prop}")
        check(prop["divAllowance"] == 500,
              f"the dividend allowance is {prop['divAllowance']}, and it is still £500")
        print("6. the April 2026 dividend rise and the April 2027 property income rates are "
              "both in, with the Section 24 credit held at 20%")

        # The 2027 card has to exist and show a real difference, because a
        # dated change nobody is shown is a change nobody plans for.
        card = pg.evaluate("""() => {
          activateTab('property');
          renderAll();
          const el = document.getElementById('prop27');
          const pill = document.getElementById('prop27Pill');
          return { html: el ? el.innerText : null, pill: pill ? pill.innerText : null }; }""")
        pg.wait_for_timeout(400)
        card = pg.evaluate("""() => {
          const el = document.getElementById('prop27');
          const pill = document.getElementById('prop27Pill');
          return { text: el ? el.innerText : '', pill: pill ? pill.innerText : '' }; }""")
        check("2027" in card["text"] and "22" in card["text"] and "42" in card["text"],
              f"the April 2027 card does not name the new rates: {card['text'][:160]!r}")
        check(card["pill"] and card["pill"] != "—",
              f"the April 2027 card's verdict pill says {card['pill']!r}")
        print(f"   the property tab carries an April 2027 card, reading {card['pill']!r} "
              f"on the default property")

        # ---- 7. ISA and lump sum figures ------------------------------------
        isa = pg.evaluate("""() => ({ annual: ISA_ANNUAL_LIMIT,
          cash2027: typeof ISA_CASH_LIMIT_FROM_2027 === 'number' ? ISA_CASH_LIMIT_FROM_2027 : null,
          exemptAge: typeof ISA_CASH_LIMIT_AGE_EXEMPT === 'number' ? ISA_CASH_LIMIT_AGE_EXEMPT : null,
          pcls: LUMP_SUM_ALLOWANCE,
          shelter: (TAX_SHELTERS.find(s => s.id === 'isaWrap') || {}).what || '' })""")
        check(isa["annual"] == 20000, f"the ISA limit is {isa['annual']}, not £20,000")
        check(isa["cash2027"] == 12000 and isa["exemptAge"] == 65,
              f"the April 2027 cash ISA cap is not recorded as £12,000 for the under-65s: {isa}")
        check("12,000" in isa["shelter"] and "2027" in isa["shelter"],
              f"the ISA panel does not mention the 2027 cash cap: {isa['shelter'][:120]!r}")
        check(isa["pcls"] == 268275,
              f"the lump sum allowance is {isa['pcls']}, not £268,275")
        print(f"7. ISA £20,000 with the 2027 cash cap of £12,000 recorded, "
              f"lump sum allowance £{isa['pcls']:,}")

        # ---- 8. no stale year labels left on screen -------------------------
        # A label saying "2025/26" next to a 2026/27 number is worse than no
        # label: it is a claim about currency that happens to be false.
        stale = pg.evaluate("""() => {
          const bad = [];
          const txt = document.body.innerHTML;
          for (const y of ['2024/25', '2025/26', '2024-25', '2024–25']) {
            let i = txt.indexOf(y);
            while (i !== -1) { bad.push(y + ': ' + txt.slice(Math.max(0,i-70), i+12).replace(/\\s+/g,' ')); i = txt.indexOf(y, i + 1); }
          }
          return bad.slice(0, 8); }""")
        check(not stale,
              "the page still labels figures with an old tax year:\n      "
              + "\n      ".join(stale))
        print("8. no figure on the page is labelled with a superseded tax year")

        # ---- 9. every country's engine still reconciles ---------------------
        # After moving six countries onto one dispatch, the salary figures must
        # still add up in each - tax plus contribution plus take-home = gross.
        recon = pg.evaluate("""() => {
          const out = {};
          for (const c of ['UK','US','FR','AU','HK','SG']) {
            const g = 60000, t = taxOnSalary(g, c, false, 45);
            out[c] = { tax: Math.round(t.tax), soc: Math.round(t.ni), net: Math.round(t.net),
                       sums: Math.abs(t.tax + t.ni + t.net - g) < 0.01,
                       eff: +t.effective.toFixed(1) };
          }
          return out; }""")
        for c, r in recon.items():
            check(r["sums"], f"{c}: tax + contribution + take-home does not equal gross: {r}")
            check(0 <= r["eff"] < 60, f"{c}: an effective rate of {r['eff']}% on 60,000 is not credible")
        check(recon["HK"]["soc"] > 0 and recon["SG"]["soc"] > 0 and recon["UK"]["soc"] > 0,
              "MPF, CPF and NI should all come off pay")
        check(recon["US"]["soc"] == 0 and recon["FR"]["soc"] == 0 and recon["AU"]["soc"] == 0,
              "the US, France and Australia have no contribution modelled in this slot")
        print("9. all six engines reconcile on 60,000 of salary: "
              + ", ".join(f"{c} {r['eff']}%" for c, r in recon.items()))

        # ---- 10. the single dispatch really is single ------------------------
        # The old code had this chain written out six times. If a copy comes
        # back, a new country silently gets Australian tax, so the count of
        # country chains in the source is itself worth asserting.
        src = (ROOT / "pension-planner.html").read_text()
        copies = src.count('currentCountry === "FR" ? frIncomeTax')
        check(copies == 0,
              f"the per-country tax chain is written out {copies} more time(s) outside "
              f"incomeTaxFor(). Every copy is a place a new country gets forgotten.")
        for fn in ("incomeTaxFor", "socialOnSalary", "retirementTaxableFraction"):
            check(f"function {fn}(" in src, f"{fn}() is missing")
        print("10. there is exactly one country dispatch, not six copies of one")

        b.close()

    if errors:
        failures.append("page errors: " + "; ".join(sorted(set(errors))[:4]))
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("\nEVERY RATE IN THE APP IS THE CURRENT TAX YEAR'S")


if __name__ == "__main__":
    main()
