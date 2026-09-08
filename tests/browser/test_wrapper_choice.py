"""ISA, your pension, or your partner's - the arithmetic, held to account.

The question that prompted this page was "I didn't think I could get 40%
relief on a pension but I think my wife can?" - and the answer is arithmetic,
not opinion, so it can be tested exactly rather than eyeballed.

Put £1 of gross pay into a pension. It costs (1 - r) of take-home, where r is
the relief on THAT SLICE of pay. It comes back as (1 - w), where w is the tax
on £1 of withdrawal - three quarters of the retirement marginal rate, because
a quarter of every withdrawal is tax-free. So:

    pension, per £1 of take-home:   (1 - w) / (1 - r)
    ISA, per £1 of take-home:       1

Everything below follows from that, and each case is one a real person hits:

    £30,000   basic rate, 20% relief             pension still wins
    £90,000   higher rate, 40% relief            pension wins by a lot
    £110,000  the 60% band, allowance withdrawn  pension wins by a very lot
    £8,000    under the personal allowance       20% relief at source anyway

The last is the one that surprises people and the easiest to get wrong in
code: relief at source pays 20% whether or not the contributor pays any tax.

The partner comparison is the point of the whole page: relief is personal, so
the same £1,000 buys different amounts in each of two pensions. If this test
ever reports the same relief rate for two people on very different salaries,
the page is reading household income somewhere it should be reading one
person's.
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

# salary -> the relief rate on the top £1,000 of it (England/Wales/NI)
EXPECTED_RELIEF = {
    8000: 0.20,     # no tax due, but relief at source still pays 20%
    30000: 0.20,    # basic rate
    90000: 0.40,    # higher rate
    110000: 0.60,   # personal allowance withdrawn: the 60% band
}


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
          experienceLevel = 'advanced'; applyLevel(); activateTab('tax'); renderAll(); }""")
        pg.wait_for_timeout(1200)

        def set_salaries(you, spouse):
            pg.evaluate("""(v) => {
              const a = document.getElementById('yourSalary');
              a.value = String(v[0]); a.dispatchEvent(new Event('change', {bubbles:true}));
              const s = document.getElementById('spouseSalary');
              if (s) { s.value = String(v[1]); s.dispatchEvent(new Event('change', {bubbles:true})); }
            }""", [you, spouse])
            pg.wait_for_timeout(800)

        # Read the rendered numbers rather than the internals, which also
        # proves the panel shows what it computed.
        def panel():
            return pg.evaluate("() => document.getElementById('wrapperChoice').innerText")

        # ---- 1. relief follows the slice of pay, per person ------------------
        print("1. relief on the next £1,000, by salary")
        for salary, want in EXPECTED_RELIEF.items():
            set_salaries(salary, 25000)
            got = pg.evaluate("""() => {
              const t = document.getElementById('wrapperChoice').innerText;
              const m = t.match(/RELIEF ON THE NEXT £1,000\\s*\\n\\s*([\\d.]+)%/);
              return m ? +m[1] / 100 : null; }""")
            if not check(got is not None, f"£{salary:,}: no relief figure on the page"):
                continue
            check(abs(got - want) < 0.005,
                  f"£{salary:,}: relief shown as {got:.0%}, expected {want:.0%}")
            print(f"   ok  £{salary:>7,} -> {got:.0%}")

        # ---- 2. the two people are measured separately ----------------------
        set_salaries(30000, 110000)
        rates = pg.evaluate("""() => [...document.getElementById('wrapperChoice')
          .innerText.matchAll(/RELIEF ON THE NEXT £1,000\\s*\\n\\s*([\\d.]+)%/g)].map(m => +m[1] / 100)""")
        check(len(rates) == 2, f"expected two people's relief rates, got {rates}")
        if len(rates) == 2:
            check(abs(rates[0] - 0.20) < 0.005 and abs(rates[1] - 0.60) < 0.005,
                  f"on £30,000 / £110,000 the rates should be 20% and 60%, got {rates}")
            check(rates[0] != rates[1],
                  "both people show the same relief rate - household income is being used "
                  "somewhere one person's should be")
        text = panel()
        check("Relief is personal" in text,
              "the page does not explain that relief is personal when the two rates differ")
        check("cannot get 40% relief" in text,
              "on £30,000 vs £110,000 the page does not say which of them cannot get 40% relief")
        print(f"2. £30,000 and £110,000 -> {rates[0]:.0%} and {rates[1]:.0%}, difference explained")

        # ---- 3. the pension still beats an ISA at basic rate -----------------
        # 20% in, 15% out (three quarters of 20%) - the case people get wrong.
        set_salaries(30000, 30000)
        vals = pg.evaluate("""() => [...document.getElementById('wrapperChoice')
          .innerText.matchAll(/WORTH, AFTER TAX\\s*\\n\\s*£([\\d,]+)/g)].map(m => +m[1].replace(/,/g, ''))""")
        check(vals and all(v > 1000 for v in vals),
              f"at basic rate the pension should still beat an ISA's £1,000, got {vals}")
        check(vals and abs(vals[0] - 1062.5) < 15,
              f"£1,000 at 20% relief and 15% out should be about £1,063, got {vals[0] if vals else None}")
        print(f"3. basic rate: £1,000 in hand -> £{vals[0]:,.0f} through a pension, beating an ISA")

        # ---- 4. and by much more in the 60% band ----------------------------
        set_salaries(110000, 30000)
        vals = pg.evaluate("""() => [...document.getElementById('wrapperChoice')
          .innerText.matchAll(/WORTH, AFTER TAX\\s*\\n\\s*£([\\d,]+)/g)].map(m => +m[1].replace(/,/g, ''))""")
        check(vals and abs(vals[0] - 2125) < 30,
              f"£1,000 at 60% relief and 15% out should be about £2,125, got {vals[0] if vals else None}")
        print(f"4. the 60% band: £1,000 in hand -> £{vals[0]:,.0f}")

        # ---- 5. the recommendation names the right pension -------------------
        for you, spouse, expect in [(110000, 30000, "Your pension"),
                                    (30000, 110000, "Your partner's pension")]:
            set_salaries(you, spouse)
            head = panel().split("\n")
            line = next((l for l in head if "better home" in l), "")
            check(expect.lower() in line.lower(),
                  f"on £{you:,}/£{spouse:,} the recommendation should be {expect!r}, got: {line[:120]!r}")
        print("5. the recommendation names whichever pension has the higher relief")

        # ---- 6. the annual allowance taper is stated ------------------------
        set_salaries(300000, 30000)
        text = panel()
        check("annual allowance" in text.lower(),
              "at £300,000 the page does not mention the annual allowance at all")
        check("10,000" in text or "tapered" in text.lower(),
              "at £300,000 the tapered annual allowance is not shown as the binding limit")
        print("6. at £300,000 the tapered annual allowance is named as the ceiling")

        # ---- 7. it does not claim pensions escape inheritance tax -----------
        check("2027" in text,
              "the page states the pension/IHT position without the April 2027 change")
        print("7. the inheritance tax position is dated, not stated as permanent")

        # ---- 8. additional rate, and Scotland -------------------------------
        # The top of the scale, where the largest sums are contributed and the
        # answer matters most. Scotland is here because it was silently wrong:
        # readInputs() never set `scotland`, so every site asking
        # `inp.scotland === "scot"` got false rather than undefined, the
        # fallback that reads the control never fired, and a Scottish reader
        # was quoted English rates while their SPOUSE got Scottish ones.
        def relief_at(salary, region):
            pg.evaluate("""(r) => { const e = document.getElementById('scotland');
              e.value = r; e.dispatchEvent(new Event('change', {bubbles:true})); }""", region)
            set_salaries(salary, 25000)
            shown = pg.evaluate("""() => { const t = document.getElementById('wrapperChoice').innerText;
              const m = t.match(/RELIEF ON THE NEXT £1,000\\s*\\n\\s*([\\d.]+)%/);
              return m ? +m[1] / 100 : None; }""".replace("None", "null"))
            # what the country's own tax function says that slice really costs
            raw = pg.evaluate("""(v) => { const scot = document.getElementById('scotland').value === 'scot';
              return (ukIncomeTax(v, scot) - ukIncomeTax(v - 1000, scot)) / 1000; }""", salary)
            return shown, raw

        print("8. relief at the top of the scale, and north of the border")
        for region, cases in (("ruk", {130000: 0.45, 200000: 0.45}),
                              ("scot", {60000: 0.42, 110000: 0.675, 200000: 0.48})):
            for salary, want in cases.items():
                shown, raw = relief_at(salary, region)
                check(shown is not None, f"{region} £{salary:,}: no relief figure shown")
                check(abs(raw - want) < 0.005,
                      f"{region} £{salary:,}: the tax tables give {raw:.2%}, expected {want:.2%}")
                check(shown is not None and abs(shown - want) < 0.005,
                      f"{region} £{salary:,}: the card shows {shown:.2%} but the true marginal "
                      f"rate on that slice is {want:.2%}")
                print(f"   ok  {region:4s} £{salary:>7,} -> {shown:.0%}")
        pg.evaluate("""() => { const e = document.getElementById('scotland');
          e.value = 'ruk'; e.dispatchEvent(new Event('change', {bubbles:true})); }""")

        # ---- 9. the annual allowance caveat is stated ------------------------
        # The taper is tested on ADJUSTED income, which includes employer
        # contributions; quoting a ceiling from salary alone without saying so
        # would understate the risk of an unexpected tax charge.
        set_salaries(300000, 25000)
        text9 = panel()
        check("adjusted" in text9.lower(),
              "the ceiling is computed from salary but the page does not say the real test "
              "is adjusted income")
        check("self-assessment" in text9.lower() or "tax return" in text9.lower(),
              "at 45% relief the page does not say the part above basic rate is claimed back "
              "rather than added by the provider")
        print("9. the adjusted-income and self-assessment caveats are both stated")

        b.close()

    if errors:
        failures.append("console/page errors: " + "; ".join(sorted(set(errors))[:5]))
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("\nWRAPPER CHOICE ARITHMETIC CORRECT")


if __name__ == "__main__":
    main()
