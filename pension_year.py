#!/usr/bin/env python3
"""
UK State Pension age calculator.

Calculates the date a UK resident reaches State Pension age (SPA) based on
date of birth and, for people born before the rules were equalised, sex.

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
import sys
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

    # --- Women born 1953-04-06 to 1955-04-05: accelerated by 2011 Act ---
    if sex == "F" and date(1953, 4, 6) <= dob <= date(1955, 4, 5):
        return interpolate_months(
            dob, date(1953, 4, 6), date(1955, 4, 6),
            63, 0, 65, 0,
        )

    # --- Men born 1953-12-06 to 1954-10-05: 65 -> 66 ---
    if sex == "M" and date(1953, 12, 6) <= dob <= date(1954, 10, 5):
        return interpolate_months(
            dob, date(1953, 12, 6), date(1954, 10, 6),
            65, 0, 66, 0,
        )

    # --- Everyone born 1955-04-06 to 1954-10-05 gap-filler (women reaching
    # 65 before the unisex 66 band kicks in): treat as flat 65/66 boundary ---
    if sex == "F" and date(1955, 4, 6) <= dob <= date(1954, 10, 5):
        # unreachable (kept for clarity of intent); real logic below covers it
        pass

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
    return parser


def report_spa(label: str, dob: date, sex: str, today: date) -> date:
    """Print the State Pension age report for one person and return their
    SPA date."""
    try:
        years, months = calculate_spa_age(dob, sex)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    spa_date = add_years_months(dob, years, months)

    print()
    print(f"{label}")
    print(f"Date of birth:        {dob.isoformat()}")
    print(f"State Pension age:    {format_age(years, months)}")
    print(f"Reaches SPA on:       {spa_date.isoformat()}")

    if spa_date > today:
        delta_days = (spa_date - today).days
        years_left = delta_days // 365
        months_left = (delta_days % 365) // 30
        print(f"Time remaining:       ~{years_left} years, {months_left} months "
              f"({delta_days} days)")
    else:
        delta_days = (today - spa_date).days
        print(f"State Pension age reached {delta_days} days ago.")

    if in_transition_window(dob):
        print("Note: this date of birth falls within a transitional period "
              "where the State Pension age was phased in gradually. This "
              "result is a close estimate based on the published "
              "legislation. Please confirm the exact date at:")
        print("  https://www.gov.uk/state-pension-age")

    return spa_date


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

    your_spa_date = report_spa("You", dob, sex, today)

    if spouse_dob is not None:
        spouse_spa_date = report_spa("Your spouse", spouse_dob, spouse_sex, today)

        print()
        if your_spa_date == spouse_spa_date:
            print("You both reach State Pension age on the same date.")
        else:
            later = "You" if your_spa_date > spouse_spa_date else "Your spouse"
            gap_days = abs((your_spa_date - spouse_spa_date).days)
            print(f"{later} reach{'es' if later == 'Your spouse' else ''} "
                  f"State Pension age later, by {gap_days} days.")


if __name__ == "__main__":
    main()
