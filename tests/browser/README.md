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
