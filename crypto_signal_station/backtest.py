"""Backtest stored signals: forward returns at fixed horizons.

For every non-Hold signal in the lake, measure the return from the signal
bar's Close to the daily Close ~7/30/90 calendar days later, then aggregate
hit rates per category/timeframe/tier. A per-category baseline (the
unconditional forward return over every daily bar) shows whether a tier
actually beats "just being long".

Buys count as wins when the forward return is positive; sells when it is
negative (the sell tiers are mean-reversion "get out" calls, so a falling
price means the call was right).

Results are printed and stored for the dashboard/digest:
    data/backtest/events.parquet  one row per signal event with fwd returns
    data/backtest/stats.parquet   tidy: category/timeframe/tier/horizon rows
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db

HORIZONS = (7, 30, 90)
# A forward close must land within this many days before the target date
# (bridges stock weekends/holidays without silently matching stale data).
ASOF_TOLERANCE_DAYS = 7


def _forward_returns(events: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Add ret_<h>d columns to events (Date + Close = entry) from daily closes.

    A horizon return is NaN when the daily history hasn't yet reached the
    target date (recent signals) or no close exists near it.
    """
    out = events.copy()
    closes = daily[["Date", "Close"]].dropna().sort_values("Date")
    closes = closes.rename(columns={"Date": "fwd_date", "Close": "fwd_close"})
    last_daily = closes["fwd_date"].max()

    for h in HORIZONS:
        probe = out[["Date", "Close"]].copy()
        probe["target"] = probe["Date"] + pd.Timedelta(days=h)
        # merge_asof resets the index, so carry the original labels through
        probe["_idx"] = probe.index
        probe = probe.sort_values("target")
        merged = pd.merge_asof(
            probe,
            closes,
            left_on="target",
            right_on="fwd_date",
            direction="backward",
            tolerance=pd.Timedelta(days=ASOF_TOLERANCE_DAYS),
        )
        ret = merged["fwd_close"] / merged["Close"] - 1
        # Horizon not elapsed yet, or the matched bar is the signal bar itself
        ret[(merged["target"] > last_daily) | (merged["fwd_date"] <= merged["Date"])] = float("nan")
        out.loc[merged["_idx"].to_numpy(), f"ret_{h}d"] = ret.to_numpy()

    return out


class _BaselineAccumulator:
    """Streaming per-(category, horizon) mean of unconditional forward returns
    (collecting every daily bar of 500 stocks would not fit a Pi's RAM)."""

    def __init__(self):
        self.sums = {}
        self.counts = {}

    def add(self, category: str, rets: pd.DataFrame):
        for h in HORIZONS:
            col = rets[f"ret_{h}d"].dropna()
            key = (category, h)
            self.sums[key] = self.sums.get(key, 0.0) + float(col.sum())
            self.counts[key] = self.counts.get(key, 0) + int(len(col))

    def mean(self, category: str, horizon: int):
        key = (category, horizon)
        if self.counts.get(key):
            return self.sums[key] / self.counts[key]
        return float("nan")


def run_backtest(progress=print):
    """Compute forward returns for every stored signal; return (events, stats).

    Reads whole categories/timeframes with bulk lake scans: per-partition
    reads (~2 DuckDB connections × ~2,800 partitions) take tens of minutes on
    a Pi, while ~a dozen glob scans take seconds.
    """
    keys = db.list_signal_keys()
    if not keys:
        progress("No stored signals found — run a refresh first.")
        return pd.DataFrame(), pd.DataFrame()

    categories = sorted({cat for _, cat, _ in keys})
    baseline = _BaselineAccumulator()
    event_frames = []

    for cat in categories:
        daily_all = db.scan_ohlcv_lake(cat, columns=["Date", "Close"])
        if daily_all.empty:
            continue
        daily_by_sym = {
            sym: g.sort_values("Date").reset_index(drop=True)
            for sym, g in daily_all.groupby("symbol")
        }
        progress(f"[{cat}] {len(daily_by_sym)} symbols; computing baseline...")
        for sym, daily in daily_by_sym.items():
            baseline.add(cat, _forward_returns(daily[["Date", "Close"]], daily))

        timeframes = sorted({tf for _, c, tf in keys if c == cat})
        for tf in timeframes:
            sigs = db.scan_signals_lake(cat, tf, columns=["Date", "Close", "signal"])
            if sigs.empty or "signal" not in sigs.columns:
                continue
            all_ev = sigs[sigs["signal"] != "Hold"]
            progress(f"[{cat}/{tf}] {len(all_ev)} signal events")
            for sym, events in all_ev.groupby("symbol"):
                daily = daily_by_sym.get(sym)
                if daily is None:
                    continue
                ev = _forward_returns(
                    events[["Date", "Close", "signal"]].reset_index(drop=True), daily
                )
                ev.insert(0, "symbol", sym)
                ev.insert(1, "category", cat)
                ev.insert(2, "timeframe", tf)
                event_frames.append(ev)

    if not event_frames:
        progress("No signal events found in the lake.")
        return pd.DataFrame(), pd.DataFrame()

    all_events = pd.concat(event_frames, ignore_index=True)

    rows = []
    grouped = all_events.groupby(["category", "timeframe", "signal"], sort=True)
    for (cat, tf, tier), g in grouped:
        side = "buy" if "Buy" in tier else "sell"
        for h in HORIZONS:
            rets = g[f"ret_{h}d"].dropna()
            if rets.empty:
                continue
            wins = (rets > 0) if side == "buy" else (rets < 0)
            rows.append(
                {
                    "category": cat,
                    "timeframe": tf,
                    "signal": tier,
                    "side": side,
                    "horizon_days": h,
                    "n": int(len(rets)),
                    "avg_return": float(rets.mean()),
                    "median_return": float(rets.median()),
                    "win_rate": float(wins.mean()),
                    "baseline_return": baseline.mean(cat, h),
                }
            )
    stats = pd.DataFrame(rows)

    db.init_db()
    db.save_table(all_events, db.table_path("backtest", "events.parquet"))
    db.save_table(stats, db.table_path("backtest", "stats.parquet"))
    return all_events, stats


def load_stats() -> pd.DataFrame:
    """Latest stored backtest stats (empty frame if backtest never ran)."""
    return db.load_table(db.table_path("backtest", "stats.parquet"))


TIER_ORDER = [
    "Excellent Buy", "Great Buy", "Good Buy",
    "Good Sell", "Great Sell", "Excellent Sell",
]


def format_report(stats: pd.DataFrame) -> str:
    if stats.empty:
        return "No backtest statistics available.\n"

    lines = [f"Signal backtest — {pd.Timestamp.now().date()}", ""]
    for (cat, tf), g in stats.groupby(["category", "timeframe"], sort=True):
        base30 = g.loc[g["horizon_days"] == 30, "baseline_return"]
        base_str = f"{base30.iloc[0]:+.1%}" if not base30.empty else "n/a"
        lines.append(f"[{cat} / {tf}]  (baseline 30d: {base_str})")
        lines.append(f"  {'tier':<15}{'n':>6}{'7d':>9}{'30d':>9}{'win30':>8}{'90d':>9}")
        tiers = sorted(
            g["signal"].unique(),
            key=lambda t: TIER_ORDER.index(t) if t in TIER_ORDER else 99,
        )
        for tier in tiers:
            row = {h: g[(g["signal"] == tier) & (g["horizon_days"] == h)] for h in HORIZONS}

            def cell(h, field, fmt):
                r = row[h]
                return fmt.format(r[field].iloc[0]) if not r.empty else "     n/a"

            n = int(row[30]["n"].iloc[0]) if not row[30].empty else (
                int(row[7]["n"].iloc[0]) if not row[7].empty else 0
            )
            lines.append(
                f"  {tier:<15}{n:>6}"
                + cell(7, "avg_return", "{:>+9.1%}")
                + cell(30, "avg_return", "{:>+9.1%}")
                + cell(30, "win_rate", "{:>8.0%}")
                + cell(90, "avg_return", "{:>+9.1%}")
            )
        lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    _, stats = run_backtest()
    print(format_report(stats))
