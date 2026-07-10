# pensionYear
A program to calculate what year a person in the UK can receive the UK Government State Pension,
when they can access a private pension (SIPP), their average UK life expectancy, and an optional
year-by-year projected pension income table.

## Web app

`pension-planner.html` is a self-contained interactive version - open it directly in a browser
(no server, no build step, no dependencies). It's split into five tabs (People, Pension Age,
Salary & Pot, Projection, Household) instead of one dense wall of numbers, with live recalculation
as you edit fields. The calculation logic mirrors `pension_year.py` exactly - see the `<script>` in
the file for the JS port.

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
