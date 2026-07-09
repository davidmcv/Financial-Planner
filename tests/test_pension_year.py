"""Tests for pension_year.py. Standard library unittest only, no third-party
test runner required - matches the script's own no-dependencies policy.

Run with: python3 -m unittest discover -s tests -t .
"""

import io
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pension_year as pw

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "pension_year.py")


class TestAddYearsMonths(unittest.TestCase):
    def test_simple_year_add(self):
        self.assertEqual(pw.add_years_months(date(1990, 5, 17), 30, 0),
                          date(2020, 5, 17))

    def test_month_rollover(self):
        self.assertEqual(pw.add_years_months(date(1990, 11, 20), 0, 3),
                          date(1991, 2, 20))

    def test_clamps_short_month(self):
        # 31 Jan + 1 month has no Feb 31, clamp to Feb 28/29.
        self.assertEqual(pw.add_years_months(date(2021, 1, 31), 0, 1),
                          date(2021, 2, 28))

    def test_leap_day_clamped_in_non_leap_year(self):
        self.assertEqual(pw.add_years_months(date(1968, 2, 29), 67, 0),
                          date(2035, 2, 28))

    def test_leap_day_preserved_in_leap_year(self):
        self.assertEqual(pw.add_years_months(date(1968, 2, 29), 60, 0),
                          date(2028, 2, 29))


class TestCalculateSpaAge(unittest.TestCase):
    def test_women_pre_equalisation_flat_60(self):
        self.assertEqual(pw.calculate_spa_age(date(1945, 6, 15), "F"), (60, 0))
        self.assertEqual(pw.calculate_spa_age(date(1950, 4, 5), "F"), (60, 0))

    def test_men_flat_65_before_2011_act(self):
        self.assertEqual(pw.calculate_spa_age(date(1945, 6, 15), "M"), (65, 0))
        self.assertEqual(pw.calculate_spa_age(date(1953, 12, 5), "M"), (65, 0))

    def test_transition_start_anchors_are_exact(self):
        # dob exactly on a transition's start date -> exactly the start age,
        # since the interpolation offset is zero.
        self.assertEqual(pw.calculate_spa_age(date(1950, 4, 6), "F"), (60, 0))
        self.assertEqual(pw.calculate_spa_age(date(1953, 4, 6), "F"), (63, 0))
        self.assertEqual(pw.calculate_spa_age(date(1953, 12, 6), "M"), (65, 0))
        self.assertEqual(pw.calculate_spa_age(date(1960, 4, 6), "F"), (66, 0))
        self.assertEqual(pw.calculate_spa_age(date(1960, 4, 6), "M"), (66, 0))

    def test_unisex_flat_66_plateau(self):
        for dob in (date(1954, 10, 6), date(1957, 1, 1), date(1960, 4, 5)):
            with self.subTest(dob=dob):
                self.assertEqual(pw.calculate_spa_age(dob, "M"), (66, 0))
                self.assertEqual(pw.calculate_spa_age(dob, "F"), (66, 0))

    def test_unisex_flat_67_plateau(self):
        for dob in (date(1961, 3, 6), date(1970, 1, 1), date(1977, 4, 5)):
            with self.subTest(dob=dob):
                self.assertEqual(pw.calculate_spa_age(dob, "M"), (67, 0))
                self.assertEqual(pw.calculate_spa_age(dob, "F"), (67, 0))

    def test_born_on_or_after_1977_04_06_is_68(self):
        self.assertEqual(pw.calculate_spa_age(date(1977, 4, 6), "M"), (68, 0))
        self.assertEqual(pw.calculate_spa_age(date(2000, 1, 1), "F"), (68, 0))

    def test_spa_is_monotonic_non_decreasing_with_dob(self):
        # The State Pension age (as a reach-date) should never move earlier
        # for someone born later - regression guard against a broken band.
        for sex in ("M", "F"):
            prev_reach_date = None
            dob = date(1945, 1, 1)
            while dob <= date(2000, 1, 1):
                years, months = pw.calculate_spa_age(dob, sex)
                reach_date = pw.add_years_months(dob, years, months)
                if prev_reach_date is not None:
                    with self.subTest(sex=sex, dob=dob):
                        self.assertGreaterEqual(reach_date, prev_reach_date)
                prev_reach_date = reach_date
                dob = pw.add_years_months(dob, 0, 1)


class TestCalculateNmpaAccess(unittest.TestCase):
    def test_turns_55_before_rise_date_keeps_age_55(self):
        dob = date(1973, 4, 5)  # 55th birthday is 2028-04-05
        self.assertEqual(pw.calculate_nmpa_access(dob), (55, date(2028, 4, 5)))

    def test_turns_55_on_rise_date_requires_57(self):
        dob = date(1973, 4, 6)  # 55th birthday is 2028-04-06
        age, access_date = pw.calculate_nmpa_access(dob)
        self.assertEqual(age, 57)
        self.assertEqual(access_date, date(2030, 4, 6))

    def test_turns_55_well_after_rise_date_requires_57(self):
        dob = date(1990, 1, 1)
        age, access_date = pw.calculate_nmpa_access(dob)
        self.assertEqual(age, 57)
        self.assertEqual(access_date, date(2047, 1, 1))


class TestFormatAge(unittest.TestCase):
    def test_years_only(self):
        self.assertEqual(pw.format_age(2, 0), "2 years")

    def test_singular_year(self):
        self.assertEqual(pw.format_age(1, 0), "1 year")

    def test_years_and_months(self):
        self.assertEqual(pw.format_age(1, 1), "1 year 1 month")

    def test_zero_falls_back_to_months(self):
        self.assertEqual(pw.format_age(0, 0), "0 months")


class TestCalendarDiff(unittest.TestCase):
    def test_whole_years(self):
        self.assertEqual(pw.calendar_diff(date(2000, 1, 1), date(2010, 1, 1)),
                          (10, 0, 0))

    def test_months_and_day_borrow(self):
        self.assertEqual(pw.calendar_diff(date(2000, 3, 15), date(2000, 5, 10)),
                          (0, 1, 25))

    def test_zero_gap(self):
        self.assertEqual(pw.calendar_diff(date(2020, 6, 1), date(2020, 6, 1)),
                          (0, 0, 0))


class TestTermLabel(unittest.TestCase):
    def test_expands_on_first_use_then_abbreviates(self):
        seen = set()
        self.assertEqual(pw.term_label("SPA", seen), "State Pension Age (SPA)")
        self.assertEqual(pw.term_label("SPA", seen), "SPA")

    def test_terms_tracked_independently(self):
        seen = set()
        pw.term_label("SPA", seen)
        self.assertEqual(pw.term_label("SIPP", seen),
                          "Self-Invested Personal Pension (SIPP)")


class TestInTransitionWindow(unittest.TestCase):
    def test_inside_first_window(self):
        self.assertTrue(pw.in_transition_window(date(1955, 1, 1)))

    def test_inside_second_window(self):
        self.assertTrue(pw.in_transition_window(date(1960, 6, 1)))

    def test_outside_windows(self):
        self.assertFalse(pw.in_transition_window(date(1945, 1, 1)))
        self.assertFalse(pw.in_transition_window(date(1990, 1, 1)))


class TestCalculateLifeExpectancy(unittest.TestCase):
    def test_male_life_expectancy(self):
        # 78.6 years -> 78 years, 0.6*12=7.2 rounds to 7 months.
        self.assertEqual(pw.calculate_life_expectancy(date(1973, 3, 1), "M"), (78, 7))

    def test_female_life_expectancy(self):
        # 82.6 years -> 82 years, 7 months.
        self.assertEqual(pw.calculate_life_expectancy(date(1976, 4, 1), "F"), (82, 7))

    def test_ignores_date_of_birth_value(self):
        # Uses a flat national-average-at-birth figure, so any DOB with the
        # same sex gives the same (years, months) result.
        self.assertEqual(
            pw.calculate_life_expectancy(date(1945, 1, 1), "M"),
            pw.calculate_life_expectancy(date(2020, 1, 1), "M"),
        )

    def test_lowercase_sex_accepted(self):
        self.assertEqual(pw.calculate_life_expectancy(date(1990, 1, 1), "m"),
                          pw.calculate_life_expectancy(date(1990, 1, 1), "M"))


class TestGenerateIncomeTable(unittest.TestCase):
    def test_row_count_spans_inclusive_age_range(self):
        rows = pw.generate_income_table(55, date(2028, 3, 1), 58, 10000, 0.0)
        self.assertEqual([r["age"] for r in rows], [55, 56, 57, 58])

    def test_first_row_uses_starting_income_unchanged(self):
        rows = pw.generate_income_table(55, date(2028, 3, 1), 60, 10000, 5.0)
        self.assertEqual(rows[0]["annual"], 10000)
        self.assertEqual(rows[0]["date"], date(2028, 3, 1))

    def test_compounds_annually_at_given_rate(self):
        rows = pw.generate_income_table(55, date(2028, 3, 1), 57, 10000, 10.0)
        self.assertAlmostEqual(rows[0]["annual"], 10000.0)
        self.assertAlmostEqual(rows[1]["annual"], 11000.0)
        self.assertAlmostEqual(rows[2]["annual"], 12100.0)

    def test_monthly_and_weekly_derived_from_annual(self):
        rows = pw.generate_income_table(55, date(2028, 3, 1), 55, 24000, 0.0)
        row = rows[0]
        self.assertAlmostEqual(row["monthly"], 2000.0)
        self.assertAlmostEqual(row["weekly"], 24000 / 52)

    def test_row_dates_advance_one_year_at_a_time(self):
        rows = pw.generate_income_table(55, date(2028, 3, 1), 57, 10000, 0.0)
        self.assertEqual([r["date"] for r in rows],
                          [date(2028, 3, 1), date(2029, 3, 1), date(2030, 3, 1)])

    def test_zero_percent_growth_keeps_income_flat(self):
        rows = pw.generate_income_table(55, date(2028, 3, 1), 60, 5000, 0.0)
        self.assertTrue(all(r["annual"] == 5000 for r in rows))

    def test_start_age_past_end_age_returns_empty_list(self):
        rows = pw.generate_income_table(90, date(2020, 1, 1), 78, 10000, 2.0)
        self.assertEqual(rows, [])

    def test_single_year_when_start_equals_end_age(self):
        rows = pw.generate_income_table(78, date(2051, 3, 1), 78, 10000, 2.0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["age"], 78)


class TestPrintIncomeTable(unittest.TestCase):
    def test_empty_rows_prints_no_projection_message(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            pw.print_income_table("You", [], 10000, 2.0)
        self.assertIn("no income projection generated", buf.getvalue())

    def test_non_empty_rows_prints_header_and_values(self):
        rows = pw.generate_income_table(55, date(2028, 3, 1), 56, 24000, 0.0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            pw.print_income_table("You", rows, 24000, 0.0)
        output = buf.getvalue()
        self.assertIn("You projected private pension income", output)
        self.assertIn("£24,000.00", output)
        self.assertIn("2028-03-01", output)
        self.assertIn("461.54", output)  # weekly = 24000/52


class TestCli(unittest.TestCase):
    def run_cli(self, *args, input_text=None):
        return subprocess.run(
            [sys.executable, SCRIPT, *args],
            input=input_text, capture_output=True, text=True,
        )

    def test_single_person_output(self):
        result = self.run_cli("--dob", "1973-03-01", "--sex", "M")
        self.assertEqual(result.returncode, 0)
        self.assertIn("State Pension Age (SPA): 67 years", result.stdout)
        self.assertIn("Reaches SPA on:       2040-03-01", result.stdout)
        self.assertIn("can normally be accessed from age 55, on 2028-03-01",
                       result.stdout)
        self.assertIn("Gap between private pension and SPA: 12 years, 0 months, "
                       "0 days (4383 days total)", result.stdout)

    def test_life_expectancy_shown_without_income_flag(self):
        result = self.run_cli("--dob", "1973-03-01", "--sex", "M")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Average UK life expectancy (Office for National "
                       "Statistics (ONS) estimate): 78 years 7 months, "
                       "around 2051-10-01", result.stdout)
        self.assertNotIn("projected private pension income", result.stdout)

    def test_income_flag_prints_projection_table(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M", "--income", "24000",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("You projected private pension income", result.stdout)
        self.assertIn("Starting annual income: £24,000.00, growing at 2.0% "
                       "per year", result.stdout)
        # First row: age 55, 2028-03-01, unchanged starting income.
        self.assertIn("55  2028-03-01          461.54       2,000.00      "
                       "24,000.00", result.stdout)
        # Last row: age 78 (life expectancy), income compounded for 23 years.
        self.assertIn("78  2051-03-01", result.stdout)

    def test_custom_growth_rate_is_applied(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M",
            "--income", "10000", "--income-growth-rate", "0",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("growing at 0.0% per year", result.stdout)
        # Flat income: 24 rows (age 55-78 inclusive) plus the header line.
        self.assertEqual(result.stdout.count("10,000.00"), 25)

    def test_spouse_income_only_shown_for_spouse(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M",
            "--spouse-dob", "1976-04-01", "--spouse-sex", "F",
            "--spouse-income", "18000",
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("You projected private pension income", result.stdout)
        self.assertIn("Your spouse projected private pension income", result.stdout)
        self.assertIn("Starting annual income: £18,000.00", result.stdout)

    def test_ons_acronym_expanded_once_across_both_people(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M",
            "--spouse-dob", "1976-04-01", "--spouse-sex", "F",
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            result.stdout.count("Office for National Statistics (ONS)"), 1)
        self.assertIn("(ONS estimate)", result.stdout)

    def test_spouse_comparison_output(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M",
            "--spouse-dob", "1976-04-01", "--spouse-sex", "F",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Your spouse", result.stdout)
        self.assertIn("Your spouse reaches State Pension age later, by 1126 days.",
                       result.stdout)

    def test_future_dob_is_rejected(self):
        result = self.run_cli("--dob", "2999-01-01", "--sex", "M")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot be in the future", result.stderr)

    def test_invalid_date_format_is_rejected(self):
        result = self.run_cli("--dob", "not-a-date", "--sex", "M")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Invalid date", result.stderr)


if __name__ == "__main__":
    unittest.main()
