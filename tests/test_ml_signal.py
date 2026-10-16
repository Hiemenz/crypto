import pandas as pd
import pytest

import db
from conftest import make_ohlcv
from crypto_signal_station import ml_signal


def _daily_ending_now(days, closes):
    end = pd.Timestamp.now().normalize()
    dates = pd.date_range(end=end, periods=days, freq="D")
    return make_ohlcv(dates.strftime("%Y-%m-%d"), closes)


def _seed_learnable_symbol(sym, category, days=900, cycle=100, signal_col="Hold"):
    """Alternating 100-day up/down phases: rsi is set to 25 during the
    uptrend phase and 75 during the downtrend phase, so it perfectly
    correlates with whether the next HORIZON_DAYS return is positive —
    a clean, separable pattern the classifier should learn easily, used
    to prove the train/evaluate/predict pipeline is wired correctly (not
    to prove logistic regression is a good trading strategy)."""
    price = 100.0
    closes = []
    rsis = []
    for i in range(days):
        phase_up = (i // cycle) % 2 == 0
        price *= (1 + (0.004 if phase_up else -0.004))
        closes.append(price)
        rsis.append(25.0 if phase_up else 75.0)

    ohlcv = _daily_ending_now(days, closes)
    db.replace_ohlcv(ohlcv, sym, category)

    sigs = pd.DataFrame({
        "Date": ohlcv["Date"],
        "Close": closes,
        "signal": signal_col,
        "rsi": rsis,
        "mfi": 50.0,
        "stoch_rsi_k": 0.5,
        "stoch_rsi_d": 0.5,
        "bb_pband": 0.5,
        "macd_hist": 0.0,
        "atr_pct": 0.02,
        "is_bull": True,
        "vol_spike": False,
        "rsi_bullish_div": False,
        "rsi_bearish_div": False,
        "ma_50": closes,
        "ma_200": closes,
        # proportional to Close so bb_bandwidth = (upper-lower)/Close stays
        # a constant, uninformative 0.04 regardless of the price trend
        "bb_upper": [c * 1.02 for c in closes],
        "bb_lower": [c * 0.98 for c in closes],
    })
    db.replace_signals(sigs, sym, category, "1d")
    return ohlcv, sigs


def test_build_dataset_empty_lake(lake):
    assert ml_signal._build_dataset("crypto").empty


def test_build_dataset_labels_match_forward_return_sign(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=400)
    data = ml_signal._build_dataset("crypto")
    assert not data.empty
    ret_col = f"ret_{ml_signal.HORIZON_DAYS}d"
    assert set(data["label"].unique()) <= {0, 1}
    assert (data.loc[data["label"] == 1, ret_col] > 0).all()
    assert (data.loc[data["label"] == 0, ret_col] <= 0).all()


def test_time_split_respects_date_ordering(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=400)
    data = ml_signal._build_dataset("crypto")
    train, test = ml_signal._time_split(data, test_fraction=0.2)
    assert not train.empty and not test.empty
    assert train["Date"].max() < test["Date"].min()


def test_select_threshold_prefers_higher_return_bucket():
    # Three tiers of (proba, return): a stricter cutoff isolates the best
    # tier alone (avg +15%) instead of diluting it with the mediocre one
    # a looser cutoff would also sweep in (avg +10%).
    returns = pd.Series([0.15] * 20 + [0.05] * 20 + [-0.05] * 60)
    proba = pd.Series([0.9] * 20 + [0.6] * 20 + [0.1] * 60).to_numpy()
    t = ml_signal._select_threshold(returns, proba, min_calls=10,
                                     candidates=[0.2, 0.5, 0.8])
    assert t == 0.8


def test_select_threshold_falls_back_when_nothing_qualifies():
    returns = pd.Series([0.01] * 5)
    proba = pd.Series([0.9] * 5).to_numpy()
    t = ml_signal._select_threshold(returns, proba, min_calls=20, candidates=[0.5, 0.8])
    assert t == 0.5


def test_select_threshold_rejects_date_clustered_calls():
    # 50 calls all landing on the same 2 calendar dates (a market-wide
    # feature firing for many symbols at once) shouldn't be trusted just
    # because n_calls clears the bar — min_dates catches what n_calls
    # alone would miss.
    dates = pd.Series(pd.to_datetime(["2024-01-01"] * 25 + ["2024-01-02"] * 25))
    returns = pd.Series([0.20] * 50)  # looks great...
    proba = pd.Series([0.9] * 50).to_numpy()
    t = ml_signal._select_threshold(
        returns, proba, train_dates=dates, min_calls=10, min_dates=10, candidates=[0.8]
    )
    assert t == 0.5  # ...but only 2 distinct dates behind it, so it's rejected


def test_select_threshold_accepts_when_dates_are_spread_out():
    dates = pd.Series(pd.date_range("2024-01-01", periods=50, freq="D"))
    returns = pd.Series([0.20] * 50)
    proba = pd.Series([0.9] * 50).to_numpy()
    t = ml_signal._select_threshold(
        returns, proba, train_dates=dates, min_calls=10, min_dates=10, candidates=[0.8]
    )
    assert t == 0.8


def test_train_model_none_below_min_rows(lake):
    # 250 days, minus the last 30 with no realized ret_30d yet: ~220 usable
    # rows, below MIN_ROWS_PER_CATEGORY (500).
    _seed_learnable_symbol("AAA-USD", "crypto", days=250)
    assert ml_signal.train_model("crypto") is None


def test_fit_evaluate_predict_roundtrip(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=900)
    _seed_learnable_symbol("BBB-USD", "crypto", days=900)

    ev = ml_signal.fit_and_evaluate("crypto")
    assert ev is not None
    assert ev["category"] == "crypto"
    assert ev["n_train"] > 0 and ev["n_test"] > 0
    # a near-perfectly separable synthetic pattern: the model should
    # clear a high bar out-of-sample, not just beat a coin flip
    assert ev["accuracy"] > 0.8
    assert ev["auc"] > 0.8
    assert not pd.isna(ev["model_buy_avg_return"])
    assert ev["model_buy_avg_return"] > ev["baseline_avg_return"]
    assert ev["label_mode"] == "absolute"
    assert 0 < ev["n_buy_dates"] <= ev["n_buy_calls"]
    assert ev["model_buy_profit_factor"] > 1  # avg return is positive -> gains outweigh losses

    # persisted model is loadable and reusable
    bundle = ml_signal.load_model("crypto")
    assert bundle is not None
    assert set(bundle["features"]) == set(ml_signal.FEATURES)

    stored_eval = ml_signal.load_eval("crypto")
    assert stored_eval["category"] == "crypto"

    preds = ml_signal.predict_latest("crypto")
    assert not preds.empty
    assert set(preds["symbol"]) == {"AAA-USD", "BBB-USD"}
    assert set(preds["ml_signal"].unique()) <= {"ML Buy", "No Call"}

    text = ml_signal.format_eval_report(ev)
    assert "crypto" in text
    assert "rule-based Buy tiers" not in text  # no "Buy" rule signals were seeded


def test_fit_and_evaluate_with_rule_based_buys(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=900, signal_col="Hold")
    sigs = db.load_signals("AAA-USD", "crypto", "1d")
    sigs.loc[sigs.index[-40:-10], "signal"] = "Good Buy"
    db.replace_signals(sigs, "AAA-USD", "crypto", "1d")

    ev = ml_signal.fit_and_evaluate("crypto")
    assert ev is not None
    if ev["n_rule_buy_calls"] > 0:
        text = ml_signal.format_eval_report(ev)
        assert "rule-based Buy tiers" in text


def test_fit_and_evaluate_insufficient_data_returns_none(lake):
    assert ml_signal.fit_and_evaluate("crypto") is None


def test_format_eval_report_handles_none():
    assert "No trained model" in ml_signal.format_eval_report(None)
    assert "No trained model" in ml_signal.format_eval_report({})


def test_predict_latest_without_model_returns_empty(lake):
    assert ml_signal.predict_latest("crypto").empty


def test_fit_all_and_report_handles_missing_data(lake):
    text = ml_signal.fit_all_and_report(categories=("crypto",))
    assert "No trained model" in text


def test_three_way_time_split_is_chronological_and_disjoint(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=400)
    data = ml_signal._build_dataset("crypto")
    train, val, test = ml_signal._three_way_time_split(data)
    assert not train.empty and not val.empty and not test.empty
    assert train["Date"].max() < val["Date"].min()
    assert val["Date"].max() < test["Date"].min()


def test_select_features_none_below_min_rows(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=250)
    assert ml_signal.select_features("crypto") is None


def test_select_features_picks_the_informative_indicator(lake):
    # rsi is the only *candidate* that varies (it perfectly tracks the
    # future return's sign); every other one is a constant, uninformative
    # column. Restrict the pool to the original raw-indicator candidates
    # (excluding the price-derived engineered features, which would
    # legitimately also correlate with this synthetic price trend and
    # muddy what this test is isolating) so the search has exactly one
    # genuinely informative candidate to find.
    _seed_learnable_symbol("AAA-USD", "crypto", days=900)
    _seed_learnable_symbol("BBB-USD", "crypto", days=900)
    candidates = ml_signal._INDICATOR_FEATURES + ["ma_spread"]

    result = ml_signal.select_features("crypto", candidates=candidates, progress=lambda *a: None)
    assert result is not None
    assert result["selected_features"] == ["rsi"]
    assert len(result["history"]) == 1
    assert result["history"][0]["added"] == "rsi"

    final = result["final_eval"]
    assert final["features"] == ["rsi"]
    assert final["accuracy"] > 0.8
    assert final["model_buy_avg_return"] > final["baseline_avg_return"]

    # persisted exactly like fit_and_evaluate()'s model
    persisted = ml_signal.fit_selected_and_persist("crypto", candidates=candidates, progress=lambda *a: None)
    assert persisted["selected_features"] == ["rsi"]
    bundle = ml_signal.load_model("crypto")
    assert bundle["features"] == ["rsi"]

    text = ml_signal.format_selection_report(result)
    assert "rsi" in text
    assert "selection path" in text


def _build_date_labeled_frame(positive_dates, n_calls_per_date, n_negative):
    """A minimal synthetic train/val frame with a single binary feature
    ('clustered') that perfectly predicts the label — used to isolate
    _forward_select()'s date-spread gate from everything else."""
    rows = []
    for d in positive_dates:
        for _ in range(n_calls_per_date):
            rows.append({"Date": d, "ret_30d": 0.10, "label": 1, "clustered": 1})
    for d in pd.date_range("2030-01-01", periods=n_negative, freq="D"):
        rows.append({"Date": d, "ret_30d": -0.01, "label": 0, "clustered": 0})
    return pd.DataFrame(rows)


def test_forward_select_rejects_date_clustered_feature():
    # 60 calls (well above min_val_calls) but confined to only 3 distinct
    # dates — not enough spread to trust, even though the feature
    # perfectly predicts the label.
    cluster_dates = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    train = _build_date_labeled_frame(cluster_dates, n_calls_per_date=20, n_negative=200)
    val = _build_date_labeled_frame(cluster_dates, n_calls_per_date=20, n_negative=200)
    assert val["label"].nunique() == 2

    result = ml_signal._forward_select(train, val, ["clustered"], "logistic", progress=lambda *a: None)
    assert result is None


def test_forward_select_accepts_date_spread_feature():
    # Same perfectly-predictive feature, but its 20 positive calls land
    # on 20 distinct dates — clears both the call-count and date-spread
    # bars, so it should be selected.
    spread_dates = pd.date_range("2024-01-01", periods=20, freq="D")
    train = _build_date_labeled_frame(spread_dates, n_calls_per_date=1, n_negative=200)
    val = _build_date_labeled_frame(spread_dates, n_calls_per_date=1, n_negative=200)

    result = ml_signal._forward_select(train, val, ["clustered"], "logistic", progress=lambda *a: None)
    assert result is not None
    assert "clustered" in result["selected"]


def test_select_features_none_when_nothing_beats_baseline(lake):
    # Every candidate feature is a constant: nothing can discriminate
    # buy-worthy rows from the rest, so the search should refuse to select
    # anything rather than force a feature that can't possibly help.
    days = 900
    ohlcv = _daily_ending_now(days, [100.0 * (1.0005 ** i) for i in range(days)])
    db.replace_ohlcv(ohlcv, "AAA-USD", "crypto")
    sigs = pd.DataFrame({
        "Date": ohlcv["Date"], "Close": ohlcv["Close"], "signal": "Hold",
        "rsi": 50.0, "mfi": 50.0, "stoch_rsi_k": 0.5, "stoch_rsi_d": 0.5,
        "bb_pband": 0.5, "macd_hist": 0.0, "atr_pct": 0.02,
        "is_bull": True, "vol_spike": False,
        "rsi_bullish_div": False, "rsi_bearish_div": False,
        "ma_50": ohlcv["Close"], "ma_200": ohlcv["Close"],
        "bb_upper": ohlcv["Close"] * 1.02, "bb_lower": ohlcv["Close"] * 0.98,
    })
    db.replace_signals(sigs, "AAA-USD", "crypto", "1d")

    assert ml_signal.select_features("crypto", progress=lambda *a: None) is None


def test_format_selection_report_handles_none():
    assert "No feature selection result" in ml_signal.format_selection_report(None)


def test_select_all_and_report_handles_missing_data(lake):
    text = ml_signal.select_all_and_report(categories=("crypto",))
    assert "No feature selection result" in text


def test_engineer_features_computes_momentum_bandwidth_and_breadth(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=900)
    sigs = db.scan_signals_lake("crypto", "1d", columns=ml_signal._RAW_COLUMNS)
    out = ml_signal._engineer_features(sigs, "crypto")

    row = out.sort_values("Date").iloc[-1]
    closes = out.sort_values("Date")["Close"]
    expected_mom5 = closes.iloc[-1] / closes.iloc[-6] - 1
    assert row["mom_5d"] == pytest.approx(expected_mom5)
    assert row["bb_bandwidth"] == pytest.approx(0.04, abs=1e-9)  # (1.02-0.98)x proportional to Close
    assert row["atr_pct_chg_5d"] == pytest.approx(0.0, abs=1e-9)  # constant atr_pct -> zero change
    # market breadth is a same-value merge across all symbols on a date
    assert not out["mkt_breadth"].isna().all()


def test_predict_latest_uses_full_history_for_rolling_features(lake):
    # mom_5d needs 5 rows of prior history to be non-NaN; predict_latest
    # must engineer features on the full per-symbol series *before*
    # truncating to each symbol's latest bar, or this would come out NaN
    # and the row would get dropped.
    _seed_learnable_symbol("AAA-USD", "crypto", days=900)
    ml_signal.fit_and_evaluate("crypto", features=["mom_5d", "rsi"])

    preds = ml_signal.predict_latest("crypto")
    assert not preds.empty
    assert set(preds["symbol"]) == {"AAA-USD"}


def test_make_estimator_unknown_method_raises():
    with pytest.raises(ValueError):
        ml_signal._make_estimator("nope")


def test_fit_supports_all_three_methods(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=900)
    _seed_learnable_symbol("BBB-USD", "crypto", days=900)
    for method in ml_signal.METHODS_ORDER:
        ev = ml_signal.fit_and_evaluate("crypto", features=["rsi"], method=method)
        assert ev is not None
        assert ev["method"] == method
        assert ev["accuracy"] > 0.7


def test_select_model_cycles_methods_and_persists_winner(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=900)
    _seed_learnable_symbol("BBB-USD", "crypto", days=900)
    candidates = ml_signal._INDICATOR_FEATURES + ["ma_spread"]

    result = ml_signal.select_model("crypto", candidates=candidates, progress=lambda *a: None)
    assert result is not None
    assert result["method"] in ml_signal.METHODS_ORDER
    assert set(result["runs"].keys()) == set(ml_signal.METHODS_ORDER)
    assert "rsi" in result["selected_features"]
    assert result["final_eval"]["method"] == result["method"]

    text = ml_signal.format_model_selection_report(result)
    assert "winner" in text
    assert result["method"] in text

    persisted = ml_signal.fit_cycled_and_persist("crypto", candidates=candidates, progress=lambda *a: None)
    assert persisted["method"] == result["method"]
    bundle = ml_signal.load_model("crypto")
    assert bundle["method"] == result["method"]


def test_select_model_none_below_min_rows(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=250)
    assert ml_signal.select_model("crypto", progress=lambda *a: None) is None


def test_format_model_selection_report_handles_none():
    assert "No model selection result" in ml_signal.format_model_selection_report(None)


def test_cycle_all_and_report_handles_missing_data(lake):
    text = ml_signal.cycle_all_and_report(categories=("crypto",))
    assert "No model selection result" in text


def _seed_constant_growth_symbol(sym, category, days, rate):
    """Pure exponential growth at a fixed daily rate: forward returns
    (and short-horizon momentum) come out as an exact constant for the
    whole series — used to build a deterministic cross-sectional ranking
    across several symbols growing at different constant rates."""
    closes = [100.0 * (1 + rate) ** i for i in range(days)]
    ohlcv = _daily_ending_now(days, closes)
    db.replace_ohlcv(ohlcv, sym, category)
    sigs = pd.DataFrame({
        "Date": ohlcv["Date"], "Close": ohlcv["Close"], "signal": "Hold",
        "rsi": 50.0, "mfi": 50.0, "stoch_rsi_k": 0.5, "stoch_rsi_d": 0.5,
        "bb_pband": 0.5, "macd_hist": 0.0, "atr_pct": 0.02,
        "is_bull": True, "vol_spike": False,
        "rsi_bullish_div": False, "rsi_bearish_div": False,
        "ma_50": ohlcv["Close"], "ma_200": ohlcv["Close"],
        "bb_upper": ohlcv["Close"] * 1.02, "bb_lower": ohlcv["Close"] * 0.98,
    })
    db.replace_signals(sigs, sym, category, "1d")
    return ohlcv


# ---- profit factor -----------------------------------------------------

def test_profit_factor_weighs_win_size_not_just_frequency():
    rets = pd.Series([0.10, 0.10, -0.05])
    assert ml_signal._profit_factor(rets) == pytest.approx(0.20 / 0.05)


def test_profit_factor_inf_with_no_losses():
    assert ml_signal._profit_factor(pd.Series([0.1, 0.2])) == float("inf")


def test_profit_factor_nan_with_no_trades_or_all_flat():
    assert pd.isna(ml_signal._profit_factor(pd.Series([], dtype=float)))
    assert pd.isna(ml_signal._profit_factor(pd.Series([0.0, 0.0])))


# ---- relative (cross-sectional) label ----------------------------------

def test_build_dataset_relative_label_uses_cross_sectional_median(lake):
    for sym, rate in (("AAA-USD", 0.002), ("BBB-USD", 0.001), ("CCC-USD", 0.0005)):
        _seed_constant_growth_symbol(sym, "crypto", 900, rate)

    data = ml_signal._build_dataset("crypto", label_mode="relative")
    assert not data.empty
    by_sym = data.groupby("symbol")["label"].mean()
    assert by_sym["AAA-USD"] == pytest.approx(1.0)   # always beats the 3-way median
    assert by_sym["BBB-USD"] == pytest.approx(0.0)   # always *is* the median (strict >)
    assert by_sym["CCC-USD"] == pytest.approx(0.0)   # always below the median


def test_build_dataset_absolute_label_default(lake):
    _seed_constant_growth_symbol("AAA-USD", "crypto", 900, 0.002)
    data = ml_signal._build_dataset("crypto")
    assert (data["label"] == 1).all()  # every forward return is positive


def test_fit_and_evaluate_relative_label_mode(lake):
    for sym, rate in (("AAA-USD", 0.002), ("BBB-USD", 0.001), ("CCC-USD", 0.0005)):
        _seed_constant_growth_symbol(sym, "crypto", 900, rate)

    ev = ml_signal.fit_and_evaluate("crypto", features=["mom_5d"], label_mode="relative")
    assert ev is not None
    assert ev["label_mode"] == "relative"
    assert ev["accuracy"] > 0.9  # mom_5d is a clean 3-valued split matching the label exactly


def test_select_features_threads_label_mode(lake):
    for sym, rate in (("AAA-USD", 0.002), ("BBB-USD", 0.001), ("CCC-USD", 0.0005)):
        _seed_constant_growth_symbol(sym, "crypto", 900, rate)

    result = ml_signal.select_features(
        "crypto", candidates=["mom_5d"], label_mode="relative", progress=lambda *a: None
    )
    assert result is not None
    assert result["final_eval"]["label_mode"] == "relative"


# ---- walk-forward validation --------------------------------------------

def test_walk_forward_folds_expanding_window_no_overlap():
    dates = pd.date_range("2020-01-01", periods=1000, freq="D")
    data = pd.DataFrame({"Date": dates})
    folds = ml_signal._walk_forward_folds(data, dates[400], n_folds=4)
    assert len(folds) == 4

    prev_train_len = 0
    prev_test_end = None
    for train, test in folds:
        assert len(train) >= prev_train_len  # expanding window: never shrinks
        prev_train_len = len(train)
        assert train["Date"].max() < test["Date"].min()  # no leakage
        if prev_test_end is not None:
            assert test["Date"].min() > prev_test_end  # folds don't overlap
        prev_test_end = test["Date"].max()


def test_walk_forward_folds_empty_when_not_enough_remaining_dates():
    dates = pd.date_range("2020-01-01", periods=10, freq="D")
    data = pd.DataFrame({"Date": dates})
    assert ml_signal._walk_forward_folds(data, dates[8], n_folds=5) == []


def test_walk_forward_validate_standalone(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=1500)
    _seed_learnable_symbol("BBB-USD", "crypto", days=1500)

    result = ml_signal.walk_forward_validate(
        "crypto", features=["rsi"], method="logistic", n_folds=4,
        min_train_fraction=0.4, progress=lambda *a: None,
    )
    assert result is not None
    assert result["summary"]["n_folds"] == 4
    assert not result["folds"].empty
    assert result["summary"]["auc_mean"] > 0.8  # same clean synthetic pattern as elsewhere

    text = ml_signal.format_walkforward_report(result)
    assert "walk-forward validation" in text
    assert "per-fold detail" in text


def test_walk_forward_validate_none_without_enough_history(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=250)
    assert ml_signal.walk_forward_validate("crypto") is None


def test_format_walkforward_report_handles_none():
    assert "No walk-forward result" in ml_signal.format_walkforward_report(None)


def test_validate_persisted_model_none_without_model(lake):
    assert ml_signal.validate_persisted_model("crypto") is None


def test_validate_persisted_model_and_report(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=1500)
    _seed_learnable_symbol("BBB-USD", "crypto", days=1500)
    ml_signal.fit_and_evaluate("crypto", features=["rsi"])

    result = ml_signal.validate_persisted_model("crypto", n_folds=3, progress=lambda *a: None)
    assert result is not None
    assert result["method"] == "logistic"
    assert result["features"] == ["rsi"]


def test_walkforward_all_and_report_no_model_branch(lake):
    text = ml_signal.walkforward_all_and_report(categories=("crypto",))
    assert "no persisted model" in text


def test_walkforward_all_and_report_with_model(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=1500)
    _seed_learnable_symbol("BBB-USD", "crypto", days=1500)
    ml_signal.fit_and_evaluate("crypto", features=["rsi"])

    text = ml_signal.walkforward_all_and_report(categories=("crypto",), n_folds=3)
    assert "walk-forward validation" in text


# ---- walk-forward integrated into select_features()/select_model() -----

def test_select_features_includes_walk_forward_confirmation(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=1500)
    _seed_learnable_symbol("BBB-USD", "crypto", days=1500)
    candidates = ml_signal._INDICATOR_FEATURES + ["ma_spread"]

    result = ml_signal.select_features(
        "crypto", candidates=candidates, confirm_folds=2, progress=lambda *a: None
    )
    assert result is not None
    assert result["walk_forward"] is not None
    assert result["walk_forward"]["summary"]["n_folds"] <= 2

    text = ml_signal.format_selection_report(result)
    assert "walk-forward confirmation" in text


# ---- exhaustive k-feature combination search ----------------------------

def test_exhaustive_feature_search_none_below_min_rows(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=250)
    assert ml_signal.exhaustive_feature_search("crypto", k=2, progress=lambda *a: None) is None


def test_exhaustive_feature_search_finds_informative_feature(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=900)
    _seed_learnable_symbol("BBB-USD", "crypto", days=900)
    candidates = ["rsi", "mfi", "stoch_rsi_k"]  # C(3,2) = 3 combinations, all cheap

    result = ml_signal.exhaustive_feature_search(
        "crypto", k=2, candidates=candidates, progress=lambda *a: None
    )
    assert result is not None
    assert result["n_combos_total"] == 3
    assert result["n_combos_tried"] == 3  # no cap given: tries all of them
    assert "rsi" in result["best_features"]
    assert len(result["best_features"]) == 2
    assert result["walk_forward"] is not None

    text = ml_signal.format_exhaustive_report(result)
    assert "exhaustive 2-feature search" in text
    assert "top combinations" in text

    # persisted exactly like the other search entry points
    persisted = ml_signal.fit_exhaustive_and_persist(
        "crypto", k=2, candidates=candidates, progress=lambda *a: None
    )
    assert persisted["best_features"] == result["best_features"]
    bundle = ml_signal.load_model("crypto")
    assert set(bundle["features"]) == set(result["best_features"])


def test_exhaustive_feature_search_max_combos_samples_a_subset(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=900)
    _seed_learnable_symbol("BBB-USD", "crypto", days=900)
    candidates = ml_signal._INDICATOR_FEATURES + ["ma_spread"]  # C(12, 3) = 220

    result = ml_signal.exhaustive_feature_search(
        "crypto", k=3, candidates=candidates, max_combos=20, seed=1, progress=lambda *a: None
    )
    assert result is not None
    assert result["n_combos_total"] == 220
    assert result["n_combos_tried"] == 20  # capped, not exhaustive


def test_exhaustive_feature_search_none_when_nothing_beats_baseline(lake):
    _seed_constant_growth_symbol("AAA-USD", "crypto", 900, 0.0005)
    result = ml_signal.exhaustive_feature_search(
        "crypto", k=2, candidates=["rsi", "mfi"], progress=lambda *a: None
    )
    assert result is None


def test_format_exhaustive_report_handles_none():
    assert "No exhaustive-search result" in ml_signal.format_exhaustive_report(None)


def test_exhaustive_all_and_report_handles_missing_data(lake):
    text = ml_signal.exhaustive_all_and_report(categories=("crypto",), k=2)
    assert "No exhaustive-search result" in text


# ---- feature correlation --------------------------------------------------

def _seed_correlation_symbol(sym, category, days=900):
    """rsi and mfi vary identically (a 100-day phase cycle); stoch_rsi_k
    varies on an unrelated, much shorter cycle — used to verify
    feature_correlation_matrix() flags (rsi, mfi) as redundant and does
    NOT flag (rsi, stoch_rsi_k)."""
    price = 100.0
    closes, rsis, stochs = [], [], []
    for i in range(days):
        phase_up = (i // 100) % 2 == 0
        price *= (1 + (0.001 if phase_up else -0.001))
        closes.append(price)
        rsis.append(25.0 if phase_up else 75.0)
        stochs.append(0.2 if (i // 37) % 2 == 0 else 0.8)

    ohlcv = _daily_ending_now(days, closes)
    db.replace_ohlcv(ohlcv, sym, category)
    sigs = pd.DataFrame({
        "Date": ohlcv["Date"], "Close": closes, "signal": "Hold",
        "rsi": rsis, "mfi": rsis,  # identical to rsi
        "stoch_rsi_k": stochs, "stoch_rsi_d": 0.5,
        "bb_pband": 0.5, "macd_hist": 0.0, "atr_pct": 0.02,
        "is_bull": True, "vol_spike": False,
        "rsi_bullish_div": False, "rsi_bearish_div": False,
        "ma_50": closes, "ma_200": closes,
        "bb_upper": [c * 1.02 for c in closes], "bb_lower": [c * 0.98 for c in closes],
    })
    db.replace_signals(sigs, sym, category, "1d")


def test_feature_correlation_matrix_none_below_min_rows(lake):
    _seed_learnable_symbol("AAA-USD", "crypto", days=250)
    assert ml_signal.feature_correlation_matrix("crypto") is None


def test_feature_correlation_matrix_flags_identical_features(lake):
    _seed_correlation_symbol("AAA-USD", "crypto", days=900)
    _seed_correlation_symbol("BBB-USD", "crypto", days=900)

    result = ml_signal.feature_correlation_matrix("crypto", features=["rsi", "mfi", "stoch_rsi_k"])
    assert result is not None
    assert result["corr_matrix"].loc["rsi", "mfi"] == pytest.approx(1.0)
    assert "ret_30d" not in result["target_corr"].index  # target itself excluded from its own corr

    pairs = ml_signal.top_correlated_pairs(result["corr_matrix"], threshold=0.9)
    pair_names = [{a, b} for a, b, _ in pairs]
    assert {"rsi", "mfi"} in pair_names
    assert {"rsi", "stoch_rsi_k"} not in pair_names

    text = ml_signal.format_correlation_report(result, threshold=0.9)
    assert "rsi" in text and "mfi" in text
    assert "correlation with forward return" in text


def test_top_correlated_pairs_empty_when_nothing_clears_threshold():
    m = pd.DataFrame({"a": [1.0, 0.1], "b": [0.1, 1.0]}, index=["a", "b"])
    assert ml_signal.top_correlated_pairs(m, threshold=0.9) == []


def test_format_correlation_report_handles_none():
    assert "No correlation result" in ml_signal.format_correlation_report(None)


def test_correlation_all_and_report_handles_missing_data(lake):
    text = ml_signal.correlation_all_and_report(categories=("crypto",))
    assert "No correlation result" in text


# ── Tests covering bugs fixed in the 2026-08 code review ──────────────────────

def test_build_dataset_engineers_on_full_series_before_dropna(lake, monkeypatch):
    """_engineer_features must receive every row — including those with NaN in a
    raw indicator column — so rolling windows span the full, untruncated
    per-symbol series.  Before the fix, _build_dataset called dropna first,
    silently corrupting mom_5d / dist_from_52w_* for bars after the gap."""
    _seed_learnable_symbol("AAA-USD", "crypto", days=400)

    # Inject one interior NaN into rsi.  The old early dropna would remove this
    # row, shifting rolling positions for every subsequent bar.
    sigs = db.scan_signals_lake("crypto", "1d", columns=ml_signal._RAW_COLUMNS)
    sigs_with_gap = sigs.copy()
    sigs_with_gap.iloc[len(sigs) // 2, sigs_with_gap.columns.get_loc("rsi")] = float("nan")
    db.replace_signals(sigs_with_gap, "AAA-USD", "crypto", "1d")

    seen_lengths = []
    original = ml_signal._engineer_features
    def capture(df, *args, **kwargs):
        seen_lengths.append(len(df))
        return original(df, *args, **kwargs)
    monkeypatch.setattr(ml_signal, "_engineer_features", capture)

    ml_signal._build_dataset("crypto")

    assert seen_lengths, "_engineer_features was never called"
    # The full series — NaN row and all — must reach _engineer_features.
    # If _build_dataset had called dropna first this would be len(sigs) - 1.
    assert seen_lengths[0] == len(sigs)


def test_build_dataset_mkt_breadth_all_nan_excluded_from_dropna(lake, monkeypatch):
    """When compute_breadth_timeseries returns empty (OHLCV history under 200
    days), mkt_breadth is NaN for every row.  The old dropna(subset=ALL_FEATURES)
    wiped the entire dataset; the fix scopes dropna to features that actually
    have data, so the dataset survives despite all-NaN mkt_breadth."""
    import cycle_forecast as cycle_forecast_mod
    monkeypatch.setattr(
        cycle_forecast_mod, "compute_breadth_timeseries",
        lambda *a, **kw: pd.DataFrame(),
    )

    _seed_learnable_symbol("AAA-USD", "crypto", days=400)
    data = ml_signal._build_dataset("crypto")

    assert not data.empty
    assert data["mkt_breadth"].isna().all()


def test_predict_latest_scores_symbol_with_nan_in_unused_column(lake):
    """A symbol with NaN in a column the persisted model doesn't use must still
    appear in predict_latest() output.  Before the fix, the early
    dropna(subset=[all_raw_cols]) silently excluded it."""
    _seed_learnable_symbol("AAA-USD", "crypto", days=900)
    ml_signal.fit_and_evaluate("crypto", features=["rsi"])

    # Seed a second symbol whose bb_upper/bb_lower are NaN — columns a rsi-only
    # model doesn't need — to prove they no longer gate scoring.
    _, sigs = _seed_learnable_symbol("BBB-USD", "crypto", days=900)
    sigs = sigs.copy()
    sigs["bb_upper"] = float("nan")
    sigs["bb_lower"] = float("nan")
    db.replace_signals(sigs, "BBB-USD", "crypto", "1d")

    preds = ml_signal.predict_latest("crypto")
    assert "BBB-USD" in preds["symbol"].values
