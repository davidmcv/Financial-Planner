"""Tests for pension_year.py. Standard library unittest only, no third-party
test runner required - matches the script's own no-dependencies policy.

Run with: python3 -m unittest discover -s tests -t .
"""

import argparse
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

    def test_no_state_pension_when_spa_date_omitted(self):
        rows = pw.generate_income_table(55, date(2028, 3, 1), 57, 10000, 0.0)
        self.assertTrue(all(r["state_annual"] == 0.0 for r in rows))
        self.assertTrue(all(r["annual"] == r["private_annual"] for r in rows))

    def test_state_pension_zero_before_spa_and_added_from_spa(self):
        rows = pw.generate_income_table(
            55, date(2028, 3, 1), 60, 10000, 0.0,
            spa_date=date(2030, 3, 1), state_pension_weekly=100.0,
        )
        before = {r["age"]: r for r in rows if r["age"] < 57}
        self.assertTrue(all(r["state_annual"] == 0.0 for r in before.values()))
        self.assertTrue(all(r["annual"] == r["private_annual"] for r in before.values()))

        from_spa = {r["age"]: r for r in rows if r["age"] >= 57}
        self.assertTrue(all(r["state_annual"] > 0.0 for r in from_spa.values()))
        first_spa_row = from_spa[57]
        self.assertAlmostEqual(first_spa_row["state_annual"], 100.0 * 52)
        self.assertAlmostEqual(first_spa_row["annual"],
                                first_spa_row["private_annual"] + 100.0 * 52)

    def test_state_pension_compounds_from_its_own_start_year(self):
        rows = pw.generate_income_table(
            65, date(2038, 3, 1), 68, 10000, 10.0,
            spa_date=date(2040, 3, 1), state_pension_weekly=100.0,
            state_pension_growth_rate_pct=10.0,
        )
        by_age = {r["age"]: r for r in rows}
        # SPA reached at age 67: state pension starts there at 100*52,
        # then compounds 10% per year from that point (not from age 65).
        self.assertEqual(by_age[65]["state_annual"], 0.0)
        self.assertEqual(by_age[66]["state_annual"], 0.0)
        self.assertAlmostEqual(by_age[67]["state_annual"], 100.0 * 52)
        self.assertAlmostEqual(by_age[68]["state_annual"], 100.0 * 52 * 1.10)

    def test_state_pension_defaults_to_triple_lock_assumed_rate(self):
        rows = pw.generate_income_table(
            65, date(2038, 3, 1), 66, 10000, 0.0,
            spa_date=date(2038, 3, 1), state_pension_weekly=100.0,
        )
        by_age = {r["age"]: r for r in rows}
        self.assertAlmostEqual(
            by_age[66]["state_annual"],
            100.0 * 52 * (1 + pw.TRIPLE_LOCK_ASSUMED_RATE / 100),
        )

    def test_spa_date_before_start_date_includes_state_pension_from_row_one(self):
        rows = pw.generate_income_table(
            60, date(2033, 3, 1), 62, 10000, 0.0,
            spa_date=date(2020, 1, 1), state_pension_weekly=100.0,
            state_pension_growth_rate_pct=0.0,
        )
        self.assertTrue(all(r["state_annual"] == 100.0 * 52 for r in rows))


class TestDiscountToPresent(unittest.TestCase):
    def test_no_today_returns_nominal_unchanged(self):
        self.assertEqual(
            pw.discount_to_present(1000.0, date(2030, 1, 1), None, 2.5), 1000.0)

    def test_future_date_not_after_today_returns_nominal_unchanged(self):
        self.assertEqual(
            pw.discount_to_present(1000.0, date(2020, 1, 1), date(2026, 1, 1), 2.5),
            1000.0)

    def test_discounts_one_year_out(self):
        # ~365 days ~ 1 year (uses a 365.25-day year), so this should land
        # close to the standard 1000/1.10 one-year discount.
        result = pw.discount_to_present(1000.0, date(2027, 1, 1), date(2026, 1, 1), 10.0)
        self.assertAlmostEqual(result, 1000.0 / 1.10, delta=1.0)

    def test_zero_discount_rate_leaves_amount_unchanged(self):
        result = pw.discount_to_present(1000.0, date(2030, 1, 1), date(2026, 1, 1), 0.0)
        self.assertAlmostEqual(result, 1000.0)


class TestGenerateDcDrawdownTable(unittest.TestCase):
    def test_first_row_withdraws_percentage_of_starting_pot(self):
        rows = pw.generate_dc_drawdown_table(
            55, date(2028, 3, 1), 55, 1000000, 4.0, 6.0)
        self.assertAlmostEqual(rows[0]["private_annual"], 40000.0)
        self.assertAlmostEqual(rows[0]["pot_start"], 1000000.0)

    def test_pot_grows_net_of_withdrawal_and_growth(self):
        rows = pw.generate_dc_drawdown_table(
            55, date(2028, 3, 1), 56, 1000000, 4.0, 6.0)
        # Year 1: withdraw 40,000 -> remaining 960,000 -> grows 6% -> 1,017,600.
        self.assertAlmostEqual(rows[1]["pot_start"], 1017600.0)
        self.assertAlmostEqual(rows[1]["private_annual"], 1017600.0 * 0.04)

    def test_zero_growth_and_drawdown_keeps_pot_flat(self):
        rows = pw.generate_dc_drawdown_table(
            55, date(2028, 3, 1), 58, 500000, 0.0, 0.0)
        self.assertTrue(all(r["pot_start"] == 500000.0 for r in rows))
        self.assertTrue(all(r["private_annual"] == 0.0 for r in rows))

    def test_state_pension_and_present_value_layered_on_top(self):
        rows = pw.generate_dc_drawdown_table(
            55, date(2028, 3, 1), 60, 1000000, 4.0, 6.0,
            spa_date=date(2033, 3, 1), state_pension_weekly=100.0,
            today=date(2028, 3, 1),
        )
        by_age = {r["age"]: r for r in rows}
        self.assertEqual(by_age[59]["state_annual"], 0.0)
        self.assertGreater(by_age[60]["state_annual"], 0.0)
        self.assertLess(by_age[60]["present_annual"], by_age[60]["annual"])

    def test_start_age_past_end_age_returns_empty_list(self):
        rows = pw.generate_dc_drawdown_table(90, date(2020, 1, 1), 78, 1000000, 4.0, 6.0)
        self.assertEqual(rows, [])


class TestDcDrawdownInjection(unittest.TestCase):
    def test_no_injection_matches_plain_series(self):
        plain = pw.generate_dc_drawdown_series(55, date(2028, 3, 1), 57, 1000000, 4.0, 6.0)
        injected = pw.generate_dc_drawdown_series(
            55, date(2028, 3, 1), 57, 1000000, 4.0, 6.0, injection_date=None)
        self.assertEqual(plain, injected)

    def test_injection_before_series_start_applies_to_first_row(self):
        series = pw.generate_dc_drawdown_series(
            55, date(2028, 3, 1), 55, 1000000, 4.0, 6.0,
            injection_date=date(2020, 1, 1), injection_amount=500000,
        )
        self.assertAlmostEqual(series[0]["pot_start"], 1500000.0)
        self.assertAlmostEqual(series[0]["private_annual"], 1500000.0 * 0.04)

    def test_injection_mid_series_applies_from_matching_row_onward(self):
        series = pw.generate_dc_drawdown_series(
            55, date(2028, 3, 1), 58, 1000000, 4.0, 0.0,
            injection_date=date(2030, 3, 1), injection_amount=200000,
        )
        by_age = {e["age"]: e for e in series}
        # Age 56 (2029): before injection - pot unaffected.
        self.assertLess(by_age[56]["pot_start"], 1000000.0)
        # Age 57 (2030): injection date reached - pot jumps up by 200,000.
        pot_before_injection_year = by_age[56]["pot_start"] - by_age[56]["private_annual"]
        self.assertAlmostEqual(by_age[57]["pot_start"], pot_before_injection_year + 200000.0)

    def test_injection_after_series_end_never_applied(self):
        series = pw.generate_dc_drawdown_series(
            55, date(2028, 3, 1), 56, 1000000, 4.0, 6.0,
            injection_date=date(2099, 1, 1), injection_amount=500000,
        )
        self.assertAlmostEqual(series[-1]["pot_start"], 1017600.0)  # unaffected


class TestRemainingDcPotAtEnd(unittest.TestCase):
    def test_matches_final_series_pot_after_growth(self):
        series = pw.generate_dc_drawdown_series(55, date(2028, 3, 1), 60, 1000000, 4.0, 6.0)
        last = series[-1]
        expected = (last["pot_start"] - last["private_annual"]) * 1.06
        remaining = pw.remaining_dc_pot_at_end(55, date(2028, 3, 1), 60, 1000000, 4.0, 6.0)
        self.assertAlmostEqual(remaining, expected)

    def test_zero_pot_stays_zero(self):
        remaining = pw.remaining_dc_pot_at_end(55, date(2028, 3, 1), 60, 0.0, 4.0, 6.0)
        self.assertEqual(remaining, 0.0)


class TestAccumulatePensionPot(unittest.TestCase):
    def test_nmpa_date_not_after_today_returns_pot_unchanged(self):
        result = pw.accumulate_pension_pot(
            1000000, today=date(2028, 3, 1), nmpa_date=date(2028, 3, 1),
            annual_contribution=9000, growth_rate_pct=6.0)
        self.assertEqual(result, 1000000)

    def test_one_whole_year_adds_contribution_then_grows(self):
        result = pw.accumulate_pension_pot(
            1000000, today=date(2027, 3, 1), nmpa_date=date(2028, 3, 1),
            annual_contribution=9000, growth_rate_pct=6.0)
        self.assertAlmostEqual(result, (1000000 + 9000) * 1.06)

    def test_multiple_years_compound(self):
        one_year = pw.accumulate_pension_pot(
            1000000, today=date(2027, 3, 1), nmpa_date=date(2028, 3, 1),
            annual_contribution=9000, growth_rate_pct=6.0)
        two_years = pw.accumulate_pension_pot(
            1000000, today=date(2026, 3, 1), nmpa_date=date(2028, 3, 1),
            annual_contribution=9000, growth_rate_pct=6.0)
        self.assertAlmostEqual(two_years, (one_year + 9000) * 1.06)

    def test_partial_final_year_not_counted(self):
        # Only 11 months remain (2027-04-01 to 2028-03-01) - not a whole
        # year, so no contribution/growth is applied for it.
        result = pw.accumulate_pension_pot(
            1000000, today=date(2027, 4, 1), nmpa_date=date(2028, 3, 1),
            annual_contribution=9000, growth_rate_pct=6.0)
        self.assertEqual(result, 1000000)

    def test_zero_contribution_still_applies_growth(self):
        result = pw.accumulate_pension_pot(
            1000000, today=date(2027, 3, 1), nmpa_date=date(2028, 3, 1),
            annual_contribution=0, growth_rate_pct=6.0)
        self.assertAlmostEqual(result, 1000000 * 1.06)


class TestParseSalary(unittest.TestCase):
    def test_valid_salary_parsed_as_float(self):
        self.assertEqual(pw.parse_salary("60000"), 60000.0)

    def test_zero_is_allowed(self):
        self.assertEqual(pw.parse_salary("0"), 0.0)

    def test_max_is_allowed(self):
        self.assertEqual(pw.parse_salary("1000000"), 1000000.0)

    def test_above_max_is_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            pw.parse_salary("1000001")

    def test_negative_is_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            pw.parse_salary("-1")

    def test_non_numeric_is_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            pw.parse_salary("not-a-number")


class TestCalculateGiftingSummary(unittest.TestCase):
    def test_zero_recipients_gives_zero_ceiling(self):
        s = pw.calculate_gifting_summary(0, 0, 250.0, 3000.0, None, 50000, 0, None)
        self.assertEqual(s["num_recipients"], 0)
        self.assertEqual(s["small_gifts_total"], 0.0)
        self.assertEqual(s["tax_free_ceiling"], 3000.0)  # annual exemption still applies

    def test_small_gifts_total_uses_statutory_default_when_no_custom_rate(self):
        s = pw.calculate_gifting_summary(2, 3, 250.0, 3000.0, None, 50000, 0, None)
        self.assertEqual(s["num_recipients"], 5)
        self.assertEqual(s["per_recipient_amount"], 250.0)
        self.assertFalse(s["is_custom_rate"])
        self.assertEqual(s["small_gifts_total"], 1250.0)
        self.assertEqual(s["tax_free_ceiling"], 1250.0 + 3000.0)

    def test_custom_gift_per_recipient_overrides_small_gift_amount(self):
        s = pw.calculate_gifting_summary(3, 0, 250.0, 3000.0, 1000.0, 50000, 0, None)
        self.assertTrue(s["is_custom_rate"])
        self.assertEqual(s["per_recipient_amount"], 1000.0)
        self.assertEqual(s["small_gifts_total"], 3000.0)
        self.assertEqual(s["tax_free_ceiling"], 6000.0)

    def test_recommended_gift_capped_by_surplus_when_surplus_is_lower(self):
        s = pw.calculate_gifting_summary(2, 3, 250.0, 3000.0, None,
                                          available_income=24000, essential_spending=40000,
                                          planned_annual_gift=None)
        self.assertEqual(s["surplus"], 0.0)
        self.assertEqual(s["recommended_gift"], 0.0)

    def test_recommended_gift_is_full_ceiling_when_surplus_is_ample(self):
        s = pw.calculate_gifting_summary(2, 3, 250.0, 3000.0, None,
                                          available_income=100000, essential_spending=20000,
                                          planned_annual_gift=None)
        self.assertEqual(s["surplus"], 80000.0)
        self.assertEqual(s["recommended_gift"], s["tax_free_ceiling"])

    def test_surplus_never_negative(self):
        s = pw.calculate_gifting_summary(1, 0, 250.0, 3000.0, None,
                                          available_income=10000, essential_spending=50000,
                                          planned_annual_gift=None)
        self.assertEqual(s["surplus"], 0.0)

    def test_no_planned_gift_leaves_excess_none(self):
        s = pw.calculate_gifting_summary(1, 0, 250.0, 3000.0, None, 50000, 0, None)
        self.assertIsNone(s["excess_over_ceiling"])

    def test_planned_gift_within_ceiling_has_zero_excess(self):
        s = pw.calculate_gifting_summary(1, 0, 250.0, 3000.0, None, 50000, 0,
                                          planned_annual_gift=2000.0)
        self.assertEqual(s["excess_over_ceiling"], 0.0)

    def test_planned_gift_over_ceiling_reports_exact_excess(self):
        s = pw.calculate_gifting_summary(2, 3, 250.0, 3000.0, None, 50000, 0,
                                          planned_annual_gift=6000.0)
        self.assertEqual(s["tax_free_ceiling"], 4250.0)
        self.assertEqual(s["excess_over_ceiling"], 1750.0)


class TestPrintGiftingSummary(unittest.TestCase):
    def test_zero_recipients_prints_nothing_to_show(self):
        s = pw.calculate_gifting_summary(0, 0, 250.0, 3000.0, None, 50000, 0, None)
        buf = io.StringIO()
        with redirect_stdout(buf):
            pw.print_gifting_summary(s)
        self.assertIn("nothing to show", buf.getvalue())

    def test_summary_shows_ceiling_breakdown(self):
        s = pw.calculate_gifting_summary(2, 3, 250.0, 3000.0, None, 50000, 20000, None)
        buf = io.StringIO()
        with redirect_stdout(buf):
            pw.print_gifting_summary(s)
        output = buf.getvalue()
        self.assertIn("Recipients: 5", output)
        self.assertIn("Small gifts total: £1,250.00", output)
        self.assertIn("Annual exemption (total pot, not per person): £3,000.00", output)
        self.assertIn("Maximum tax-free gifts this year: £4,250.00", output)

    def test_excess_flagged_as_pet_when_over_ceiling(self):
        s = pw.calculate_gifting_summary(2, 3, 250.0, 3000.0, None, 50000, 0,
                                          planned_annual_gift=6000.0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            pw.print_gifting_summary(s)
        output = buf.getvalue()
        self.assertIn("£1,750.00 OVER the tax-free ceiling", output)
        self.assertIn("Potentially Exempt Transfer (PET)", output)

    def test_no_excess_message_when_within_ceiling(self):
        s = pw.calculate_gifting_summary(2, 3, 250.0, 3000.0, None, 50000, 0,
                                          planned_annual_gift=2000.0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            pw.print_gifting_summary(s)
        output = buf.getvalue()
        self.assertIn("within the tax-free ceiling, no excess", output)
        self.assertNotIn("OVER the tax-free ceiling", output)

    def test_no_planned_gift_omits_plan_lines(self):
        s = pw.calculate_gifting_summary(2, 3, 250.0, 3000.0, None, 50000, 0, None)
        buf = io.StringIO()
        with redirect_stdout(buf):
            pw.print_gifting_summary(s)
        output = buf.getvalue()
        self.assertNotIn("You plan to gift", output)


class TestApplyInheritedPot(unittest.TestCase):
    def test_no_inherited_income_returns_rows_unchanged(self):
        rows = pw.generate_income_table(55, date(2028, 3, 1), 57, 10000, 0.0)
        result = pw.apply_inherited_pot(rows, [], today=None, discount_rate_pct=2.5)
        self.assertEqual(result, rows)

    def test_inherited_income_added_only_to_matching_years(self):
        rows = pw.generate_income_table(55, date(2028, 3, 1), 57, 10000, 0.0)
        inherited = pw.generate_dc_drawdown_series(
            55, date(2028, 3, 1), 57, 0.0, 4.0, 0.0,
            injection_date=date(2029, 3, 1), injection_amount=100000,
        )
        result = pw.apply_inherited_pot(rows, inherited, today=None, discount_rate_pct=2.5)
        by_age = {r["age"]: r for r in result}
        self.assertEqual(by_age[55]["private_annual"], 10000.0)  # unaffected
        self.assertAlmostEqual(by_age[56]["private_annual"], 10000.0 + 100000.0 * 0.04)
        self.assertAlmostEqual(by_age[56]["annual"], by_age[56]["private_annual"])


class TestApplyPensionTransfer(unittest.TestCase):
    def make_summary(self, life_expectancy_date, nmpa_age=55, nmpa_date=date(2028, 3, 1),
                      life_expectancy_age=78, spa_date=date(2040, 3, 1)):
        return pw.PersonSummary(
            spa_date=spa_date, nmpa_age=nmpa_age, nmpa_date=nmpa_date,
            life_expectancy_age=life_expectancy_age,
            life_expectancy_date=life_expectancy_date,
        )

    def test_no_transfer_when_life_expectancy_dates_equal(self):
        summary = self.make_summary(date(2051, 3, 1))
        your_rows = pw.generate_dc_drawdown_table(55, date(2028, 3, 1), 78, 1000000, 4.0, 6.0)
        spouse_rows = pw.generate_income_table(55, date(2028, 3, 1), 78, 18000, 2.0)
        result = pw.apply_pension_transfer(
            summary, summary, your_rows, spouse_rows,
            1000000, 4.0, 6.0, None, 4.0, 6.0,
            230.25, 2.5, 2.5, date(2026, 1, 1),
        )
        self.assertEqual(result, (your_rows, spouse_rows, None))

    def test_no_transfer_when_deceased_used_flat_income(self):
        your_summary = self.make_summary(date(2051, 3, 1))
        spouse_summary = self.make_summary(date(2058, 3, 1))
        your_rows = pw.generate_income_table(55, date(2028, 3, 1), 78, 24000, 2.0)
        spouse_rows = pw.generate_income_table(55, date(2028, 3, 1), 78, 18000, 2.0)
        _, _, note = pw.apply_pension_transfer(
            your_summary, spouse_summary, your_rows, spouse_rows,
            None, 4.0, 6.0, None, 4.0, 6.0,
            230.25, 2.5, 2.5, date(2026, 1, 1),
        )
        self.assertIsNone(note)

    def test_earlier_life_expectancy_pot_transfers_to_survivor(self):
        your_summary = self.make_summary(date(2051, 3, 1), life_expectancy_age=78)
        spouse_summary = self.make_summary(date(2058, 4, 1), nmpa_date=date(2033, 4, 1),
                                            life_expectancy_age=82)
        your_rows = pw.generate_dc_drawdown_table(
            55, date(2028, 3, 1), 78, 1000000, 4.0, 6.0,
            your_summary.spa_date, 230.25, 2.5, date(2026, 1, 1), 2.5)
        spouse_rows = pw.generate_income_table(
            57, date(2033, 4, 1), 82, 18000, 2.0,
            spouse_summary.spa_date, 230.25, 2.5, date(2026, 1, 1), 2.5)

        new_your_rows, new_spouse_rows, note = pw.apply_pension_transfer(
            your_summary, spouse_summary, your_rows, spouse_rows,
            1000000, 4.0, 6.0, None, 4.0, 6.0,
            230.25, 2.5, 2.5, date(2026, 1, 1),
        )

        self.assertIsNotNone(note)
        self.assertIn("You reach average life expectancy first", note)
        # The deceased's own rows are untouched.
        self.assertEqual(new_your_rows, your_rows)
        # The survivor's rows for years after the transfer gain extra income.
        old_by_year = {r["date"].year: r for r in spouse_rows}
        new_by_year = {r["date"].year: r for r in new_spouse_rows}
        year_after_death = 2052
        self.assertGreater(
            new_by_year[year_after_death]["private_annual"],
            old_by_year[year_after_death]["private_annual"],
        )
        # Years before the deceased's death are unaffected.
        self.assertEqual(
            new_by_year[2040]["private_annual"], old_by_year[2040]["private_annual"])

    def test_survivor_with_own_pot_gets_merged_pot(self):
        your_summary = self.make_summary(date(2051, 3, 1), life_expectancy_age=78)
        spouse_summary = self.make_summary(date(2058, 4, 1), nmpa_date=date(2033, 4, 1),
                                            life_expectancy_age=82)
        your_rows = pw.generate_dc_drawdown_table(
            55, date(2028, 3, 1), 78, 1000000, 4.0, 6.0,
            your_summary.spa_date, 230.25, 2.5, date(2026, 1, 1), 2.5)
        spouse_rows = pw.generate_dc_drawdown_table(
            57, date(2033, 4, 1), 82, 500000, 4.0, 6.0,
            spouse_summary.spa_date, 230.25, 2.5, date(2026, 1, 1), 2.5)

        _, new_spouse_rows, note = pw.apply_pension_transfer(
            your_summary, spouse_summary, your_rows, spouse_rows,
            1000000, 4.0, 6.0, 500000, 4.0, 6.0,
            230.25, 2.5, 2.5, date(2026, 1, 1),
        )

        self.assertIsNotNone(note)
        # Result still has a pot column (survivor's own pot, boosted).
        self.assertIn("pot_start", new_spouse_rows[0])
        old_by_year = {r["date"].year: r for r in spouse_rows}
        new_by_year = {r["date"].year: r for r in new_spouse_rows}
        self.assertGreater(
            new_by_year[2052]["pot_start"], old_by_year[2052]["pot_start"])

    def test_no_transfer_when_remaining_pot_not_positive(self):
        your_summary = self.make_summary(date(2051, 3, 1), life_expectancy_age=78)
        spouse_summary = self.make_summary(date(2058, 4, 1), nmpa_date=date(2033, 4, 1),
                                            life_expectancy_age=82)
        your_rows = pw.generate_dc_drawdown_table(55, date(2028, 3, 1), 78, 100000, 100.0, 0.0)
        spouse_rows = pw.generate_income_table(57, date(2033, 4, 1), 82, 18000, 2.0)
        _, _, note = pw.apply_pension_transfer(
            your_summary, spouse_summary, your_rows, spouse_rows,
            100000, 100.0, 0.0, None, 4.0, 6.0,
            230.25, 2.5, 2.5, date(2026, 1, 1),
        )
        self.assertIsNone(note)


class TestPrintIncomeTable(unittest.TestCase):
    def test_empty_rows_prints_no_projection_message(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            pw.print_income_table("You", [], ["some assumption"])
        self.assertIn("no income projection generated", buf.getvalue())

    def test_non_empty_rows_prints_header_assumptions_and_values(self):
        rows = pw.generate_income_table(55, date(2028, 3, 1), 56, 24000, 0.0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            pw.print_income_table("You", rows, ["Starting income: £24,000.00/year"])
        output = buf.getvalue()
        self.assertIn("You projected pension income", output)
        self.assertIn("Starting income: £24,000.00/year", output)
        self.assertIn("2028", output)
        self.assertIn("462", output)  # weekly = round(24000/52)

    def test_dc_drawdown_rows_show_pot_column(self):
        rows = pw.generate_dc_drawdown_table(55, date(2028, 3, 1), 55, 1000000, 4.0, 6.0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            pw.print_income_table("You", rows, ["DC pot: £1,000,000.00"])
        output = buf.getvalue()
        self.assertIn("Pot", output)
        self.assertIn("Draw", output)
        self.assertIn("1,000,000", output)

    def test_flat_growth_rows_have_no_pot_column(self):
        rows = pw.generate_income_table(55, date(2028, 3, 1), 55, 24000, 0.0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            pw.print_income_table("You", rows, ["Starting income: £24,000.00/year"])
        output = buf.getvalue()
        self.assertNotIn("Draw", output)

    def test_present_and_future_columns_both_shown(self):
        rows = pw.generate_income_table(
            55, date(2028, 3, 1), 55, 24000, 0.0, today=date(2026, 7, 9))
        buf = io.StringIO()
        with redirect_stdout(buf):
            pw.print_income_table("You", rows, ["Starting income: £24,000.00/year"])
        output = buf.getvalue()
        self.assertIn("FV", output)
        self.assertIn("PV", output)

    def test_table_rows_fit_within_80_characters(self):
        rows = pw.generate_dc_drawdown_table(55, date(2028, 3, 1), 78, 1000000, 4.0, 6.0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            pw.print_income_table("You", rows, ["DC pot: £1,000,000.00"])
        lines = [line for line in buf.getvalue().splitlines() if line.strip()]
        self.assertTrue(all(len(line) <= 80 for line in lines))


class TestCombineIncomeTables(unittest.TestCase):
    def test_overlapping_years_sum_both_incomes(self):
        rows_a = pw.generate_income_table(55, date(2028, 3, 1), 57, 10000, 0.0)
        rows_b = pw.generate_income_table(55, date(2028, 4, 1), 57, 5000, 0.0)
        combined = pw.combine_income_tables(rows_a, rows_b)
        by_year = {r["year"]: r for r in combined}
        self.assertEqual(by_year[2028]["your_annual"], 10000.0)
        self.assertEqual(by_year[2028]["spouse_annual"], 5000.0)
        self.assertEqual(by_year[2028]["annual"], 15000.0)

    def test_non_overlapping_years_contribute_zero_for_absent_person(self):
        rows_a = pw.generate_income_table(55, date(2028, 3, 1), 56, 10000, 0.0)
        rows_b = pw.generate_income_table(60, date(2035, 3, 1), 61, 5000, 0.0)
        combined = pw.combine_income_tables(rows_a, rows_b)
        by_year = {r["year"]: r for r in combined}
        self.assertEqual(by_year[2028]["your_annual"], 10000.0)
        self.assertEqual(by_year[2028]["spouse_annual"], 0.0)
        self.assertEqual(by_year[2035]["your_annual"], 0.0)
        self.assertEqual(by_year[2035]["spouse_annual"], 5000.0)

    def test_years_sorted_and_deduplicated(self):
        rows_a = pw.generate_income_table(55, date(2028, 3, 1), 57, 10000, 0.0)
        rows_b = pw.generate_income_table(56, date(2029, 3, 1), 58, 5000, 0.0)
        combined = pw.combine_income_tables(rows_a, rows_b)
        years = [r["year"] for r in combined]
        self.assertEqual(years, sorted(set(years)))
        self.assertEqual(years, [2028, 2029, 2030, 2031])

    def test_present_values_summed_too(self):
        rows_a = pw.generate_income_table(
            55, date(2028, 3, 1), 55, 10000, 0.0, today=date(2026, 1, 1))
        rows_b = pw.generate_income_table(
            55, date(2028, 4, 1), 55, 5000, 0.0, today=date(2026, 1, 1))
        combined = pw.combine_income_tables(rows_a, rows_b)
        self.assertAlmostEqual(
            combined[0]["present_annual"],
            rows_a[0]["present_annual"] + rows_b[0]["present_annual"])

    def test_empty_inputs_produce_empty_table(self):
        self.assertEqual(pw.combine_income_tables([], []), [])


class TestPrintCombinedIncomeTable(unittest.TestCase):
    def test_empty_rows_prints_not_generated_message(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            pw.print_combined_income_table([])
        self.assertIn("not generated", buf.getvalue())

    def test_non_empty_rows_prints_header_and_values(self):
        rows_a = pw.generate_income_table(55, date(2028, 3, 1), 55, 10000, 0.0)
        rows_b = pw.generate_income_table(55, date(2028, 4, 1), 55, 5000, 0.0)
        combined = pw.combine_income_tables(rows_a, rows_b)
        buf = io.StringIO()
        with redirect_stdout(buf):
            pw.print_combined_income_table(combined)
        output = buf.getvalue()
        self.assertIn("Combined household projected pension income", output)
        self.assertIn("You", output)
        self.assertIn("Spouse", output)
        self.assertIn("2028", output)
        self.assertIn("15,000", output)  # combined future annual


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
        self.assertNotIn("projected pension income", result.stdout)

    def test_income_flag_prints_projection_table(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M", "--income", "24000",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("You projected pension income", result.stdout)
        self.assertIn("Starting private pension income: £24,000.00/year, "
                       "growing at 2.0% per year", result.stdout)
        self.assertIn("FV = nominal future value", result.stdout)
        # First row (age 55): state pension not yet due (£0), FV equals the
        # unchanged starting income. (PV not asserted exactly - depends on
        # today's date.)
        self.assertIn(
            "55 2028   24,000       0     462   2,000    24,000", result.stdout)
        # SPA reached at age 67 (2040): State Pension added on top.
        self.assertIn(
            "67 2040   30,438  11,973     816   3,534    42,411", result.stdout)
        # Last row: age 78 (life expectancy).
        self.assertIn("78 2051", result.stdout)

    def test_table_rows_fit_within_80_characters(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M",
            "--pension-pot", "1000000", "--income-growth-rate", "0",
        )
        self.assertEqual(result.returncode, 0)
        table_lines = [
            line for line in result.stdout.splitlines()
            if line.strip() and line.strip().split()[0].isdigit()
        ]
        self.assertTrue(table_lines)
        self.assertTrue(all(len(line) <= 80 for line in table_lines))

    def test_custom_growth_rate_is_applied(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M",
            "--income", "10000", "--income-growth-rate", "0",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("growing at 0.0% per year", result.stdout)
        # Private column flat at 10,000 for all 24 rows (age 55-78); FV
        # also reads 10,000 for the 12 pre-SPA rows (no State Pension yet,
        # age 55-66); plus one header occurrence ("£10,000.00").
        self.assertEqual(result.stdout.count("10,000"), 24 + 12 + 1)

    def test_state_pension_included_by_default(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M", "--income", "24000",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("State Pension added from SPA: £230.25/week "
                       "(£11,973.00/year), growing at 2.5% per year "
                       "(assumed triple lock)", result.stdout)

    def test_state_pension_weekly_override(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M", "--income", "24000",
            "--state-pension-weekly", "300",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("State Pension added from SPA: £300.00/week "
                       "(£15,600.00/year)", result.stdout)

    def test_state_pension_growth_rate_override(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M", "--income", "24000",
            "--state-pension-growth-rate", "5",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("growing at 5.0% per year (assumed triple lock)", result.stdout)

    def test_discount_rate_shown_and_overridable(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M", "--income", "24000",
            "--discount-rate", "3.5",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(
            f"Present values discounted at 3.5% per year (assumed inflation) "
            f"back to today ({date.today().isoformat()})", result.stdout)

    def test_pension_pot_triggers_dc_drawdown_table(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M",
            "--pension-pot", "1000000", "--drawdown-rate", "4",
            "--pot-growth-rate", "6",
        )
        self.assertEqual(result.returncode, 0)
        # Default --salary (100) still runs the pot through the
        # today-to-NMPA-age accumulation phase (negligible contribution,
        # but real investment growth), so the table's opening pot is
        # slightly above the raw --pension-pot value - see the assumption
        # lines for the exact accumulated figure.
        self.assertIn("DC pension pot today: £1,000,000.00; employer "
                       "contribution: 15.0% of £100.00 salary", result.stdout)
        self.assertIn("Pot after contributions and 6.0% growth to access "
                       "age:", result.stdout)
        self.assertIn("Pot", result.stdout)
        self.assertIn("Draw", result.stdout)

    def test_pension_pot_takes_priority_over_income(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M",
            "--income", "24000", "--pension-pot", "1000000",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("DC pension pot", result.stdout)
        self.assertNotIn("Starting private pension income", result.stdout)

    def test_salary_shows_employer_contribution_amount_and_rate(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M",
            "--pension-pot", "1000000", "--salary", "60000",
            "--employer-contribution-rate", "15",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("employer contribution: 15.0% of £60,000.00 salary = "
                       "£9,000.00/year", result.stdout)

    def test_default_salary_has_negligible_contribution(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M", "--pension-pot", "1000000",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("£100.00 salary = £15.00/year", result.stdout)

    def test_employer_contribution_rate_override(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M",
            "--pension-pot", "1000000", "--salary", "60000",
            "--employer-contribution-rate", "10",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("employer contribution: 10.0% of £60,000.00 salary = "
                       "£6,000.00/year", result.stdout)

    def test_salary_above_one_million_is_rejected(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M",
            "--pension-pot", "1000000", "--salary", "1000001",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Salary must be between", result.stderr)

    def test_salary_ignored_without_pension_pot(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M",
            "--income", "24000", "--salary", "60000",
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("employer contribution", result.stdout)

    def test_gifting_summary_shown_with_recipients(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M", "--income", "24000",
            "--num-children", "2", "--num-grandchildren", "3",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Tax-free gifting to children/grandchildren (per year)", result.stdout)
        self.assertIn("Recipients: 5", result.stdout)
        self.assertIn("Maximum tax-free gifts this year: £4,250.00", result.stdout)

    def test_gifting_summary_omitted_without_recipients(self):
        result = self.run_cli("--dob", "1973-03-01", "--sex", "M", "--income", "24000")
        self.assertEqual(result.returncode, 0)
        self.assertIn("no children or grandchildren given", result.stdout)

    def test_gifting_custom_rate_and_planned_gift_excess(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M", "--income", "24000",
            "--num-children", "3", "--gift-per-recipient", "1000",
            "--planned-annual-gift", "10000",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("3 (£1,000.00 each - custom rate)", result.stdout)
        self.assertIn("Maximum tax-free gifts this year: £6,000.00", result.stdout)
        self.assertIn("£4,000.00 OVER the tax-free ceiling", result.stdout)
        self.assertIn("Potentially Exempt Transfer (PET)", result.stdout)

    def test_gifting_essential_spending_reduces_surplus(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M", "--income", "24000",
            "--num-children", "1", "--essential-spending", "23000",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("surplus £1,000.00", result.stdout)
        self.assertIn("capped by your surplus, below the tax-free ceiling", result.stdout)

    def test_spouse_income_only_shown_for_spouse(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M",
            "--spouse-dob", "1976-04-01", "--spouse-sex", "F",
            "--spouse-income", "18000",
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("You projected pension income", result.stdout)
        self.assertIn("Your spouse projected pension income", result.stdout)
        self.assertIn("Starting private pension income: £18,000.00/year",
                       result.stdout)

    def test_spouse_pension_pot_independent_of_your_mode(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M", "--income", "24000",
            "--spouse-dob", "1976-04-01", "--spouse-sex", "F",
            "--spouse-pension-pot", "500000",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Starting private pension income: £24,000.00/year",
                       result.stdout)
        self.assertIn("DC pension pot: £500,000.00 starting value", result.stdout)

    def test_combined_table_shown_when_both_have_income(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M", "--income", "24000",
            "--spouse-dob", "1976-04-01", "--spouse-sex", "F",
            "--spouse-income", "18000",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Combined household projected pension income", result.stdout)
        self.assertIn("Year      You   Spouse", result.stdout)

    def test_combined_table_omitted_when_only_one_has_income(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M", "--income", "24000",
            "--spouse-dob", "1976-04-01", "--spouse-sex", "F",
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("Combined household projected pension income", result.stdout)

    def test_combined_table_omitted_without_spouse(self):
        result = self.run_cli(
            "--dob", "1973-03-01", "--sex", "M", "--income", "24000",
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("Combined household projected pension income", result.stdout)

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
