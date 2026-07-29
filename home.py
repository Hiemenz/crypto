import streamlit as st
import duckdb
import pandas as pd
import plotly.graph_objs as go

DB_PATH = "crypto_data.duckdb"

st.set_page_config(layout="wide")


@st.cache_data
def get_available_pairs(db_path):
    conn = duckdb.connect(db_path)
    tables = conn.execute("SHOW TABLES").fetchall()
    conn.close()
    tables = [t[0] for t in tables]
    pairs = []
    for table in tables:
        if table.startswith("crypto_prices_"):
            pair = table[len("crypto_prices_"):]
            pairs.append((pair, table))
    return pairs

@st.cache_data
def get_timeframes(db_path, table_name):
    conn = duckdb.connect(db_path)
    timeframes = conn.execute(f"SELECT DISTINCT Timeframe FROM {table_name}").fetchall()
    conn.close()
    timeframes = [t[0] for t in timeframes]
    return timeframes

def get_data(db_path, table_name, timeframe):
    conn = duckdb.connect(db_path)
    df = conn.execute(f"SELECT * FROM {table_name} WHERE Timeframe='{timeframe}' ORDER BY Date").fetch_df()
    conn.close()
    if not df.empty and not pd.api.types.is_datetime64_any_dtype(df['Date']):
        df['Date'] = pd.to_datetime(df['Date'])
    return df

st.title('Cryptocurrency Price and Indicators')

pairs_list = get_available_pairs(DB_PATH)
if not pairs_list:
    st.write("No pair tables found in the database.")
else:
    pairs = [p[0] for p in pairs_list]
    pair = st.selectbox("Select Crypto Pair", pairs, key="pair_select")
    pair_table_name = [t[1] for t in pairs_list if t[0] == pair][0]

    timeframes = get_timeframes(DB_PATH, pair_table_name)
    if not timeframes:
        st.write(f"No timeframes found in table for {pair}.")
    else:
        timeframe = st.selectbox("Select Timeframe", timeframes, key="timeframe_select")

        df = get_data(DB_PATH, pair_table_name, timeframe)
        if df.empty:
            st.write("No data found for this pair and timeframe.")
        else:
            total_bars = len(df)
            default_bars = min(total_bars, 200)
            bars_to_show = st.slider("Number of recent bars to show", 
                                     min_value=50, max_value=total_bars, 
                                     value=default_bars, step=50, key="bars_slider")
            df = df.tail(bars_to_show)

            # Plotting charts as before
            fig_price = go.Figure()
            fig_price.add_trace(go.Candlestick(x=df['Date'],
                                               open=df['Open'],
                                               high=df['High'],
                                               low=df['Low'],
                                               close=df['Close'],
                                               name='Price'))
            fig_price.add_trace(go.Scatter(x=df['Date'], y=df['MA_50'], line=dict(color='blue'), name='MA_50'))
            fig_price.add_trace(go.Scatter(x=df['Date'], y=df['MA_100'], line=dict(color='orange'), name='MA_100'))
            fig_price.add_trace(go.Scatter(x=df['Date'], y=df['MA_200'], line=dict(color='red'), name='MA_200'))
            fig_price.update_layout(title=f"{pair} {timeframe} Price + MAs", xaxis_rangeslider_visible=False, height=600)


            # Plotting charts as before
            fig_price = go.Figure()
            fig_price.add_trace(go.Candlestick(x=df['Date'],
                                            open=df['Open'],
                                            high=df['High'],
                                            low=df['Low'],
                                            close=df['Close'],
                                            name='Price'))
            fig_price.add_trace(go.Scatter(x=df['Date'], y=df['MA_50'], line=dict(color='blue'), name='MA_50'))
            fig_price.add_trace(go.Scatter(x=df['Date'], y=df['MA_100'], line=dict(color='orange'), name='MA_100'))
            fig_price.add_trace(go.Scatter(x=df['Date'], y=df['MA_200'], line=dict(color='red'), name='MA_200'))

            # Add shaded regions for buy/sell conditions
            region_colors = {
                'Good Buy': 'rgba(0, 255, 0, 0.4)',  # Bright green
                'Good Sell': 'rgba(255, 0, 0, 0.4)',  # Bright red
                'Great Buy': 'rgba(0, 200, 0, 0.6)',  # Darker green
                'Great Sell': 'rgba(200, 0, 0, 0.6)',  # Darker red
                'Excellent Buy': 'rgba(0, 128, 0, 0.8)',  # Deep green
                'Excellent Sell': 'rgba(128, 0, 0, 0.8)'  # Deep red
            }

            df['market_condition'] = None
            df.loc[(df['RSI'] < 40) & (df['MFI'] < 50) & (df['Stoch_RSI'] < 0.3), 'market_condition'] = 'Good Buy'
            df.loc[(df['RSI'] > 60) & (df['MFI'] > 50) & (df['Stoch_RSI'] > 0.7), 'market_condition'] = 'Good Sell'
            df.loc[(df['RSI'] < 30) & (df['MFI'] < 20) & (df['Stoch_RSI'] < 0.2), 'market_condition'] = 'Great Buy'
            df.loc[(df['RSI'] > 70) & (df['MFI'] > 80) & (df['Stoch_RSI'] > 0.8), 'market_condition'] = 'Great Sell'
            df.loc[(df['RSI'] < 20) & (df['MFI'] < 10) & (df['Stoch_RSI'] < 0.1), 'market_condition'] = 'Excellent Buy'
            df.loc[(df['RSI'] > 80) & (df['MFI'] > 90) & (df['Stoch_RSI'] > 0.9), 'market_condition'] = 'Excellent Sell'

            for condition, color in region_colors.items():
                condition_df = df[df['market_condition'] == condition]
                if not condition_df.empty:
                    condition_df['region_id'] = (condition_df['Date'].diff() != pd.Timedelta(days=1)).cumsum()
                    for _, region_data in condition_df.groupby('region_id'):
                        start_date = region_data['Date'].iloc[0]
                        end_date = region_data['Date'].iloc[-1]
                        fig_price.add_shape(
                            type="rect",
                            xref="x",
                            yref="paper",
                            x0=start_date,
                            x1=end_date,
                            y0=0,
                            y1=1,
                            fillcolor=color,
                            opacity=0.2,
                            line_width=0
                        )

            # Render chart

            st.plotly_chart(fig_price, use_container_width=True)

            # RSI
            fig_rsi = go.Figure()
            fig_rsi.add_trace(go.Scatter(x=df['Date'], y=df['RSI'], line=dict(color='purple'), name='RSI'))
            fig_rsi.add_hline(y=30, line_dash="dot", line_color="gray")
            fig_rsi.add_hline(y=70, line_dash="dot", line_color="gray")
            fig_rsi.update_layout(title="RSI", height=300)
            st.plotly_chart(fig_rsi, use_container_width=True)

            # MFI
            fig_mfi = go.Figure()
            fig_mfi.add_trace(go.Scatter(x=df['Date'], y=df['MFI'], line=dict(color='green'), name='MFI'))
            fig_mfi.add_hline(y=20, line_dash="dot", line_color="gray")
            fig_mfi.add_hline(y=80, line_dash="dot", line_color="gray")
            fig_mfi.update_layout(title="MFI", height=300)
            st.plotly_chart(fig_mfi, use_container_width=True)

            # Stoch RSI
            fig_stoch = go.Figure()
            fig_stoch.add_trace(go.Scatter(x=df['Date'], y=df['Stoch_RSI'], line=dict(color='magenta'), name='Stoch_RSI'))
            fig_stoch.add_hline(y=0.2, line_dash="dot", line_color="gray")
            fig_stoch.add_hline(y=0.8, line_dash="dot", line_color="gray")
            fig_stoch.update_layout(title="Stoch RSI", height=300)
            st.plotly_chart(fig_stoch, use_container_width=True)

            # MACD
            fig_macd = go.Figure()
            fig_macd.add_trace(go.Scatter(x=df['Date'], y=df['MACD'], line=dict(color='blue'), name='MACD'))
            fig_macd.add_trace(go.Scatter(x=df['Date'], y=df['MACD_Signal'], line=dict(color='red'), name='MACD_Signal'))
            fig_macd.add_trace(go.Bar(x=df['Date'], y=df['MACD_Hist'], name='MACD_Hist', marker_color='gray'))
            fig_macd.update_layout(title="MACD", height=300)
            st.plotly_chart(fig_macd, use_container_width=True)


if "selected_pair" not in st.session_state:
    st.session_state.selected_pair = pairs[0]

st.session_state.selected_pair = st.selectbox("Select Crypto Pair", pairs, index=pairs.index(st.session_state.selected_pair), key="pair_select")

# Similarly for timeframes
if "selected_timeframe" not in st.session_state:
    st.session_state.selected_timeframe = timeframes[0]

st.session_state.selected_timeframe = st.selectbox("Select Timeframe", timeframes, 
    index=timeframes.index(st.session_state.selected_timeframe), key="timeframe_select")

