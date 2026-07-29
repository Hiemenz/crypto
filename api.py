"""
FastAPI backend for Crypto Signal Station.

Exposes the Parquet/DuckDB data lake in db.py as JSON over HTTP so the
Flutter app (web or mobile) can consume it. Mostly read-only: the pipeline
(crypto_signal_station/crypto_signal_pipeline.py) remains the sole writer of
signal/OHLCV data. The one exception is /api/alerts, which edits the
price_alerts section of cryptos.yml so the app can manage the pipeline's
existing server-side price-alert-to-ntfy feature.

Run:
    poetry run uvicorn api:app --reload --port 8000
"""

from datetime import timedelta

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ruamel.yaml import YAML

import db

CRYPTOS_YML = "crypto_signal_station/cryptos.yml"

app = FastAPI(title="Crypto Signal Station API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CATEGORIES = ["crypto", "stocks"]
TIMEFRAMES = ["1d", "2d", "3d", "1wk", "2wk"]


def _clean(value):
    """Convert NaN/NaT to None and numpy scalars to native Python types so
    the JSON encoder doesn't choke."""
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp,)):
        return str(value.date())
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (bool,)):
        return value
    if hasattr(value, "item"):  # numpy scalar (int64, float64, bool_, ...)
        return value.item()
    return value


def _row_to_dict(symbol: str, category: str, timeframe: str, row: pd.Series) -> dict:
    date = row["Date"]
    return {
        "symbol": symbol,
        "category": category,
        "timeframe": timeframe,
        "date": str(date.date()) if hasattr(date, "date") else str(date)[:10],
        "open": _clean(row.get("Open")),
        "high": _clean(row.get("High")),
        "low": _clean(row.get("Low")),
        "close": _clean(row.get("Close")),
        "volume": _clean(row.get("Volume")),
        "rsi": _clean(row.get("rsi")),
        "mfi": _clean(row.get("mfi")),
        "stoch_rsi": _clean(row.get("stoch_rsi")),
        "stoch_rsi_k": _clean(row.get("stoch_rsi_k")),
        "stoch_rsi_d": _clean(row.get("stoch_rsi_d")),
        "bb_upper": _clean(row.get("bb_upper")),
        "bb_lower": _clean(row.get("bb_lower")),
        "bb_pband": _clean(row.get("bb_pband")),
        "macd": _clean(row.get("macd")),
        "macd_signal": _clean(row.get("macd_signal")),
        "macd_hist": _clean(row.get("macd_hist")),
        "ma_50": _clean(row.get("ma_50")),
        "ma_200": _clean(row.get("ma_200")),
        "is_bull": bool(row.get("is_bull", False)),
        "signal": row.get("signal") or "Hold",
    }


def _symbol_keys(category: str | None = None, timeframe: str | None = None):
    keys = db.list_signal_keys()
    if category:
        keys = [k for k in keys if k[1] == category]
    if timeframe:
        keys = [k for k in keys if k[2] == timeframe]
    return keys


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/meta")
def meta():
    return {"categories": CATEGORIES, "timeframes": TIMEFRAMES}


@app.get("/api/symbols")
def symbols(
    category: str = Query(None, description="crypto | stocks"),
    timeframe: str = Query(None),
):
    keys = _symbol_keys(category, timeframe)
    seen = set()
    out = []
    for sym, cat, _tf in keys:
        if (sym, cat) in seen:
            continue
        seen.add((sym, cat))
        out.append({"symbol": sym, "category": cat})
    return out


@app.get("/api/feed")
def feed(
    category: str | None = Query(None),
    timeframe: str = Query("1d"),
    signal: str | None = Query(None, description="Filter: Buy, Sell, Hold, Great Buy, Great Sell..."),
):
    """Latest signal row per symbol -- the main mobile feed."""
    items = []
    for sym, cat, tf in _symbol_keys(category, timeframe):
        df = db.load_signals(sym, cat, tf)
        if df.empty:
            continue
        item = _row_to_dict(sym, cat, tf, df.iloc[-1])
        if signal and signal.lower() not in item["signal"].lower():
            continue
        items.append(item)

    items.sort(key=lambda x: x["date"], reverse=True)
    return items


@app.get("/api/history/{symbol}")
def history(
    symbol: str,
    category: str = Query(...),
    timeframe: str = Query("1d"),
    limit: int = Query(200, ge=1, le=2000),
):
    df = db.load_signals(symbol, category, timeframe)
    if df.empty:
        raise HTTPException(status_code=404, detail="No data for symbol/category/timeframe")
    df = df.tail(limit)
    return [_row_to_dict(symbol, category, timeframe, row) for _, row in df.iterrows()]


@app.get("/api/watch")
def watch():
    """Assets near a Buy/Sell trigger (ported from watch_feed.py)."""
    watch_items = []
    for category in CATEGORIES:
        for tf in TIMEFRAMES:
            for sym, cat, _tf in _symbol_keys(category, tf):
                df = db.load_signals(sym, cat, tf)
                if df.empty:
                    continue
                latest = df.iloc[-1]

                rsi = latest.get("rsi") or 0
                mfi = latest.get("mfi") or 0
                stoch_rsi = latest.get("stoch_rsi") or 0
                is_bull = bool(latest.get("is_bull", False))
                close = latest.get("Close") or 0
                signal = latest.get("signal") or "Hold"

                if signal != "Hold":
                    continue

                near_type = None
                reasons = []

                if not is_bull:
                    if 30 <= rsi <= 45:
                        reasons.append(f"RSI: {rsi:.1f}")
                    if 20 <= mfi <= 35:
                        reasons.append(f"MFI: {mfi:.1f}")
                    if 0.2 <= stoch_rsi <= 0.4:
                        reasons.append(f"StochRSI: {stoch_rsi:.2f}")
                    if reasons:
                        near_type = "Near Buy"
                else:
                    if 55 <= rsi <= 70:
                        reasons.append(f"RSI: {rsi:.1f}")
                    if 65 <= mfi <= 80:
                        reasons.append(f"MFI: {mfi:.1f}")
                    if 0.6 <= stoch_rsi <= 0.8:
                        reasons.append(f"StochRSI: {stoch_rsi:.2f}")
                    if reasons:
                        near_type = "Near Sell"

                if near_type:
                    watch_items.append({
                        "category": cat,
                        "symbol": sym,
                        "timeframe": tf,
                        "type": near_type,
                        "price": float(close),
                        "reasons": reasons,
                        "market": "Bull" if is_bull else "Bear",
                    })

    return watch_items


@app.get("/api/crosses/ma")
def ma_crosses(days: int = Query(365, ge=1, le=3650)):
    """Golden/Death (MA50/MA200) crosses in the last N days (ported from cross_feed.py)."""
    events = []
    cutoff_date = pd.Timestamp.now().normalize() - timedelta(days=days)

    for sym, cat, _tf in _symbol_keys(timeframe="1d"):
        df = db.load_signals(sym, cat, "1d")
        if df.empty or "ma_50" not in df.columns or "ma_200" not in df.columns:
            continue

        df = df[df["Date"] >= (cutoff_date - timedelta(days=1))]
        if len(df) < 2:
            continue

        prev_ma50 = df["ma_50"].shift(1)
        prev_ma200 = df["ma_200"].shift(1)
        golden_mask = (prev_ma50 <= prev_ma200) & (df["ma_50"] > df["ma_200"])
        death_mask = (prev_ma50 >= prev_ma200) & (df["ma_50"] < df["ma_200"])

        for _, row in df[golden_mask].iterrows():
            events.append({
                "date": str(row["Date"].date()), "symbol": sym, "category": cat,
                "type": "Golden Cross", "price": _clean(row["Close"]),
            })
        for _, row in df[death_mask].iterrows():
            events.append({
                "date": str(row["Date"].date()), "symbol": sym, "category": cat,
                "type": "Death Cross", "price": _clean(row["Close"]),
            })

    events.sort(key=lambda x: x["date"], reverse=True)
    return events


@app.get("/api/crosses/stoch")
def stoch_crosses():
    """1wk StochRSI K/D crosses (ported from stoch_cross_feed.py)."""
    crosses = []
    for sym, cat, _tf in _symbol_keys(timeframe="1wk"):
        df = db.load_signals(sym, cat, "1wk")
        if len(df) < 2 or "stoch_rsi_k" not in df.columns:
            continue

        prev_k = df["stoch_rsi_k"].shift(1)
        prev_d = df["stoch_rsi_d"].shift(1)
        curr_k, curr_d = df["stoch_rsi_k"], df["stoch_rsi_d"]

        golden_mask = (prev_k < prev_d) & (curr_k > curr_d)
        death_mask = (prev_k > prev_d) & (curr_k < curr_d)

        for _, row in df[golden_mask].iterrows():
            k, d = row.get("stoch_rsi_k") or 0, row.get("stoch_rsi_d") or 0
            crosses.append({
                "category": cat, "symbol": sym,
                "type": "Confirmed Golden Cross" if k > 0.2 and d > 0.2 else "Golden Cross",
                "price": _clean(row.get("Close")), "k": k, "d": d,
                "date": str(row["Date"].date()),
            })
        for _, row in df[death_mask].iterrows():
            k, d = row.get("stoch_rsi_k") or 0, row.get("stoch_rsi_d") or 0
            crosses.append({
                "category": cat, "symbol": sym,
                "type": "Confirmed Death Cross" if k < 0.8 and d < 0.8 else "Death Cross",
                "price": _clean(row.get("Close")), "k": k, "d": d,
                "date": str(row["Date"].date()),
            })

    crosses.sort(key=lambda x: x["date"], reverse=True)
    return crosses


# ── price alerts (server-side, pushed via crypto_signal_station/notify.py) ──

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.indent(mapping=2, sequence=4, offset=2)


def _load_yaml_config():
    with open(CRYPTOS_YML, "r") as f:
        return _yaml.load(f)


def _save_yaml_config(cfg):
    with open(CRYPTOS_YML, "w") as f:
        _yaml.dump(cfg, f)


class AlertIn(BaseModel):
    symbol: str
    threshold: float


@app.get("/api/alerts")
def list_alerts():
    cfg = _load_yaml_config()
    alerts = cfg.get("price_alerts") or {}
    return [{"symbol": sym, "threshold": float(thr)} for sym, thr in alerts.items()]


@app.post("/api/alerts")
def upsert_alert(alert: AlertIn):
    cfg = _load_yaml_config()
    if cfg.get("price_alerts") is None:
        cfg["price_alerts"] = {}
    cfg["price_alerts"][alert.symbol] = alert.threshold
    _save_yaml_config(cfg)
    return {"symbol": alert.symbol, "threshold": alert.threshold}


@app.delete("/api/alerts/{symbol}")
def delete_alert(symbol: str):
    cfg = _load_yaml_config()
    alerts = cfg.get("price_alerts") or {}
    if symbol not in alerts:
        raise HTTPException(status_code=404, detail="No alert configured for this symbol")
    del alerts[symbol]
    _save_yaml_config(cfg)
    return {"deleted": symbol}
