"""The Savings page: what belongs on it, and whether its four read-outs add up.

Savings, investments, Premium Bonds and property moved off the Pensions page
onto a page of their own; only pensions were left behind. Four new sections
came with the move - an emergency fund, an ISA allowance tracker, debts, and
Premium Bonds held apart from ordinary savings - and each of them states a
number, so each of them can be wrong.
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
errors = []


def money(text):
    import re
    m = re.search(r"£\s*([\d,]+(?:\.\d+)?)", text)
    return float(m.group(1).replace(",", "")) if m else None


with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME)
    pg = b.new_context(viewport={"width": 1500, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
    pg.goto(FILE)
    pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
    pg.evaluate("() => { experienceLevel = 'advanced'; applyLevel(); renderAll(); }")
    pg.wait_for_timeout(1000)

    # 1. The pages hold what they say they hold.
    where = pg.evaluate("""() => { const panel = id => { const el = document.getElementById(id);
        const s = el && el.closest('.panel'); return s ? s.id : null; };
      return { savings: panel('savingsList_you'), property: panel('propertyList_you'),
               shares: panel('shareList_you'), bonds: panel('premiumBonds'),
               pensions: panel('employerPensionList_you'), pot: panel('yourPot'),
               contrib: panel('yourEmployerRate'), summary: panel('assetsSummary'),
               debts: panel('debtList'), isa: panel('isaAllowance'),
               emergency: panel('emergencyOn') }; }""")
    for k in ["savings", "property", "shares", "bonds", "debts", "isa", "emergency", "summary"]:
        assert where[k] == "tab-savings", (k, where[k])
    for k in ["pensions", "pot", "contrib"]:
        assert where[k] == "tab-salary", (k, where[k])
    print("1. savings, shares, bonds, property, debts, ISAs and the summary are on Savings; "
          "the pot, its contributions and employer pensions stayed on Pensions")

    # 2. The tab is named Pensions now, and Savings sits between People and it.
    tabs = pg.evaluate("""() => [...document.querySelectorAll('.rail .tab-btn')]
      .map(b => ({ tab: b.dataset.tab, text: b.textContent.trim() }))""")
    # the labels carry an emoji, so match on the words rather than equality
    names = [t["text"] for t in tabs]
    order = [t["tab"] for t in tabs]
    assert not any("Paying In" in n for n in names), names
    assert any("Pensions" in n for n in names) and any("Savings" in n for n in names), names
    assert order.index("savings") == order.index("people") + 1, order
    assert order.index("salary") == order.index("savings") + 1, order
    print(f"2. tabs read: {' / '.join(names)}")

    pg.evaluate("() => activateTab('savings')")
    pg.wait_for_timeout(800)

    # 3. Premium Bonds pay their prize rate, tax-free, and count as cash you
    #    could actually spend - so they lift the liquid total.
    liquidBefore = pg.evaluate("() => lastModel.assetTotals.cash")
    pg.evaluate("""() => { els('premiumBonds').value = '30,000';
      els('premiumBonds').dispatchEvent(new Event('input', { bubbles: true })); }""")
    pg.wait_for_timeout(700)
    after = pg.evaluate("""() => ({ cash: lastModel.assetTotals.cash,
      yield: els('premiumBondsYield').textContent,
      rate: parseFloat(els('premiumBondsRate').value) })""")
    assert abs((after["cash"] - liquidBefore) - 30000) < 1, (liquidBefore, after)
    assert abs(money(after["yield"]) - 30000 * after["rate"] / 100) < 1, after
    print(f"3. £30,000 of Premium Bonds: cash up by £30,000, "
          f"{after['rate']}% prize rate = {after['yield'].strip()} tax-free")

    # 4. The emergency fund is measured in MONTHS OF SPENDING, and its target
    #    moves with both the months and the spending.
    pg.evaluate("""() => { els('emergencyOn').checked = true;
      els('emergencyOn').dispatchEvent(new Event('change', { bubbles: true })); }""")
    pg.wait_for_timeout(700)
    seen = {}
    for months in [3, 6, 12]:
        pg.evaluate("""(m) => { els('emergencyMonths').value = String(m);
          els('emergencyMonths').dispatchEvent(new Event('input', { bubbles: true })); }""", months)
        pg.wait_for_timeout(600)
        seen[months] = pg.evaluate("""() => ({ target: els('emergencyTarget').textContent,
          cover: els('emergencyCover').textContent,
          spend: lastModel.rlsTarget || lastModel.inp.retireSpend,
          cash: lastModel.assetTotals.cash + (lastModel.assetTotalsSpouse ? lastModel.assetTotalsSpouse.cash : 0) })""")
        s = seen[months]
        assert abs(money(s["target"]) - s["spend"] / 12 * months) < 2, (months, s)
    # cover is the same in every case - it's what you hold, not what you want
    covers = {round(float(v["cover"].split()[0]), 1) for v in seen.values()}
    assert len(covers) == 1, seen
    exp = seen[6]["cash"] / (seen[6]["spend"] / 12)
    assert abs(list(covers)[0] - exp) < 0.15, (covers, exp)
    print(f"4. emergency fund: 3/6/12 months = {', '.join(seen[m]['target'] for m in [3, 6, 12])}; "
          f"cover {list(covers)[0]} months either way")

    # 5. The ISA allowance is £20,000 across ALL ISAs, per person, and going
    #    over it is called out rather than quietly capped.
    pg.evaluate("""() => { els('isaPaidYou').value = '8,000';
      els('isaPaidYou').dispatchEvent(new Event('input', { bubbles: true }));
      els('stratIsaOn').checked = false;
      els('stratIsaOn').dispatchEvent(new Event('change', { bubbles: true })); }""")
    pg.wait_for_timeout(800)
    isa = pg.evaluate("() => els('isaAllowance').textContent")
    assert "£8,000" in isa and "£12,000" in isa, isa
    pg.evaluate("""() => { els('isaPaidYou').value = '25,000';
      els('isaPaidYou').dispatchEvent(new Event('input', { bubbles: true })); }""")
    pg.wait_for_timeout(700)
    over = pg.evaluate("() => els('isaAllowance').textContent")
    assert "over the" in over and "£5,000" in over, over
    assert "£0" in over, "allowance left should be nil once you are over"
    print("5. ISA tracker: £8,000 in leaves £12,000; £25,000 in is flagged as £5,000 over")
    pg.evaluate("""() => { els('isaPaidYou').value = '0';
      els('isaPaidYou').dispatchEvent(new Event('input', { bubbles: true })); }""")
    pg.wait_for_timeout(500)

    # 6. Debts come off net worth, and the verdict compares each rate with the
    #    growth rate you assume - the only comparison that decides the question.
    pg.evaluate("() => { const b = document.querySelector('.add-btn[data-add=debts]'); b.click(); }")
    pg.wait_for_timeout(700)

    def set_debt(balance, rate):
        pg.evaluate("""([bal, r]) => { const row = document.querySelector('#debtList .asset-row');
          const b = row.querySelector('[data-field=balance]'); b.value = bal;
          b.dispatchEvent(new Event('change', { bubbles: true }));
          const p = row.querySelector('[data-field=ratePct]'); p.value = r;
          p.dispatchEvent(new Event('change', { bubbles: true })); }""", [balance, rate])
        pg.wait_for_timeout(700)

    pg.evaluate("""() => { els('yourPotGrowth').value = '5';
      els('yourPotGrowth').dispatchEvent(new Event('input', { bubbles: true })); }""")
    pg.wait_for_timeout(600)
    set_debt("100,000", "3")
    cheap = pg.evaluate("() => els('debtVerdict').textContent")
    assert "less than" in cheap and "safer choice" in cheap, cheap
    set_debt("100,000", "9")
    dear = pg.evaluate("() => els('debtVerdict').textContent")
    assert "charges more than" in dear, dear
    # 9% on £100,000 against 5% hoped-for = £4,000 a year of certain gain
    assert money(dear.split("worth about")[1]) == 4000, dear
    net = pg.evaluate("() => els('assetsSummary').textContent")
    assert "Net worth" in net and "£100,000" in net, net[:200]
    print("6. debts: 3% is 'safer not richer'; 9% against 5% growth is worth £4,000/yr to clear, "
          "and £100,000 comes off net worth")

    # 7. Nothing here disturbed the plan itself: a debt is counted against net
    #    worth but is NOT quietly deducted from retirement funding twice.
    before = pg.evaluate("() => lastModel.assetTotals.cash + lastModel.assetTotals.shares")
    set_debt("400,000", "9")
    after2 = pg.evaluate("() => lastModel.assetTotals.cash + lastModel.assetTotals.shares")
    assert before == after2, (before, after2)
    print("7. adding £400,000 of debt did not silently change what funds the plan")

    # 8. It all survives being saved and re-loaded.
    trip = pg.evaluate("""() => { const d = collectProfileData();
      const copy = JSON.parse(JSON.stringify(d));
      els('emergencyOn').checked = false; els('premiumBonds').value = '0';
      assets.you.debts = [];
      applyProfileData(copy);
      return { emergency: els('emergencyOn').checked, months: els('emergencyMonths').value,
               bonds: els('premiumBonds').value, debts: (assets.you.debts || []).length }; }""")
    pg.wait_for_timeout(700)
    assert trip["emergency"] is True and trip["bonds"] == "30,000" and trip["debts"] == 1, trip
    print(f"8. saved and reloaded intact: {trip}")

    if errors:
        raise SystemExit("CONSOLE/PAGE ERRORS:\n" + "\n".join(errors[:10]))
    print("\nALL SAVINGS PAGE TESTS PASSED, no console/page errors")
    b.close()
