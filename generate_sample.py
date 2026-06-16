"""Generate a realistic sample sales dataset for demoing the agent.

Creates sample_data/superstore_sales.csv with seasonality, regional effects,
category margins, some missing values, and a few outliers — enough to support
diverse business questions (trends, comparisons, correlations, segmentation).
"""
import os

import numpy as np
import pandas as pd

SEED = 42
N = 2400

REGIONS = {"West": 1.25, "East": 1.05, "Central": 0.9, "South": 0.8}
STATES = {
    "West": ["California", "Washington", "Oregon", "Arizona", "Nevada"],
    "East": ["New York", "Pennsylvania", "Massachusetts", "Ohio", "Florida"],
    "Central": ["Texas", "Illinois", "Michigan", "Wisconsin", "Minnesota"],
    "South": ["Georgia", "Tennessee", "Louisiana", "Alabama", "Kentucky"],
}
CATEGORIES = {
    "Technology": {"margin": 0.18, "base": 420,
                   "subs": ["Phones", "Laptops", "Accessories", "Networking"]},
    "Furniture": {"margin": 0.08, "base": 360,
                  "subs": ["Chairs", "Tables", "Bookcases", "Furnishings"]},
    "Office Supplies": {"margin": 0.13, "base": 120,
                        "subs": ["Binders", "Paper", "Storage", "Art", "Pens"]},
}
SEGMENTS = ["Consumer", "Corporate", "Home Office"]
SHIP_MODES = ["Standard Class", "Second Class", "First Class", "Same Day"]


def main():
    rng = np.random.default_rng(SEED)
    start = pd.Timestamp("2023-01-01")
    rows = []
    customers = [f"CUST-{i:04d}" for i in range(1, 401)]

    for i in range(N):
        order_date = start + pd.Timedelta(days=int(rng.integers(0, 730)))
        region = rng.choice(list(REGIONS))
        state = rng.choice(STATES[region])
        category = rng.choice(list(CATEGORIES), p=[0.32, 0.23, 0.45])
        cat = CATEGORIES[category]
        sub = rng.choice(cat["subs"])
        segment = rng.choice(SEGMENTS, p=[0.52, 0.30, 0.18])

        # Seasonality: Q4 lift; regional multiplier; lognormal spread.
        month = order_date.month
        season = 1.35 if month in (11, 12) else (1.15 if month in (3, 4) else 1.0)
        base = cat["base"] * REGIONS[region] * season
        sales = float(base * rng.lognormal(mean=0.0, sigma=0.55))

        quantity = int(rng.integers(1, 9))
        discount = float(rng.choice([0, 0, 0.1, 0.15, 0.2, 0.3, 0.4],
                                     p=[0.34, 0.16, 0.18, 0.12, 0.1, 0.06, 0.04]))

        # Profit shrinks (and can go negative) as discount rises.
        margin = cat["margin"] - discount * 0.55
        profit = sales * margin + rng.normal(0, sales * 0.04)

        ship_days = int(rng.integers(0, 7))
        rows.append({
            "order_id": f"ORD-{2023}-{i:05d}",
            "order_date": order_date.date().isoformat(),
            "ship_date": (order_date + pd.Timedelta(days=ship_days)).date().isoformat(),
            "ship_mode": rng.choice(SHIP_MODES, p=[0.6, 0.2, 0.15, 0.05]),
            "customer_id": rng.choice(customers),
            "segment": segment,
            "region": region,
            "state": state,
            "category": category,
            "sub_category": sub,
            "quantity": quantity,
            "discount": round(discount, 2),
            "sales": round(sales, 2),
            "profit": round(profit, 2),
        })

    df = pd.DataFrame(rows)

    # Inject a little realistic messiness.
    null_idx = rng.choice(df.index, size=int(0.03 * N), replace=False)
    df.loc[null_idx, "discount"] = np.nan
    outlier_idx = rng.choice(df.index, size=6, replace=False)
    df.loc[outlier_idx, "sales"] = df.loc[outlier_idx, "sales"] * rng.uniform(8, 14, 6)

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "superstore_sales.csv")
    df.to_csv(path, index=False)
    print(f"Wrote {len(df):,} rows to {path}")


if __name__ == "__main__":
    main()
