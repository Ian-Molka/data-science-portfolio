import pandas as pd
import numpy as np
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.outliers_influence import variance_inflation_factor
from pathlib import Path

# ============================================================
# CMV Crash Inference Model (Segment-level)
# - Builds the SAME aggregated dataset you’re using now
# - Fits a Poisson baseline (with log(VMT) offset)
# - Fits Negative Binomial GLM (with log(VMT) offset)
# - Compares fit + checks overdispersion in Poisson
# - Saves summaries + IRR tables for both
# ============================================================

FILE = r"data/input_file.csv"

OUT_DIR = r"data/output_file.csv"
OUT_AGG_CSV   = rf"{OUT_DIR}\cmv_segment_agg_POISSON_BASELINE.csv"
OUT_VIF_CSV   = rf"{OUT_DIR}\VIF_POISSON_BASELINE.csv"

OUT_SUM_POIS  = rf"{OUT_DIR}\POISSON_model_summary.txt"
OUT_IRR_POIS  = rf"{OUT_DIR}\POISSON_model_IRR.csv"

OUT_SUM_NB    = rf"{OUT_DIR}\NB_model_summary.txt"
OUT_IRR_NB    = rf"{OUT_DIR}\NB_model_IRR.csv"

VIF_THRESH_WARN = 10.0

# ------------------ helpers ------------------

def mode_or_unknown(s: pd.Series, unknown="UNKNOWN"):
    s = s.dropna()
    if s.empty:
        return unknown
    m = s.mode()
    return m.iloc[0] if not m.empty else unknown

def safe_mean(s: pd.Series):
    s = pd.to_numeric(s, errors="coerce")
    return float(s.mean()) if s.notna().any() else np.nan

def collapse_rare(series: pd.Series, min_count: int = 50, other_label: str = "UNKNOWN"):
    series = series.fillna(other_label).astype(str)
    vc = series.value_counts(dropna=False)
    rare_levels = vc[vc < min_count].index
    return series.where(~series.isin(rare_levels), other_label)

def compute_vif(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    X = df[features].replace([np.inf, -np.inf], np.nan).dropna()
    if X.empty:
        return pd.DataFrame(columns=["variable", "VIF"])
    X = sm.add_constant(X, has_constant="add")
    return pd.DataFrame({
        "variable": X.columns,
        "VIF": [variance_inflation_factor(X.values, i) for i in range(X.shape[1])]
    }).sort_values("VIF", ascending=False)

def irr_table(model):
    return pd.DataFrame({
        "coef": model.params,
        "IRR": np.exp(model.params),
        "p_value": model.pvalues
    }).sort_values("p_value")

# ------------------ main ------------------

def main():
    print("📂 Loading crash file...")
    df = pd.read_csv(FILE, low_memory=False)

    # 1) Filter to CMV only
    if "cmv_inferred" not in df.columns:
        raise KeyError("❌ 'cmv_inferred' not found.")
    df = df[df["cmv_inferred"] == True].copy()
    print(f"CMV crash records: {len(df):,}")

    if "segment_id" not in df.columns:
        raise KeyError("❌ 'segment_id' not found.")

    # 2) Numeric coercion (no post-crash speed variables)
    for c in ["VMT", "speedlimit", "numberoflanes", "speed_before_15m", "speed_at_crash"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = np.nan

    # Speed availability flag (before + at)
    df["has_speed_pair"] = (df["speed_before_15m"].notna() & df["speed_at_crash"].notna()).astype(int)

    # 3) Weather → precip_flag (same logic you used)
    precip_terms = {
        "RAINING", "SNOW", "SLEET", "WINTRY MIX", "BLOWING SNOW",
        "BLOWING SAND, SOIL, DIRT"
    }
    def is_precip(x):
        return int(str(x).upper().strip() in precip_terms)

    if "weather_description" in df.columns:
        df["precip_flag"] = df["weather_description"].apply(is_precip)
    else:
        # if weather_description missing, still run (flag defaults to 0)
        df["precip_flag"] = 0

    # 4) Segment aggregation
    cat_candidates = [
        "roadalignment", "roadgrade", "intersectiontype",
        "trafficcontrol", "light", "surfacecondition",
        "roadcondition"
    ]
    cat_cols = [c for c in cat_candidates if c in df.columns]

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

    # keep valid exposure
    agg = agg[agg["VMT"].notna() & (agg["VMT"] > 0)].copy()

    # feature engineering (NO speed_diff_at)
    agg["speed_diff_before"] = agg["speed_before_15m"] - agg["speedlimit"]
    agg["abs_delta_before_to_at"] = (agg["speed_at_crash"] - agg["speed_before_15m"]).abs()

    # categorical cleanup
    for c in cat_cols:
        agg[c] = collapse_rare(agg[c], min_count=50, other_label="UNKNOWN")

    # drop missing required numeric fields
    before = len(agg)
    agg = agg.dropna(subset=[
        "speedlimit", "numberoflanes", "pct_speed_pair", "precip_flag",
        "speed_diff_before", "abs_delta_before_to_at", "VMT"
    ])
    dropped = before - len(agg)
    if dropped:
        print(f"🧹 Dropped {dropped:,} segments due to missing required numeric fields.")

    print(f"🚛 Segments in model: {len(agg):,}")

    # 5) VIF
    vif_features = [
        "speedlimit", "numberoflanes", "pct_speed_pair",
        "precip_flag", "speed_diff_before", "abs_delta_before_to_at"
    ]
    vif = compute_vif(agg, vif_features)
    print("\n📊 VIF (numeric predictors):")
    print(vif.to_string(index=False))
    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
    vif.to_csv(OUT_VIF_CSV, index=False)

    # 6) Build formula
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

    print("\n🧾 Formula:")
    print(formula)

    offset = np.log(agg["VMT"])

    # ============================================================
    # 7) POISSON BASELINE
    # ============================================================
    print("\n🚀 Fitting POISSON baseline (robust SEs HC0)...")
    pois = smf.glm(
        formula=formula,
        data=agg,
        family=sm.families.Poisson(),
        offset=offset
    ).fit(cov_type="HC0")

    print("\n📊 POISSON SUMMARY:")
    print(pois.summary())

    # Overdispersion check (rule of thumb)
    pearson_chi2 = float(pois.pearson_chi2)
    df_resid = float(pois.df_resid)
    overdisp_ratio = pearson_chi2 / df_resid if df_resid else np.nan

    print("\n🧪 Overdispersion check (Poisson):")
    print(f"Pearson chi2 / df_resid = {overdisp_ratio:.3f}")
    print("Rule of thumb: ~1 = OK for Poisson; >>1 suggests overdispersion → NB preferred.")

    irr_pois = irr_table(pois)
    irr_pois.to_csv(OUT_IRR_POIS, index=True)
    with open(OUT_SUM_POIS, "w") as f:
        f.write(pois.summary().as_text())

    # ============================================================
    # 8) NEGATIVE BINOMIAL (GLM)
    # ============================================================
    print("\n🚀 Fitting NEGATIVE BINOMIAL GLM (robust SEs HC0)...")
    nb = smf.glm(
        formula=formula,
        data=agg,
        family=sm.families.NegativeBinomial(),
        offset=offset
    ).fit(cov_type="HC0")

    print("\n📊 NEGATIVE BINOMIAL SUMMARY:")
    print(nb.summary())

    irr_nb = irr_table(nb)
    irr_nb.to_csv(OUT_IRR_NB, index=True)
    with open(OUT_SUM_NB, "w") as f:
        f.write(nb.summary().as_text())

    # ============================================================
    # 9) Compare model fit (informal but standard)
    # ============================================================
    print("\n📌 Model comparison:")
    print(f"Poisson   AIC: {pois.aic:,.2f} | LogLik: {pois.llf:,.2f} | Deviance: {pois.deviance:,.2f}")
    print(f"NegBin GLM AIC: {nb.aic:,.2f} | LogLik: {nb.llf:,.2f} | Deviance: {nb.deviance:,.2f}")
    print("Lower AIC is better (penalizes complexity).")
    print("If Poisson overdispersion ratio >> 1, NB is usually the correct choice.")

    # Save aggregated dataset
    agg.to_csv(OUT_AGG_CSV, index=False)

    print("\n💾 Saved outputs:")
    print(f"- Aggregated data: {OUT_AGG_CSV}")
    print(f"- VIF:            {OUT_VIF_CSV}")
    print(f"- Poisson summary: {OUT_SUM_POIS}")
    print(f"- Poisson IRR:     {OUT_IRR_POIS}")
    print(f"- NB summary:      {OUT_SUM_NB}")
    print(f"- NB IRR:          {OUT_IRR_NB}")

if __name__ == "__main__":
    main()
