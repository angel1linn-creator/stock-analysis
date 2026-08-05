import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import time
import plotly.graph_objects as go
import json
import os

# 設定網頁標題與佈局
st.set_page_config(page_title="台股動態即時量價與融資籌碼分析儀表板", layout="wide")

# --- 投資組合儲存邏輯 ---
PORTFOLIO_FILE = "portfolio.json"

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r") as f:
                return json.load(f)
        except:
            return ["6239", "2330"]
    return ["6239", "2330"]

def save_portfolio(portfolio):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f)

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_portfolio()

st.title("📊 台股上市櫃股票 - 動態即時量價與融資籌碼分析儀表板")
st.markdown("本儀表板結合 `yfinance` 報價、**價量關係**與**融資融券籌碼結構**，即時診斷市場籌碼沉澱度、軋空潛力與融資斷頭風險。")

# 側邊欄：使用者輸入代碼與籌碼設定
st.sidebar.header("🎛️ 控制面板")
stock_code = st.sidebar.text_input("請輸入台股代碼（例如：6239 或 2330）：", value="6239").strip()
refresh_rate = st.sidebar.slider("即時報價更新頻率 (秒)", min_value=5, max_value=60, value=10)

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ 融資與籌碼動態模擬參數")
st.sidebar.caption("因 API 盤中融資資料於盤後更新，您可在此微調今日籌碼趨勢進行即時模擬診斷：")
margin_trend = st.sidebar.radio("今日估計融資變化：", options=["融資增加 (散戶進場/開槓桿)", "融資減少 (籌碼沉澱/退場)"], index=1)
short_ratio_level = st.sidebar.select_slider("當前券資比程度 (觀察軋空力道)：", options=["低 (<10%)", "中 (10%~30%)", "高 (>30% 具強烈軋空潛力)"], value="中 (10%~30%)")

# 側邊欄：自選投資組合管理
st.sidebar.markdown("---")
st.sidebar.subheader("⭐ 自選投資組合管理")
new_stock = st.sidebar.text_input("新增股票代碼:", key="new_stock_input").strip()
if st.sidebar.button("加入組合"):
    if new_stock and new_stock not in st.session_state.portfolio:
        st.session_state.portfolio.append(new_stock)
        save_portfolio(st.session_state.portfolio)
        st.rerun()

# 顯示自選股清單與刪除按鈕
for s in st.session_state.portfolio:
    cols = st.sidebar.columns([3, 1])
    cols[0].write(s)
    if cols[1].button("❌", key=f"remove_{s}"):
        st.session_state.portfolio.remove(s)
        save_portfolio(st.session_state.portfolio)
        st.rerun()

# 使用 Streamlit 內建快取歷史資料，TTL 設為 10 分鐘，防範被限流
@st.cache_data(ttl=600)
def get_historical_data(ticker_str):
    tz = datetime.timezone(datetime.timedelta(hours=8))
    end_dt = datetime.datetime.now(tz)
    start_dt = end_dt - datetime.timedelta(days=120)  # 確保有足夠天數算出 MA60
    
    stock_obj = yf.Ticker(ticker_str)
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

# 12種價/量/融資綜合情境診斷矩陣數據庫
SCENARIO_MATRIX = {
    ('Up', 'High', 'Up'): {
        "title": "🔥 高檔過熱 / 散戶追高",
        "risk": "中高風險",
        "color": "warning",
        "desc": "股價上漲且成交量放大，但融資同步大幅增加，代表散戶與槓桿資金瘋狂追高。籌碼趨於凌亂，若遭遇突發利空容易引發高檔獲利了結賣壓。"
    },
    ('Up', 'High', 'Down'): {
        "title": "🚀 健康多頭 / 主力強勢吸籌",
        "risk": "低~中風險",
        "color": "success",
        "desc": "價漲量增且融資持續減少，屬於最健康的『法人/主力吸籌』格局！浮動籌碼被清洗乾淨，散戶退場，股價由聰明錢（Smart Money）推升，續漲動能強勁。"
    },
    ('Up', 'Low', 'Up'): {
        "title": "⚠️ 虛漲背離 / 槓桿硬推",
        "risk": "中高風險",
        "color": "warning",
        "desc": "成交量並未放大，股價卻靠融資槓桿推升，呈現『價量背離』。缺乏實體資金支撐，容易形成假突破，追高需極度謹慎。"
    },
    ('Up', 'Low', 'Down'): {
        "title": "🌱 溫和整理上攻 / 籌碼安定",
        "risk": "低風險",
        "color": "success",
        "desc": "股價小幅推升，量能溫和，融資同步下降。代表無散戶浮躁追高，籌碼高度安定，屬於波段多頭中的健康休整期。"
    },
    ('Flat', 'High', 'Up'): {
        "title": "🧱 高檔出貨 / 多空劇烈分歧",
        "risk": "高風險",
        "color": "error",
        "desc": "股價滯漲盤整，但爆出巨量且融資大增。暗示主力正利用高檔交投熱絡大量拋售籌碼給散戶接盤，容易形成中期頭部。"
    },
    ('Flat', 'High', 'Down'): {
        "title": "🧲 籌碼洗盤換手 / 大戶逢低承接",
        "risk": "低風險",
        "color": "info",
        "desc": "股價平盤整理，帶量但融資顯著減少。代表散戶失去耐心停損出場，而大戶與法人則在盤下靜靜接走籌碼，利於後續築底完成。"
    },
    ('Flat', 'Low', 'Up'): {
        "title": "🫧 虛浮盤整 / 零星槓桿",
        "risk": "中度風險",
        "color": "warning",
        "desc": "市場交投清淡，股價無明確方向，但融資微幅爬升。顯示市場缺乏法人關注，僅剩少量散戶用槓桿博弈，走勢易受大盤拖累。"
    },
    ('Flat', 'Low', 'Down'): {
        "title": "💤 窒息沉澱 / 完全觀望",
        "risk": "低風險",
        "color": "info",
        "desc": "量能急凍、融資持續遞減，市場陷入極度冷清。這通常是籌碼落底前夕的『窒息量』特徵，待新買盤進駐即有反彈機會。"
    },
    ('Down', 'High', 'Up'): {
        "title": "🚨 極度危險 / 融資死摳與斷頭高危區",
        "risk": "極高風險",
        "color": "error",
        "desc": "股價重挫且帶量，融資卻不減反增！代表散戶不斷逢低『攤平』接刀。若股價繼續下探，將觸發融資維持率不足（Margin Call），引發連環斷頭踩踏賣壓！"
    },
    ('Down', 'High', 'Down'): {
        "title": "💥 恐慌殺多 / 斷頭洗盤築底",
        "risk": "中度風險（迎向築底）",
        "color": "warning",
        "desc": "帶量下殺且融資出現暴減，代表市場出現恐慌性停損與融資斷頭潮。雖然短線陣痛劇烈，但籌碼清洗最徹底，歷史上常是中長期落底訊號。"
    },
    ('Down', 'Low', 'Up'): {
        "title": "🩸 無量陰跌 / 槓桿套牢",
        "risk": "高風險",
        "color": "error",
        "desc": "成交量低迷，股價緩步陰跌，但融資並未退場。市場缺乏接盤買盤，籌碼持續被套牢，走勢極為孱弱。"
    },
    ('Down', 'Low', 'Down'): {
        "title": "📉 順勢陰跌整理 / 靜待止跌",
        "risk": "中高風險",
        "color": "warning",
        "desc": "無量下跌且融資同步退場，屬於散戶落跑、法人觀望的自然修正期。雖然無大爆量殺多風險，但仍需等待止跌訊號出現。"
    }
}

tab1, tab2 = st.tabs(["🔍 單一股票與籌碼矩陣分析", "⭐ 自選組合即時概覽"])

with tab1:
    if stock_code:
        # 判斷上市 (.TW) 或上櫃 (.TWO)
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
            # ⚡ 動態即時股價與籌碼呈現區塊 (利用 Fragment 技術進行局部重繪)
            # ----------------------------------------------------
            @st.fragment(run_every=refresh_rate)
            def render_realtime_section(ticker_str, historical_df):
                try:
                    rt_stock = yf.Ticker(ticker_str)
                    rt_df = rt_stock.history(period="1d", interval="1m")

                    if not rt_df.empty:
                        latest_rt = rt_df.iloc[-1]
                        current_price = round(latest_rt['Close'], 2)
                        current_volume = int(rt_df['Volume'].sum()) 
                    else:
                        current_price = round(historical_df.iloc[-1]['Close'], 2)
                        current_volume = int(historical_df.iloc[-1]['Volume'])
                except:
                    current_price = round(historical_df.iloc[-1]['Close'], 2)
                    current_volume = int(historical_df.iloc[-1]['Volume'])

                prev_data = historical_df.iloc[-2] if len(historical_df) > 1 else historical_df.iloc[-1]
                max_volume_row = historical_df.loc[historical_df['Volume'].idxmax()]

                prev_price = round(prev_data['Close'], 2)
                prev_volume = int(prev_data['Volume'])
                ma20_val = round(historical_df.iloc[-1]['MA20'], 2) if not pd.isna(historical_df.iloc[-1]['MA20']) else 0

                max_vol = int(max_volume_row['Volume'])
                max_vol_date = max_volume_row.name.strftime('%Y-%m-%d')
                max_vol_price = round(max_volume_row['Close'], 2)

                bias_ma20 = round(((current_price - ma20_val) / ma20_val) * 100, 2) if ma20_val > 0 else 0
                price_change = round(current_price - prev_price, 2)

                # 即時 KPI 卡片
                st.markdown("### ⚡ 盤中即時價量與籌碼概況")
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric(label="即時成交價", value=f"${current_price} 元", delta=f"{price_change} 元")
                kpi2.metric(label="今日累計成交量", value=f"{current_volume // 1000:,} 張" if current_volume > 1000 else f"{current_volume} 股")
                kpi3.metric(label="20日月線 (MA20)", value=f"${ma20_val} 元", delta=f"月線乖離率 {bias_ma20}%")
                
                # 計算融資與籌碼趨勢鍵值
                p_trend = "Up" if current_price > prev_price else ("Down" if current_price < prev_price else "Flat")
                v_trend = "High" if current_volume >= prev_volume else "Low"
                m_trend = "Up" if "增加" in margin_trend else "Down"

                diag_key = (p_trend, v_trend, m_trend)
                diag_info = SCENARIO_MATRIX.get(diag_key, {
                    "title": "綜合評估中", "risk": "中等", "color": "info", "desc": "資料更新中..."
                })

                kpi4.metric(label="籌碼與技術診斷", value=diag_info["title"].split(' ')[1] if ' ' in diag_info["title"] else diag_info["title"], delta=f"風險評估: {diag_info['risk']}")

                # 一、 量價與籌碼關係對比表
                st.markdown("### 一、 量價與融資籌碼指標對比表")
                summary_data = {
                    "觀察指標 / 項目": ["波段最高天量日", "前一交易日", "今日即時與籌碼趨勢"],
                    "股價位置": [f"${max_vol_price} 元", f"${prev_price} 元", f"${current_price} 元"],
                    "成交量狀態": [f"{max_vol // 1000:,} 張 (天量)", f"{prev_volume // 1000:,} 張", f"{current_volume // 1000:,} 張 ({'帶量' if v_trend=='High' else '量縮'})"],
                    "融資與籌碼解讀": [
                        f"爆出近期天量（{max_vol_date}），為多空主力劇烈換手或高檔出貨區。",
                        "前日量能基準點，作為今日多空交投熱度之對比對象。",
                        f"目前設定融資趨勢為【{margin_trend.split(' ')[0]}】，券資比【{short_ratio_level}】。"
                    ]
                }
                st.table(pd.DataFrame(summary_data))

                # 二、 融資籌碼與價量綜合診斷矩陣 (核心新增區塊)
                st.markdown("### 二、 融資籌碼與價量綜合診斷矩陣")
                
                diag_card_style = {
                    "success": "background-color: rgba(14, 188, 95, 0.1); border-left: 5px solid #0ebc5f; padding: 15px; border-radius: 8px;",
                    "warning": "background-color: rgba(255, 219, 15, 0.1); border-left: 5px solid #e6b800; padding: 15px; border-radius: 8px;",
                    "error": "background-color: rgba(222, 45, 41, 0.1); border-left: 5px solid #de2d29; padding: 15px; border-radius: 8px;",
                    "info": "background-color: rgba(49, 134, 255, 0.1); border-left: 5px solid #3186ff; padding: 15px; border-radius: 8px;"
                }

                st.markdown(f"""
                <div style="{diag_card_style[diag_info['color']]}">
                    <h3 style="margin-top:0; color: inherit;">{diag_info['title']}（風險等級：{diag_info['risk']}）</h3>
                    <p style="font-size: 15px; line-height: 1.6; margin-bottom: 0;">{diag_info['desc']}</p>
                </div>
                """, unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)
                
                # 籌碼面進階三大觀察重點
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.markdown("#### 1. 籌碼穩定度（籌碼集中度）")
                    if m_trend == "Down" and p_trend in ["Up", "Flat"]:
                        st.success("🟢 **籌碼高度安定**：融資減、股價不跌，代表浮動籌碼順利流向法人與主力大戶手上。")
                    elif m_trend == "Up" and p_trend in ["Down", "Flat"]:
                        st.error("🔴 **籌碼趨於凌亂**：融資增、股價停滯或下跌，籌碼流向散戶，主力正在高檔出貨或離場。")
                    else:
                        st.info("🟡 **籌碼平衡震盪**：籌碼無極端傾斜，後續視大盤動向與量能是否連續放大而定。")

                with col_b:
                    st.markdown("#### 2. 融資斷頭與踩踏風險")
                    if p_trend == "Down" and m_trend == "Up":
                        st.error("🚨 **高危斷頭預警**：股價下跌但融資持續增加，散戶逢低接刀套牢，極易誘發融資維持率低於 130% 之斷頭賣壓！")
                    elif p_trend == "Down" and v_trend == "High" and m_trend == "Down":
                        st.warning("⚡ **恐慌斷頭宣洩中**：融資正在快速斷頭或停損退場，雖然短線劇烈修正，但屬於沉澱落底必要過程。")
                    else:
                        st.success("✅ **融資風險安全**：無融資死摳或連環斷頭之立即危險。")

                with col_c:
                    st.markdown("#### 3. 軋空潛力評估 (Short Squeeze)")
                    if "高" in short_ratio_level and p_trend == "Up":
                        st.success("🔥 **強烈軋空機會**：高券資比加上股價上漲，逼迫空頭借券買回補回（Short Squeeze），形成雙重推升買盤！")
                    elif "高" in short_ratio_level and p_trend == "Down":
                        st.warning("⚔️ **軋多/多頭棄守**：高券資比但股價下跌，空頭佔據上風，多頭小心遭軋多踩踏。")
                    else:
                        st.info("🔹 **軋空力道平緩**：券資比處於常態範圍，股價主要受現貨買賣盤支配。")

                # 三、 綜合實戰操作策略建議
                st.markdown("### 三、 綜合實戰操作策略建議")
                if bias_ma20 > 15:
                    st.error(f"🚨 **策略建議：【嚴禁追高】** 目前股價離 20 日月線高達 **{bias_ma20}%** 巨大正乖離。即使籌碼良好，隨時有技術面修正引力，建議等待拉回至乖離率 5%~8% 內再行切入。")
                elif bias_ma20 > 0 and bias_ma20 <= 15:
                    if m_trend == "Down":
                        st.success("🎯 **策略建議：【分批逢低布局 / 多頭買點】** 股價站於月線之上且融資退場籌碼沉澱，配合量縮拉回是極佳的法人順勢買點。")
                    else:
                        st.warning("⚖️ **策略建議：【小量試單】** 多頭架構仍存，但散戶融資稍顯偏高，建議採守護停損點（如月線）方式小量操作。")
                else:
                    if p_trend == "Down" and m_trend == "Up":
                        st.error("📉 **策略建議：【觀望避開 / 嚴禁接刀】** 股價已跌破月線且融資逆勢增加，面臨多頭踩踏與斷頭賣壓，切勿徒手接刀！")
                    else:
                        st.info("📉 **策略建議：【等待築底訊號】** 股價位於月線下方，建議耐心等待連兩天出現『極度窒息量』與融資大幅減碼後再考量波段建倉。")

                st.caption(f"🔄 儀表板自動更新中 (更新頻率: {refresh_rate}s) 最新同步時間：{datetime.datetime.now().strftime('%H:%M:%S')}")

            # 執行即時與籌碼診斷區塊
            render_realtime_section(ticker_symbol, df)

            st.markdown("---")

            # 四、 歷史走勢與技術均線圖
            st.markdown("### 📈 歷史 K 線與中長期均線走勢圖 (每10分鐘後台更新)")
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

with tab2:
    st.subheader("⭐ 自選組合即時與籌碼概覽")
    if not st.session_state.portfolio:
        st.info("目前自選組合為空，請從側邊欄加入股票。")
    else:
        @st.fragment(run_every=refresh_rate)
        def render_portfolio_overview():
            portfolio_results = []
            for code in st.session_state.portfolio:
                try:
                    t_symbol = f"{code}.TW"
                    t_obj = yf.Ticker(t_symbol)
                    t_hist = t_obj.history(period="2d")
                    if t_hist.empty:
                        t_symbol = f"{code}.TWO"
                        t_obj = yf.Ticker(t_symbol)
                        t_hist = t_obj.history(period="2d")

                    if not t_hist.empty:
                        curr_p = round(t_hist.iloc[-1]['Close'], 2)
                        prev_p = round(t_hist.iloc[-2]['Close'], 2) if len(t_hist) > 1 else curr_p
                        chg = round(curr_p - prev_p, 2)
                        chg_pct = round((chg / prev_p) * 100, 2) if prev_p != 0 else 0
                        vol = int(t_hist.iloc[-1]['Volume'])

                        portfolio_results.append({
                            "代碼": code,
                            "現價": f"${curr_p}",
                            "漲跌": f"{chg} ({chg_pct}%)",
                            "成交量": f"{vol // 1000:,} 張" if vol > 1000 else f"{vol} 股",
                            "盤面狀態": "多頭攻勢" if chg > 0 else ("壓回整理" if chg < 0 else "平盤觀望")
                        })
                    else:
                        portfolio_results.append({
                            "代碼": code, "現價": "N/A", "漲跌": "N/A", "成交量": "N/A", "盤面狀態": "無數據"
                        })
                except:
                    portfolio_results.append({
                        "代碼": code, "現價": "Error", "漲跌": "Error", "成交量": "Error", "盤面狀態": "讀取失敗"
                    })

            st.table(pd.DataFrame(portfolio_results))
            st.caption(f"🔄 自選組合自動更新中... (頻率: {refresh_rate}s) 最新同步時間：{datetime.datetime.now().strftime('%H:%M:%S')}")

        render_portfolio_overview()