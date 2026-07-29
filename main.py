import os
import datetime
import duckdb
import pandas as pd
import yfinance as yf
import yaml
from ta.momentum import RSIIndicator, StochRSIIndicator
from ta.volume import MFIIndicator
from ta.trend import MACD

# Configuration
CONFIG_FILE = "config.yml"

with open(CONFIG_FILE, 'r') as f:
    config = yaml.safe_load(f)

DB_FILE = config.get("db_path", "crypto_data.duckdb")
cryptos = config.get("pairs", [])

# Connect to DuckDB
con = duckdb.connect(DB_FILE)

def symbol_to_table_name(symbol: str) -> str:
    # Convert something like BTC-USD to btc_usd
    return symbol.lower().replace('-', '_')

def ensure_raw_table(symbol):
    raw_table = f"crypto_raw_{symbol_to_table_name(symbol)}"
    table_exists = con.execute(f"SELECT * FROM information_schema.tables WHERE table_name='{raw_table}'").fetchone()
    if table_exists is None:
        con.execute(f"""
        CREATE TABLE {raw_table} (
            Symbol VARCHAR,
            Date DATE,
            Timeframe VARCHAR,
            Open DOUBLE,
            High DOUBLE,
            Low DOUBLE,
            Close DOUBLE,
            Volume DOUBLE
        );
        """)
        con.commit()
    return raw_table

def ensure_processed_table(symbol):
    processed_table = f"crypto_prices_{symbol_to_table_name(symbol)}"
    table_exists = con.execute(f"SELECT * FROM information_schema.tables WHERE table_name='{processed_table}'").fetchone()
    if table_exists is None:
        con.execute(f"""
        CREATE TABLE {processed_table} (
            Symbol VARCHAR,
            Date DATE,
            Timeframe VARCHAR,
            Open DOUBLE,
            High DOUBLE,
            Low DOUBLE,
            Close DOUBLE,
            Volume DOUBLE,
            RSI DOUBLE,
            MFI DOUBLE,
            Stoch_RSI DOUBLE,
            MACD DOUBLE,
            MACD_Signal DOUBLE,
            MACD_Hist DOUBLE,
            MA_50 DOUBLE,
            MA_100 DOUBLE,
            MA_200 DOUBLE,
            Strategy VARCHAR
        );
        """)
        con.commit()
    return processed_table

def download_data(symbol, start=None, end=None, period=None, interval="1d"):
    # If start is given, we prioritize start/end over period
    if start is not None:
        return yf.download(symbol, start=start, end=end, interval=interval)
    else:
        # If period is specified, use it; else fallback to max
        if period is None:
            period = "max"
        return yf.download(symbol, period=period, interval=interval)

def store_raw_data(symbol, timeframe, df):
    if df.empty:
        return
    
    raw_table = ensure_raw_table(symbol)

    df = df.copy()
    df['Symbol'] = symbol
    df['Timeframe'] = timeframe
    df.reset_index(inplace=True)
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

    # Flatten multi-index columns if needed
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            '_'.join([part for part in col if part]) if isinstance(col, tuple) else col
            for col in df.columns
        ]

    # Rename columns if needed
    rename_map = {}
    for col in df.columns:
        if 'Open_' in col:
            rename_map[col] = 'Open'
        elif 'High_' in col:
            rename_map[col] = 'High'
        elif 'Low_' in col:
            rename_map[col] = 'Low'
        elif 'Close_' in col:
            rename_map[col] = 'Close'
        elif 'Volume_' in col:
            rename_map[col] = 'Volume'

    df.rename(columns=rename_map, inplace=True)

    required_cols = ['Symbol', 'Date', 'Timeframe', 'Open', 'High', 'Low', 'Close', 'Volume']
    df = df[required_cols]

    con.register("temp_df", df)
    # Notice: No DELETE here.
    # Insert new data (append).
    con.execute(f'''
    INSERT INTO {raw_table} ("Symbol", "Date", "Timeframe", "Open", "High", "Low", "Close", "Volume")
    SELECT "Symbol", "Date", "Timeframe", "Open", "High", "Low", "Close", "Volume" FROM temp_df
    ''')
    con.commit()
    con.unregister("temp_df")
def update_daily_data(symbol):
    raw_table = ensure_raw_table(symbol)
    
    # Check if we have any existing data
    max_date_query = f"SELECT MAX(Date) FROM {raw_table} WHERE Symbol='{symbol}' AND Timeframe='1d'"
    max_date = con.execute(max_date_query).fetchone()[0]

    if max_date is None:
        # First run: no data in DB, fetch full historical data using period="max"
        df = download_data(symbol, period="max", interval="1d")
        df = df.sort_index()
        df = df[["Open", "High", "Low", "Close", "Volume"]]
        print(df)
        
        # Insert all data as is, no need to delete because DB is empty
        store_raw_data(symbol, '1d', df)
    else:
        # Subsequent runs: re-download data starting from the max date
        start_date_str = max_date.isoformat()
        today = datetime.date.today()

        # Download new data from the max_date to now
        df = download_data(
            symbol,
            start=start_date_str,
            end=(today + datetime.timedelta(days=1)).isoformat(),
            interval="1d"
        )
        
        df = df.sort_index()
        df = df[["Open", "High", "Low", "Close", "Volume"]]

        if df.empty:
            print(f"No new data available for {symbol} from {start_date_str} to {today}. Keeping existing history.")
        else:
            # Delete overlapping rows starting from max_date to update the data
            con.execute(f"DELETE FROM {raw_table} WHERE Symbol='{symbol}' AND Timeframe='1d' AND Date >= '{start_date_str}'")
            con.commit()
            # Insert the newly fetched rows (which include updated data for max_date and any new dates)
            store_raw_data(symbol, '1d', df)

    return df

def calculate_indicators(df):
    if df.empty:
        return df

    df = df.copy()
    df = df.sort_index()

    rsi = RSIIndicator(close=df['Close'], window=14)
    df['RSI'] = rsi.rsi()

    mfi = MFIIndicator(high=df['High'], low=df['Low'], close=df['Close'], volume=df['Volume'], window=14)
    df['MFI'] = mfi.money_flow_index()

    stoch_rsi = StochRSIIndicator(close=df['Close'], window=14, smooth1=3, smooth2=4)
    df['Stoch_RSI'] = stoch_rsi.stochrsi()

    macd = MACD(close=df['Close'], window_slow=26, window_fast=12, window_sign=9)
    df['MACD'] = macd.macd()
    df['MACD_Signal'] = macd.macd_signal()
    df['MACD_Hist'] = macd.macd_diff()

    df['MA_50'] = df['Close'].rolling(window=50, min_periods=1).mean()
    df['MA_100'] = df['Close'].rolling(window=100, min_periods=1).mean()
    df['MA_200'] = df['Close'].rolling(window=200, min_periods=1).mean()

    return df

def classify_market_signal(row):
    rsi = row.get('RSI')
    mfi = row.get('MFI')
    stoch_rsi = row.get('Stoch_RSI')
    ma_50 = row.get('MA_50')
    ma_200 = row.get('MA_200')
    close = row.get('Close')

    # Check for missing values
    if pd.isna(rsi) or pd.isna(mfi) or pd.isna(stoch_rsi) or pd.isna(ma_50) or pd.isna(ma_200) or pd.isna(close):
        return None

    if rsi < 20 and mfi < 10 and stoch_rsi < 0.1 and ma_50 > ma_200 and close > ma_200:
        return 'Excellent Buy'
    elif rsi > 80 and mfi > 90 and stoch_rsi > 0.9 and ma_50 < ma_200 and close < ma_200:
        return 'Excellent Sell'
    elif rsi < 30 and mfi < 20 and stoch_rsi < 0.2 and ma_50 > ma_200:
        return 'Great Buy'
    elif rsi > 70 and mfi > 80 and stoch_rsi > 0.8 and ma_50 < ma_200:
        return 'Great Sell'
    elif rsi < 40 and mfi < 50 and stoch_rsi < 0.3:
        return 'Good Buy'
    elif rsi > 60 and mfi > 70 and stoch_rsi > 0.7:
        return 'Good Sell'
    else:
        return 'Hold'

def resample_data(df, rule):
    if df.empty:
        return df
    df_res = df.resample(rule, origin='start').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }).dropna()
    df_res = df_res.sort_index()
    return df_res

def store_processed_data(symbol, timeframe, df):
    if df.empty:
        return

    processed_table = ensure_processed_table(symbol)

    df = df.copy()
    df['Symbol'] = symbol
    df['Timeframe'] = timeframe
    df['Strategy'] = df.apply(classify_market_signal, axis=1)

    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.date

    df.reset_index(inplace=True)

    required_cols = [
        'Symbol', 'Date', 'Timeframe', 'Open', 'High', 'Low', 'Close', 'Volume',
        'RSI', 'MFI', 'Stoch_RSI', 'MACD', 'MACD_Signal', 'MACD_Hist',
        'MA_50', 'MA_100', 'MA_200', 'Strategy'
    ]

    # Ensure columns exist
    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    df = df[required_cols]

    con.register("temp_processed_df", df)

    con.execute(f"DELETE FROM {processed_table} WHERE Symbol='{symbol}' AND Timeframe='{timeframe}';")

    col_list = '", "'.join(required_cols)
    con.execute(f'''
    INSERT INTO {processed_table} ("{col_list}")
    SELECT "{col_list}" FROM temp_processed_df
    ''')

    con.commit()
    con.unregister("temp_processed_df")

def get_raw_data_for_processing(symbol, timeframe='1d', lookback_days=200):
    processed_table = ensure_processed_table(symbol)

    max_processed_date_query = f"SELECT MAX(Date) FROM {processed_table} WHERE Symbol='{symbol}' AND Timeframe='{timeframe}'"
    max_processed_date = con.execute(max_processed_date_query).fetchone()[0]

    raw_table = ensure_raw_table(symbol)

    if max_processed_date is None:
        query = f"SELECT Date, Open, High, Low, Close, Volume FROM {raw_table} WHERE Symbol='{symbol}' AND Timeframe='1d' ORDER BY Date"
    else:
        start_date = max_processed_date - datetime.timedelta(days=lookback_days)
        query = f"""
        SELECT Date, Open, High, Low, Close, Volume 
        FROM {raw_table} 
        WHERE Symbol='{symbol}' AND Timeframe='1d' AND Date >= '{start_date}' 
        ORDER BY Date
        """

    df = con.execute(query).df()
    if not df.empty:
        df.set_index('Date', inplace=True)
        df = df.sort_index()
    return df

# Main data update loop
for symbol in cryptos:
    # 1. Update daily raw data for each symbol
    update_daily_data(symbol)

    # 2. Pull only necessary raw data from DB for indicators
    daily_raw = get_raw_data_for_processing(symbol, '1d', lookback_days=200)

    # Calculate daily indicators
    daily_processed = calculate_indicators(daily_raw)
    store_processed_data(symbol, '1d', daily_processed)

    # Create other timeframes from daily data
    three_day = resample_data(daily_raw, '3D')
    three_day = calculate_indicators(three_day)
    store_processed_data(symbol, '3d', three_day)

    one_week = resample_data(daily_raw, '7D')
    one_week = calculate_indicators(one_week)
    store_processed_data(symbol, '1w', one_week)

    two_week = resample_data(daily_raw, '14D')
    two_week = calculate_indicators(two_week)
    store_processed_data(symbol, '2w', two_week)

con.close()
print("Data update completed with per-pair tables and date range attempts.")