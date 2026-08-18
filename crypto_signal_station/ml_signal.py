"""Trained buy-signal model: a classifier over the same indicator columns
crypto_signal_pipeline.py already computes (RSI, MFI, StochRSI, MACD,
Bollinger %B, ATR%, volume spikes, RSI divergence, MA50/200 regime), as an
alternative to _label_signal()'s hand-set thresholds.

_label_signal() decides "Excellent Buy" from RSI<20 & MFI<10 &
StochRSI<0.10 because those numbers looked right. This learns which
combinations of indicators actually preceded a winning forward return
historically, then reports honest out-of-sample performance: the most
recent slice of the date range is held out and never touched during
training, so the reported accuracy isn't the model grading its own
homework. Every evaluation also reports the existing rule-based Buy tiers'
win rate over that *same* held-out window, so it's a fair, apples-to-apples
"does this beat what we already have" comparison, not just a plausible-
looking number in isolation.

Label: forward 30-day return > 0, using backtest.py's own forward-return
machinery (the same merge_asof/weekend-bridging logic already tested
there) applied to every daily bar instead of just signal events.

Model: logistic regression (scaled features, class-balanced) — chosen for
interpretability over a black box, since the whole point is understanding
*why* it agrees or disagrees with the rule-based tiers.

Beyond the 8 raw indicator columns, a handful of engineered features widen
what the model can see: short-horizon price momentum (5/10/20-day trailing
returns — raw trend, which none of the oscillators capture directly),
volatility trend (5-day change in ATR%) and Bollinger bandwidth (squeeze
vs. expansion, distinct from %B's position-in-band), distance from the
52-week high/low (drawdown context), and the symbol's category-wide market
breadth on that date (cycle_forecast.py's reconstructed breadth time
series — lets the model see "is the whole market supportive," not just
this one symbol's technicals).

select_features() goes one step further than picking a fixed feature set:
it algorithmically searches which *combination* of indicators actually
earns its place, via greedy forward selection scored on a third, untouched
validation slice (never the test slice) — repeatedly adding whichever
remaining indicator most improves the validation buy calls' average
return, among additions with enough validation calls to be trusted,
stopping the moment nothing helps anymore.

select_model() goes one step further again: it cycles through 3 different
modeling methods (logistic regression, gradient-boosted trees, a shallow
decision tree) — each running that same forward search independently — and
picks whichever method+feature combination scored best *on validation*.
Only that single winner is then refit on train+validation and confirmed
against the test slice. Choosing the best of several searches by peeking
at test performance would be the same threshold-overfitting mistake this
module already learned from, one level up — so test stays untouched until
there's exactly one candidate left to confirm.

That confirmation is itself two things, not one: a single evaluate() over
the whole test slice (final_eval — one split, one number, kept for
backward compatibility), and walk_forward_validate() across several
expanding-window folds *within* that same test slice (walk_forward — a
distribution, not one number). This distinction earned its place the hard
way: a search once reported a crypto model at +43.5% return on its
validation slice, which collapsed to exactly the baseline once confirmed
on a single test slice. A single split — validation or test — can be
lucky or unlucky; only walking forward through several splits shows
whether a result is a real pattern or one window's noise. Trust
walk_forward over final_eval when they disagree.

label_mode="relative" is an alternative to the default "absolute" label
(forward return > 0, which is mostly a bet on market-wide drift): it asks
whether a symbol's forward return beat the cross-sectional median of every
symbol in its category on that same date, canceling out the shared market
move to isolate which symbols' setups actually mattered — usually an
easier target, and a directly actionable one (buy the top-ranked names).

Every buy-call metric also reports n_dates alongside n_calls, and profit
factor (total gains / total losses) alongside win rate: n_dates matters
because a market-wide feature like mkt_breadth is identical for every
symbol on a given date, so a model leaning on it can rack up many "calls"
that are really a handful of dates firing for every symbol at once —
n_calls alone overstates how independent those bets are. Profit factor
matters because win rate alone is close to meaningless without knowing
whether the wins are bigger than the losses.

Storage: data/ml_signal/model_<category>.joblib  (fitted model + scaler)
         data/ml_signal/eval_<category>.json      (out-of-sample scorecard)
Usage:
    poetry run python crypto_signal_station/crypto_signal_pipeline.py mlsignal       # full feature set, logistic regression
    poetry run python crypto_signal_station/crypto_signal_pipeline.py mlselect       # algorithmic feature selection
    poetry run python crypto_signal_station/crypto_signal_pipeline.py mlcycle        # + cycles through 3 methods
    poetry run python crypto_signal_station/crypto_signal_pipeline.py mlwalkforward  # validate the persisted model across time
"""

import json
import math
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
import backtest as backtest_mod
import cycle_forecast as cycle_forecast_mod

HORIZON_DAYS = 30
# Raw indicator columns, as computed by crypto_signal_pipeline.py.
_INDICATOR_FEATURES = [
    "rsi", "mfi", "stoch_rsi_k", "stoch_rsi_d", "bb_pband", "macd_hist",
    "atr_pct", "is_bull", "vol_spike", "rsi_bullish_div", "rsi_bearish_div",
]
# Engineered on top of the raw columns/OHLCV — see module docstring.
_ENGINEERED_FEATURES = [
    "ma_spread", "mom_5d", "mom_10d", "mom_20d", "atr_pct_chg_5d",
    "bb_bandwidth", "dist_from_52w_high", "dist_from_52w_low", "mkt_breadth",
]
FEATURES = _INDICATOR_FEATURES + _ENGINEERED_FEATURES
_RAW_COLUMNS = [
    "Date", "Close", "signal", "rsi", "mfi", "stoch_rsi_k", "stoch_rsi_d",
    "bb_pband", "macd_hist", "atr_pct", "is_bull", "vol_spike",
    "rsi_bullish_div", "rsi_bearish_div", "ma_50", "ma_200", "bb_upper", "bb_lower",
]
_BOOL_FEATURES = ("is_bull", "vol_spike", "rsi_bullish_div", "rsi_bearish_div")
_ROLLING_52W_WINDOW = 252
_ROLLING_52W_MIN_PERIODS = 60  # allow a partial-window distance for younger symbols

METHODS_ORDER = ("logistic", "gboost", "tree")

MIN_ROWS_PER_CATEGORY = 500
TEST_FRACTION = 0.2  # most recent slice of the date range, held out

# Decision threshold isn't hardcoded at 0.5: it's picked from the training
# set (never the test set) as whichever candidate maximizes the average
# forward return of the resulting buy calls, among thresholds with enough
# calls to not just be a handful of lucky rows. The floor scales with
# training size (0.5%, minimum 20) — on a dataset with a million rows, 13
# calls "winning" isn't a signal worth trusting, it's noise dressed up
# with a good-looking average.
#
# n_calls alone isn't enough, though — walk-forward validation caught a
# stocks model whose "804 calls, 90% win rate" turned out to be ~800 calls
# clustered on 3 calendar dates (mkt_breadth firing for hundreds of
# symbols at once). MIN_DATES_FOR_THRESHOLD/MIN_VAL_DATES_FOR_SELECTION
# require a minimum spread of *distinct dates* behind a threshold/feature
# choice too, so a date-clustered fluke can't clear the bar just because
# its row count looks big.
THRESHOLD_CANDIDATES = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
MIN_CALLS_FOR_THRESHOLD = 20
MIN_CALL_FRACTION = 0.005
MIN_DATES_FOR_THRESHOLD = 10

# Feature-selection search: validation is a third slice, disjoint from
# both train and test, so the search can freely try many combinations
# without ever touching (and thereby contaminating) the final test score.
VAL_FRACTION = 0.2
MIN_VAL_CALLS_FOR_SELECTION = 15
MIN_VAL_CALL_FRACTION = 0.01
MIN_VAL_DATES_FOR_SELECTION = 10

# Walk-forward confirmation: after search picks a feature/method
# combination using train+val, that choice is confirmed not just once
# (a single test slice) but across this many expanding-window folds
# walking forward through the test slice — so "did this hold up" is a
# distribution, not one split's number that could be lucky or unlucky.
CONFIRM_N_FOLDS = 3
WALK_FORWARD_MIN_TRAIN_FRACTION = 0.4


def _model_path(category):
    return db.table_path("ml_signal", f"model_{category}.joblib")


def _eval_path(category):
    return db.table_path("ml_signal", f"eval_{category}.json")


def _engineer_features(sigs: pd.DataFrame, category: str) -> pd.DataFrame:
    """Add every engineered feature column (ma_spread, momentum,
    volatility trend, Bollinger bandwidth, 52w distance, market breadth).
    Several of these need rolling per-symbol history, so this must run on
    the *full* per-symbol series — never on an already-truncated frame
    (e.g. just the latest row), or the rolling windows come out empty."""
    df = sigs.sort_values(["symbol", "Date"]).copy()
    df["ma_spread"] = df["ma_50"] / df["ma_200"] - 1
    for col in _BOOL_FEATURES:
        df[col] = df[col].fillna(False).astype(int)

    g = df.groupby("symbol")
    df["mom_5d"] = g["Close"].pct_change(5)
    df["mom_10d"] = g["Close"].pct_change(10)
    df["mom_20d"] = g["Close"].pct_change(20)
    df["atr_pct_chg_5d"] = g["atr_pct"].diff(5)
    df["bb_bandwidth"] = (df["bb_upper"] - df["bb_lower"]) / df["Close"]
    roll_high = g["Close"].transform(
        lambda s: s.rolling(_ROLLING_52W_WINDOW, min_periods=_ROLLING_52W_MIN_PERIODS).max()
    )
    roll_low = g["Close"].transform(
        lambda s: s.rolling(_ROLLING_52W_WINDOW, min_periods=_ROLLING_52W_MIN_PERIODS).min()
    )
    df["dist_from_52w_high"] = df["Close"] / roll_high - 1
    df["dist_from_52w_low"] = df["Close"] / roll_low - 1

    breadth_ts = cycle_forecast_mod.compute_breadth_timeseries(category)
    if not breadth_ts.empty:
        df = df.merge(
            breadth_ts[["Date", "pct_above_ma200"]].rename(columns={"pct_above_ma200": "mkt_breadth"}),
            on="Date", how="left",
        )
    else:
        df["mkt_breadth"] = float("nan")
    return df


def _build_dataset(category, timeframe="1d", label_mode="absolute") -> pd.DataFrame:
    """One row per symbol/day with every candidate feature, the rule-based
    signal label, and the forward HORIZON_DAYS return + binary label.
    Empty if the lake has nothing usable.

    label_mode="absolute" (default): label = 1 if the forward return is
    positive. Dominated by market-wide drift — on any given day most
    symbols move together, so this mostly asks "is the market going up,"
    not "is this symbol's setup good."

    label_mode="relative": label = 1 if the forward return beats the
    cross-sectional median forward return of every symbol in the category
    on that *same* date. Cancels out the shared market move and isolates
    which symbols' setups actually mattered — a generally easier, more
    standard target, and a directly actionable one (buy the top-ranked
    names), at the cost of needing enough symbols on each date for the
    median to mean something (thin for crypto's ~9-symbol universe)."""
    sigs = db.scan_signals_lake(category, timeframe, columns=_RAW_COLUMNS)
    if sigs.empty:
        return pd.DataFrame()
    required = ["Close", "ma_50", "ma_200", "bb_upper", "bb_lower"] + [
        c for c in _INDICATOR_FEATURES if c not in _BOOL_FEATURES
    ]
    sigs = sigs.dropna(subset=required)
    if sigs.empty:
        return pd.DataFrame()
    sigs = _engineer_features(sigs, category)
    sigs = sigs.dropna(subset=[c for c in FEATURES if c not in _BOOL_FEATURES])
    if sigs.empty:
        return pd.DataFrame()

    daily = db.scan_ohlcv_lake(category, columns=["Date", "Close"])
    if daily.empty:
        return pd.DataFrame()
    daily_by_sym = {sym: g.sort_values("Date").reset_index(drop=True) for sym, g in daily.groupby("symbol")}

    cols = ["Date", "Close", "signal"] + FEATURES
    frames = []
    for sym, g in sigs.groupby("symbol"):
        d = daily_by_sym.get(sym)
        if d is None or d.empty:
            continue
        ev = g[cols].sort_values("Date").reset_index(drop=True)
        out = backtest_mod._forward_returns(ev, d)
        out.insert(0, "symbol", sym)
        frames.append(out)

    if not frames:
        return pd.DataFrame()
    data = pd.concat(frames, ignore_index=True)
    ret_col = f"ret_{HORIZON_DAYS}d"
    data = data.dropna(subset=[ret_col])

    if label_mode == "relative":
        mkt_median = data.groupby("Date")[ret_col].transform("median")
        data["label"] = (data[ret_col] > mkt_median).astype(int)
        data["mkt_median_return"] = mkt_median
    else:
        data["label"] = (data[ret_col] > 0).astype(int)
    return data


def _time_split(data: pd.DataFrame, test_fraction=TEST_FRACTION):
    """Split by date, not row count or shuffle: the most recent
    test_fraction of the date range is held out entirely, so no row in
    train has a later date than any row in test."""
    dates = pd.Series(data["Date"].unique()).sort_values()
    if len(dates) < 10:
        return data.iloc[0:0].copy(), data.iloc[0:0].copy()
    split_date = dates.iloc[int(len(dates) * (1 - test_fraction))]
    train = data[data["Date"] < split_date].copy()
    test = data[data["Date"] >= split_date].copy()
    return train, test


def _three_way_time_split(data: pd.DataFrame, val_fraction=VAL_FRACTION, test_fraction=TEST_FRACTION):
    """Chronological train / validation / test split. Validation is used
    to decide which features to keep; test is touched exactly once, after
    that decision is already locked in, purely to confirm it."""
    dates = pd.Series(data["Date"].unique()).sort_values()
    if len(dates) < 15:
        empty = data.iloc[0:0].copy()
        return empty, empty.copy(), empty.copy()
    n = len(dates)
    test_start = dates.iloc[int(n * (1 - test_fraction))]
    val_start = dates.iloc[int(n * (1 - test_fraction - val_fraction))]
    train = data[data["Date"] < val_start].copy()
    val = data[(data["Date"] >= val_start) & (data["Date"] < test_start)].copy()
    test = data[data["Date"] >= test_start].copy()
    return train, val, test


def _select_threshold(train_returns, proba_train, train_dates=None, min_calls=MIN_CALLS_FOR_THRESHOLD,
                       min_dates=MIN_DATES_FOR_THRESHOLD, candidates=THRESHOLD_CANDIDATES):
    """Pick the probability cutoff (evaluated on training data only) that
    maximizes the average forward return of the resulting buy calls, among
    thresholds that clear min_calls *and* span at least min_dates distinct
    dates (when train_dates is given) — a threshold whose calls all land
    on a handful of dates isn't backed by min_calls independent bets, no
    matter how big min_calls looks. Falls back to 0.5 if nothing
    qualifies — e.g. too few training rows to trust a stricter cutoff."""
    best_t, best_ret = 0.5, None
    for t in candidates:
        mask = proba_train >= t
        n = int(mask.sum())
        if n < min_calls:
            continue
        if train_dates is not None and int(train_dates[mask].nunique()) < min_dates:
            continue
        avg_ret = float(train_returns[mask].mean())
        if best_ret is None or avg_ret > best_ret:
            best_t, best_ret = t, avg_ret
    return best_t


def _make_estimator(method: str):
    """The 3 methods select_model() cycles through: a linear model, a
    nonlinear ensemble, and a single interpretable tree — genuinely
    different inductive biases, not 3 flavors of the same thing. All 3
    are scale-invariant to per-feature affine transforms (trees split on
    thresholds; that's why fitting through the same StandardScaler below
    doesn't need a tree-specific branch)."""
    if method == "logistic":
        from sklearn.linear_model import LogisticRegression
        return LogisticRegression(max_iter=1000, class_weight="balanced")
    if method == "gboost":
        from sklearn.ensemble import HistGradientBoostingClassifier
        return HistGradientBoostingClassifier(
            max_iter=100, max_depth=4, class_weight="balanced", random_state=0
        )
    if method == "tree":
        from sklearn.tree import DecisionTreeClassifier
        return DecisionTreeClassifier(max_depth=4, class_weight="balanced", random_state=0)
    raise ValueError(f"unknown method: {method!r}")


def _fit(train: pd.DataFrame, features, method: str = "logistic") -> dict:
    """Fit the classifier and pick its buy threshold using `train` alone.
    Returns {model, scaler, threshold}. Split out so feature-selection
    search (many fits against different feature subsets/methods) and the
    standard single-model path share the exact same fitting logic."""
    from sklearn.preprocessing import StandardScaler

    X_train, y_train = train[features].to_numpy(), train["label"].to_numpy()
    scaler = StandardScaler().fit(X_train)
    clf = _make_estimator(method)
    clf.fit(scaler.transform(X_train), y_train)

    ret_col = f"ret_{HORIZON_DAYS}d"
    proba_train = clf.predict_proba(scaler.transform(X_train))[:, 1]
    min_calls = max(MIN_CALLS_FOR_THRESHOLD, int(MIN_CALL_FRACTION * len(train)))
    threshold = _select_threshold(train[ret_col], proba_train, train_dates=train["Date"], min_calls=min_calls)
    return {"model": clf, "scaler": scaler, "threshold": threshold, "method": method}


def _profit_factor(rets: pd.Series) -> float:
    """Total gains / total losses among a set of returns — a complement
    to win rate that captures payoff size, not just frequency. >1 means
    net profitable even with a sub-50% win rate (small frequent losses,
    larger rare wins); undefined (nan) with no losses to divide by."""
    wins = float(rets[rets > 0].sum())
    losses = float(rets[rets < 0].sum())
    if losses == 0:
        return float("inf") if wins > 0 else float("nan")
    return wins / abs(losses)


def _score(bundle: dict, frame: pd.DataFrame, features) -> dict:
    """Score a fitted {model, scaler, threshold} bundle against any frame
    (train/val/test) using its own features and threshold. No side effects
    — safe to call repeatedly during a search.

    n_dates matters alongside n_calls: a feature like mkt_breadth is
    identical for every symbol on a given date, so a model leaning on it
    can rack up many "calls" that are really just a handful of dates
    firing for every symbol at once — n_calls overstates how many
    independent bets that actually is."""
    from sklearn.metrics import accuracy_score, roc_auc_score

    clf, scaler, threshold = bundle["model"], bundle["scaler"], bundle["threshold"]
    ret_col = f"ret_{HORIZON_DAYS}d"

    X = frame[features].to_numpy()
    proba = clf.predict_proba(scaler.transform(X))[:, 1]
    pred = (proba >= threshold).astype(int)
    buy_mask = pred == 1
    n_calls = int(buy_mask.sum())
    buy_rets = frame.loc[buy_mask, ret_col]

    return {
        "n_calls": n_calls,
        "n_dates": int(frame.loc[buy_mask, "Date"].nunique()) if n_calls else 0,
        "accuracy": float(accuracy_score(frame["label"], pred)),
        "auc": float(roc_auc_score(frame["label"], proba)) if frame["label"].nunique() > 1 else float("nan"),
        "avg_return": float(buy_rets.mean()) if n_calls else float("nan"),
        "win_rate": float((buy_rets > 0).mean()) if n_calls else float("nan"),
        "profit_factor": _profit_factor(buy_rets) if n_calls else float("nan"),
    }


def train_model(category, timeframe="1d", features=None, method="logistic", label_mode="absolute"):
    """Fit the classifier, holding out the most recent slice of the date
    range as an out-of-sample test set. Returns a dict with the fitted
    model/scaler and the train/test frames, or None if there isn't enough
    data (or the split leaves only one class on either side)."""
    features = list(features) if features else list(FEATURES)

    data = _build_dataset(category, timeframe, label_mode=label_mode)
    if len(data) < MIN_ROWS_PER_CATEGORY:
        return None

    train, test = _time_split(data)
    if train.empty or test.empty:
        return None
    if train["label"].nunique() < 2 or test["label"].nunique() < 2:
        return None

    bundle = _fit(train, features, method=method)
    return {
        "category": category, "features": features, "method": method, "label_mode": label_mode,
        "model": bundle["model"], "scaler": bundle["scaler"], "threshold": bundle["threshold"],
        "train": train, "test": test,
    }


def _json_safe(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, pd.Timestamp):
            out[k] = str(v.date())
        elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            out[k] = None
        else:
            out[k] = v
    return out


def evaluate(fit: dict) -> dict:
    """Out-of-sample scorecard at the training-set-selected threshold: the
    return/win-rate of actually trading the model's buy calls, the
    existing rule-based Buy tiers' return/win-rate over the *same* test
    window, and the unconditional baseline — all directly comparable."""
    features = fit["features"]
    test = fit["test"]
    s = _score(fit, test, features)

    ret_col = f"ret_{HORIZON_DAYS}d"
    rule_buys = test[test["signal"].str.endswith("Buy")]

    clf = fit["model"]
    if hasattr(clf, "coef_"):
        importance = dict(zip(features, clf.coef_[0].tolist()))
    elif hasattr(clf, "feature_importances_"):
        importance = dict(zip(features, clf.feature_importances_.tolist()))
    else:
        importance = {}

    ev = {
        "category": fit["category"],
        "horizon_days": HORIZON_DAYS,
        "features": features,
        "method": fit.get("method", "logistic"),
        "label_mode": fit.get("label_mode", "absolute"),
        "threshold": fit["threshold"],
        "n_train": int(len(fit["train"])),
        "n_test": int(len(test)),
        "test_start": test["Date"].min(),
        "test_end": test["Date"].max(),
        "accuracy": s["accuracy"],
        "auc": s["auc"],
        "n_buy_calls": s["n_calls"],
        "n_buy_dates": s["n_dates"],
        "pct_buy_calls": s["n_calls"] / len(test) if len(test) else float("nan"),
        "model_buy_avg_return": s["avg_return"],
        "model_buy_win_rate": s["win_rate"],
        "model_buy_profit_factor": s["profit_factor"],
        "n_rule_buy_calls": int(len(rule_buys)),
        "rule_buy_avg_return": float(rule_buys[ret_col].mean()) if not rule_buys.empty else float("nan"),
        "rule_buy_win_rate": float((rule_buys[ret_col] > 0).mean()) if not rule_buys.empty else float("nan"),
        "rule_buy_profit_factor": _profit_factor(rule_buys[ret_col]) if not rule_buys.empty else float("nan"),
        "baseline_avg_return": float(test[ret_col].mean()),
        "baseline_win_rate": float((test[ret_col] > 0).mean()),
        "importance": importance,
    }
    return ev


def _persist(fit: dict, ev: dict):
    """Save the fitted model bundle + its scorecard so predict_latest()
    and load_eval() can read them back later."""
    import joblib

    model_path = _model_path(fit["category"])
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump(
        {
            "model": fit["model"], "scaler": fit["scaler"], "features": fit["features"],
            "threshold": fit["threshold"], "method": fit.get("method", "logistic"),
            "label_mode": fit.get("label_mode", "absolute"),
        },
        model_path,
    )

    eval_path = _eval_path(fit["category"])
    with open(eval_path, "w") as f:
        json.dump(_json_safe(ev), f)


def fit_and_evaluate(category, timeframe="1d", features=None, method="logistic", label_mode="absolute"):
    """Train on the full feature set (or the given subset), evaluate
    out-of-sample, and persist both the model and the scorecard. Returns
    the evaluation dict, or None if there wasn't enough data to fit."""
    fit = train_model(category, timeframe, features=features, method=method, label_mode=label_mode)
    if fit is None:
        return None
    ev = evaluate(fit)
    _persist(fit, ev)
    return ev


def _forward_select(train: pd.DataFrame, val: pd.DataFrame, candidates, method: str, progress):
    """Greedy forward feature search for one method: starting from no
    features, repeatedly add whichever remaining candidate improves the
    validation slice's buy-call average return the most, among additions
    with enough validation calls *and* enough distinct dates behind them
    to be trusted (a date-clustered feature like mkt_breadth can rack up
    a big call count on a handful of dates — n_calls alone can't tell that
    apart from genuinely independent bets) — and only if it actually beats
    the current best (which starts at the validation set's own baseline
    return: buying indiscriminately). Stops the moment nothing clears
    that bar.

    Returns {"selected": [...], "history": [...], "val_score": float}, or
    None if nothing ever beat the baseline."""
    ret_col = f"ret_{HORIZON_DAYS}d"
    min_val_calls = max(MIN_VAL_CALLS_FOR_SELECTION, int(MIN_VAL_CALL_FRACTION * len(val)))
    min_val_dates = MIN_VAL_DATES_FOR_SELECTION

    selected, remaining, history = [], list(candidates), []
    best_score = float(val[ret_col].mean())

    while remaining:
        round_results = []
        for feat in remaining:
            trial_features = selected + [feat]
            bundle = _fit(train, trial_features, method=method)
            s = _score(bundle, val, trial_features)
            round_results.append((feat, s))

        qualifying = [
            (f, s) for f, s in round_results
            if s["n_calls"] >= min_val_calls and s["n_dates"] >= min_val_dates
        ]
        if not qualifying:
            progress(f"[ml-select] ({method}) no remaining feature clears the validation "
                     f"sample-size bar ({min_val_calls} calls, {min_val_dates} distinct dates) "
                     f"— stopping with {selected}")
            break
        best_feat, best_s = max(qualifying, key=lambda fr: fr[1]["avg_return"])
        if not (best_s["avg_return"] > best_score):
            progress(f"[ml-select] ({method}) adding {best_feat} ({best_s['avg_return']:+.2%}) "
                     f"wouldn't beat the current best ({best_score:+.2%}) — stopping with {selected}")
            break
        selected.append(best_feat)
        remaining.remove(best_feat)
        best_score = best_s["avg_return"]
        history.append({"added": best_feat, "method": method, "features_so_far": list(selected), **best_s})
        progress(f"[ml-select] ({method}) + {best_feat}: val avg return {best_s['avg_return']:+.2%}, "
                 f"win {best_s['win_rate']:.0%}, AUC {best_s['auc']:.2f}, n={best_s['n_calls']} "
                 f"-> {selected}")

    if not selected:
        return None
    return {"selected": selected, "history": history, "val_score": best_score}


def _walk_forward_folds(data: pd.DataFrame, min_train_end_date, n_folds=5):
    """Expanding-window folds after min_train_end_date: fold i trains on
    everything up to a cutoff (starting at min_train_end_date) and tests
    on the next equal-sized slice of the remaining dates; the cutoff
    walks forward each fold to include the previous fold's test window,
    so later folds train on strictly more history than earlier ones —
    the same shape a periodically-retrained live model would see.
    Returns a list of (train_df, test_df) tuples, oldest fold first."""
    dates = pd.Series(data["Date"].unique()).sort_values()
    remaining_dates = dates[dates > min_train_end_date].reset_index(drop=True)
    n_remaining = len(remaining_dates)
    if n_remaining < n_folds:
        return []
    window = n_remaining // n_folds

    folds = []
    cur_cutoff = min_train_end_date
    for i in range(n_folds):
        start_idx = i * window
        end_idx = n_remaining if i == n_folds - 1 else (i + 1) * window
        if start_idx >= end_idx:
            break
        test_start_date = remaining_dates.iloc[start_idx]
        test_end_date = remaining_dates.iloc[end_idx - 1]
        train = data[data["Date"] <= cur_cutoff]
        test = data[(data["Date"] >= test_start_date) & (data["Date"] <= test_end_date)]
        folds.append((train, test))
        cur_cutoff = test_end_date
    return folds


def walk_forward_validate(category, timeframe="1d", features=None, method="logistic",
                           label_mode="absolute", n_folds=5,
                           min_train_fraction=WALK_FORWARD_MIN_TRAIN_FRACTION,
                           progress=print, data=None, min_train_end_date=None):
    """Fit the SAME feature set + method repeatedly across several
    expanding-window folds walking forward through history, and report
    the *distribution* of out-of-sample results — not just one split's
    number. This is a stability check on an already-chosen configuration,
    not a search: pick features/method first (train_model(),
    select_features(), select_model(), or a persisted model via
    validate_persisted_model()), then use this to see whether that
    choice's performance holds up walking forward through time, or was a
    product of which single test window got used — exactly the failure
    mode a single train/val/test split can't catch on its own.

    data/min_train_end_date let select_features()/select_model() reuse
    their own already-built dataset and confine folds to the test region
    their search never touched, instead of rebuilding from scratch and
    re-deriving a generic cutoff.

    Returns {category, method, features, folds (DataFrame), summary}, or
    None if there isn't enough history for even one fold."""
    features = list(features) if features else list(FEATURES)
    if data is None:
        data = _build_dataset(category, timeframe, label_mode=label_mode)
    if len(data) < MIN_ROWS_PER_CATEGORY:
        return None

    if min_train_end_date is None:
        dates = pd.Series(data["Date"].unique()).sort_values()
        if len(dates) < 10:
            return None
        min_train_end_date = dates.iloc[int(len(dates) * min_train_fraction)]

    folds = _walk_forward_folds(data, min_train_end_date, n_folds=n_folds)
    if not folds:
        return None

    ret_col = f"ret_{HORIZON_DAYS}d"
    rows = []
    for i, (train, test) in enumerate(folds, 1):
        if train.empty or test.empty or train["label"].nunique() < 2:
            progress(f"[ml-walkforward:{category}] fold {i}: skipped (insufficient data/class variety)")
            continue
        bundle = _fit(train, features, method=method)
        s = _score(bundle, test, features)
        baseline = float(test[ret_col].mean())
        row = {
            "fold": i, "test_start": test["Date"].min(), "test_end": test["Date"].max(),
            "n_train": len(train), "n_test": len(test), "baseline_avg_return": baseline,
            "beats_baseline": bool(s["n_calls"] and s["avg_return"] > baseline),
            **s,
        }
        rows.append(row)
        progress(f"[ml-walkforward:{category}] fold {i} ({row['test_start'].date()}-{row['test_end'].date()}): "
                 f"avg return {s['avg_return']:+.2%} (baseline {baseline:+.2%}), win {s['win_rate']:.0%}, "
                 f"AUC {s['auc']:.2f}, n_calls={s['n_calls']} across {s['n_dates']} dates")

    if not rows:
        return None
    folds_df = pd.DataFrame(rows)
    with_calls = folds_df[folds_df["n_calls"] > 0]
    finite_pf = with_calls["profit_factor"].replace([float("inf")], pd.NA).dropna()

    summary = {
        "category": category, "method": method, "features": features,
        "n_folds": int(len(folds_df)), "n_folds_with_calls": int(len(with_calls)),
        "avg_return_mean": float(with_calls["avg_return"].mean()) if not with_calls.empty else float("nan"),
        "avg_return_std": float(with_calls["avg_return"].std()) if len(with_calls) > 1 else float("nan"),
        "win_rate_mean": float(with_calls["win_rate"].mean()) if not with_calls.empty else float("nan"),
        "auc_mean": float(folds_df["auc"].mean()),
        "profit_factor_mean": float(finite_pf.mean()) if not finite_pf.empty else float("nan"),
        "pct_folds_beating_baseline": float(folds_df["beats_baseline"].mean()),
        "total_calls": int(folds_df["n_calls"].sum()),
        "total_distinct_dates": int(folds_df["n_dates"].sum()),
    }
    return {"category": category, "method": method, "features": features, "folds": folds_df, "summary": summary}


def validate_persisted_model(category, timeframe="1d", n_folds=5,
                              min_train_fraction=WALK_FORWARD_MIN_TRAIN_FRACTION, progress=print):
    """Walk-forward validation of whatever model is currently persisted
    for this category (from mlsignal/mlselect/mlcycle) — a general
    "has this held up over time" check, runnable any time. None if no
    model has been persisted yet."""
    bundle = load_model(category)
    if bundle is None:
        return None
    return walk_forward_validate(
        category, timeframe, features=bundle["features"], method=bundle.get("method", "logistic"),
        label_mode=bundle.get("label_mode", "absolute"), n_folds=n_folds,
        min_train_fraction=min_train_fraction, progress=progress,
    )


def format_walkforward_report(result) -> str:
    if not result:
        return "No walk-forward result available (not enough history for multiple folds).\n"
    s = result["summary"]
    lines = [
        f"[{s['category']}] walk-forward validation ({s['method']}, {len(s['features'])} features, "
        f"{s['n_folds']} folds)",
        f"  avg return across folds: {s['avg_return_mean']:+.2%} +/- {s['avg_return_std']:.2%} "
        f"(win rate {s['win_rate_mean']:.0%}, AUC {s['auc_mean']:.2f}, "
        f"profit factor {s['profit_factor_mean']:.2f})",
        f"  {s['pct_folds_beating_baseline']:.0%} of folds beat their own baseline "
        f"({s['n_folds_with_calls']}/{s['n_folds']} folds had any buy calls)",
        f"  total buy calls: {s['total_calls']} across {s['total_distinct_dates']} distinct dates",
        "  per-fold detail:",
    ]
    for _, r in result["folds"].iterrows():
        lines.append(
            f"    fold {int(r['fold'])} {r['test_start'].date()}-{r['test_end'].date()}: "
            f"{r['avg_return']:+.2%} vs baseline {r['baseline_avg_return']:+.2%}, "
            f"win {r['win_rate']:.0%}, n={r['n_calls']} ({r['n_dates']} dates)"
        )
    return "\n".join(lines) + "\n"


def select_features(category, timeframe="1d", candidates=None, progress=print, method="logistic",
                     label_mode="absolute", confirm_folds=CONFIRM_N_FOLDS):
    """Algorithmic feature selection for a single method (default:
    logistic regression) — see _forward_select() for the search itself.
    The final feature subset is fit once on train+validation and
    confirmed two ways: a single evaluate() on the test slice (final_eval,
    kept for backward compatibility — one split, one number), and a
    walk_forward_validate() across confirm_folds expanding-window folds
    *within* that same test slice (walk_forward — several splits, a
    distribution). Trust the distribution over the single number; a
    single split can be lucky or unlucky (see module docstring).

    Returns {selected_features, history, final_eval, walk_forward, fit},
    or None if there isn't enough data or nothing ever clears the bar."""
    candidates = list(candidates or FEATURES)
    data = _build_dataset(category, timeframe, label_mode=label_mode)
    if len(data) < MIN_ROWS_PER_CATEGORY:
        return None

    train, val, test = _three_way_time_split(data)
    if train.empty or val.empty or test.empty:
        return None
    if train["label"].nunique() < 2 or val["label"].nunique() < 2:
        return None

    result = _forward_select(train, val, candidates, method, progress)
    if result is None:
        progress(f"[ml-select:{category}] ({method}) no single feature beat the validation baseline")
        return None

    trainval = pd.concat([train, val], ignore_index=True)
    bundle = _fit(trainval, result["selected"], method=method)
    fit = {
        "category": category, "features": result["selected"], "method": method, "label_mode": label_mode,
        "model": bundle["model"], "scaler": bundle["scaler"], "threshold": bundle["threshold"],
        "train": trainval, "test": test,
    }
    final_eval = evaluate(fit)
    walk_forward = walk_forward_validate(
        category, features=result["selected"], method=method, progress=progress,
        data=pd.concat([trainval, test], ignore_index=True),
        min_train_end_date=trainval["Date"].max(), n_folds=confirm_folds,
    )

    return {
        "category": category, "selected_features": result["selected"],
        "history": result["history"], "final_eval": final_eval,
        "walk_forward": walk_forward, "fit": fit,
    }


def select_model(category, timeframe="1d", methods=METHODS_ORDER, candidates=None, progress=print,
                  label_mode="absolute", confirm_folds=CONFIRM_N_FOLDS):
    """Cycle through several modeling methods, running the same forward
    feature search (train-to-fit, validation-to-decide) independently for
    each, then pick whichever method+feature combination scored best *on
    validation*. That single winner is refit on train+validation and
    confirmed two ways: a single evaluate() on the test slice (final_eval)
    and a walk_forward_validate() across confirm_folds expanding-window
    folds within that same test slice (walk_forward) — comparing several
    searches by whichever looks best on test would repeat the threshold-
    overfitting mistake this module already learned from, one level up,
    so only the single winner ever touches test, and even then via
    multiple folds rather than trusting one split.

    Returns {category, method, selected_features, runs, final_eval,
    walk_forward, fit}, or None if no method's search ever beat the
    validation baseline."""
    candidates = list(candidates or FEATURES)
    data = _build_dataset(category, timeframe, label_mode=label_mode)
    if len(data) < MIN_ROWS_PER_CATEGORY:
        return None

    train, val, test = _three_way_time_split(data)
    if train.empty or val.empty or test.empty:
        return None
    if train["label"].nunique() < 2 or val["label"].nunique() < 2:
        return None

    runs = {}
    for method in methods:
        progress(f"[ml-cycle:{category}] === method: {method} ===")
        runs[method] = _forward_select(train, val, candidates, method, progress)

    qualifying = {m: r for m, r in runs.items() if r is not None}
    if not qualifying:
        progress(f"[ml-cycle:{category}] no method's search ever beat the validation baseline")
        return None

    best_method = max(qualifying, key=lambda m: qualifying[m]["val_score"])
    best = qualifying[best_method]
    progress(f"[ml-cycle:{category}] winner: {best_method} ({best['val_score']:+.2%} val) "
             f"-> {best['selected']}")

    trainval = pd.concat([train, val], ignore_index=True)
    bundle = _fit(trainval, best["selected"], method=best_method)
    fit = {
        "category": category, "features": best["selected"], "method": best_method, "label_mode": label_mode,
        "model": bundle["model"], "scaler": bundle["scaler"], "threshold": bundle["threshold"],
        "train": trainval, "test": test,
    }
    final_eval = evaluate(fit)
    walk_forward = walk_forward_validate(
        category, features=best["selected"], method=best_method, progress=progress,
        data=pd.concat([trainval, test], ignore_index=True),
        min_train_end_date=trainval["Date"].max(), n_folds=confirm_folds,
    )

    return {
        "category": category, "method": best_method, "selected_features": best["selected"],
        "runs": runs, "final_eval": final_eval, "walk_forward": walk_forward, "fit": fit,
    }


def fit_selected_and_persist(category, timeframe="1d", candidates=None, progress=print,
                              label_mode="absolute"):
    """Run select_features() and persist the resulting model/eval exactly
    like fit_and_evaluate() does, so predict_latest() picks it up."""
    result = select_features(category, timeframe, candidates=candidates, progress=progress,
                              label_mode=label_mode)
    if result is None:
        return None
    _persist(result["fit"], result["final_eval"])
    return result


def fit_cycled_and_persist(category, timeframe="1d", methods=METHODS_ORDER, candidates=None,
                            progress=print, label_mode="absolute"):
    """Run select_model() and persist the winning method+features exactly
    like fit_and_evaluate() does, so predict_latest() picks it up."""
    result = select_model(category, timeframe, methods=methods, candidates=candidates, progress=progress,
                           label_mode=label_mode)
    if result is None:
        return None
    _persist(result["fit"], result["final_eval"])
    return result


def format_selection_report(result) -> str:
    if not result:
        return "No feature selection result available (not enough data, or nothing beat baseline).\n"
    lines = [f"[{result['category']}] algorithmic feature selection (forward search, validation-scored)"]
    lines.append("  selection path:")
    for step in result["history"]:
        lines.append(
            f"    + {step['added']:<18} val avg return {step['avg_return']:+.2%}, "
            f"win {step['win_rate']:.0%}, AUC {step['auc']:.2f}, n={step['n_calls']}"
        )
    lines.append(f"  selected: {', '.join(result['selected_features'])}")
    lines.append("")
    lines.append(format_eval_report(result["final_eval"]).rstrip())
    lines.append("")
    lines.append("  single-split confirmation above; walk-forward confirmation below "
                  "(trust this more — it's several splits, not one):")
    lines.append(format_walkforward_report(result.get("walk_forward")).rstrip())
    return "\n".join(lines) + "\n"


def format_model_selection_report(result) -> str:
    if not result:
        return "No model selection result available (not enough data, or no method beat baseline).\n"
    lines = [f"[{result['category']}] cycling {len(result['runs'])} methods x forward feature search"]
    for method, run in result["runs"].items():
        if run is None:
            lines.append(f"  {method:<10} no feature combination beat the validation baseline")
        else:
            lines.append(
                f"  {method:<10} val avg return {run['val_score']:+.2%} "
                f"({len(run['selected'])} features: {', '.join(run['selected'])})"
            )
    lines.append(f"  winner: {result['method']}")
    lines.append("")
    lines.append(format_eval_report(result["final_eval"]).rstrip())
    lines.append("")
    lines.append("  single-split confirmation above; walk-forward confirmation below "
                  "(trust this more — it's several splits, not one):")
    lines.append(format_walkforward_report(result.get("walk_forward")).rstrip())
    return "\n".join(lines) + "\n"


def select_all_and_report(categories=("crypto", "stocks"), label_mode="absolute") -> str:
    lines = [f"ML Signal Model — algorithmic feature selection ({label_mode} label) — "
             f"{pd.Timestamp.now().date()}", ""]
    for cat in categories:
        result = fit_selected_and_persist(cat, label_mode=label_mode)
        lines.append(format_selection_report(result).rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def cycle_all_and_report(categories=("crypto", "stocks"), methods=METHODS_ORDER, label_mode="absolute") -> str:
    lines = [f"ML Signal Model — method x feature cycling ({label_mode} label) — "
             f"{pd.Timestamp.now().date()}", ""]
    for cat in categories:
        result = fit_cycled_and_persist(cat, methods=methods, label_mode=label_mode)
        lines.append(format_model_selection_report(result).rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def walkforward_all_and_report(categories=("crypto", "stocks"), n_folds=5) -> str:
    """Walk-forward validation of whichever model is currently persisted
    per category — run any time to sanity-check that a model built by
    mlsignal/mlselect/mlcycle still holds up walking forward through
    history, independent of re-running the search that built it."""
    lines = [f"ML Signal Model — walk-forward validation — {pd.Timestamp.now().date()}", ""]
    for cat in categories:
        result = validate_persisted_model(cat, n_folds=n_folds)
        if result is None:
            lines.append(f"[{cat}] no persisted model to validate — run mlsignal/mlselect/mlcycle first.")
        else:
            lines.append(format_walkforward_report(result).rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def load_model(category):
    """Load the persisted {model, scaler, features} bundle, or None if
    fit_and_evaluate() hasn't run for this category yet."""
    import joblib

    path = _model_path(category)
    if not os.path.exists(path):
        return None
    return joblib.load(path)


def load_eval(category) -> dict:
    path = _eval_path(category)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def predict_latest(category, timeframe="1d") -> pd.DataFrame:
    """The trained model's buy probability for every symbol's most recent
    bar, ranked highest-first. Empty if there's no trained model yet."""
    bundle = load_model(category)
    if bundle is None:
        return pd.DataFrame()
    clf, scaler, features = bundle["model"], bundle["scaler"], bundle["features"]
    threshold = bundle.get("threshold", 0.5)

    sigs = db.scan_signals_lake(category, timeframe, columns=_RAW_COLUMNS)
    if sigs.empty:
        return pd.DataFrame()
    required = ["Close", "ma_50", "ma_200", "bb_upper", "bb_lower"] + [
        c for c in _INDICATOR_FEATURES if c not in _BOOL_FEATURES
    ]
    sigs = sigs.dropna(subset=required)
    if sigs.empty:
        return pd.DataFrame()
    # Engineer on the full per-symbol history (rolling windows need it),
    # THEN truncate to each symbol's latest bar.
    sigs = _engineer_features(sigs, category)

    latest = sigs.sort_values("Date").groupby("symbol").tail(1).copy()
    latest = latest.dropna(subset=[c for c in features if c not in _BOOL_FEATURES])
    if latest.empty:
        return latest
    X = scaler.transform(latest[features].to_numpy())
    latest["ml_buy_proba"] = clf.predict_proba(X)[:, 1]
    latest["ml_signal"] = latest["ml_buy_proba"].ge(threshold).map({True: "ML Buy", False: "No Call"})
    return latest[["symbol", "Date", "Close", "signal", "ml_buy_proba", "ml_signal"]].sort_values(
        "ml_buy_proba", ascending=False
    ).reset_index(drop=True)


def format_eval_report(ev) -> str:
    if not ev:
        return "No trained model / evaluation available yet.\n"
    lines = [
        f"[{ev['category']}] ML buy-signal model ({ev.get('method', 'logistic')}, "
        f"{ev['horizon_days']}d horizon, {ev.get('label_mode', 'absolute')} label)",
        f"  out-of-sample window {ev['test_start']} -> {ev['test_end']} "
        f"(train n={ev['n_train']}, test n={ev['n_test']})",
        f"  accuracy {ev['accuracy']:.0%}, AUC {ev['auc']:.2f} "
        f"(buy threshold {ev['threshold']:.2f}, picked from training data)",
        f"  model buy calls: {ev['n_buy_calls']} across {ev['n_buy_dates']} distinct dates "
        f"({ev['pct_buy_calls']:.0%} of test rows) — avg return {ev['model_buy_avg_return']:+.1%}, "
        f"win rate {ev['model_buy_win_rate']:.0%}, profit factor {ev['model_buy_profit_factor']:.2f}",
    ]
    if not pd.isna(ev.get("rule_buy_avg_return")):
        lines.append(
            f"  rule-based Buy tiers (same window): {ev['n_rule_buy_calls']} calls — "
            f"avg return {ev['rule_buy_avg_return']:+.1%}, win rate {ev['rule_buy_win_rate']:.0%}, "
            f"profit factor {ev['rule_buy_profit_factor']:.2f}"
        )
    lines.append(
        f"  baseline (unconditional, same window): avg return {ev['baseline_avg_return']:+.1%}, "
        f"win rate {ev['baseline_win_rate']:.0%}"
    )
    importance = ev.get("importance") or {}
    if importance:
        top = sorted(importance.items(), key=lambda kv: abs(kv[1]), reverse=True)[:5]
        lines.append("  strongest features: " + ", ".join(f"{k} ({v:+.2f})" for k, v in top))
    return "\n".join(lines) + "\n"


def fit_all_and_report(categories=("crypto", "stocks"), label_mode="absolute") -> str:
    lines = [f"ML Signal Model ({label_mode} label) — {pd.Timestamp.now().date()}", ""]
    for cat in categories:
        ev = fit_and_evaluate(cat, label_mode=label_mode)
        lines.append(format_eval_report(ev).rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    print(fit_all_and_report())
