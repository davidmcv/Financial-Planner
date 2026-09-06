"""Saving and loading a plan: where the controls are, and what Save does.

Two faults, both reported from an iPad.

1. The plan controls lived on the People page, wedged between Country and UK
   region. From any other tab you had to navigate away from your work to save
   it - the control people reach for most often was the one hardest to find.
   They now live in the rail, visible from every tab, and on a phone the same
   block moves into a sheet opened from the top bar. MOVED, not copied: two
   copies would be two elements sharing an id, and every getElementById in the
   app would silently take the first.

2. Pressing "Save file" on an iPad opened the system share sheet, whose top
   row is AirDrop contacts. The most prominent thing on screen after asking to
   save a complete personal financial plan was a row of people to send it to.
   Saving and sending are different intentions. Safari has downloaded to Files
   since iOS 13, so Save now downloads, and sharing moved to its own button
   where it is chosen rather than sprung.

The share-sheet case is the one worth guarding hardest, because it only
appears on devices that have navigator.canShare with files - which desktop
Chromium does not - so it is simulated here rather than left untested.
"""
import os
import pathlib

from playwright.sync_api import sync_playwright

FILE = (pathlib.Path(__file__).resolve().parents[2] / "pension-planner.html").as_uri()
CHROME = os.environ.get("CHROME_PATH", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

# Make the page look like an iPad: no save picker, but file sharing available.
# navigator.share is recorded rather than performed, so the test can tell
# whether pressing Save reaches for it.
AS_IPAD = """() => {
  delete window.showSaveFilePicker;
  window.__shared = [];
  navigator.canShare = (d) => !!(d && d.files && d.files.length);
  navigator.share = (d) => { window.__shared.push((d.files || []).map(f => f.name)); return Promise.resolve(); };
  // record downloads instead of performing them
  window.__downloaded = [];
  const click = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (this.download) { window.__downloaded.push(this.download); return; }
    return click.apply(this, arguments);
  };
}"""


def main():
    errors, failures = [], []

    def check(cond, msg):
        if not cond:
            failures.append(msg)
        return cond

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)

        # ---- desktop: the rail ---------------------------------------------
        pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)
        pg.goto(FILE)
        pg.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
        pg.evaluate("""() => { localStorage.setItem('pensionPlanner.rememberChoice','advanced');
          experienceLevel = 'advanced'; applyLevel(); renderAll(); }""")
        pg.wait_for_timeout(900)

        # exactly one of each control, anywhere in the document
        dupes = pg.evaluate("""() => { const c = {};
          document.querySelectorAll('[id]').forEach(e => c[e.id] = (c[e.id] || 0) + 1);
          return Object.entries(c).filter(([k, v]) => v > 1); }""")
        check(not dupes, f"duplicate element ids: {dupes}")

        where = pg.evaluate("""() => { const b = document.getElementById('planBox');
          return { parent: b && b.parentElement.className,
                   inRail: !!(b && b.closest('.rail')),
                   visible: !!(b && b.getBoundingClientRect().height > 0) }; }""")
        check(where["inRail"], f"the plan block is not in the rail (parent: {where['parent']})")
        check(where["visible"], "the plan block is in the rail but has no height")
        print(f"1. plan block lives in the rail ({where['parent']}), one copy only")

        # reachable from every tab, which is the point of moving it
        for tab in ("people", "savings", "salary", "projection", "planner", "tax", "gifting", "relocate"):
            pg.evaluate("(t) => activateTab(t)", tab)
            pg.wait_for_timeout(120)
            ok = pg.evaluate("""() => { const s = document.getElementById('profileSelect');
              const r = s.getBoundingClientRect(); return r.width > 0 && r.height > 0; }""")
            check(ok, f"the plan picker is not visible on the {tab} tab")
        print("2. the plan picker is visible from all 8 tabs")

        # it is no longer duplicated on the People page it came from
        onPeople = pg.evaluate("""() => !!document.querySelector('#tab-people #profileSelect')""")
        check(not onPeople, "the plan controls are still on the People page as well as the rail")
        print("3. the People page no longer carries a second copy")

        # ---- the iPad path --------------------------------------------------
        pg2 = b.new_context(viewport={"width": 1024, "height": 1366}).new_page()
        pg2.on("pageerror", lambda e: errors.append(f"pageerror(ipad): {e}"))
        pg2.goto(FILE)
        pg2.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
        pg2.evaluate(AS_IPAD)
        pg2.evaluate("""() => { localStorage.setItem('pensionPlanner.rememberChoice','advanced');
          experienceLevel = 'advanced'; applyLevel(); renderAll(); }""")
        pg2.wait_for_timeout(800)
        pg2.evaluate("() => document.getElementById('profileExportBtn').click()")
        pg2.wait_for_timeout(700)

        copy = pg2.evaluate("() => document.getElementById('saveFileWhere').innerText")
        check("share sheet will open" not in copy.lower(),
              f"the dialog still promises the share sheet: {copy[:140]!r}")
        check("download" in copy.lower(),
              f"the dialog does not say the file downloads: {copy[:140]!r}")
        print(f"4. dialog now says: {copy.strip()[:100]}...")

        # Share is offered as its own button, not as what Save does
        share = pg2.evaluate("""() => { const b = document.getElementById('saveFileShare');
          return { exists: !!b, shown: b && getComputedStyle(b).display !== 'none' }; }""")
        check(share["exists"] and share["shown"],
              "no separate Share button on a device that can share files")
        print("5. a separate Share button is offered")

        # THE point: pressing Save must download and must not reach for share
        pg2.evaluate("""() => { document.getElementById('saveFileName').value = 'Example-Pension-12345'; }""")
        pg2.evaluate("() => document.getElementById('saveFileConfirm').click()")
        pg2.wait_for_timeout(900)
        res = pg2.evaluate("() => ({ shared: window.__shared, downloaded: window.__downloaded })")
        check(not res["shared"],
              f"pressing Save opened the share sheet: {res['shared']} - it must download instead")
        check(res["downloaded"] == ["Example-Pension-12345.pension.json"],
              f"Save did not download the expected file: {res['downloaded']}")
        print(f"6. Save downloaded {res['downloaded']} and did NOT open the share sheet")

        # ...and Share, pressed deliberately, does share
        pg2.evaluate("() => document.getElementById('profileExportBtn').click()")
        pg2.wait_for_timeout(500)
        pg2.evaluate("() => document.getElementById('saveFileShare').click()")
        pg2.wait_for_timeout(700)
        shared = pg2.evaluate("() => window.__shared")
        check(shared and shared[-1] and shared[-1][0].endswith(".pension.json"),
              f"the Share button did not share a plan file: {shared}")
        print(f"7. Share, pressed deliberately, shares {shared[-1]}")

        # ---- the phone sheet -------------------------------------------------
        pg3 = b.new_context(viewport={"width": 393, "height": 852}).new_page()
        pg3.on("pageerror", lambda e: errors.append(f"pageerror(phone): {e}"))
        pg3.goto(FILE)
        pg3.wait_for_function("document.querySelectorAll('#profileSelect option').length > 2")
        pg3.evaluate("""() => { localStorage.setItem('pensionPlanner.rememberChoice','advanced');
          experienceLevel = 'advanced'; applyLevel(); renderAll(); }""")
        pg3.wait_for_timeout(800)

        # the rail is hidden on a phone, so the block must be reachable another way
        hidden = pg3.evaluate("""() => { const s = document.getElementById('profileSelect');
          const r = s.getBoundingClientRect(); return r.width === 0 || r.height === 0; }""")
        check(hidden, "the rail plan block is somehow visible on a phone - the rail should be hidden")
        btn = pg3.evaluate("""() => { const b = document.getElementById('openPlansMobile');
          return !!b && b.getBoundingClientRect().width > 0; }""")
        check(btn, "no way to reach saved plans on a phone: the top-bar button is missing")

        pg3.evaluate("() => document.getElementById('openPlansMobile').click()")
        pg3.wait_for_timeout(500)
        opened = pg3.evaluate("""() => { const b = document.getElementById('planBox');
          const s = document.getElementById('profileSelect').getBoundingClientRect();
          return { parent: b.parentElement.id, open: document.getElementById('planModal').classList.contains('open'),
                   usable: s.width > 100 && s.height > 0,
                   labels: [...document.querySelectorAll('#planModalBody .btn-label')]
                     .filter(e => getComputedStyle(e).display !== 'none').map(e => e.textContent) }; }""")
        check(opened["open"] and opened["parent"] == "planModalBody",
              f"the plan sheet did not open with the block inside it: {opened}")
        check(opened["usable"], "the plan picker in the sheet is too small to use")
        check("Save" in opened["labels"] and "Load" in opened["labels"],
              f"the sheet's buttons are icon-only, with no words: {opened['labels']}")
        print(f"8. phone sheet opens with the real block inside, labelled {opened['labels']}")

        # closing it puts the block back, so the desktop rail still has it
        pg3.evaluate("() => document.getElementById('closePlanModal2').click()")
        pg3.wait_for_timeout(400)
        back = pg3.evaluate("""() => ({ parent: document.getElementById('planBox').parentElement.className,
          dupes: document.querySelectorAll('#profileSelect').length })""")
        check("rail-footer" in back["parent"],
              f"closing the sheet did not return the block to the rail: {back}")
        check(back["dupes"] == 1, f"there are now {back['dupes']} plan pickers")
        print("9. closing the sheet returns the block to the rail, still one copy")

        b.close()

    if errors:
        failures.append("console/page errors: " + "; ".join(sorted(set(errors))[:5]))
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        raise SystemExit(1)
    print("\nPLAN SAVE/LOAD IS REACHABLE AND SAVE MEANS SAVE")


if __name__ == "__main__":
    main()
