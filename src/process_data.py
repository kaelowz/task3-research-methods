"""Data validation ("warm-up" analogue), statistical aggregation and RQ tests.

Data: Nawaz, S. (2026). Academic Stress, Sleep Quality, and Lifestyle Factors Among
University Students. Mendeley Data, v1, DOI 10.17632/srd3wmjd4r.1 (CC BY 4.0).

Pipeline:  data/raw/test_run.jsonl
             -> data/processed/metrics_summary.csv   (descriptives per sleep-quality group)
             -> data/processed/tests_summary.csv     (RQ1-RQ3 inferential results)

Every stochastic step (bootstrap) takes an explicit seed -> reproducible.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.miscmodels.ordinal_model import OrderedModel
from statsmodels.stats.proportion import proportion_confint

SEED = 42
N_BOOT = 2000
ALPHA = 0.05

DIFF_ORDER = ["Never", "Rarely", "Sometimes", "Often", "Almost Always"]
QUAL_ORDER = ["Poor", "Average", "Good"]
DUR_ORDER = ["<5 hrs", "5-6 hrs", "7-8 hrs", ">8 hrs"]
BED_ORDER = ["Before 10 PM", "10-11 PM", "11-12 AM", "After 12 AM"]
YESNO = ["Yes", "No"]
VALID_LABELS = {
    "Difficulty_falling_asleep": DIFF_ORDER,
    "Sleep_quality": QUAL_ORDER,
    "Average_sleep_duration_per_night": DUR_ORDER,
    "Bedtime_on_regular_nights": BED_ORDER,
    "Use_of_electronic_devices_before_bed": YESNO,
    "Night_time_caffeine_consumption": YESNO,
    "Gender": ["Female", "Male"],
}
VALID_RANGES = {"Age": (16, 60), "Current_CGPA": (0, 4.0), "Current_stress_level": (1, 5),
                "Depression_level": (1, 5), "Anxiety_level": (1, 5)}
NUMERIC_OUTCOMES = ["Current_stress_level", "Anxiety_level", "Depression_level",
                    "Current_CGPA", "difficulty_score"]


# ----------------------------------------------------------------- ingestion
def load_raw(path: str | Path) -> pd.DataFrame:
    with open(path, encoding="utf-8") as fh:
        return pd.DataFrame([json.loads(line) for line in fh])


def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Quality filter (analogue of warm-up filtering).

    1. Harmonise text labels (strip whitespace, Yes/No capitalisation) - counted as *recoded cells*.
    2. Exclusion cascade: duplicate respondents -> unknown category labels -> out-of-range numbers.
    Returns (valid_df, log). ``log.attrs['guardrail']`` = share of records excluded or recoded.
    """
    cur = df.copy()
    recoded = 0
    for c in cur.select_dtypes(include=["object", "string"]).columns:
        orig = cur[c].copy()
        cur[c] = cur[c].astype(str).str.strip()
        if c in ("Use_of_electronic_devices_before_bed", "Night_time_caffeine_consumption",
                 "Awareness_of_recommended_sleep", "Skipped_class_due_to_poor_sleep_or_stress",
                 "Family_history_of_health_issues", "Chronic_illness"):
            cur[c] = cur[c].str.capitalize()
        recoded += int((orig != cur[c]).sum())
    log = [{"step": "recoded label cells (whitespace / Yes-No case)", "affected": recoded}]

    def drop(name: str, mask: pd.Series) -> None:
        nonlocal cur
        log.append({"step": name, "affected": int(mask.sum())})
        cur = cur[~mask]

    cols = [c for c in cur.columns if c != "Q Number"]
    drop("duplicate respondents", cur.duplicated(subset=cols))
    bad = pd.Series(False, index=cur.index)
    for c, allowed in VALID_LABELS.items():
        bad |= ~cur[c].isin(allowed)
    drop("unknown category label", bad)
    bad = pd.Series(False, index=cur.index)
    for c, (lo, hi) in VALID_RANGES.items():
        bad |= ~cur[c].between(lo, hi)
    drop("numeric value out of range", bad)
    out = pd.DataFrame(log)
    n_excl = int(out.loc[1:, "affected"].sum())
    out.attrs["n_raw"] = len(df)
    out.attrs["exclusion_rate"] = n_excl / len(df)          # guardrail metric
    out.attrs["recode_rate"] = recoded / (len(df) * df.shape[1])
    return cur.reset_index(drop=True), out


def derive(d: pd.DataFrame) -> pd.DataFrame:
    """Add analysis variables (documented in docs/domain_model.md)."""
    d = d.copy()
    d["device"] = (d["Use_of_electronic_devices_before_bed"] == "Yes").astype(int)
    d["caffeine"] = (d["Night_time_caffeine_consumption"] == "Yes").astype(int)
    d["male"] = (d["Gender"] == "Male").astype(int)
    d["stress"] = d["Current_stress_level"].astype(float)
    d["age"] = d["Age"].astype(float)
    d["difficulty_score"] = d["Difficulty_falling_asleep"].map({k: i for i, k in enumerate(DIFF_ORDER)})
    d["quality_score"] = d["Sleep_quality"].map({k: i for i, k in enumerate(QUAL_ORDER)})
    d["good_sleep"] = (d["Sleep_quality"] == "Good").astype(int)
    d["freq_difficulty"] = (d["difficulty_score"] >= 3).astype(int)          # Often / Almost Always
    d["ge7h"] = d["Average_sleep_duration_per_night"].isin(["7-8 hrs", ">8 hrs"]).astype(int)
    d["late_bed"] = (d["Bedtime_on_regular_nights"] == "After 12 AM").astype(int)
    return d


def exclusion_rate(log: pd.DataFrame) -> float:
    """Guardrail metric: share of raw records excluded by validation."""
    return float(log.attrs["exclusion_rate"])


# --------------------------------------------------------------- statistics
def bootstrap_ci(x, stat=np.median, n_boot: int = N_BOOT, alpha: float = ALPHA,
                 seed: int = SEED) -> tuple[float, float]:
    x = np.asarray(x, dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    boots = np.apply_along_axis(stat, 1, x[idx])
    lo, hi = np.percentile(boots, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return float(lo), float(hi)


def wilson(k: int, n: int) -> tuple[float, float]:
    lo, hi = proportion_confint(k, n, alpha=ALPHA, method="wilson")
    return float(lo), float(hi)


def describe(d: pd.DataFrame, by: str = "Sleep_quality", seed: int = SEED) -> pd.DataFrame:
    """Mean±SD, median, p25/p75, p95, p99 and bootstrap 95 % CI of the median."""
    rows = []
    groups = [("ALL", d)] + [(g, d[d[by] == g]) for g in QUAL_ORDER]
    for var in NUMERIC_OUTCOMES:
        for name, g in groups:
            x = g[var].to_numpy(float)
            lo, hi = bootstrap_ci(x, np.median, seed=seed)
            rows.append({"grouping": by, "group": name, "variable": var, "n": len(x),
                         "mean": x.mean(), "sd": x.std(ddof=1), "median": np.median(x),
                         "p25": np.percentile(x, 25), "p75": np.percentile(x, 75),
                         "p95": np.percentile(x, 95), "p99": np.percentile(x, 99),
                         "median_ci_low": lo, "median_ci_high": hi})
    return pd.DataFrame(rows)


def _row(rq, test, est, lo, hi, p, n, h1, model=None, term=None):
    """h1 = True/False if the term has a pre-specified expected direction, None otherwise."""
    return {"rq": rq, "test": test, "estimate": est, "ci_low": lo, "ci_high": hi, "p_value": p,
            "n": n, "h1_met": None if h1 is None else bool(h1), "model": model, "term": term}


# expected direction of each effect (+1: increases the outcome, -1: decreases, absent: no hypothesis)
EXPECTED_RQ2 = {"device": +1, "stress": +1, "caffeine": +1}
EXPECTED_RQ3 = {"ge7h": +1, "late_bed": -1, "device": -1, "stress": -1, "caffeine": -1}


def share_by_device(d: pd.DataFrame) -> pd.DataFrame:
    """Share with good sleep quality per pre-bedtime device-use group (Wilson 95 % CI)."""
    rows = []
    for lab, g in [("No device use", d[d.device == 0]), ("Device use", d[d.device == 1])]:
        k, n = int(g.good_sleep.sum()), len(g)
        lo, hi = wilson(k, n)
        rows.append({"group": lab, "n": n, "good_n": k, "rate": k / n, "ci_low": lo, "ci_high": hi})
    return pd.DataFrame(rows)


def rq1(d: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    """RQ1: pre-bedtime device use vs. self-rated sleep quality."""
    a, b = d[d.device == 1], d[d.device == 0]          # a = users, b = non-users
    # (i) difference in share of good sleepers (users - non-users), bootstrap CI
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(N_BOOT):
        ia, ib = rng.integers(0, len(a), len(a)), rng.integers(0, len(b), len(b))
        diffs.append(a.good_sleep.to_numpy()[ia].mean() - b.good_sleep.to_numpy()[ib].mean())
    dlo, dhi = np.percentile(diffs, [2.5, 97.5])
    rd = a.good_sleep.mean() - b.good_sleep.mean()
    # (ii) Fisher exact: odds of good sleep, users vs non-users
    tab = [[int(a.good_sleep.sum()), int(len(a) - a.good_sleep.sum())],
           [int(b.good_sleep.sum()), int(len(b) - b.good_sleep.sum())]]
    or_, p_f = stats.fisher_exact(tab)
    import statsmodels.api as sm
    t22 = sm.stats.Table2x2(np.array(tab))
    olo, ohi = t22.oddsratio_confint()
    # (iii) Mann-Whitney on the 3-level ordinal quality; rank-biserial effect size
    u, p_u = stats.mannwhitneyu(a.quality_score, b.quality_score, alternative="two-sided")
    rbc = 2 * u / (len(a) * len(b)) - 1

    def rb(x, y):
        uu = stats.mannwhitneyu(x, y).statistic
        return 2 * uu / (len(x) * len(y)) - 1
    boots = []
    for _ in range(1000):
        ia, ib = rng.integers(0, len(a), len(a)), rng.integers(0, len(b), len(b))
        boots.append(rb(a.quality_score.to_numpy()[ia], b.quality_score.to_numpy()[ib]))
    rlo, rhi = np.percentile(boots, [2.5, 97.5])
    n = len(d)
    return pd.DataFrame([
        _row("RQ1", "Risk difference, good sleep: device users - non-users", rd, dlo, dhi, p_f, n,
             p_f < ALPHA and rd < 0),
        _row("RQ1", "Odds ratio of good sleep, users vs non-users (Fisher exact)", or_, olo, ohi, p_f,
             n, p_f < ALPHA and or_ < 1),
        _row("RQ1", "Rank-biserial r, sleep-quality rank, users vs non-users (Mann-Whitney)", rbc,
             rlo, rhi, p_u, n, p_u < ALPHA and rbc < 0),
    ])


def rq2(d: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    """RQ2: predictors of difficulty falling asleep (ordinal logit, proportional odds)."""
    preds = ["device", "stress", "caffeine", "male", "age"]
    y = pd.Series(pd.Categorical(d["Difficulty_falling_asleep"], categories=DIFF_ORDER, ordered=True))
    m = OrderedModel(y, d[preds].astype(float), distr="logit").fit(method="bfgs", disp=False, maxiter=1000)
    ci = m.conf_int()
    rows = []
    labels = {"device": "pre-bedtime device use (yes vs no)", "stress": "stress level (+1 point)",
              "caffeine": "night-time caffeine (yes vs no)", "male": "male vs female",
              "age": "age (+1 year)"}
    for p in preds:
        rows.append(_row("RQ2", f"Ordered-logit OR, difficulty falling asleep: {labels[p]}",
                         float(np.exp(m.params[p])), float(np.exp(ci.loc[p, 0])), float(np.exp(ci.loc[p, 1])),
                         float(m.pvalues[p]), int(m.nobs),
                         None if p not in EXPECTED_RQ2 else
                         (m.pvalues[p] < ALPHA and np.sign(m.params[p]) == EXPECTED_RQ2[p]),
                         model="RQ2 ordinal logit", term=labels[p]))
    rho, p = stats.spearmanr(d.stress, d.difficulty_score)
    boots = []
    rng = np.random.default_rng(seed)
    s, y_ = d.stress.to_numpy(), d.difficulty_score.to_numpy()
    for _ in range(N_BOOT):
        i = rng.integers(0, len(d), len(d))
        boots.append(stats.spearmanr(s[i], y_[i])[0])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    rows.append(_row("RQ2", "Spearman rho: stress level vs difficulty falling asleep", rho, lo, hi, p,
                     len(d), p < ALPHA and rho > 0))
    return pd.DataFrame(rows)


def rq3(d: pd.DataFrame) -> pd.DataFrame:
    """RQ3: sleep-hygiene factors and the odds of good sleep quality (logistic regression)."""
    m = smf.logit("good_sleep ~ ge7h + late_bed + device + stress + caffeine + male + age", d).fit(disp=0)
    ci = m.conf_int()
    labels = {"ge7h": "sleep duration >= 7 h (vs < 7 h)", "late_bed": "bedtime after 12 AM",
              "device": "pre-bedtime device use", "stress": "stress level (+1 point)",
              "caffeine": "night-time caffeine", "male": "male vs female", "age": "age (+1 year)"}
    rows = []
    for k, lab in labels.items():
        rows.append(_row("RQ3", f"Logistic OR, good sleep quality: {lab}", float(np.exp(m.params[k])),
                         float(np.exp(ci.loc[k, 0])), float(np.exp(ci.loc[k, 1])), float(m.pvalues[k]),
                         int(m.nobs),
                         None if k not in EXPECTED_RQ3 else
                         (m.pvalues[k] < ALPHA and np.sign(m.params[k]) == EXPECTED_RQ3[k]),
                         model="RQ3 logistic", term=lab))
    return pd.DataFrame(rows)


def all_tests(d: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    return pd.concat([rq1(d, seed), rq2(d, seed), rq3(d)], ignore_index=True)


def run(raw_path="data/raw/test_run.jsonl",
        summary_path="data/processed/metrics_summary.csv",
        tests_path="data/processed/tests_summary.csv"):
    raw = load_raw(raw_path)
    valid, log = validate(raw)
    d = derive(valid)
    summary, tests = describe(d), all_tests(d)
    Path(summary_path).parent.mkdir(parents=True, exist_ok=True)
    summary.round(4).to_csv(summary_path, index=False)
    tests.round(6).to_csv(tests_path, index=False)
    return d, log, summary, tests


if __name__ == "__main__":
    _, lg, sm_, ts = run()
    print(lg.to_string(index=False), f"\nexclusion rate: {exclusion_rate(lg):.1%}\n")
    print(ts.drop(columns=["model", "term"]).round(4).to_string(index=False))
