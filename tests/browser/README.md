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
Australia, where super is already tax-free after 60 so there is nothing to
escape. Checks the caps bind, the tax matches the country's taxable share, and
that the Australian panel says there is nothing to gain rather than selling the
strategy anyway.

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

WCAG 2.2 AA via axe-core, across 60 page states: every tab, both themes, both
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
