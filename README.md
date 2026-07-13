# pensionYear
A program to calculate what year a person in the UK can receive the UK Government State Pension,
when they can access a private pension (SIPP), their average UK life expectancy, and an optional
year-by-year projected pension income table.

## Web app

`pension-planner.html` is a self-contained interactive financial planner - open it directly in a
browser (no server, no build step, no dependencies). Six tabs (People, Paying In, Paying Out,
Planner, Tax, Gifting) with live recalculation as you edit fields, money formatted with comma
separators in your country's currency. The web app extends far beyond the CLI (`pension_year.py`);
the shared UK State-Pension-age / NMPA / life-expectancy maths still mirrors the Python exactly.
Everything is a simplified planning model - not financial or tax advice.

**Planner** is the Voyant/Nova-style centrepiece:
- a large **major-events cash-flow chart**: stacked household income per year (savings bridge,
  private drawdown, DB pensions, State Pension), with flags carrying an icon per event -
  retirements (🏖️), State Pension start (🏛️) and your own custom one-off events (💰 in, 🏡 out,
  e.g. an inheritance in or a house purchase out);
- a Voyant Go-style **year-by-year breakdown**: a stacked bar chart underneath, one bar per year
  split by income source, with your spending target drawn across so short years are obvious;
- both charts span the whole life, splitting the **Accumulation** (what you pay in each year) and
  **Decumulation** (household income by source) phases with a labelled retirement divider; every
  event flag shows the person's age and the date;
- **spending phases** (go-go / slow-go / no-go): configurable percentages of the target by age, so
  you can plan higher spending in the active early travel years and less later — shown as a stepped
  target line;
- a **funding view with smoothing**: turn on *use non-pension savings to smooth spending* and the
  breakdown bars show exactly where each year's money comes from — guaranteed income and pension
  drawdown first, then tax-free lump sums, cash, Cash ISA, GIA, S&S ISA and any **home-downsizing**
  proceeds, drawn to hold the target and flatten the later drop-off (with the year savings run out
  called out). The **25% tax-free lump sum** can be taken per person at access age, and **property
  & vehicles** are recorded per person with an optional downsize year;
- a **Longevity chart** (adviser mode): your chance of still being alive by age (either-alive for
  a couple, from a Gompertz survival curve anchored to life expectancy), the Monte Carlo portfolio
  success rate by age (money still lasts), and a **longevity-adjusted** success rate =
  `1 − (1 − success) × survival` (it only "fails" if the pot runs out *and* you're alive to see
  it), with 50%/10%-survival age markers. The People tab shows each person's **maximum modelled
  age** for the country and the odds of reaching given ages;
- **living-standard targets** from the PLSA / Loughborough University Retirement Living Standards
  (Low = Minimum, Medium = Moderate, High = Comfortable; single and couple amounts), with a
  years-below-target verdict;
- a **Monte Carlo market stress test** (adviser mode): your household pots replayed against an
  *approximate* 1925-2024 UK/global-equity real-return history, resampled in 5-year blocks, giving
  a "% of runs where the money lasts" score and a 10th-90th percentile fan chart;
- **what-if scenarios** (retire earlier/later, markets better/worse, spend more/less) overlaid on
  the chart with a lifetime-income comparison table.
- **tax strategies** with an honest Inheritance Tax verdict: save more each year; take the 25%
  tax-free lump sum at pension access age into a GIA in the lower-tax spouse's name; or move a
  pension into ISAs over time (default £20,000/person/year). Each shows its income-tax effect and
  estate impact. The key caveat is made plain: under current rules an unused pension is *outside*
  your estate while ISAs and GIAs are *inside* it, so these moves usually *increase* IHT rather
  than reduce it - the gain is income-tax efficiency. From 6 April 2027 unused pensions fall into
  the estate, so for later retirements the verdict flips to broadly IHT-neutral.

**Tax** models each country's headline 2025/26-era income tax per person, on salary today and on
retirement income (a Net column also appears in Paying Out):
- **UK**: England/Wales/NI *and* Scottish bands (starter/basic/intermediate/higher/advanced/top),
  personal-allowance taper above £100k, employee National Insurance, and UFPLS-style drawdown
  (25% tax-free / 75% taxable, no NI on pensions);
- **US**: 2025 federal brackets + standard deduction (single filer per person; no state tax);
- **France**: 2025 barème (per person; social charges not modelled);
- **Australia**: 2024-25 resident rates + Medicare levy, with superannuation income tax-free from
  age 60.

**Internationalisation**: a country picker (UK / US / France / Australia) switches the currency
symbol **everywhere** (every field label, hint and table header, not just the output figures),
the state-pension defaults and ages (Social Security 67, France 64, Age Pension 67; private access
59½ / 64 / 60), and the whole tax engine. UK keeps the full SPA legislation including transitional
bands. (UK-specific statutory figures - the £325,000 nil-rate band, the annual-allowance taper -
stay in pounds, as they are UK amounts.)

**Usability**: a **Plain English / Expert** wording toggle and a separate **Simple / Adviser**
detail-level toggle (Simple hides advanced fields like growth rates and the Monte Carlo panel), so
the same tool serves a novice and a professional planner.

**Ten demo profiles** (very low wealth through ultra-high-net-worth, singles and couples, all four
countries, a Scottish DB-pension case) are seeded on first run so it can be explored immediately;
your own profiles persist in the browser alongside them, including events, scenarios and targets.

**People** holds each person's date of birth, sex, and **planned retirement date**, plus the
resulting timeline (private pension access, State Pension, life expectancy) in chronological order.

**Paying In** (accumulation) has each person's pension pot and contributions, plus their own asset
sections. **Pension contributions** take the employer amount as either a **percentage of salary**
or a **fixed £/month**, capped at the **annual allowance** (default £60,000) with a warning when
exceeded and a high-earner **taper** note (adjusted income over £260,000). **Bonus, equity & other
savings** (optional) covers an annual **bonus** with a configurable immediate-cash / deferred-cash /
RSU split and vesting years, **RSUs** already held plus ongoing grants, a **Sharesave / SAYE**
scheme (monthly, term, discount), one-off upcoming cash, and extra regular saving - each added net
of marginal tax to your investments and grown to retirement.

Assets are held **per person**: **Cash savings** (current account + savings accounts, each with a
type - Cash ISA, Easy Access, etc.), **Employer pensions** (each Defined Contribution or Defined
Benefit), and **Shares & investments** (each with a type - S&S ISA, GIA, LISA, etc.) appear under
**You** and, when a spouse is included, under **Your spouse**, each feeding that person's own
projection, with a per-person assets-today summary.

**Paying Out** (decumulation) projects your income year by year from your retirement date to average
life expectancy. Retiring before a pension starts is handled across all the numbers: the gap years
are funded from **cash first, then shares** (shortfalls flagged in red), **Defined Contribution**
employer pots fold into your drawdown pot, and **Defined Benefit** pensions add a fixed income from
their own start age. (These are simplified planning assumptions - e.g. DB income is flat, DC pots
grow at your pot's rate, and cash/shares are only drawn during an early-retirement gap.)

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

A "Profile" picker on the People tab saves your inputs under a name you choose (e.g. "David &
wife"), so you can switch between saved scenarios later. Opened from disk, profiles live in the
browser's local storage only; served by the backend below, an Account card appears and signed-in
profiles also sync to the server - across devices, and shareable with an adviser.

## Server backend

`server/` is an optional backend that turns the single file into a hosted, multi-user product. The
page detects it automatically: opened from disk nothing changes, served by the backend it gains

- **accounts and sign-in** (email + password; scrypt-hashed passwords, expiring bearer tokens);
- **profile sync**: saved profiles live in the database and follow you across devices (local
  storage still works offline and is merged on sign-in);
- **adviser/client sharing**: share a profile with another account, view-only or view-and-edit
  (the &#128101; button next to the profile picker);
- **maintained reference data**: the tax tables and the 100-year market-return history are served
  versioned from the database (`GET /api/reference`) and replace the built-ins, so rates can be
  updated centrally without shipping a new HTML file.

It's Python (FastAPI + SQLAlchemy) over a plain relational schema - `users`, `auth_tokens`,
`profiles`, `profile_shares`, `reference_docs` - queryable with ordinary SQL. SQLite by default
(zero setup, fine for development and small deployments); set `DATABASE_URL` to a PostgreSQL URL
for production - the code is identical.

```
pip install -r server/requirements.txt
uvicorn server.app:app --reload        # then open http://localhost:8000
python3 -m unittest discover -s server/tests -t .   # API test suite
```

Or the production-shaped stack (app + PostgreSQL): `docker compose up --build`.

### Recommended deployment

For up to ~10,000 users with ~100 signed in at once, this workload is small: the API is light JSON
reads/writes and all heavy computation (projections, Monte Carlo) runs in each user's browser. One
small box is genuinely enough.

- **Simplest (recommended): a single small VM** - e.g. a Hetzner CX22, DigitalOcean Basic droplet
  or AWS Lightsail instance (2 vCPU / 4 GB, roughly £4-10/month) running `docker compose up` with
  [Caddy](https://caddyserver.com) in front for automatic HTTPS. Nightly `pg_dump` to object
  storage for backups. This comfortably serves 100 concurrent sessions with 2 uvicorn workers.
- **Zero-ops alternative: a PaaS** - Fly.io, Railway or Render for the container, plus a managed
  PostgreSQL (Neon, Supabase, or the platform's own). Slightly dearer, but patching, TLS and
  backups are someone else's job. Good fit if nobody wants to own a server.
- **Scaling path**: the app is stateless (sessions are rows in `auth_tokens`), so if it ever
  outgrows one box you run more replicas behind a load balancer and scale PostgreSQL vertically -
  no code changes. PostgreSQL on default settings won't be the bottleneck until well past this
  user count.

Avoid serverless/Lambda-style hosting here: always-on token-authenticated sessions and a relational
pool suit a long-running process better, and the fixed cost of one tiny VM is lower than
per-request pricing at this scale.

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
