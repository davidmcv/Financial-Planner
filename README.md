# pensionYear
A program to calculate what year a person in the UK can receive the UK Government State Pension,
when they can access a private pension (SIPP), their average UK life expectancy, and an optional
year-by-year projected pension income table.

## Web app

`pension-planner.html` is a self-contained interactive version - open it directly in a browser
(no server, no build step, no dependencies). It's split into six tabs (People, Pension Age,
Salary & Pot, Projection, Household, Gifting) instead of one dense wall of numbers, with live
recalculation as you edit fields. All money is shown in GBP with comma separators, in the input
fields as well as the tables. The calculation logic mirrors `pension_year.py` exactly - see the
`<script>` in the file for the JS port.

The layout is mobile-first and app-like: on a phone the tabs sit in a fixed bottom navigation bar
(no horizontal scrolling), the desktop sidebar collapses into a compact top bar, stat tiles reflow
two-up, and safe-area insets keep content clear of the notch/home indicator. (A true installable
React Native app isn't shippable as a single self-contained web file - RN compiles to a native
iOS/Android binary requiring Xcode/Android Studio and app-store distribution - so this delivers the
native *feel* as a mobile web app.)

A **Plain English / Expert** toggle (top bar and sidebar) switches all jargon between novice-friendly
phrasing and the accurate terms, so both a beginner and an expert can use it - e.g. "When you can
take your private pension" vs "Normal Minimum Pension Age (NMPA)", "Today's £" vs "PV", "a gift
that becomes tax-free once you survive 7 years" vs "Potentially Exempt Transfer (PET)". The Pension
Age tab lists events chronologically (private pension access before the State Pension) and its
heading adapts to singular when no spouse is included. The Salary & Pot and Projection tabs label
the **accumulation** (paying in) and **decumulation** (drawing down) phases explicitly.

The Gifting tab also tracks planned gifts year by year until your average life expectancy and
estimates the Inheritance Tax due at death: each year's excess over the tax-free ceiling is a
Potentially Exempt Transfer (PET); PETs made within 7 years of death use the £325,000 nil-rate
band in date order, and the remainder is taxed at 40% with taper relief (3-4 yrs 32%, 4-5 24%,
5-6 16%, 6-7 8%; 7+ years fully exempt). This is a simplified planning estimate - it ignores the
estate itself sharing the nil-rate band, spousal transfers, and the residence nil-rate band.

A "Profile" picker on the People tab saves your inputs to the browser's local storage under a name you
choose (e.g. "David & wife"), so you can switch between saved scenarios later. This is local-only,
not a real login - there's no way to do genuine Google/Apple sign-in inside a static, dependency-free
page without a hosted domain and registered OAuth credentials, so anyone with access to the browser
can open any saved profile.

## Usage

```
python3 pension_year.py --dob 1973-03-01 --sex M \
  --spouse-dob 1976-04-01 --spouse-sex F \
  --pension-pot 1000000 --drawdown-rate 4 --pot-growth-rate 6 \
  --salary 60000 --employer-contribution-rate 15 \
  --spouse-income 18000
```

Private pension income can be modelled two ways, per person:
- `--income`/`--spouse-income` (+ `--income-growth-rate`, default 2.0%): a flat starting income
  compounding at a fixed rate each year.
- `--pension-pot`/`--spouse-pension-pot` (+ `--drawdown-rate`, default 4.0%, and
  `--pot-growth-rate`, default 6.0%): a DC pension pot, withdrawing a percentage of the current
  balance each year, with the remainder growing at the assumed rate. Takes priority over `--income`
  if both are given.

For you (not your spouse), `--pension-pot` is treated as today's pot value: `--salary` (gross
annual salary, £0-£1,000,000, default £100 - a nominal value that makes the contribution
negligible unless you set a real salary) and `--employer-contribution-rate` (default 15.0%) combine
into an annual employer contribution, added to the pot each year until your SIPP/NMPA access age,
compounding alongside `--pot-growth-rate`. The assumption lines above your table show both the
contribution rate and its £ amount, plus the grown pot value at access age.

From State Pension age onward, the full new State Pension is added on top
(`--state-pension-weekly`, default the 2025/26 rate of £230.25/week), growing at an assumed "triple
lock" rate (`--state-pension-growth-rate`, default 2.5% - the legislated minimum, since future
CPI/earnings figures aren't known in advance).

Each row also shows the present-day (inflation-adjusted) value of that year's income alongside its
nominal future value (labelled PV and FV), discounted at `--discount-rate` (default 2.5%). Tables
are formatted to fit in ~80 characters (an iPad screen without wrapping): money is rounded to the
nearest pound, and dates are shown as just the calendar year.

If both you and your spouse have an income projection (`--income`/`--pension-pot` and
`--spouse-income`/`--spouse-pension-pot`), a combined household table is also printed, summing both
incomes by calendar year (a year covered by only one person shows £0 for the other).

If one of you used `--pension-pot` and reaches average life expectancy before the other, their
remaining DC pension pot is assumed to transfer to the survivor as a lump sum from that point,
boosting the survivor's income for their remaining years (drawn down at the survivor's own rate if
they also have a pot, otherwise at the deceased's rate as a separate inherited sub-account). A flat
`--income` stream has no pot balance, so nothing transfers if the deceased wasn't in pot mode.

### Tax-free gifting

`--num-children`/`--num-grandchildren` (default 0 each) print a tax-free gifting summary for you,
combining two UK Inheritance Tax allowances:
- `--small-gift-amount` (default £250): the "small gifts" exemption, per recipient, to any number
  of people.
- `--annual-exemption` (default £3,000): a single total pot for the year, **not** per recipient -
  split it however you like across recipients.
- `--gift-per-recipient`: overrides the small gifts exemption with a custom per-person figure, if
  you want to plan around a different amount.

The recommended gift is the tax-free ceiling capped by your surplus (your first year of private
pension income minus `--essential-spending`, default £0). If you set `--planned-annual-gift`, it's
checked against the ceiling and any excess is flagged clearly as a Potentially Exempt Transfer
(PET) - only free of Inheritance Tax if you survive 7 years from the gift date. This is a
simplified planning estimate, not tax advice: it assumes no unused prior-year carry-forward on the
annual exemption, and that small gifts don't go to whoever received a share of it.

## Tests

Run the test suite (standard library `unittest`, no dependencies to install):

```
python3 -m unittest discover -s tests -t .
```
