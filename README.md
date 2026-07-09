# pensionYear
A program to calculate what year a person in the UK can receive the UK Government State Pension,
when they can access a private pension (SIPP), their average UK life expectancy, and an optional
year-by-year projected pension income table.

## Usage

```
python3 pension_year.py --dob 1973-03-01 --sex M \
  --spouse-dob 1976-04-01 --spouse-sex F \
  --income 24000 --spouse-income 18000
```

`--income` / `--spouse-income` (starting annual private pension income) trigger a projected income
table, from private pension access age up to average UK life expectancy, growing at
`--income-growth-rate` / `--spouse-income-growth-rate` percent per year (default 2.0). From State
Pension age onward, the full new State Pension is added on top (`--state-pension-weekly`, default
the 2025/26 rate of £230.25/week - override if a newer rate applies).

## Tests

Run the test suite (standard library `unittest`, no dependencies to install):

```
python3 -m unittest discover -s tests -t .
```
