"""Property investment: the tax has to be right, and the company has to be
compared honestly.

This is the page most capable of flattering somebody into a bad decision, in
three specific ways, and each has a test here.

SECTION 24. An individual landlord is taxed on rent BEFORE mortgage interest
and gets a 20% credit back. That is the whole reason the company question
exists, and it produces the result that matters: a higher-rate landlord can
pay tax on a property that loses money. If the model ever starts deducting
interest for an individual, the page becomes a sales brochure.

TAXED TWICE. A company pays corporation tax going in and dividend tax coming
out. Comparing corporation tax against income tax and stopping there is the
commonest error in the subject and it makes companies look far better than
they are. Both must be charged, and the page must show the answer with the
money drawn AND left in, because those are genuinely different positions.

NO BUSINESS PROPERTY RELIEF. Property investment companies do not qualify -
the relief excludes businesses that wholly or mainly hold investments. A page
that implied a company dodges inheritance tax would be worse than useless.

The arithmetic is checked against figures worked by hand rather than against
the app's own output, which would only prove it is consistent with itself.
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

# price -> SDLT on an ADDITIONAL dwelling, worked by hand from the 2026/27
# bands (0/125k, 2%/125-250k, 5%/250-925k, 10%/925k-1.5m, 12% above) plus the
# 5% surcharge on the whole price.
SDLT = {
    150000: 500 + 7500,            # 2% on 25k, 5% on 150k
    220000: 1900 + 11000,
    250000: 2500 + 12500,
    500000: 15000 + 25000,
    1000000: 30000 + 50000 + 13750,  # bands to 925k, then 10%, + 5% surcharge
}
# profit -> corporation tax, with marginal relief between 50k and 250k
CT = {
    20000: 20000 * 0.19,
    50000: 50000 * 0.19,
    100000: 100000 * 0.25 - (250000 - 100000) * 3 / 200,
    250000: 250000 * 0.25,
    400000: 400000 * 0.25,
}


def main():
    errors, failures = [], []

    def check(cond, msg):
        if not cond:
            failures.append(msg)
        return cond

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        pg = b.new_context(viewport={"width": 1400, "height": 1100}).new_page()
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(FILE)
        pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
        pg.evaluate("""() => { localStorage.setItem('pensionPlanner.rememberChoice','advanced');
          experienceLevel = 'advanced'; applyLevel(); activateTab('property'); renderAll(); }""")
        pg.wait_for_timeout(1400)

        def setf(id_, val):
            pg.evaluate("""(a) => { const e = document.getElementById(a.id);
              e.value = a.v;
              e.dispatchEvent(new Event('input', {bubbles:true}));
              e.dispatchEvent(new Event('change', {bubbles:true})); }""", {"id": id_, "v": str(val)})

        def model(**over):
            return pg.evaluate("""(o) => {
              const i = Object.assign(propInputs(), o);
              return { me: propertyModel(Object.assign({}, i, {viaCompany:false})),
                       co: propertyModel(Object.assign({}, i, {viaCompany:true})) }; }""", over)

        # ---- 1. stamp duty, including the surcharge on the whole price ------
        print("1. stamp duty on an additional dwelling")
        for price, want in SDLT.items():
            got = pg.evaluate("(v) => sdltOnPurchase(v, false).total", price)
            check(abs(got - want) < 1,
                  f"SDLT on £{price:,}: app says £{got:,.0f}, hand calculation says £{want:,.0f}")
            print(f"   ok  £{price:>9,} -> £{got:>8,.0f}")
        # the surcharge is not a band: it applies below the nil-rate threshold too
        low = pg.evaluate("() => sdltOnPurchase(100000, false)")
        check(abs(low["base"]) < 1 and abs(low["surcharge"] - 5000) < 1,
              f"on a £100,000 purchase the surcharge should still be £5,000: {low}")
        print(f"   ok  the surcharge applies below the nil-rate band too (£100,000 -> £5,000)")

        # ---- 2. corporation tax, with marginal relief -----------------------
        print("2. corporation tax")
        for profit, want in CT.items():
            got = pg.evaluate("(v) => corporationTax(v)", profit)
            check(abs(got - want) < 1,
                  f"CT on £{profit:,}: app says £{got:,.0f}, expected £{want:,.0f}")
        mid = pg.evaluate("() => corporationTax(150000) / 150000")
        check(0.19 < mid < 0.25, f"the marginal-relief band should sit between 19% and 25%, got {mid:.1%}")
        print(f"   ok  19% to £50k, 25% above £250k, {mid:.1%} effective at £150k")

        # ---- 3. Section 24: interest is NOT deducted for an individual ------
        # The test that matters most. Raise the mortgage rate: an individual's
        # taxable profit must not move, because interest is not an expense to
        # them. A company's must fall.
        base = model(rate=3)
        dear = model(rate=8)
        check(abs(base["me"]["operating"] - dear["me"]["operating"]) < 1,
              "an individual's taxable profit changed when the mortgage rate did - "
              "interest is being deducted, which Section 24 forbids")
        check(dear["co"]["coProfit"] < base["co"]["coProfit"] - 1,
              "a company's taxable profit did not fall when interest rose - "
              "the company is not deducting interest, which it may")
        print(f"3. Section 24 holds: at 3% and 8% the individual is taxed on the same "
              f"£{base['me']['operating']:,.0f}; the company on "
              f"£{base['co']['coProfit']:,.0f} then £{dear['co']['coProfit']:,.0f}")

        # ...and the consequence people need to see: tax on a loss
        loss = model(rate=9, band="higher")
        check(loss["me"]["cashflowYear"] < 0,
              "the 9% case should be cash-flow negative, or this proves nothing")
        check(loss["me"]["personalTax"] > 0,
              "a higher-rate landlord losing money should still owe tax under Section 24 - "
              "the model is not reproducing the effect the page exists to explain")
        print(f"   at 9% the property loses £{abs(loss['me']['cashflowYear']):,.0f} a year "
              f"and still owes £{loss['me']['personalTax']:,.0f} of tax")

        # ---- 4. a company is taxed twice ------------------------------------
        m = model(rate=4, band="higher")
        co = m["co"]
        check(co["coTax"] > 0, "no corporation tax charged on a profitable company")
        check(co["divTax"] > 0, "no dividend tax charged on taking the profit out")
        check(co["coNetIfDrawn"] < co["coNetIfKept"] - 1,
              f"taking the money out of the company costs nothing: drawn "
              f"{co['coNetIfDrawn']:,.0f} vs kept {co['coNetIfKept']:,.0f}")
        # and the page has to show both, not just the flattering one
        text = pg.evaluate("() => document.getElementById('propCompare').innerText")
        check("dividend tax" in text.lower(),
              "the comparison does not mention dividend tax, so the company looks better than it is")
        check("left inside the company" in text.lower() or "leave the money in it" in text.lower(),
              "the page does not distinguish drawing the profit from leaving it in the company")
        print(f"4. company taxed twice: £{co['coTax']:,.0f} corporation tax then "
              f"£{co['divTax']:,.0f} dividend tax; both shown")

        # ---- 5. basic rate should NOT be pushed towards a company -----------
        # The 20% credit gives a basic-rate landlord back what Section 24 took,
        # so the structural advantage nearly vanishes. If the page recommends a
        # company to a basic-rate taxpayer, something is wrong.
        basic = model(band="basic", rate=5.25)
        higher = model(band="higher", rate=5.25)
        gapB = basic["co"]["coNetIfDrawn"] - basic["me"]["personalNet"]
        gapH = higher["co"]["coNetIfDrawn"] - higher["me"]["personalNet"]
        check(gapH > gapB,
              f"the company advantage should grow with the tax rate: basic £{gapB:,.0f} "
              f"vs higher £{gapH:,.0f}")
        print(f"5. company advantage grows with the band: £{gapB:,.0f} at basic, £{gapH:,.0f} at higher")

        # ---- 6. the lender's test, not the optimist's ------------------------
        tight = model(rent=400)
        check(not tight["me"]["passesStress"],
              "a property with £400 of rent against this mortgage should fail the lender's cover test")
        check(tight["me"]["rentNeeded"] > 400,
              "the rent the lender needs is not being computed")
        rich = model(rent=4000)
        check(rich["me"]["passesStress"], "£4,000 of rent should comfortably pass")
        check(rich["me"]["maxLoan"] > tight["me"]["maxLoan"],
              "the maximum loan does not respond to the rent")
        print(f"6. lender test: needs £{tight['me']['rentNeeded']:,.0f}/mo here; "
              f"£400 fails, £4,000 passes")

        # ---- 7. selling: a company has no CGT allowance and is taxed twice --
        sale = model(holdYears=15, growthPct=4)
        check(sale["me"]["cgtPersonal"] > 0, "no CGT on a gain held personally")
        check(sale["co"]["coGainOut"] > 0,
              "getting a company's sale proceeds out costs nothing - dividend tax is missing")
        check(sale["me"]["netSalePersonal"] > sale["co"]["netSaleCompany"],
              f"selling through a company should net less than selling personally on these figures: "
              f"{sale['me']['netSalePersonal']:,.0f} vs {sale['co']['netSaleCompany']:,.0f}")
        sellText = pg.evaluate("() => document.getElementById('propSell').innerText")
        check("60 days" in sellText, "the 60-day CGT reporting deadline is not mentioned")
        print(f"7. selling: £{sale['me']['netSalePersonal']:,.0f} personally vs "
              f"£{sale['co']['netSaleCompany']:,.0f} through a company")

        # ---- 8. inheritance: no Business Property Relief --------------------
        iht = pg.evaluate("() => document.getElementById('propIht').innerText")
        check("business property relief" in iht.lower(),
              "the inheritance section does not mention Business Property Relief at all")
        check("not an inheritance tax shelter" in iht.lower() or "does not qualify" in iht.lower()
              or "excludes" in iht.lower(),
              "the page does not say a property company fails to get Business Property Relief")
        check("gift with reservation" in iht.lower(),
              "the page does not warn about giving a property away while still taking the rent")
        check("40%" in iht, "the inheritance tax rate is not stated")
        print("8. inheritance: BPR unavailable, gift-with-reservation warned, 40% stated")

        # ---- 9. the portfolio adds up ---------------------------------------
        pg.evaluate("() => { propPortfolio = []; renderPropPortfolio(); }")
        for price, rent in ((180000, 1250), (260000, 1500), (120000, 800)):
            setf("propPrice", price)
            setf("propRent", rent)
            pg.wait_for_timeout(350)
            pg.evaluate("() => document.getElementById('propAddBtn').click()")
            pg.wait_for_timeout(250)
        agg = pg.evaluate("""() => {
          const rows = propPortfolio.map(p => propertyModel(Object.assign({}, p, {viaCompany:false})));
          return { n: propPortfolio.length,
                   value: rows.reduce((t, r) => t + r.price, 0),
                   loans: rows.reduce((t, r) => t + r.loan, 0) }; }""")
        check(agg["n"] == 3, f"expected three properties in the portfolio, got {agg['n']}")
        check(abs(agg["value"] - 560000) < 1, f"portfolio value should be £560,000, got {agg['value']:,.0f}")
        shown = pg.evaluate("() => document.getElementById('propPortfolio').innerText")
        check("560,000" in shown, f"the portfolio total is not on the page: {shown[:120]!r}")
        check(shown.count("remove") == 3, "each property should be removable")
        # ten is the stated limit
        pg.evaluate("""() => { for (let i = 0; i < 20; i++) document.getElementById('propAddBtn').click(); }""")
        pg.wait_for_timeout(400)
        n = pg.evaluate("() => propPortfolio.length")
        check(n == 10, f"the portfolio should cap at ten, got {n}")
        print(f"9. portfolio: three properties totalling £{agg['value']:,.0f}, capped at ten")

        # ---- 10. the caveats that stop this being a brochure ----------------
        page = pg.evaluate("() => document.getElementById('tab-property').innerText").lower()
        for phrase, why in [
            ("scotland", "that Scotland and Wales have different property taxes"),
            ("personal guarantee", "that a company mortgage still needs a personal guarantee"),
            ("already own", "that moving an owned property into a company triggers SDLT and CGT"),
            ("higher", "that company mortgage rates are higher"),
        ]:
            check(phrase in page, f"the page does not warn {why}")
        print("10. warnings intact: Scotland/Wales, personal guarantee, incorporating an owned property, rates")

        b.close()

    if errors:
        failures.append("console/page errors: " + "; ".join(sorted(set(errors))[:5]))
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("\nPROPERTY TAX MODELLED CORRECTLY, COMPANY COMPARED HONESTLY")


if __name__ == "__main__":
    main()
