"""Central reference data seeded into the database on startup.

This is the maintained, versioned copy of the tax tables and market-return
history that the single-page client otherwise carries as built-ins. Bump
REFERENCE_VERSION whenever a table changes; the client shows the version it
is running against. Band thresholds are statutory GROSS thresholds; the
client subtracts the personal allowance itself where a country applies one.
"""

REFERENCE_VERSION = "2025-26.1"

TAX_TABLES = {
    "UK": {
        # Personal allowance, tapered 50p per £1 of income above the taper threshold.
        "pa": 12570,
        "paTaperFrom": 100000,
        # England / Wales / NI bands: [gross threshold, marginal rate].
        "bands": [[12570, 0.20], [50270, 0.40], [125140, 0.45]],
        # Scottish bands (starter/basic/intermediate/higher/advanced/top).
        "scotBands": [[12570, 0.19], [15397, 0.20], [27491, 0.21],
                      [43662, 0.42], [75000, 0.45], [125140, 0.48]],
        # Employee Class 1 National Insurance (gross thresholds, no allowance).
        "niBands": [[12570, 0.08], [50270, 0.02]],
        # UFPLS drawdown: this share of each private withdrawal is tax-free.
        "ufplsTaxFree": 0.25,
    },
    "US": {
        # 2025 federal, single filer.
        "stdDeduction": 15000,
        "bands": [[0, 0.10], [11925, 0.12], [48475, 0.22], [103350, 0.24],
                  [197300, 0.32], [250525, 0.35], [626350, 0.37]],
    },
    "FR": {
        # 2025 barème, 1 part per person.
        "bands": [[11497, 0.11], [29315, 0.30], [83823, 0.41], [180294, 0.45]],
    },
    "AU": {
        # 2024-25 resident rates.
        "bands": [[18200, 0.16], [45000, 0.30], [135000, 0.37], [190000, 0.45]],
        "medicareRate": 0.02,
        "medicareFrom": 26000,
        "superTaxFreeAge": 60,
    },
}

# Approximate annual REAL total returns (%) for a UK/global equity portfolio
# (FTSE All-Share-like), 1925-2024. Reconstructed to match the published
# shape of the historical record; an approximation for stress-testing only,
# not a licensed data series. Must stay in step with the client's built-in
# copy so offline and online behaviour agree.
HIST_REAL_RETURNS = [
    # 1925-34
    27, 3, 9, 12, -20, -12, -25, 32, 21, 10,
    # 1935-44
    8, 10, -14, -8, -5, -12, 12, 14, 8, 9,
    # 1945-54
    4, 12, 2, -8, -6, 4, 2, -6, 18, 36,
    # 1955-64
    4, -8, 2, 30, 40, -4, -3, -4, 12, -8,
    # 1965-74
    3, -12, 24, 38, -18, -12, 34, 8, -35, -58,
    # 1975-84
    87, -6, 34, 2, -4, 18, 2, 20, 23, 26,
    # 1985-94
    15, 22, 4, 6, 27, -17, 13, 16, 23, -9,
    # 1995-04
    17, 12, 20, 11, 21, -8, -15, -24, 17, 9,
    # 2005-14
    19, 13, 1, -33, 25, 10, -8, 9, 18, 0,
    # 2015-24
    0, 15, 9, -12, 17, -12, 14, -8, 4, 7,
]


def reference_payload():
    """The document served at /api/reference and stored in the DB."""
    return {
        "version": REFERENCE_VERSION,
        "taxTables": TAX_TABLES,
        "returns": HIST_REAL_RETURNS,
        "returnsStartYear": 1925,
    }
