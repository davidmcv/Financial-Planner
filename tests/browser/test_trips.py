"""Long trips, without moving: the estimate, and the words used for it.

The Where to live page is about emigrating. This card is the alternative most
people actually take - go somewhere for a season and come home - so it has to
be costed against the same plan rather than described in the abstract.

Three things are worth guarding.

THE WORD. A Briton takes a long holiday, an American a vacation. The page uses
the reader's own word, and the French entry has to stay in English rather than
dropping French nouns into English sentences: "partir for a season" is not a
sentence in either language, and that is what the first version said.

THE DAY COUNT. Ninety days in any rolling 180 governs everything for a British
or American passport, and an EU citizen has no limit at all. A slider that
lets you pick twenty weeks has to say so.

THE ARITHMETIC. Two ways to get this flattering, both of which the first
version got wrong:

  * a campervan you OWN costs money in the ten months it sits on the drive.
    Charging insurance, tax, servicing and depreciation only for the weeks
    away made owning look like £421 a year - which is the arithmetic that
    sells campervans, not the arithmetic that pays for them.
  * going away is not all extra: the food and energy you would have used at
    home stop. Ignoring that overstates the cost of every option equally.
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

# Hong Kong and Singapore are both tropical, so the season people leave is
# the hot one. "Winter sun" is meaningless in one and backwards in the other.
TERMS = {"UK": "holiday", "US": "vacation", "AU": "holiday", "FR": "stay",
         "HK": "holiday", "SG": "holiday"}


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
          experienceLevel = 'advanced'; applyLevel(); activateTab('relocate'); renderAll(); }""")
        pg.wait_for_timeout(1400)

        def set_trip(weeks=None, style=None, transport=None, van=None):
            if weeks is not None:
                pg.evaluate("""(w) => { const e = document.getElementById('tripWeeks');
                  e.value = String(w); e.dispatchEvent(new Event('input', {bubbles:true})); }""", weeks)
            for eid, val in (("tripStyle", style), ("tripTransport", transport), ("tripVanMode", van)):
                if val is not None:
                    pg.evaluate("""(a) => { const e = document.getElementById(a.id);
                      e.value = a.v; e.dispatchEvent(new Event('change', {bubbles:true})); }""",
                                {"id": eid, "v": val})
            pg.wait_for_timeout(650)

        def est():
            return pg.evaluate("() => tripEstimate(lastModel)")

        # ---- 1. the reader's own word ---------------------------------------
        print("1. the word for it follows the country")
        for code, word in TERMS.items():
            pg.evaluate("""(c) => { const e = document.getElementById('country');
              e.value = c; e.dispatchEvent(new Event('change', {bubbles:true})); }""", code)
            pg.wait_for_timeout(750)
            title = pg.evaluate("() => document.getElementById('relocTripTitle').textContent")
            intro = pg.evaluate("() => document.getElementById('relocTripIntro').innerText")
            check(word in title.lower(), f"{code}: the title says {title!r}, expected the word {word!r}")
            # the sentence must be English throughout, not a translation salad
            for bad in ("partir for", "séjours, without"):
                check(bad not in (title + intro),
                      f"{code}: untranslated wording left in an English sentence: {bad!r}")
            print(f"   ok  {code} -> {title!r}")
        pg.evaluate("""() => { const e = document.getElementById('country');
          e.value = 'UK'; e.dispatchEvent(new Event('change', {bubbles:true})); }""")
        pg.wait_for_timeout(800)

        # ---- 2. the 90/180 rule is enforced in the wording -------------------
        set_trip(weeks=10)
        short = pg.evaluate("() => document.getElementById('tripWeeksHint').innerText")
        set_trip(weeks=20)
        long_ = pg.evaluate("() => document.getElementById('tripWeeksHint').innerText")
        check("inside the 90" in short, f"a 10-week trip is not described as inside the 90: {short!r}")
        check("over the 90" in long_, f"a 20-week trip is not flagged as over the 90 days: {long_!r}")
        check("140 days" in long_, f"the hint does not count the days: {long_!r}")
        print(f"2. 10 weeks reads as inside the 90; 20 weeks is flagged: {long_[:60]}...")

        # ---- 3. every option is costed, and they differ ---------------------
        set_trip(weeks=12, style="base")
        base = est()
        results = {"base": base["net"]}
        for t in ("plane", "train", "van"):
            set_trip(style="tour", transport=t, van="own")
            results[t] = est()["net"]
        check(len(set(round(v) for v in results.values())) == len(results),
              f"two options cost exactly the same, so one is not being read: {results}")
        for k, v in results.items():
            check(v > 0, f"{k} comes out at {v:,.0f} - a long trip cannot be free")
        check(results["base"] < results["plane"],
              f"staying in one place ({results['base']:,.0f}) should cost less than flying "
              f"between stops ({results['plane']:,.0f})")
        print("3. " + ", ".join(f"{k} £{v:,.0f}" for k, v in results.items()))

        # ---- 4. a van you own costs money all year --------------------------
        set_trip(weeks=12, style="tour", transport="van", van="own")
        own = est()
        check(own["yearRound"] > 0,
              "an owned campervan has no year-round cost - insurance, tax, servicing and "
              "depreciation do not pause while it sits on the drive")
        # and that cost must not scale with how long the trip is
        set_trip(weeks=4)
        shortTrip = est()
        set_trip(weeks=24)
        longTrip = est()
        check(abs(shortTrip["yearRound"] - longTrip["yearRound"]) < 1,
              f"the van's standing cost changes with trip length "
              f"({shortTrip['yearRound']:,.0f} vs {longTrip['yearRound']:,.0f}) - it should not")
        check(longTrip["gross"] > shortTrip["gross"],
              "a longer trip does not cost more")
        # hiring has no year-round cost
        set_trip(weeks=12, van="hire")
        hire = est()
        check(hire["yearRound"] == 0, f"hiring a van has a year-round cost of {hire['yearRound']:,.0f}")
        print(f"4. owning: £{own['yearRound']:,.0f} a year regardless of the trip; hiring: £0")

        # ---- 5. what you stop spending at home is netted off ----------------
        set_trip(weeks=12, style="base")
        e = est()
        check(e["saved"] > 0, "nothing is saved at home while away - the whole trip is treated as extra")
        check(abs(e["net"] - (e["gross"] - e["saved"])) < 1,
              f"the net cost is not gross minus what you save: {e['net']:,.0f} vs "
              f"{e['gross'] - e['saved']:,.0f}")
        check(e["saved"] < e["homeYear"],
              "more is saved at home than the plan says you spend in a whole year")
        print(f"5. £{e['gross']:,.0f} away less £{e['saved']:,.0f} not spent at home = £{e['net']:,.0f} net")

        # ---- 6. it is measured against this plan, not a generic one ---------
        # The target can come from the living-standard band or from a typed
        # figure, so this checks the card takes whichever the plan is using
        # rather than assuming which control drives it.
        e6 = est()
        planTarget = pg.evaluate("""() => lastModel.rlsTarget || (lastModel.inp && lastModel.inp.retireSpend) || 0""")
        check(abs(e6["homeYear"] - planTarget) < 1,
              f"the card uses {e6['homeYear']:,.0f} as your yearly spending, but the plan says "
              f"{planTarget:,.0f}")
        check(planTarget > 0 and abs(e6["shareOfIncome"] - e6["net"] / planTarget) < 1e-6,
              "the share of income is not the net cost over the plan's own target")
        # ...and the household size, which the plan also decides, must reach it
        couple = est()
        pg.evaluate("""() => { const s = document.getElementById('spouseSwitch');
          if (s && s.classList.contains('on')) s.click(); }""")
        pg.wait_for_timeout(1100)
        single = est()
        check(single["couple"] is False,
              "turning the spouse off did not reach the trip estimate")
        check(single["perMonth"] < couple["perMonth"],
              f"one person costs the same as two ({single['perMonth']:,.0f} vs "
              f"{couple['perMonth']:,.0f}) - the household size is not being read")
        print(f"6. reads the plan: £{planTarget:,.0f} target, and one person "
              f"(£{single['perMonth']:,.0f}/mo) costs less than two (£{couple['perMonth']:,.0f}/mo)")

        # ---- 7. drawn icons, not emoji --------------------------------------
        # The same fault as the flags: an emoji here renders as a small
        # monochrome symbol on Windows beside colour ones.
        icons = pg.evaluate("""() => {
          const heads = [...document.querySelectorAll('#relocTripDetail .taxopt-head h4')];
          return { count: heads.length,
                   drawn: heads.filter(h => h.querySelector('svg.ic')).length,
                   emoji: heads.filter(h => /[\\u2190-\\u2BFF\\uD800-\\uDFFF]/.test(h.textContent)).length }; }""")
        check(icons["count"] == 3, f"expected three ways to travel, found {icons['count']}")
        check(icons["drawn"] == icons["count"],
              f"only {icons['drawn']} of {icons['count']} travel icons are drawn")
        check(icons["emoji"] == 0, f"{icons['emoji']} travel headings still contain emoji")
        print(f"3 travel options, all with drawn icons and no emoji")

        b.close()

    if errors:
        failures.append("console/page errors: " + "; ".join(sorted(set(errors))[:5]))
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("\nLONG TRIPS ARE COSTED AGAINST THE PLAN")


if __name__ == "__main__":
    main()
