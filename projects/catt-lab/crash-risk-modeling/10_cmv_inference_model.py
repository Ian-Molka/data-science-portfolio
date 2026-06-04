import pandas as pd
import numpy as np
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.outliers_influence import variance_inflation_factor
from pathlib import Path

# ============================================================
# CMV Crash Inference Model (Segment-level Negative Binomial)
# - NO post-crash speed predictors
# - Drops speed_diff_at (multicollinearity fix)
# - Weather collapsed to precipitation indicator
# - Robust SEs (HC0)
# ============================================================

FILE = r"data/input_file.csv"

OUT_SUMMARY = r"data/output_file.csv"
OUT_IRR     = r"data/output_file.csv"
OUT_AGG_CSV = r"data/output_file.csv"
OUT_VIF_CSV = r"data/output_file.csv"

VIF_THRESH_WARN = 10.0

# ------------------ helpers ------------------

def mode_or_unknown(s, unknown="UNKNOWN"):
    s = s.dropna()
    if s.empty:
        return unknown
    return s.mode().iloc[0]

def safe_mean(s):
    s = pd.to_numeric(s, errors="coerce")
    return s.mean() if s.notna().any() else np.nan

def collapse_rare(series, min_count=50, other="UNKNOWN"):
    series = series.fillna(other).astype(str)
    vc = series.value_counts()
    return series.where(series.isin(vc[vc >= min_count].index), other)

def compute_vif(df, features):
    X = df[features].replace([np.inf, -np.inf], np.nan).dropna()
    X = sm.add_constant(X)
    return pd.DataFrame({
        "variable": X.columns,
        "VIF": [variance_inflation_factor(X.values, i) for i in range(X.shape[1])]
    }).sort_values("VIF", ascending=False)

# ------------------ main ------------------

def main():
    print("📂 Loading crash file...")
    df = pd.read_csv(FILE, low_memory=False)

    df = df[df["cmv_inferred"] == True].copy()
    print(f"CMV crash records: {len(df):,}")

    # numeric coercion
    for c in ["VMT", "speedlimit", "numberoflanes", "speed_before_15m", "speed_at_crash"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # availability flag (pre + at only)
    df["has_speed_pair"] = (
        df["speed_before_15m"].notna() &
        df["speed_at_crash"].notna()
    ).astype(int)

    # ------------------ WEATHER → PRECIP FLAG ------------------
    precip_terms = {
        "RAINING", "SNOW", "SLEET", "WINTRY MIX",
        "BLOWING SNOW", "BLOWING SAND, SOIL, DIRT"
    }

    def is_precip(x):
        return int(str(x).upper().strip() in precip_terms)

    df["precip_flag"] = df["weather_description"].apply(is_precip)

    # ------------------ aggregation ------------------
    cat_cols = [
        "roadalignment", "roadgrade", "intersectiontype",
        "trafficcontrol", "light", "surfacecondition",
        "roadcondition"
    ]
    cat_cols = [c for c in cat_cols if c in df.columns]

    agg_dict = {
        "vehicleid": "count",
        "has_speed_pair": "mean",
        "precip_flag": "mean",
        "VMT": safe_mean,
        "speedlimit": safe_mean,
        "numberoflanes": safe_mean,
        "speed_before_15m": safe_mean,
        "speed_at_crash": safe_mean
    }
    for c in cat_cols:
        agg_dict[c] = mode_or_unknown

    agg = df.groupby("segment_id").agg(agg_dict).reset_index()
    agg = agg.rename(columns={
        "vehicleid": "CMV_Count",
        "has_speed_pair": "pct_speed_pair"
    })

    agg = agg[(agg["VMT"] > 0) & agg["VMT"].notna()].copy()

    # ------------------ feature engineering ------------------
    agg["speed_diff_before"] = agg["speed_before_15m"] - agg["speedlimit"]
    agg["abs_delta_before_to_at"] = (
        agg["speed_at_crash"] - agg["speed_before_15m"]
    ).abs()

    # collapse rare categories
    for c in cat_cols:
        agg[c] = collapse_rare(agg[c])

    # drop missing
    agg = agg.dropna(subset=[
        "speedlimit", "numberoflanes", "pct_speed_pair",
        "speed_diff_before", "abs_delta_before_to_at", "VMT"
    ])

    print(f"🚛 Segments in model: {len(agg):,}")

    # ------------------ VIF ------------------
    vif_features = [
        "speedlimit",
        "numberoflanes",
        "pct_speed_pair",
        "precip_flag",
        "speed_diff_before",
        "abs_delta_before_to_at"
    ]

    vif = compute_vif(agg, vif_features)
    print("\n📊 VIF:")
    print(vif.to_string(index=False))
    vif.to_csv(OUT_VIF_CSV, index=False)

    # ------------------ MODEL ------------------
    base_terms = [
        "speedlimit",
        "numberoflanes",
        "pct_speed_pair",
        "precip_flag",
        "speed_diff_before",
        "abs_delta_before_to_at"
    ]
    cat_terms = [f"C({c})" for c in cat_cols]

    formula = "CMV_Count ~ " + " + ".join(base_terms + cat_terms)
    print("\n🧾 Model formula:")
    print(formula)

    model = smf.glm(
        formula=formula,
        data=agg,
        family=sm.families.NegativeBinomial(),
        offset=np.log(agg["VMT"])
    ).fit(cov_type="HC0")

    print(model.summary())

    # ------------------ IRR ------------------
    irr = pd.DataFrame({
        "coef": model.params,
        "IRR": np.exp(model.params),
        "p_value": model.pvalues
    }).sort_values("p_value")

    print("\n🔥 IRR:")
    print(irr.head(30).to_string())

    # ------------------ save ------------------
    Path(OUT_SUMMARY).parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_SUMMARY, "w") as f:
        f.write(model.summary().as_text())

    irr.to_csv(OUT_IRR)
    agg.to_csv(OUT_AGG_CSV, index=False)

    print("\n💾 Outputs saved.")

if __name__ == "__main__":
    main()
