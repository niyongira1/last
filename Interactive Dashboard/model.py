"""
Same composite accessibility model as the standalone Python project and the
notebook, kept here too so this dashboard repo is self-contained and does
not depend on files outside itself.
"""

import pandas as pd

RAW_SECTOR_DATA = [
    # Sector,        Population, Area_km2, Primary_Schools, Secondary_Schools
    ("Bungwe",        16322, 25, 5, 3),
    ("Butaro",        38013, 59, 6, 7),
    ("Cyanika",       44510, 40, 9, 5),
    ("Cyeru",         14719, 23, 4, 4),
    ("Gahunga",       28059, 38, 4, 3),
    ("Gatebe",        18867, 39, 5, 2),
    ("Gitovu",        11531, 38, 3, 3),
    ("Kagogo",        23089, 27, 4, 4),
    ("Kinoni",        19017, 30, 5, 4),
    ("Kinyababa",     23746, 54, 4, 4),
    ("Kivuye",        18057, 37, 5, 4),
    ("Nemba",         21401, 38, 5, 3),
    ("Rugarama",      27051, 33, 4, 4),
    ("Rugengabari",   20920, 30, 4, 2),
    ("Ruhunde",       20157, 43, 3, 2),
    ("Rusarabuye",    20659, 42, 7, 3),
    ("Rwerere",       21611, 48, 4, 2),
]


def load_sector_data():
    return pd.DataFrame(
        RAW_SECTOR_DATA,
        columns=["Sector", "Population", "Area_km2", "Primary_Schools", "Secondary_Schools"],
    )


def compute_indices(df):
    df = df.copy()
    df["Total_Schools"] = df["Primary_Schools"] + df["Secondary_Schools"]

    district_primary_density = df["Primary_Schools"].sum() / df["Area_km2"].sum()
    district_secondary_density = df["Secondary_Schools"].sum() / df["Area_km2"].sum()

    df["Primary_Access_Index"] = (df["Primary_Schools"] / df["Area_km2"]) / district_primary_density
    df["Secondary_Access_Index"] = (df["Secondary_Schools"] / df["Area_km2"]) / district_secondary_density
    df["C1_Density_Index"] = (df["Primary_Access_Index"] + df["Secondary_Access_Index"]) / 2

    district_schools_per_10k = df["Total_Schools"].sum() / df["Population"].sum() * 10000
    df["Schools_per_10k"] = df["Total_Schools"] / df["Population"] * 10000
    df["C2_Population_Index"] = df["Schools_per_10k"] / district_schools_per_10k

    return df


def compute_cwai(df, w2=0.67):
    df = df.copy()
    w1 = 1 - w2
    df["CWAI"] = w1 * df["C1_Density_Index"] + w2 * df["C2_Population_Index"]
    df = df.sort_values("CWAI").reset_index(drop=True)
    df["Composite_Rank"] = df.index + 1
    return df


def classify_tiers(df, group_sizes=(2, 3, 3, 3, 6),
                    labels=("Priority 1, Critical", "Priority 2, High", "Priority 3, Moderate",
                            "Priority 4, Below Average", "Priority 5, Adequate")):
    assert sum(group_sizes) == len(df)
    df = df.sort_values("CWAI").reset_index(drop=True)
    tiers = []
    for size, label in zip(group_sizes, labels):
        tiers.extend([label] * size)
    df["Tier"] = tiers
    return df


def area_based_rank(df):
    ranked = df.sort_values("C1_Density_Index").reset_index(drop=True)
    ranked["Area_Based_Rank"] = ranked.index + 1
    return ranked[["Sector", "Area_Based_Rank"]]
