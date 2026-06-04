import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from pathlib import Path
import statsmodels.api as sm
import statsmodels.formula.api as smf
from patsy import dmatrix

# =========================
# INPUT / OUTPUT
# =========================
AGG_FILE = r"data/input_file.csv"
OUT_DIR  = r"data/output_file.csv"

Path(OUT_DIR).mkdir(parents=True, exist_ok=True)

# =========================
# CONFIG
# =========================
NUM_VARS = [
    "speedlimit",
    "numberoflanes",
    "pct_speed_pair",
    "precip_flag",
    "speed_diff_before",
    "abs_delta_before_to_at"
]

CAT_VARS = [
    "roadalignment","roadgrade","intersectiontype",
    "trafficcontrol","light","surfacecondition","roadcondition"
]

SPEED_KNOT = 55
SPLINE_DF = 5


def safe_cat_terms(df, cats):
    present = [c for c in cats if c in df.columns]
    return [f"C({c})" for c in present], present

def irr_table(res):
    return pd.DataFrame({
        "coef": res.params,
        "IRR": np.exp(res.params),
        "p_value": res.pvalues
    }).sort_values("p_value")

def save_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def main():
    print("📂 Loading aggregated segment file...")
    agg = pd.read_csv(AGG_FILE, low_memory=False)

    # Required
    for c in ["CMV_Count", "VMT"] + NUM_VARS:
        if c not in agg.columns:
            raise KeyError(f"Missing required column: {c}")

    # Coerce numerics
    agg["CMV_Count"] = pd.to_numeric(agg["CMV_Count"], errors="coerce").fillna(0).astype(int)
    agg["VMT"] = pd.to_numeric(agg["VMT"], errors="coerce")
    for c in NUM_VARS:
        agg[c] = pd.to_numeric(agg[c], errors="coerce")

    # Valid exposure + complete numerics
    agg = agg[agg["VMT"].notna() & (agg["VMT"] > 0)].copy()
    before = len(agg)
    agg = agg.dropna(subset=["VMT"] + NUM_VARS).copy()
    print(f"🧹 Dropped {before - len(agg):,} segments due to NA in predictors/VMT.")
    print(f"🚛 Final segments used: {len(agg):,}")

    zero_share = (agg["CMV_Count"] == 0).mean()
    print(f"📌 Share of zero-count segments: {zero_share:.3f}")

    # Build base formula
    cat_terms, cats_present = safe_cat_terms(agg, CAT_VARS)
    formula_base = "CMV_Count ~ " + " + ".join(NUM_VARS + cat_terms)
    offset = np.log(agg["VMT"])

    print("\n🧾 GLM formula (Poisson/NB with offset log(VMT)):")
    print(formula_base)

    # -------------------------
    # Poisson baseline
    # -------------------------
    print("\n🚀 Fitting Poisson GLM (offset log(VMT), robust HC0)...")
    pois = smf.glm(
        formula=formula_base,
        data=agg,
        family=sm.families.Poisson(),
        offset=offset
    ).fit(cov_type="HC0")

    pearson_ratio = float(pois.pearson_chi2) / float(pois.df_resid)
    print(f"🧪 Poisson overdispersion (Pearson chi2 / df): {pearson_ratio:.3f}")

    save_text(Path(OUT_DIR) / "Poisson_summary.txt", pois.summary().as_text())
    irr_table(pois).to_csv(Path(OUT_DIR) / "Poisson_IRR.csv")

    # -------------------------
    # NB GLM
    # -------------------------
    print("\n🚀 Fitting Negative Binomial GLM (offset log(VMT), robust HC0)...")
    nb_glm = smf.glm(
        formula=formula_base,
        data=agg,
        family=sm.families.NegativeBinomial(),
        offset=offset
    ).fit(cov_type="HC0")

    save_text(Path(OUT_DIR) / "NB_GLM_summary.txt", nb_glm.summary().as_text())
    irr_table(nb_glm).to_csv(Path(OUT_DIR) / "NB_GLM_IRR.csv")

    print("\n📌 GLM fit comparison:")
    print(f"Poisson AIC: {pois.aic:,.2f} | LogLik: {pois.llf:,.2f}")
    print(f"NB GLM  AIC: {nb_glm.aic:,.2f} | LogLik: {nb_glm.llf:,.2f}")

    # -------------------------
    # Zero-inflation decision
    # -------------------------
    if zero_share < 0.01:
        print("\n🛑 Zero-inflation test skipped:")
        print("This aggregated file contains essentially no zero-count segments.")
        print("To test ZIP/ZINB, you must build a universe of ALL segments (with VMT) and merge CMV_Count onto it as 0s.")
    else:
        print("\n✅ Zero-inflation might be relevant here (zeros exist).")
        print("If you want ZIP/ZINB, use an ALL-segments exposure universe file (not crash-only).")

    # -------------------------
    # Piecewise NB test
    # -------------------------
    print(f"\n🧩 Piecewise NB GLM test (speedlimit knot = {SPEED_KNOT})...")
    agg["speed_over_knot"] = np.clip(agg["speedlimit"] - SPEED_KNOT, 0, None)

    piece_vars = [
        "speedlimit", "speed_over_knot",
        "numberoflanes", "pct_speed_pair", "precip_flag",
        "speed_diff_before", "abs_delta_before_to_at"
    ] + cat_terms

    formula_piece = "CMV_Count ~ " + " + ".join(piece_vars)

    nb_piece = smf.glm(
        formula=formula_piece,
        data=agg,
        family=sm.families.NegativeBinomial(),
        offset=offset
    ).fit(cov_type="HC0")

    save_text(Path(OUT_DIR) / "NB_piecewise_summary.txt", nb_piece.summary().as_text())
    irr_table(nb_piece).to_csv(Path(OUT_DIR) / "NB_piecewise_IRR.csv")

    print("\n📌 AIC comparison:")
    print(f"NB base     AIC: {nb_glm.aic:,.2f}")
    print(f"NB piecewise AIC: {nb_piece.aic:,.2f}")

    # -------------------------
    # Spline NB test
    # -------------------------
    print(f"\n🧠 Spline NB GLM test (bs(speedlimit, df={SPLINE_DF}))...")
    spline_basis = dmatrix(
        f"bs(speedlimit, df={SPLINE_DF}, degree=3, include_intercept=False)",
        data=agg,
        return_type="dataframe"
    )

    X_spline = pd.concat([
        spline_basis,
        agg[["numberoflanes","pct_speed_pair","precip_flag","speed_diff_before","abs_delta_before_to_at"]],
    ], axis=1)

    if cats_present:
        dummies = pd.get_dummies(agg[cats_present].astype(str), prefix=cats_present, drop_first=True)
        X_spline = pd.concat([X_spline, dummies], axis=1)

    X_spline = sm.add_constant(X_spline, has_constant="add").astype(float)

    nb_spline = sm.GLM(
        agg["CMV_Count"],
        X_spline,
        family=sm.families.NegativeBinomial(),
        offset=offset
    ).fit(cov_type="HC0")

    save_text(Path(OUT_DIR) / "NB_spline_summary.txt", nb_spline.summary().as_text())

    print("\n📌 AIC comparison (nonlinearity):")
    print(f"NB base     AIC: {nb_glm.aic:,.2f}")
    print(f"NB piecewise AIC: {nb_piece.aic:,.2f}")
    print(f"NB spline    AIC: {nb_spline.aic:,.2f}")

    print(f"\n✅ Done. Outputs saved to: {OUT_DIR}")

if __name__ == "__main__":
    main()
