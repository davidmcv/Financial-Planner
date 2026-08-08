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
