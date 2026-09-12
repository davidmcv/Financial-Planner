"""Hong Kong and Singapore, checked against the statutes rather than the app.

Two countries were added across the whole app, and both of them break an
assumption the other five share, so neither can be verified by "it renders
without an error". What has to hold:

  HONG KONG   Salaries tax is the LOWER of two calculations - progressive
              rates after a generous allowance, or a flat standard rate with
              no allowance at all. Modelling one of them is wrong in both
              directions, and the crossover is a real number that can be
              found and checked.

              And the fact that makes Hong Kong worth getting right: the 2010
              UK-Hong Kong treaty assigns pensions to the country they ARISE
              in, not the country you live in. That is the reverse of almost
              every other UK treaty. So the Where to live tab must NOT show
              Hong Kong as tax-free on a UK pension, however much the reader
              expects it to. A 0% row there would be the most expensive thing
              this app could print.

  SINGAPORE   Progressive to 24%, with earned income relief that steps up at
              55 and again at 60 - the reader is usually in one of those
              steps. Employee CPF comes off pay AND off taxable income, at a
              rate that falls as you age, capped at the Ordinary Wage
              ceiling. Foreign income received by an individual is exempt,
              but the treaty only hands the taxing right over where the
              pension is actually subject to tax there, which at nil it may
              not be.

Every figure below is the 2026/27 Hong Kong year of assessment and Singapore
YA2026, hand-computed here from the published bands so that a change to the
app's tables fails this file rather than passing quietly.
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
FILE = (ROOT / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

failures = []

COUNTRY_NAMES = {"HK": "Hong Kong", "SG": "Singapore", "AU": "Australia"}


def check(cond, msg):
    if not cond:
        failures.append(msg)
    return cond


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        ctx = b.new_context(viewport={"width": 1400, "height": 1000})
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto(FILE)
        pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
        pg.evaluate("""() => { localStorage.setItem('pensionPlanner.rememberChoice','advanced');
          experienceLevel = 'advanced'; applyLevel(); renderAll(); }""")
        pg.wait_for_timeout(700)

        # ---- 1. Hong Kong takes the LOWER of two sums ----------------------
        # Progressive: 2/6/10/14/17% on HK$50,000 slices after HK$145,000.
        # Standard:    15% of everything, no allowance, to HK$5m.
        def hk_progressive(inc, allowance=145000):
            t, rem = 0.0, max(0.0, inc - allowance)
            for rate in (0.02, 0.06, 0.10, 0.14):
                slice_ = min(rem, 50000)
                t += slice_ * rate
                rem -= slice_
                if rem <= 0:
                    return t
            return t + rem * 0.17

        cases = [200000, 500000, 1000000, 2000000, 2500000, 6000000]
        got = pg.evaluate("(xs) => xs.map(x => Math.round(hkIncomeTax(x, false)))", cases)
        for inc, g in zip(cases, got):
            prog = hk_progressive(inc)
            std = inc * 0.15 if inc <= 5000000 else 5000000 * 0.15 + (inc - 5000000) * 0.16
            want = round(min(prog, std))
            check(abs(g - want) <= 1,
                  f"HK salaries tax on HK${inc:,}: app HK${g:,}, "
                  f"lower of progressive HK${round(prog):,} and standard HK${round(std):,} = HK${want:,}")
        print(f"1. Hong Kong: the lower of two calculations holds at {len(cases)} incomes "
              f"(HK${cases[0]:,} to HK${cases[-1]:,})")

        # The crossover is a fact about the regime, not an implementation
        # detail: below it the progressive sum wins, above it the flat one does.
        # 17% on the top slice beats a flat 15% of everything once the
        # allowance stops being worth more than the rate difference:
        # 0.17x - 42,650 = 0.15x, so x = HK$2,132,500.
        cross = pg.evaluate("""() => {
          const hk = TAXDATA.HK;
          for (let x = 200000; x <= 5000000; x += 500) {
            const prog = taxBands(Math.max(0, x - hk.basicAllowance), hk.bands);
            const std = taxBands(x, hk.stdBands);
            if (prog >= std) return x;
          }
          return null; }""")
        check(cross is not None and abs(cross - 2132500) <= 500,
              f"the progressive/standard crossover came out at {cross}, not HK$2,132,500")
        check(pg.evaluate("(x) => Math.abs(hkIncomeTax(x + 100000, false) - (x + 100000) * 0.15) < 1",
                          cross),
              "above the crossover the app is not charging the flat standard rate")
        print(f"   the flat 15% takes over above HK${cross:,}, which is where 17% of the top "
              f"slice overtakes 15% of the lot")

        # A married couple electing joint assessment gets double the allowance.
        pair = pg.evaluate("() => [hkIncomeTax(400000,false), hkIncomeTax(400000,true)]")
        check(pair[1] < pair[0],
              f"the married person's allowance made no difference: {pair}")
        check(abs(pair[1] - hk_progressive(400000, 290000)) <= 1,
              f"married HK tax on HK$400,000 was {pair[1]}, expected {hk_progressive(400000, 290000)}")
        print(f"   the married allowance of HK$290,000 cuts HK$400,000 from "
              f"HK${round(pair[0]):,} to HK${round(pair[1]):,}")

        # MPF: 5% of pay, capped at HK$18,000, and deductible.
        mpf = pg.evaluate("() => [hkMPF(200000), hkMPF(360000), hkMPF(900000)]")
        check(abs(mpf[0] - 10000) < 1 and abs(mpf[1] - 18000) < 1 and abs(mpf[2] - 18000) < 1,
              f"MPF is 5% capped at HK$18,000; got {mpf}")
        deducted = pg.evaluate("""() => {
          const t = taxOnSalary(500000, 'HK', false, 50);
          return { tax: Math.round(t.tax), mpf: Math.round(t.ni),
                   direct: Math.round(hkIncomeTax(500000 - hkMPF(500000), false)) }; }""")
        check(deducted["tax"] == deducted["direct"],
              f"MPF was not deducted before the bands: {deducted}")
        print(f"2. MPF: HK${deducted['mpf']:,} off pay and off taxable income, "
              f"leaving HK${deducted['tax']:,} of salaries tax on HK$500,000")

        # ---- 3. Singapore bands, hand-computed ----------------------------
        SG_BANDS = [(20000, 0), (30000, 0.02), (40000, 0.035), (80000, 0.07),
                    (120000, 0.115), (160000, 0.15), (200000, 0.18), (240000, 0.19),
                    (280000, 0.195), (320000, 0.20), (500000, 0.22), (1000000, 0.23),
                    (float("inf"), 0.24)]

        def sg_tax(chargeable):
            t, lower = 0.0, 0.0
            for upper, rate in SG_BANDS:
                if chargeable <= lower:
                    break
                t += (min(chargeable, upper) - lower) * rate
                lower = upper
            return t

        # Earned income relief: 1,000 under 55, 6,000 from 55, 8,000 from 60.
        for inc, age, relief in [(40000, 40, 1000), (100000, 57, 6000),
                                 (100000, 62, 8000), (250000, 70, 8000)]:
            g = pg.evaluate("(a) => Math.round(sgIncomeTax(a[0], a[1]))", [inc, age])
            want = round(sg_tax(inc - relief))
            check(abs(g - want) <= 1,
                  f"SG tax on S${inc:,} at {age}: app S${g:,}, expected S${want:,} "
                  f"(relief S${relief:,})")
        print("3. Singapore: bands and the earned income relief steps at 55 and 60 all check out")

        # ---- 4. CPF falls in steps with age, and is capped ----------------
        cpf = pg.evaluate("""() => [40,57,62,67,72].map(a => ({ age: a,
          rate: +(sgCPF(60000, a) / 60000).toFixed(4),
          onHighPay: Math.round(sgCPF(200000, a)) }))""")
        want_rates = {40: 0.20, 57: 0.18, 62: 0.125, 67: 0.075, 72: 0.05}
        for row in cpf:
            check(abs(row["rate"] - want_rates[row["age"]]) < 0.0005,
                  f"employee CPF at {row['age']} came out at {row['rate']:.1%}, "
                  f"expected {want_rates[row['age']]:.1%}")
            # S$8,000 a month ceiling: nothing above S$96,000 attracts CPF.
            check(abs(row["onHighPay"] - 96000 * want_rates[row["age"]]) < 1,
                  f"the Ordinary Wage ceiling was not applied at {row['age']}: {row}")
        print("4. CPF: 20% to 55, then 18 / 12.5 / 7.5 / 5%, all capped at the "
              "S$8,000-a-month ceiling")

        # CPF comes off taxable income as well as off pay.
        sg_sal = pg.evaluate("""() => { const t = taxOnSalary(120000, 'SG', false, 45);
          return { tax: Math.round(t.tax), cpf: Math.round(t.ni), net: Math.round(t.net),
                   direct: Math.round(sgIncomeTax(120000 - sgCPF(120000, 45), 45)) }; }""")
        check(sg_sal["tax"] == sg_sal["direct"],
              f"CPF was not exempted from taxable income: {sg_sal}")
        check(sg_sal["net"] == 120000 - sg_sal["tax"] - sg_sal["cpf"],
              f"take-home does not reconcile: {sg_sal}")
        print(f"   S$120,000 at 45: S${sg_sal['cpf']:,} of CPF, S${sg_sal['tax']:,} of tax, "
              f"S${sg_sal['net']:,} in hand")

        # ---- 5. what each country does to a pension ----------------------
        # Hong Kong taxes retirement benefits at nil; Singapore taxes half of
        # an SRS withdrawal and none of CPF LIFE.
        ret = pg.evaluate("""() => {
          const draw = 40000, state = 10000, age = 68;
          const out = {};
          for (const c of ['UK','US','FR','AU','HK','SG']) {
            out[c] = { frac: retirementTaxableFraction(c, age),
                       net: Math.round(taxOnRetirement(draw, state, age, c, false)) };
          }
          return out; }""")
        check(ret["HK"]["frac"] == 0, f"Hong Kong should tax none of a pot withdrawal: {ret['HK']}")
        check(ret["HK"]["net"] == 50000,
              f"Hong Kong took tax off a pension: net {ret['HK']['net']} of 50,000")
        check(ret["SG"]["frac"] == 0.5,
              f"Singapore should treat half an SRS withdrawal as taxable: {ret['SG']}")
        # Singapore genuinely charges nothing on a modest income: half of a
        # £40,000 draw is S$20,000, and after earned income relief that sits
        # entirely inside the 0% band. So the half-taxable rule has to be
        # shown biting where it should rather than where it should not.
        sg_big = pg.evaluate("""() => {
          const gross = 300000;
          const net = taxOnRetirement(gross, 0, 68, 'SG', false);
          return { tax: Math.round(gross - net),
                   onHalf: Math.round(sgIncomeTax(gross * 0.5, 68)) }; }""")
        check(sg_big["tax"] > 0 and sg_big["tax"] == sg_big["onHalf"],
              f"the half-taxable SRS rule does not bite on a large draw: {sg_big}")
        # Its own state pension is outside the charge in both.
        sg_state_free = pg.evaluate("""() => Math.round(taxOnRetirement(0, 40000, 68, 'SG', false))""")
        check(sg_state_free == 40000,
              f"CPF LIFE payouts should not be taxed; net came to {sg_state_free} of 40,000")
        print(f"5. a £40,000 draw plus £10,000 of state pension at 68: "
              + ", ".join(f"{c} {v['net']:,}" for c, v in ret.items()))

        # ---- 6. the treaty, which is the whole point of Hong Kong --------
        # Where to live must NOT show Hong Kong as free of tax on a UK
        # pension, because Article 17 leaves the UK taxing it.
        treaty = pg.evaluate("""() => {
          const o = { people: 1, scot: false };
          const hk = RELOCATE.HK.tax(40000, o), uk = RELOCATE.UK.tax(40000, o);
          const sg = RELOCATE.SG.tax(40000, o);
          return { hk: Math.round(hk), uk: Math.round(uk), sg: Math.round(sg),
                   hkNote: RELOCATE.HK.taxNote, sgNote: RELOCATE.SG.taxNote,
                   hkMoney: RELOCATE.HK.money.join(' '), sgMoney: RELOCATE.SG.money.join(' ') }; }""")
        check(treaty["hk"] > 0,
              "Where to live shows Hong Kong taking NO tax on a UK pension. Under Article 17 of "
              "the UK-Hong Kong treaty the UK keeps the taxing right, so a zero here tells the "
              "reader they would save their whole tax bill by moving. They would not.")
        check(treaty["hk"] == treaty["uk"],
              f"the Hong Kong row should equal the UK bill (the UK is still the taxing country): "
              f"HK {treaty['hk']} vs UK {treaty['uk']}")
        check("treaty" in treaty["hkNote"].lower() and "17" in treaty["hkNote"],
              "the Hong Kong note does not explain that the treaty leaves the UK taxing it")
        check("do not assume a tax saving" in treaty["hkMoney"].lower(),
              "the Hong Kong advice does not warn against assuming a saving")
        check(treaty["sg"] > 0,
              "Where to live shows Singapore taking no tax, which over-promises: the treaty only "
              "moves the taxing right where the pension is actually subject to tax there.")
        check("subject to tax" in treaty["sgNote"].lower(),
              "the Singapore note does not mention the 'subject to tax' condition, which is the "
              "one thing that decides whether the move saves anything")
        print(f"6. the treaty is respected: Hong Kong shows £{treaty['hk']:,} on a £40,000 pension, "
              f"the same as staying in the UK, and says why")

        # Both freeze the UK State Pension, and both say so.
        frozen = pg.evaluate("""() => ['HK','SG','CA','AU'].map(c =>
          ({ c, frozen: /frozen/i.test(RELOCATE[c].money.join(' ')) }))""")
        for row in frozen:
            check(row["frozen"],
                  f"{row['c']} does not warn that the UK State Pension is frozen there")
        print("   all four frozen-pension countries say so: Hong Kong, Singapore, Canada, Australia")

        # ---- 7. no retirement visa, said plainly -------------------------
        visas = pg.evaluate("""() => {
          const out = {};
          for (const c of ['HK','SG']) {
            out[c] = { first: RELOCATE[c].immigration[0].name,
                       routes: RELOCATE[c].immigration.length,
                       entry: entryRoute(c) };
          }
          return out; }""")
        for c, v in visas.items():
            check("no retirement visa" in v["first"].lower(),
                  f"{c} does not lead with the fact that there is no retirement visa: {v['first']!r}")
            check("No retirement visa" in v["entry"],
                  f"the {c} row in the table says {v['entry']!r} rather than naming the obstacle")
            check(v["routes"] >= 4, f"{c} lists only {v['routes']} routes")
        print(f"7. both lead with 'no retirement visa' and list the workarounds "
              f"({visas['HK']['routes']} for Hong Kong, {visas['SG']['routes']} for Singapore)")

        # ---- 8. the app carries them everywhere, not just in one table ---
        wired = pg.evaluate("""() => {
          const out = {};
          for (const c of ['HK','SG']) {
            out[c] = {
              inPicker: !!document.querySelector(`#country option[value="${c}"]`),
              inSpousePicker: !!document.querySelector(`#spouseCountry option[value="${c}"]`),
              currency: COUNTRIES[c].currency,
              spName: COUNTRIES[c].spName,
              social: COUNTRIES[c].social,
              maxAge: MAX_AGE[c],
              gift: !!GIFT_TAX[c],
              giftTaxed: GIFT_TAX[c].hasTax,
              moveOut: !!MOVE_OUT[c],
              flag: !!FLAG_SVG[c],
              trip: !!TRIP_TERMS[c],
              relocate: !!RELOCATE[c],
              taxdata: !!TAXDATA[c],
              standards: LIVING_STANDARDS[c] === null,
              srcLink: !!GLOSSARY[MOVE_OUT[c].src],
              dcLink: !!(GLOSSARY.dcPension.byCountry[c]),
              contribLabel: personalContribLabels(c).field,
            };
          }
          return out; }""")
        for c, w in wired.items():
            for key in ("inPicker", "inSpousePicker", "gift", "moveOut", "flag",
                        "trip", "relocate", "taxdata", "srcLink", "dcLink"):
                check(w[key], f"{c} is missing from {key}")
            check(w["giftTaxed"] is False,
                  f"{c} is shown as having an inheritance or gift tax; both abolished theirs")
            check(w["maxAge"] >= 105,
                  f"{c} models to only {w['maxAge']}, and these two have the longest lives on earth")
            check(w["standards"],
                  f"{c} should have no official retirement living standard, so the page points at "
                  f"the Budget planner instead of borrowing someone else's numbers")
            check(w["social"], f"{c} does not name its mandatory contribution")
        check(wired["HK"]["social"] == "MPF" and wired["SG"]["social"] == "CPF",
              f"the contributions are misnamed: {wired['HK']['social']}, {wired['SG']['social']}")
        check("MPF" in wired["HK"]["contribLabel"], "the Hong Kong contribution field says the wrong thing")
        check("SRS" in wired["SG"]["contribLabel"], "the Singapore contribution field says the wrong thing")
        print(f"8. both are wired through all thirteen country-keyed structures "
              f"({wired['HK']['currency']} / {wired['SG']['currency']}, "
              f"{wired['HK']['spName']} / {wired['SG']['spName']})")

        # ---- 9. moving out of the wrapper is honestly described ----------
        # Neither has anything to gain, for opposite reasons. Saying "yes, do
        # this" where there is no shelter to move into would be worse than
        # not offering it.
        mo = pg.evaluate("""() => ['HK','SG'].map(c => ({ c,
          worse: !!MOVE_OUT[c].worseByDesign, frac: MOVE_OUT[c].taxableFraction,
          note: MOVE_OUT[c].note }))""")
        for row in mo:
            check(row["worse"],
                  f"{row['c']} offers the move-out strategy as though it helped: {row['note'][:70]!r}")
        check(mo[1]["frac"] == 0.5,
              f"Singapore's SRS should be half taxable on the way out, got {mo[1]['frac']}")
        print("9. moving money out of MPF or SRS is marked as pointless, and each says why")

        # ---- 9b. the gifting card stopped talking about Queensland --------
        # Three countries have no transfer tax, and the card used to tell all
        # three that Australia abolished death duties in 1979 and warn them
        # about Age Pension means-testing.
        for c, want, mustnot in (("HK", "2006", "Age Pension"),
                                 ("SG", "2008", "Age Pension"),
                                 ("AU", "1979", "Old Age Living")):
            pg.evaluate("""(c) => { const s = document.getElementById('country');
              s.value = c; s.dispatchEvent(new Event('change', { bubbles: true })); }""", c)
            pg.wait_for_timeout(450)
            pg.evaluate("() => activateTab('gifting')")
            pg.wait_for_timeout(350)
            txt = pg.evaluate("() => document.getElementById('giftingCards').innerText")
            check(want in txt,
                  f"{c}: the gifting card does not give its own abolition date ({want}): "
                  f"{txt[:150]!r}")
            check(mustnot not in txt,
                  f"{c}: the gifting card carries another country's watch-out ({mustnot!r})")
            check(COUNTRY_NAMES[c] in txt,
                  f"{c}: the gifting card does not name the country")
        print("9b. the no-transfer-tax card gives each country its own history and watch-outs")

        # ---- 9c. the property tab admits whose law it is ------------------
        # The whole tab is UK law and was not gated, so a Singapore reader was
        # shown English stamp duty on a Singapore flat.
        for c, phrase in (("HK", "28 February 2024"), ("SG", "60%"), ("UK", None)):
            pg.evaluate("""(c) => { const s = document.getElementById('country');
              s.value = c; s.dispatchEvent(new Event('change', { bubbles: true })); }""", c)
            pg.wait_for_timeout(450)
            pg.evaluate("() => activateTab('property')")
            pg.wait_for_timeout(450)
            note = pg.evaluate("""() => { const n = document.getElementById('propCountryNote');
              return { hidden: n.hidden, text: n.innerText }; }""")
            if phrase is None:
                check(note["hidden"],
                      "the 'this is not your country's law' notice shows even in the UK")
            else:
                check(not note["hidden"],
                      f"{c}: the property tab shows UK stamp duty with no warning that the "
                      f"reader's country works differently")
                check(phrase in note["text"],
                      f"{c}: the notice does not carry the fact that matters ({phrase!r}): "
                      f"{note['text'][:160]!r}")
        print("9c. the property tab says whose law it is, and what is different in Hong Kong "
              "(all extra duties abolished 2024) and Singapore (60% ABSD)")

        # ---- 10. every tab renders, in both registers --------------------
        TABS = ["people", "savings", "salary", "projection", "planner", "tax",
                "gifting", "property", "relocate"]
        for c in ("HK", "SG"):
            pg.evaluate("""(c) => { const s = document.getElementById('country');
              s.value = c; s.dispatchEvent(new Event('change', { bubbles: true })); }""", c)
            pg.wait_for_timeout(500)
            for level in ("advanced", "simple"):
                pg.evaluate("(l) => { experienceLevel = l; applyLevel(); renderAll(); }", level)
                pg.wait_for_timeout(300)
                for t in (TABS if level == "advanced" else ["simple"]):
                    pg.evaluate("(t) => activateTab(t)", t)
                    pg.wait_for_timeout(120)
            pg.evaluate("() => { experienceLevel = 'advanced'; applyLevel(); }")
            # And the currency followed the country everywhere it is shown.
            cur = pg.evaluate("""() => {
              const t = document.getElementById('taxRegimeNote');
              return { cur: CUR(), regime: t ? t.innerText : '' }; }""")
            check(cur["cur"] == wired[c]["currency"],
                  f"{c}: the currency symbol is {cur['cur']}, not {wired[c]['currency']}")
            check("models" in cur["regime"].lower() and "only" in cur["regime"].lower(),
                  f"{c}: the Tax tab does not warn that it models only this country's tax, so a "
                  f"reader with a UK pension will take a nil bill at face value: {cur['regime'][:120]!r}")
        print("10. every tab renders in both registers for both countries, with the right currency "
              "and the treaty caveat on the Tax tab")

        ctx.close()
        b.close()

    if errors:
        failures.append("page errors: " + "; ".join(sorted(set(errors))[:4]))
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("\nHONG KONG AND SINGAPORE ARE MODELLED CORRECTLY, TREATY AND ALL")


if __name__ == "__main__":
    main()
