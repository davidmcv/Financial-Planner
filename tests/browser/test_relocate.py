"""The Where to live page: the ranking has to come from the plan's numbers.

A country comparison is the easiest page in an app like this to fake. A table
of countries with plausible percentages beside them looks authoritative and
can be completely disconnected from the user - and nobody would notice,
because nobody knows what their tax would be in Italy. That is exactly why it
needs a test.

So this checks the page is computed, not written down:

  * the income being compared comes from the plan, and changing it re-ranks
  * every country's tax responds to the income and to household size
  * the special regimes actually reduce the bill and are labelled as
    conditional rather than presented as the standard rate
  * personal allowances are applied - banding a pension from the first pound
    made Spain look like a 29% jurisdiction on a middling income
  * a couple pays less than one person on the same total, everywhere
  * the countries the user asked for are all present
  * the honest parts survive: the health warning, the no-retirement-visa
    verdicts, and the fact that leaving the UK gives up the 25% tax-free
    quarter
"""
import os
import pathlib
import re

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

WANT = ["United Kingdom", "Italy", "Spain", "Canada", "United States", "France", "Australia"]
NO_VISA = ["Canada", "United States", "Australia"]


def money(s):
    m = re.search(r"[\d,]+", s.replace("−", "-"))
    return float(m.group(0).replace(",", "")) if m else None


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
          experienceLevel = 'advanced'; applyLevel(); activateTab('relocate'); renderAll(); }""")
        pg.wait_for_timeout(1400)

        def rank():
            return pg.evaluate("""() => relocRank(lastModel).rows.map(r => ({
              code: r.code, name: r.c.name, tax: r.tax, plain: r.plain,
              regime: r.usesRegime, net: r.net, vsHome: r.vsHome }))""")

        # ---- 1. every requested country is on the page ----------------------
        rows = rank()
        names = [r["name"] for r in rows]
        for w in WANT:
            check(w in names, f"{w} is missing from the comparison")
        print(f"1. {len(names)} countries: {', '.join(names)}")

        # ---- 2. the income comes from the plan ------------------------------
        shown = pg.evaluate("() => document.getElementById('relocIncome').value")
        from_plan = pg.evaluate("() => Math.round(relocBaseIncome(lastModel))")
        check(money(shown) == from_plan,
              f"the income box shows {shown} but the plan says {from_plan:,}")
        check(from_plan > 0, "the plan produced no retirement income to compare")
        print(f"2. comparing {shown} a year, taken from the plan")

        # ---- 3. changing the income re-ranks --------------------------------
        pg.evaluate("""() => { const e = document.getElementById('relocIncome');
          e.value = '150,000'; e.dispatchEvent(new Event('input', {bubbles:true})); }""")
        pg.wait_for_timeout(600)
        big = {r["name"]: r["tax"] for r in rank()}
        pg.evaluate("""() => { const e = document.getElementById('relocIncome');
          e.value = '25,000'; e.dispatchEvent(new Event('input', {bubbles:true})); }""")
        pg.wait_for_timeout(600)
        small = {r["name"]: r["tax"] for r in rank()}
        flat = [n for n in big if big[n] <= small[n] + 1]
        check(not flat, f"tax did not rise with income in: {', '.join(flat)} - these are not computed")
        print(f"3. every country's tax rises with income "
              f"(£25k -> £150k, e.g. Spain {small['Spain']:,.0f} -> {big['Spain']:,.0f})")

        # ---- 4. personal allowances are applied -----------------------------
        # On a modest income nobody should be paying their top marginal rate
        # from the first pound. Spain from the first euro was 29%; with the
        # personal minimum it is far lower.
        pg.evaluate("""() => { const e = document.getElementById('relocIncome');
          e.value = '25,000'; e.dispatchEvent(new Event('input', {bubbles:true})); }""")
        pg.wait_for_timeout(500)
        for r in rank():
            rate = r["tax"] / 25000
            check(rate < 0.25,
                  f"{r['name']} charges {rate:.0%} on a £25,000 household income - "
                  f"personal allowances are not being applied")
        print("4. on £25,000 every country's effective rate is under 25% - allowances applied")

        # ---- 5. a couple pays less than one person --------------------------
        for people in ("1", "2"):
            pg.evaluate("""(v) => { const e = document.getElementById('relocPeople');
              e.value = v; e.dispatchEvent(new Event('change', {bubbles:true})); }""", people)
            pg.wait_for_timeout(500)
            if people == "1":
                single = {r["name"]: r["tax"] for r in rank()}
            else:
                couple = {r["name"]: r["tax"] for r in rank()}
        worse = [n for n in single if couple[n] > single[n] + 1]
        check(not worse, f"a couple pays MORE than one person on the same income in: {', '.join(worse)}")
        print(f"5. splitting the same income across two people always costs less or the same")

        # ---- 6. special regimes reduce the bill and say they are conditional -
        it = next(r for r in rank() if r["name"] == "Italy")
        check(it["regime"], "Italy is not being shown on its 7% regime")
        check(it["tax"] < it["plain"] - 1,
              f"Italy's 7% regime ({it['tax']:,.0f}) is not cheaper than ordinary rates ({it['plain']:,.0f})")
        summary = pg.evaluate("() => document.getElementById('relocSummary').innerText")
        table = pg.evaluate("() => document.getElementById('relocTable').innerText")
        check("conditions" in summary or "conditions" in table or "flat tax" in table,
              "the 7% regime is presented without saying it is conditional")
        print(f"6. Italy shown at {it['tax']:,.0f} on the 7% regime vs {it['plain']:,.0f} ordinary, flagged as conditional")

        # ---- 7. the awkward facts are still on the page ---------------------
        page = pg.evaluate("() => document.getElementById('tab-relocate').innerText")
        for phrase, why in [
            ("not as the answer", "the health warning about this being a shortlist, not advice"),
            ("No retirement visa", "the no-retirement-visa verdict"),
            ("25% tax-free", "the point that leaving the UK gives up the tax-free quarter"),
            ("90 days", "the Schengen 90/180 limit on wintering abroad"),
            ("government service pension", "the government-pension exception"),
        ]:
            check(phrase.lower() in page.lower(), f"the page no longer states {why}")
        print("7. warnings intact: shortlist-not-advice, no retirement visa, the 25% quarter, 90/180, government pensions")

        # ---- 8. picking a country changes the detail ------------------------
        seen = {}
        for code in ("IT", "ES", "CA", "US"):
            pg.evaluate("""(c) => { const b = document.querySelector(`[data-reloc="${c}"]`); if (b) b.click(); }""", code)
            pg.wait_for_timeout(500)
            seen[code] = pg.evaluate("() => document.getElementById('relocDetail').innerText")[:400]
        check(len(set(seen.values())) == len(seen), "the country detail does not change when you pick a different one")
        for code, txt in seen.items():
            check(len(txt) > 200, f"{code}: the detail panel is nearly empty")
        print(f"8. all {len(seen)} country panels render distinct content")

        b.close()

    if errors:
        failures.append("console/page errors: " + "; ".join(sorted(set(errors))[:5]))
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("\nWHERE TO LIVE IS COMPUTED FROM THE PLAN")


if __name__ == "__main__":
    main()
