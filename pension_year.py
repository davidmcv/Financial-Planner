#!/usr/bin/env python3
"""
UK State Pension age calculator.

Calculates the date a UK resident reaches State Pension age (SPA) based on
date of birth and, for people born before the rules were equalised, sex.
Also reports the Normal Minimum Pension Age (NMPA) - the earliest age a
SIPP or other private/personal pension can normally be accessed - and the
average UK life expectancy for that sex. Optionally prints a year-by-year
projected private pension income table, from NMPA access age up to average
life expectancy, growing at a given annual rate (--income/--spouse-income).

State Pension age has been raised several times by different Acts of
Parliament:
  - Pensions Act 1995: began equalising women's SPA (60) with men's (65)
  - Pensions Act 2011: accelerated that equalisation and raised SPA to 66
  - Pensions Act 2014: raised SPA from 66 to 67, and (for anyone born on or
    after 6 April 1977) to 68

The bands below are accurate for the long stable plateaus (60, 65, 66, 67,
68). For dates of birth that fall inside a transitional period, the exact
day is interpolated month-by-month, which matches the real rules closely
but is not guaranteed to be exact to the day in every case. Anyone born in
a transitional window is shown a warning and pointed to the official
GOV.UK checker.

No third-party dependencies; standard library only.
"""

import argparse
import calendar
import sys
from collections import namedtuple
from datetime import date, timedelta


def add_years_months(d: date, years: int, months: int) -> date:
    """Add a whole number of years and months to a date, clamping the day
    if the resulting month is shorter (e.g. 31 Jan + 1 month -> 28/29 Feb)."""
    total_months = d.month - 1 + months + years * 12
    new_year = d.year + total_months // 12
    new_month = total_months % 12 + 1
    day = d.day
    while True:
        try:
            return date(new_year, new_month, day)
        except ValueError:
            day -= 1


def interpolate_months(dob: date, start: date, end: date,
                        start_years: int, start_months: int,
                        end_years: int, end_months: int):
    """Linearly interpolate SPA (in whole months of age) between two known
    anchor points, stepping in whole calendar months of date of birth."""
    total_span_months = (end.year - start.year) * 12 + (end.month - start.month)
    dob_offset_months = (dob.year - start.year) * 12 + (dob.month - start.month)
    if dob.day < start.day:
        dob_offset_months -= 1
    dob_offset_months = max(0, min(dob_offset_months, total_span_months))

    start_total = start_years * 12 + start_months
    end_total = end_years * 12 + end_months
    span_age_months = end_total - start_total

    age_months = start_total + round(span_age_months * dob_offset_months / total_span_months)
    return age_months // 12, age_months % 12


TRANSITION_WINDOWS = [
    (date(1950, 4, 6), date(1960, 4, 5)),
    (date(1960, 4, 6), date(1961, 3, 5)),
]


def in_transition_window(dob: date) -> bool:
    return any(start <= dob <= end for start, end in TRANSITION_WINDOWS)


# Normal Minimum Pension Age (NMPA): the earliest age most people can draw
# a SIPP or other private/personal pension without ill-health early access.
# Currently 55; Finance Act 2022 raises it to 57 from 6 April 2028. Anyone
# who reaches 55 before that date keeps access from 55; everyone reaching
# 55 on or after that date must wait until 57.
NMPA_RISE_DATE = date(2028, 4, 6)


def calculate_nmpa_access(dob: date):
    """Return (age_years, access_date) for when a SIPP/personal pension can
    normally be accessed, per the Finance Act 2022 55->57 rise."""
    age_55_date = add_years_months(dob, 55, 0)
    if age_55_date < NMPA_RISE_DATE:
        return 55, age_55_date
    return 57, add_years_months(dob, 57, 0)


# Average UK life expectancy at birth, by sex (ONS National Life Tables,
# UK: 2020-2022). This is a national average, not a personalised cohort
# projection - it doesn't account for current health, lifestyle, or the
# statistical fact that someone who has already survived to their current
# age has, on average, a slightly longer remaining life expectancy than
# this birth figure implies. Treat it as a rough planning estimate only.
LIFE_EXPECTANCY_AT_BIRTH = {
    "M": 78.6,
    "F": 82.6,
}


def calculate_life_expectancy(dob: date, sex: str):
    """Return (years, months) of average UK life expectancy at birth for
    the given sex, ignoring the date of birth itself (the ONS figures used
    here are national averages at birth, not age-adjusted cohort tables)."""
    sex = sex.upper()
    total_years = LIFE_EXPECTANCY_AT_BIRTH[sex]
    years = int(total_years)
    months = round((total_years - years) * 12)
    if months == 12:
        years += 1
        months = 0
    return years, months


def calculate_spa_age(dob: date, sex: str):
    """Return (years, months) of State Pension age for the given date of
    birth and sex ('M' or 'F')."""
    sex = sex.upper()

    # --- Women: pre-equalisation table (Pensions Act 1995) ---
    if sex == "F" and dob < date(1950, 4, 6):
        return 60, 0
    if sex == "F" and date(1950, 4, 6) <= dob <= date(1953, 4, 5):
        return interpolate_months(
            dob, date(1950, 4, 6), date(1953, 4, 6),
            60, 0, 63, 0,
        )

    # --- Men: flat 65 before the 2011 Act changes began ---
    if sex == "M" and dob < date(1953, 12, 6):
        return 65, 0

    # --- Women born 1953-04-06 to 1954-10-05: accelerated by 2011 Act,
    # converging with the men's 65->66 transition below at 1954-10-06 so
    # both sexes land on the same unisex 66 plateau from that date. ---
    if sex == "F" and date(1953, 4, 6) <= dob <= date(1954, 10, 5):
        return interpolate_months(
            dob, date(1953, 4, 6), date(1954, 10, 6),
            63, 0, 66, 0,
        )

    # --- Men born 1953-12-06 to 1954-10-05: 65 -> 66 ---
    if sex == "M" and date(1953, 12, 6) <= dob <= date(1954, 10, 5):
        return interpolate_months(
            dob, date(1953, 12, 6), date(1954, 10, 6),
            65, 0, 66, 0,
        )

    # --- Unisex flat 66 plateau ---
    if date(1954, 10, 6) <= dob <= date(1960, 4, 5):
        return 66, 0

    # --- Unisex 66 -> 67 transition (Pensions Act 2014) ---
    if date(1960, 4, 6) <= dob <= date(1961, 3, 5):
        return interpolate_months(
            dob, date(1960, 4, 6), date(1961, 3, 6),
            66, 0, 67, 0,
        )

    # --- Unisex flat 67 plateau ---
    if date(1961, 3, 6) <= dob <= date(1977, 4, 5):
        return 67, 0

    # --- Born on/after 6 April 1977: SPA 68 under current legislation ---
    if dob >= date(1977, 4, 6):
        return 68, 0

    raise ValueError(
        "Could not determine State Pension age for this date of birth. "
        "Please check https://www.gov.uk/state-pension-age directly."
    )


def format_age(years: int, months: int) -> str:
    parts = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months or not parts:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    return " ".join(parts)


def calendar_diff(earlier: date, later: date):
    """Return (years, months, days) between two dates, calendar-correct
    (e.g. 2028-03-01 to 2040-03-01 is exactly 12 years, 0 months, 0 days)."""
    years = later.year - earlier.year
    months = later.month - earlier.month
    days = later.day - earlier.day
    if days < 0:
        months -= 1
        prev_month = later.month - 1 or 12
        prev_year = later.year if later.month > 1 else later.year - 1
        days += calendar.monthrange(prev_year, prev_month)[1]
    if months < 0:
        years -= 1
        months += 12
    return years, months, days


# Acronyms are spelled out in full the first time they appear in a run's
# output, then abbreviated on subsequent uses.
TLA_EXPANSIONS = {
    "SPA": "State Pension Age (SPA)",
    "SIPP": "Self-Invested Personal Pension (SIPP)",
    "NMPA": "Normal Minimum Pension Age (NMPA)",
    "ONS": "Office for National Statistics (ONS)",
}


def term_label(term: str, seen_terms: set) -> str:
    if term not in seen_terms:
        seen_terms.add(term)
        return TLA_EXPANSIONS[term]
    return term


def generate_income_table(start_age: int, start_date: date, end_age: int,
                           start_income: float, growth_rate_pct: float):
    """Return one row per whole age-year from start_age to end_age
    (inclusive), with annual income compounding at growth_rate_pct percent
    per year from start_income in the first row. Returns [] if start_age
    is already past end_age (e.g. private pension access age is beyond
    average life expectancy)."""
    rate = growth_rate_pct / 100
    rows = []
    for offset, age in enumerate(range(start_age, end_age + 1)):
        annual = start_income * ((1 + rate) ** offset)
        rows.append({
            "age": age,
            "date": add_years_months(start_date, offset, 0),
            "annual": annual,
            "monthly": annual / 12,
            "weekly": annual / 52,
        })
    return rows


def print_income_table(label: str, rows: list, start_income: float,
                        growth_rate_pct: float):
    print()
    if not rows:
        print(f"{label}: private pension access age is already at or beyond "
              f"average life expectancy - no income projection generated.")
        return
    print(f"{label} projected private pension income")
    print(f"  Starting annual income: £{start_income:,.2f}, growing at "
          f"{growth_rate_pct:.1f}% per year")
    print(f"  {'Age':>4}  {'Year':<12}{'Weekly (£)':>14}{'Monthly (£)':>15}"
          f"{'Annual (£)':>15}")
    for row in rows:
        print(f"  {row['age']:>4}  {row['date'].isoformat():<12}"
              f"{row['weekly']:>14,.2f}{row['monthly']:>15,.2f}"
              f"{row['annual']:>15,.2f}")


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{value}'. Use YYYY-MM-DD, e.g. 1990-05-17."
        )


def prompt_for_dob() -> date:
    while True:
        raw = input("Date of birth (YYYY-MM-DD): ").strip()
        try:
            return date.fromisoformat(raw)
        except ValueError:
            print("  Please enter a valid date in YYYY-MM-DD format.")


def prompt_for_sex() -> str:
    while True:
        raw = input("Sex recorded at birth (M/F): ").strip().upper()
        if raw in ("M", "F"):
            return raw
        print("  Please enter M or F.")


def prompt_yes_no(question: str) -> bool:
    while True:
        raw = input(f"{question} (y/n): ").strip().lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  Please enter y or n.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calculate UK State Pension age from date of birth.",
    )
    parser.add_argument(
        "--dob", type=parse_date,
        help="Date of birth, YYYY-MM-DD (e.g. 1990-05-17).",
    )
    parser.add_argument(
        "--sex", choices=["M", "F", "m", "f"],
        help="Sex recorded at birth. Only affects the calculation for "
             "people born before 6 April 1955.",
    )
    parser.add_argument(
        "--spouse-dob", type=parse_date,
        help="Spouse/partner's date of birth, YYYY-MM-DD. If given, their "
             "State Pension age is calculated too.",
    )
    parser.add_argument(
        "--spouse-sex", choices=["M", "F", "m", "f"],
        help="Spouse/partner's sex recorded at birth.",
    )
    parser.add_argument(
        "--income", type=float,
        help="Your starting annual private pension income at SIPP/NMPA "
             "access age, e.g. 24000. If given, prints a year-by-year "
             "income projection (weekly/monthly/annual) growing at "
             "--income-growth-rate up to your average UK life expectancy.",
    )
    parser.add_argument(
        "--income-growth-rate", type=float, default=2.0,
        help="Anticipated annual income growth rate as a percentage "
             "(default: 2.0).",
    )
    parser.add_argument(
        "--spouse-income", type=float,
        help="Spouse/partner's starting annual private pension income. "
             "Requires --spouse-dob.",
    )
    parser.add_argument(
        "--spouse-income-growth-rate", type=float, default=2.0,
        help="Spouse/partner's anticipated annual income growth rate as a "
             "percentage (default: 2.0).",
    )
    return parser


PersonSummary = namedtuple(
    "PersonSummary",
    ["spa_date", "nmpa_age", "nmpa_date", "life_expectancy_age", "life_expectancy_date"],
)


def report_spa(label: str, dob: date, sex: str, today: date, seen_terms: set) -> PersonSummary:
    """Print the full pension report for one person and return a
    PersonSummary of the key dates/ages calculated along the way."""
    try:
        years, months = calculate_spa_age(dob, sex)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    spa_date = add_years_months(dob, years, months)

    print()
    print(f"{label}")
    print(f"Date of birth:        {dob.isoformat()}")
    print(f"{term_label('SPA', seen_terms)}: {format_age(years, months)}")
    print(f"Reaches SPA on:       {spa_date.isoformat()}")

    if spa_date > today:
        delta_days = (spa_date - today).days
        years_left = delta_days // 365
        months_left = (delta_days % 365) // 30
        print(f"Time remaining:       ~{years_left} years, {months_left} months "
              f"({delta_days} days)")
    else:
        delta_days = (today - spa_date).days
        print(f"SPA reached {delta_days} days ago.")

    if in_transition_window(dob):
        print("Note: this date of birth falls within a transitional period "
              "where the State Pension age was phased in gradually. This "
              "result is a close estimate based on the published "
              "legislation. Please confirm the exact date at:")
        print("  https://www.gov.uk/state-pension-age")

    nmpa_age, nmpa_date = calculate_nmpa_access(dob)
    print(f"{term_label('SIPP', seen_terms)}/private pension: can normally be "
          f"accessed from age {nmpa_age}, on {nmpa_date.isoformat()}")
    if nmpa_age == 57:
        print(f"  ({term_label('NMPA', seen_terms)} rises from 55 to 57 on "
              f"6 April 2028; some older scheme rules give a lower "
              f"'protected pension age' - check with your provider.)")

    gap_years, gap_months, gap_days = calendar_diff(nmpa_date, spa_date)
    gap_total_days = (spa_date - nmpa_date).days
    print(f"Gap between private pension and SPA: {gap_years} years, "
          f"{gap_months} months, {gap_days} days ({gap_total_days} days total)")

    le_years, le_months = calculate_life_expectancy(dob, sex)
    life_expectancy_date = add_years_months(dob, le_years, le_months)
    print(f"Average UK life expectancy ({term_label('ONS', seen_terms)} estimate): "
          f"{format_age(le_years, le_months)}, around "
          f"{life_expectancy_date.isoformat()}")
    print("  (National average at birth, by sex - not a personalised "
          "projection. See ons.gov.uk for detailed life tables.)")

    return PersonSummary(
        spa_date=spa_date,
        nmpa_age=nmpa_age,
        nmpa_date=nmpa_date,
        life_expectancy_age=le_years,
        life_expectancy_date=life_expectancy_date,
    )


def main():
    parser = build_parser()
    args = parser.parse_args()

    today = date.today()

    dob = args.dob if args.dob else prompt_for_dob()
    if dob > today:
        print("Error: date of birth cannot be in the future.", file=sys.stderr)
        sys.exit(1)
    sex = args.sex.upper() if args.sex else prompt_for_sex()

    spouse_dob = args.spouse_dob
    spouse_sex = args.spouse_sex.upper() if args.spouse_sex else None
    if spouse_dob is None and not args.dob:
        if prompt_yes_no("Add your wife/spouse/partner's details too?"):
            spouse_dob = prompt_for_dob()
            spouse_sex = prompt_for_sex()
    elif spouse_dob is not None and spouse_sex is None:
        spouse_sex = prompt_for_sex()

    if spouse_dob is not None and spouse_dob > today:
        print("Error: spouse's date of birth cannot be in the future.", file=sys.stderr)
        sys.exit(1)

    seen_terms = set()
    your_summary = report_spa("You", dob, sex, today, seen_terms)

    if args.income is not None:
        your_rows = generate_income_table(
            your_summary.nmpa_age, your_summary.nmpa_date,
            your_summary.life_expectancy_age,
            args.income, args.income_growth_rate,
        )
        print_income_table("You", your_rows, args.income, args.income_growth_rate)

    if spouse_dob is not None:
        spouse_summary = report_spa("Your spouse", spouse_dob, spouse_sex, today, seen_terms)

        if args.spouse_income is not None:
            spouse_rows = generate_income_table(
                spouse_summary.nmpa_age, spouse_summary.nmpa_date,
                spouse_summary.life_expectancy_age,
                args.spouse_income, args.spouse_income_growth_rate,
            )
            print_income_table("Your spouse", spouse_rows, args.spouse_income,
                                args.spouse_income_growth_rate)

        print()
        if your_summary.spa_date == spouse_summary.spa_date:
            print("You both reach State Pension age on the same date.")
        else:
            later = "You" if your_summary.spa_date > spouse_summary.spa_date else "Your spouse"
            gap_days = abs((your_summary.spa_date - spouse_summary.spa_date).days)
            print(f"{later} reach{'es' if later == 'Your spouse' else ''} "
                  f"State Pension age later, by {gap_days} days.")


if __name__ == "__main__":
    main()
