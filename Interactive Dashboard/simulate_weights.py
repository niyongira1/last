import numpy as np
import pandas as pd

from model import compute_indices


def run_weight_sensitivity(raw_df, n_iter=10000, w2_low=0.50, w2_high=0.8333, seed=42):
    rng = np.random.default_rng(seed)
    base = compute_indices(raw_df)
    sectors = base["Sector"].to_numpy()
    c1 = base["C1_Density_Index"].to_numpy()
    c2 = base["C2_Population_Index"].to_numpy()

    rank_matrix = np.empty((n_iter, len(sectors)))
    drawn_weights = rng.uniform(w2_low, w2_high, n_iter)

    for i, w2 in enumerate(drawn_weights):
        cwai = (1 - w2) * c1 + w2 * c2
        ranks = pd.Series(cwai).rank(method="min").to_numpy()
        rank_matrix[i, :] = ranks

    result = pd.DataFrame({
        "Sector": sectors,
        "Mean_Rank": rank_matrix.mean(axis=0),
        "Rank_StdDev": rank_matrix.std(axis=0),
        "Best_Rank": rank_matrix.min(axis=0).astype(int),
        "Worst_Rank": rank_matrix.max(axis=0).astype(int),
        "Prob_Top2_Critical": (rank_matrix <= 2).mean(axis=0),
        "Prob_Top5_HighPriority": (rank_matrix <= 5).mean(axis=0),
    }).sort_values("Mean_Rank").reset_index(drop=True)

    return result
