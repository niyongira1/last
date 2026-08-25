import numpy as np
import pandas as pd

from model import compute_indices

GROWTH_RATE_MEAN = 0.023
GROWTH_RATE_SD = 0.006


def project_population(raw_df, years=10, n_sim=2000, w2=0.67,
                        growth_mean=GROWTH_RATE_MEAN, growth_sd=GROWTH_RATE_SD, seed=7):
    rng = np.random.default_rng(seed)
    base = compute_indices(raw_df)
    district_schools_per_10k_now = base["Total_Schools"].sum() / base["Population"].sum() * 10000
    w1 = 1 - w2

    records = []
    for _, row in base.iterrows():
        for year in range(0, years + 1):
            growth_draws = rng.normal(growth_mean, growth_sd, n_sim)
            growth_draws = np.clip(growth_draws, -0.02, 0.08)
            pop_future = row["Population"] * (1 + growth_draws) ** year

            schools_per_10k_future = row["Total_Schools"] / pop_future * 10000
            c2_future = schools_per_10k_future / district_schools_per_10k_now
            cwai_future = w1 * row["C1_Density_Index"] + w2 * c2_future

            records.append({
                "Sector": row["Sector"],
                "Year": 2026 + year,
                "CWAI_mean": cwai_future.mean(),
                "CWAI_p10": np.percentile(cwai_future, 10),
                "CWAI_p90": np.percentile(cwai_future, 90),
                "Prob_Below_District_Average": float((cwai_future < 1.0).mean()),
            })

    return pd.DataFrame(records)
