"""Tests for pension_year.py. Standard library unittest only, no third-party
test runner required - matches the script's own no-dependencies policy.

Run with: python3 -m unittest discover -s tests -t .
"""

import os
import subprocess
import sys
import unittest
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
