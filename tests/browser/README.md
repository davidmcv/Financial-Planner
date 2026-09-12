# Browser tests

Driven by Playwright against `pension-planner.html` opened from disk. They
check the things a unit test cannot see: what is actually laid out, what is
readable, and whether one control updates everything that depends on it.

    pip install playwright
    python3 tests/browser/test_clipping.py
    python3 tests/browser/test_ui_batch.py

`CHROME_PATH` overrides the browser binary; it defaults to the one bundled in
the dev container.

**These live in the repo on purpose.** They previously sat in a scratch
directory outside it, and a container rebuild took the lot — twenty-eight
suites of accumulated regression cover, gone, with nothing to re-run against
the next change. Anything worth running twice belongs in version control.

## test_clipping.py

A standing guard: walks every visible element across six widths, two text
sizes, both rail states and all six tabs, and fails when text is wider than the
box drawn around it. This is the class of bug that clipped "Decades" and
"Numbers" to "Deca" and "Numb" in the sidebar — invisible to a test that only
checks the page doesn't scroll sideways, because a clipped child doesn't widen
the page. 132 page states per run.

Form controls are exempt: a text input whose value is longer than its box
scrolls internally, which is how text fields have always worked.

## test_options_effective.py

The standing answer to "does this control actually do anything?". Walks every
option in the app and proves each one changes something observable, sorting
them into three kinds: MODEL (the projection changes), DISPLAY (only the
drawing changes) and REPORT (only a panel or tracker changes, on purpose).

A control in none of the three fails the run, so adding an option forces a
decision about which kind it is and a test that it works. This exists because
two controls shipped inert: the ISA sub-option under the tax-free lump sum,
which was read only inside `if (o.takePcls ...)`, and "move pension to ISA over
time", which fed a comparison table and never the projection. Both looked
exactly like working controls.

Some options only bite when there is an amount for them to act on, so the
setup gives the household real figures first; a bonus of zero moves nothing
however it is toggled, and that is not the same as being unwired.

## test_move_out_countries.py

The pension-to-wrapper strategy under each country's rules: ISA in the UK
(£20,000 each a year, 75% of the withdrawal taxed), a Roth conversion in the US
(no cap, fully taxed), a PEA in France (€150,000 for life, fully taxed), and
three countries where there is nothing to gain for three different reasons —
Australia, where super is already tax-free after 60; Hong Kong, which taxes no
gains, dividends or interest outside the pension either, so an ordinary account
already is a shelter; and Singapore, which charges half of every SRS withdrawal
on the way out and taxes nothing on the outside. Checks the caps bind, the tax
matches each country's taxable share, and that all three panels say there is
nothing to gain rather than selling the strategy anyway.

## test_strategy_verdicts.py

Every "is this worth doing?" panel runs the plan twice and subtracts. This
pins what is subtracted: spendable money, after income tax, counting what is
left in the pension, discounted to today. Each of those three was missing at
some point, and each produced a confident wrong number rather than a crash —
"move only what comes out tax-free" cost £0 in tax and was reported £320,264
behind. The assertion that cannot be argued with: a transfer that costs
nothing cannot leave the household worse off.

## test_wrapper_choice.py

The arithmetic behind "ISA, your pension, or your partner's?" — relief on the
top slice of each person's pay against the tax on the way out. Checks the four
cases people actually hit (basic rate, higher rate, the 60% band, and a
non-taxpayer who still gets 20% at source), and that two people on different
salaries get different answers. If it ever reports the same relief rate for
two very different salaries, the page is reading household income where it
should read one person's.

## test_relocate.py

The Where to live page. A country comparison is the easiest page here to fake:
plausible percentages beside country names look authoritative and nobody
checks. So this proves it is computed — the income comes from the plan,
changing it re-ranks, every country's tax responds to income and household
size, personal allowances are applied (banding from the first pound made Spain
look like a 29% jurisdiction), and the honest parts survive: the health
warning, the no-retirement-visa verdicts, the Schengen 90/180 limit, and the
fact that leaving the UK gives up the 25% tax-free quarter.

## test_plan_save.py

Where the plan controls are, and what Save actually does. The controls used to
sit on the People page between Country and UK region, so saving meant
navigating away from your work; they now live in the rail, visible from every
tab, and move into a sheet on a phone — moved, not copied, because two copies
would be two elements sharing an id. And pressing Save on an iPad used to open
the system share sheet, whose top row is AirDrop contacts: the test simulates
that device (desktop Chromium has no `navigator.canShare` for files) and holds
Save to downloading, with sharing on its own button.

## test_stress_runs.py

The stress test's run count is a slider from 1,000 to 100,000 in 2,000 steps.
Two things had to be true before that was safe: 100,000 runs must not lock the
page (the work runs in slices between frames, with progress and a cancel), and
the longevity chart must not inherit the number — it re-simulates on every
redraw, so at 100,000 the whole app would stall each time anything moved. Both
are pinned here, along with the honesty check: more runs make the answer
steadier, not more accurate about markets, and the page has to say so with the
actual margin of error.

## test_accessibility.py

WCAG 2.2 AA via axe-core, across 64 page states: every tab, both themes, both
detail levels, phone and desktop, the dialogs, and the largest text setting.
The app is used in the UK, US, France and Australia, whose accessibility laws
(Equality Act, ADA/Section 508, EAA via EN 301 549, DDA) all point at the same
standard, so testing the strictest covers them.

Plus the things a static scan cannot judge: that Tab reaches the controls
without sticking, that focus is visible where it lands, and that Escape closes
every dialog.

axe-core is vendored in `vendor/` so the suite runs offline against a known
version. Automated checks find roughly a third of WCAG failures — this is the
floor, not a certificate.

## test_platform_glyphs.py

Nothing in the interface may depend on which glyphs a platform happens to
have. Both faults here came from a Windows PC: flag emoji rendered as
two-letter codes (Windows has never shipped flag glyphs), and the navigation
icons came out as four colour pictures beside four small monochrome symbols,
because characters like the bank, scales and map are text-presentation by
default. Neither is fixable in CSS — both are font-selection decisions — so
flags and icons are inline SVG now. This checks no emoji creep back into the
source or the chrome, that every country and tab has artwork that actually
reaches the page, that icons share one size, stroke and inherited colour, and
that flags stay decorative so a screen reader doesn't read each country twice.

## test_trips.py

The "long trips, without moving" card on Where to live — the alternative to
emigrating that most people actually take, costed against the same plan. Three
things to guard: the reader's own word (a Briton takes a holiday, an American a
vacation, and the French entry must stay in English rather than dropping French
nouns into English sentences); the 90-days-in-180 limit, which a slider offering
26 weeks has to acknowledge; and the arithmetic, which the first version got
flattering in two ways — a campervan you own costs money in the ten months it
sits on the drive, and going away is not all extra because the food and energy
you'd have used at home stop.

## test_privacy_claim.py

The front page says nothing you type leaves your device and the app runs with
Wi-Fi off. That is the one kind of copy that can become a lie without anyone
touching it — a web font, a CDN library, an analytics snippet are each one
line and none looks like a privacy change. So this watches the network rather
than reading the claim: opened from a file the page makes exactly one request
(itself); served over http it makes one more, to its own address, probing for
the optional account server, and the note discloses that rather than glossing
it. Anything to a third-party host fails. Then it loads the page, cuts the
browser off entirely, and drives every tab and a full market simulation to
prove the offline claim is true rather than aspirational.

## test_property.py

The property investment tab. Ten checks against hand-computed figures: stamp
duty at five prices including below the nil-rate band (where the 5% surcharge
still applies to the whole price), corporation tax across the marginal-relief
range, Section 24 at three interest rates, the double taxation a company suffers
on the way out, the company advantage widening with the owner's band, the
lender's interest-cover test passing and failing, sale proceeds both ways, the
inheritance position (Business Property Relief does not apply to a property
investment company, whatever the seminar said), the ten-property cap, and the
warnings.

## test_hk_sg.py

Hong Kong and Singapore, checked against the statutes rather than against the
app. Two things here are not verifiable by "it renders":

Hong Kong charges the **lower** of a progressive calculation after a HK$145,000
allowance and a flat standard rate with no allowance at all, so modelling one of
them is wrong in both directions. The crossover is a real number — HK$2,132,500,
where 17% of the top slice overtakes 15% of the lot — and the test finds it.

And the fact that makes Hong Kong worth getting right: Article 17 of the 2010
UK–Hong Kong treaty assigns pensions to the country they **arise** in, the
reverse of almost every other UK treaty. Everyone knows Hong Kong has low taxes,
so everyone assumes a UK pension lands there untaxed; the UK carries on taxing
it. A 0% row on Where to live would be the most expensive thing this app could
print, so the test asserts the Hong Kong figure equals the UK figure and that
the page says why.

Singapore's version is subtler: the treaty moves the taxing right only where the
pension is actually *subject to tax* there, and Singapore taxes foreign income
received by an individual at nil — so the condition may fail and the UK keeps
the right by default. The test requires the page to say so rather than promise a
saving.

Also pins: CPF falling in steps with age (20% to 55, then 18 / 12.5 / 7.5 / 5%)
and capped at the S$8,000-a-month ceiling; earned income relief stepping up at
55 and 60; that both countries are wired through all thirteen country-keyed
structures rather than just the comparison table; that the gifting card gives
each no-transfer-tax country its own history instead of telling everyone about
Queensland death duties; and that the property tab admits it is UK law and names
what is different locally.

## test_tax_year_current.py

The suite the app most needed and did not have. Every other suite checks the
arithmetic is consistent with the tables; none checked the tables are **this
year's**. So the app sat on 2025/26 UK rates, 2025 US brackets, a 2025 French
barème, 2024–25 Australian rates and a £230.25 State Pension while presenting
itself as current — none of which breaks anything, it just quietly gives
everybody the wrong answer.

Every figure is written out longhand here from the primary announcements, so a
rate change fails this file and has to be updated deliberately. It also checks
no label on the page still says a superseded tax year, that the 60% band and
Scotland's 67.5% allowance-withdrawal band both emerge from the engine rather
than being rounded away, and that the per-country tax chain exists **once** —
it used to be copy-pasted at six call sites, and the copy you miss is where a
new country silently gets Australian tax.
