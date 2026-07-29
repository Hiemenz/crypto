import duckdb
import pandas as pd
from datetime import datetime

DB_PATH = "crypto_data.duckdb"

def get_crypto_tables(db_path):
    """
    Fetches all table names for cryptocurrencies.
    
    Args:
        db_path (str): Path to the DuckDB database.
    
    Returns:
        list: List of table names.
    """
    conn = duckdb.connect(db_path)
    tables = conn.execute("SHOW TABLES").fetchall()
    conn.close()
    # Filter for tables starting with "crypto_prices_"
    return [t[0] for t in tables if t[0].startswith("crypto_prices_")]

def get_conditions_for_table(db_path, table_name, target_date, timeframe):
    """
    Fetches cryptos with market conditions for a given table, date, and timeframe.
    
    Args:
        db_path (str): Path to the DuckDB database.
        table_name (str): Name of the cryptocurrency table.
        target_date (str): Date to filter data (YYYY-MM-DD).
        timeframe (str): The timeframe to filter by (e.g., '1D', '3D').
    
    Returns:
        pd.DataFrame: Dataframe with cryptos and their market conditions.
    """
    conn = duckdb.connect(db_path)
    query = f"""
        SELECT 
            '{table_name[len("crypto_prices_"):]}' AS Pair, 
            Date, 
            Timeframe, 
            CASE
                WHEN RSI < 40 AND MFI < 50 AND Stoch_RSI < 0.3 THEN 'Good Buy'
                WHEN RSI > 60 AND MFI > 50 AND Stoch_RSI > 0.7 THEN 'Good Sell'
                WHEN RSI < 30 AND MFI < 20 AND Stoch_RSI < 0.2 THEN 'Great Buy'
                WHEN RSI > 70 AND MFI > 80 AND Stoch_RSI > 0.8 THEN 'Great Sell'
                WHEN RSI < 20 AND MFI < 10 AND Stoch_RSI < 0.1 THEN 'Excellent Buy'
                WHEN RSI > 80 AND MFI > 90 AND Stoch_RSI > 0.9 THEN 'Excellent Sell'
                ELSE NULL
            END AS market_condition
        FROM {table_name}
        WHERE strftime(Date, '%Y-%m-%d') = '{target_date}'
          AND Timeframe = '{timeframe}'
          AND (
              RSI < 40 OR RSI > 60 OR 
              MFI < 50 OR MFI > 50 OR 
              Stoch_RSI < 0.3 OR Stoch_RSI > 0.7
          )
        ORDER BY Date
    """
    df = conn.execute(query).fetch_df()
    conn.close()
    return df

def generate_summary_message(df, timeframe):
    """
    Generates a summary message based on the cryptos with market conditions.
    
    Args:
        df (pd.DataFrame): Dataframe with cryptos and their market conditions.
        timeframe (str): The timeframe associated with the data.
    
    Returns:
        str: A formatted message summarizing good buys and sells.
    """
    if df.empty:
        return f"No actionable buy/sell signals for the {timeframe} timeframe today."

    message = f"Crypto Market Highlights for the {timeframe} timeframe:\n\n"
    for _, row in df.iterrows():
        message += f"{row['Pair']}: {row['market_condition']} detected at {row['Date']:%H:%M %p}.\n"
    return message

if __name__ == "__main__":
    # Default to today's date
    today_date = datetime.now().strftime('%Y-%m-%d')

    # Define the timeframe to filter (e.g., '1D', '3D')
    timeframe = '1D'  # Change to your desired timeframe

    # Fetch all crypto tables
    crypto_tables = get_crypto_tables(DB_PATH)

    # Collect conditions from all tables
    all_conditions = pd.DataFrame()
    for table in crypto_tables:
        df_conditions = get_conditions_for_table(DB_PATH, table, today_date, timeframe)
        all_conditions = pd.concat([all_conditions, df_conditions], ignore_index=True)

    # Generate and display the summary message
    message = generate_summary_message(all_conditions, timeframe)
    print(message)