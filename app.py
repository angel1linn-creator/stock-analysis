import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import time
import plotly.graph_objects as go

# 設定網頁標題與佈局
st.set_page_config(page_title="台股動態即時量價分析", layout="wide")

st.title("📊 台股上市櫃股票 - 動態即時量價分析儀表板")
st.markdown("本儀表板採用 `yfinance` 核心，並導入區域局部重繪技術，實現盤中動態即時報價。")

# 側邊欄：使用者輸入代碼
st.sidebar.header("控制面板")
stock_code = st.sidebar.text_input("請輸入台股代碼（例如：6239 或 2330）：", value="6239").strip()
refresh_rate = st.sidebar.slider("即時報價更新頻率 (秒)", min_value=5, max_value=60, value=10)

# 使用 Streamlit 內建快取歷史資料，TTL 設為 10 分鐘，徹底防範雲端 IP 被 Yahoo 限流
@st.cache_data(ttl=600)
def get_historical_data(ticker_str):
    tz = datetime.timezone(datetime.timedelta(hours=8))
    end_dt = datetime.datetime.now(tz)
    start_dt = end_dt - datetime.timedelta(days=120)  # 確保有足夠天數算出 MA60
    
    stock_obj = yf.Ticker(ticker_str)
    # 抓取日 K 線歷史資料
    hist_df = stock_obj.history(start=start_dt.strftime('%Y-%m-%d'), end=(end_dt + datetime.timedelta(days=1)).strftime('%Y-%m-%d'))
    
    if hist_df.empty:
        return pd.DataFrame(), {}
        
    # 計算技術指標
    hist_df['MA5'] = hist_df['Close'].rolling(window=5).mean()
    hist_df['MA20'] = hist_df['Close'].rolling(window=20).mean()
    hist_df['MA60'] = hist_df['Close'].rolling(window=60).mean()
    
    info = stock_obj.info
    name = info.get('longName', info.get('shortName', f"台股 {ticker_str.split('.')[0]}"))
    
    return hist_df, {"name": name}

if stock_code:
    # 判斷上市或上櫃後綴
    ticker_symbol = f"{stock_code}.TW"
    df, info_dict = get_historical_data(ticker_symbol)
    
    if df.empty:
        ticker_symbol = f"{stock_code}.TWO"
        df, info_dict = get_historical_data(ticker_symbol)
        
    if df.empty:
        st.error(f"無法取得代碼 {stock_code} 的歷史數據，請確認代碼是否正確。")
    else:
        stock_name = info_dict["name"]
        st.subheader(f"🔍 當前分析標的：{stock_code} {stock_name}")
        
        # ----------------------------------------------------
        # ⚡ 動態即時股價呈現區塊 (利用 Fragment 技術進行局部重繪)
        # ----------------------------------------------------
        @st.fragment
        def render_realtime_section(ticker_str, historical_df):
            # 即時抓取最新的一筆盤中數據 (用 1m Ｋ線抓最後一分鐘)
            try:
                rt_stock = yf.Ticker(ticker_str)
                rt_df = rt_stock.history(period="1d", interval="1m")
                
                if not rt_df.empty:
                    latest_rt = rt_df.iloc[-1]
                    current_price = round(latest_rt['Close'], 2)
                    # 盤中即時累計量
                    current_volume = int(rt_df['Volume'].sum()) 
                else:
                    # 若週六日或盤後沒即時1分K，則抓歷史日K最後一筆
                    current_price = round(historical_df.iloc[-1]['Close'], 2)
                    current_volume = int(historical_df.iloc[-1]['Volume'])
            except:
                # 發生異常時降級讀取歷史暫存
                current_price = round(historical_df.iloc[-1]['Close'], 2)
                current_volume = int(historical_df.iloc[-1]['Volume'])

            # 取得前一交易日與歷史關鍵數據
            prev_data = historical_df.iloc[-2] if len(historical_df) > 1 else historical_df.iloc[-1]
            max_volume_row = historical_df.loc[historical_df['Volume'].idxmax()]
            
            prev_price = round(prev_data['Close'], 2)
            prev_volume = int(prev_data['Volume'])
            ma20_val = round(historical_df.iloc[-1]['MA20'], 2) if not pd.isna(historical_df.iloc[-1]['MA20']) else 0
            
            max_vol = int(max_volume_row['Volume'])
            max_vol_date = max_volume_row.name.strftime('%Y-%m-%d')
            max_vol_price = round(max_volume_row['Close'], 2)
            
            # 計算即時乖離率與漲跌
            bias_ma20 = round(((current_price - ma20_val) / ma20_val) * 100, 2) if ma20_val > 0 else 0
            price_change = round(current_price - prev_price, 2)
            
            # 建立即時 KPI 卡片
            st.markdown("### ⚡ 盤中動態即時報價")
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric(label="動態即時股價", value=f"${current_price} 元", delta=f"{price_change} 元")
            kpi2.metric(label="今日累計成交量", value=f"{current_volume // 1000:,} 張" if current_volume > 1000 else f"{current_volume} 股")
            kpi3.metric(label="20日平均線 (月線)", value=f"${ma20_val} 元", delta=f"當前乖離 {bias_ma20}%")
            kpi4.metric(label="波段最高天量", value=f"{max_vol // 1000:,} 張", delta=f"日期: {max_vol_date}")
            
            # 一、 量價關係對比彙總表
            st.markdown("### 一、 量價關係對比彙總表")
            summary_data = {
                "日期/項目": ["波段最高天量日", "前一交易日", "今日動態即時"],
                "股價位置": [f"${max_vol_price} 元", f"${prev_price} 元", f"${current_price} 元"],
                "成交量": [f"{max_vol // 1000:,} 張", f"{prev_volume // 1000:,} 張", f"{current_volume // 1000:,} 張"],
                "盤面技術與籌碼意涵": [
                    f"爆出近期歷史天量（{max_vol_date}），屬於多空劇烈震盪或主力強攻換手區。",
                    "前一日量能狀態，作為今日量能是否委縮的對比基準。",
                    "每秒動態更新之最新交易結果，呈現當前多空最新表態。"
                ]
            }
            st.table(pd.DataFrame(summary_data))
            
            # 二、 今日「量縮」的籌碼面與操作解析
            st.markdown("### 二、 今日「量縮」的籌碼面與操作解析")
            is_vol_shrunk_prev = current_volume < prev_volume
            is_vol_shrunk_max = current_volume < (max_vol * 0.4)
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 🔄 即時量能對比")
                if is_vol_shrunk_prev:
                    st.success(f"✅ **當前成交量較前一日減少**：目前 {current_volume // 1000:,} 張 對比昨日 {prev_volume // 1000:,} 張，量能出現委縮。")
                else:
                    st.warning(f"⚠️ **當前成交量較前一日放大**：目前 {current_volume // 1000:,} 張 對比昨日 {prev_volume // 1000:,} 張，短線動能仍在釋放。")
                    
                if is_vol_shrunk_max:
                    st.info(f"❄️ **量能極度急凍**：當前量能不達最高天量的四成，短線熱錢、當沖與隔日沖資金出現明顯撤離。")
            
            with col2:
                st.markdown("#### 🧠 即時籌碼面解讀")
                if current_price >= prev_price and is_vol_shrunk_prev:
                    st.markdown("> **量縮橫盤/小漲：** 高檔追高意願降低，但**無恐慌性賣壓**（良性量縮），籌碼正處於沈澱期。")
                elif current_price < prev_price and is_vol_shrunk_prev:
                    st.markdown("> **量縮下跌：** 多頭架構下的良性拉回。技術面尚未爆量踩踏，主力並未不計代價出貨。")
                else:
                    st.markdown("> **帶量震盪：** 盤面震盪幅度與量能同步放大，多空雙方在此價格區間仍有分歧。")

            # 三、 綜合結論：今天適合進場嗎？
            st.markdown("### 三、 綜合結論：今天適合進場嗎？")
            if bias_ma20 > 15:
                st.error(f"🚨 **策略建議：目前「極度不適合」盲目追高。** 目前股價距離月線存在高達 **{bias_ma20}%** 的巨大正乖離，隨時有修正引力。建議等股價與月線距離縮小至 5-10% 內再行切入。")
            elif bias_ma20 > 0 and bias_ma20 <= 15:
                st.warning(f"⚖️ **策略建議：適合「小量試單」或「分批逢低布局」。** 股價在月線之上，多頭架構不變，且乖離率已修正至相對安全範圍，配合量縮是標準的拉回找買點。")
            else:
                st.info(f"📉 **策略建議：股價已跌破月線。** 短線趨勢偏弱，建議不要伸手接刀，等待成交量出現連續 2-3 天的「極度窒息量」再考慮波段切入。")

            # 倒數計時並自動觸發局部重繪
            st.caption(f"🔄 儀表板將在 {refresh_rate} 秒後自動重新整理... 最新同步時間：{datetime.datetime.now().strftime('%H:%M:%S')}")
            time.sleep(refresh_rate)
            st.rerun()

        # 執行即時呈現區塊
        render_realtime_section(ticker_symbol, df)
        
        st.markdown("---")
        
        # 💡 四、 歷史走勢圖（此區塊不會隨著每秒即時更新而閃爍，維持使用者體驗）
        st.markdown("### 📈 歷史K線與中長期均線走勢圖 (每10分鐘後台更新)")
        ma5_val_h = round(df.iloc[-1]['MA5'], 2) if not pd.isna(df.iloc[-1]['MA5']) else "計算中"
        ma20_val_h = round(df.iloc[-1]['MA20'], 2) if not pd.isna(df.iloc[-1]['MA20']) else "計算中"
        ma60_val_h = round(df.iloc[-1]['MA60'], 2) if not pd.isna(df.iloc[-1]['MA60']) else "計算中"
        
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='日K線'))
        if not isinstance(ma5_val_h, str): fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='orange', width=1.5), name='5日線'))
        if not isinstance(ma20_val_h, str): fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='magenta', width=2), name='月線(20MA)'))
        if not isinstance(ma60_val_h, str): fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='cyan', width=2), name='季線(60MA)'))
        fig.update_layout(xaxis_rangeslider_visible=False, height=450, margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)