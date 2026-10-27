import streamlit as st
import datetime
import calendar
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import plotly.express as px
import json
import os

# 1. 頁面設定
st.set_page_config(
    page_title="台股全方位動態即時與結算籌碼分析儀表板",
    page_icon="📈",
    layout="wide"
)

# --- 投資組合儲存邏輯 ---
PORTFOLIO_FILE = "portfolio.json"

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r") as f:
                return json.load(f)
        except:
            return ["3661", "2330"]
    return ["3661", "2330"]

def save_portfolio(portfolio):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f)

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = load_portfolio()

# 2. 核心計算函數：期指結算日與交易日偏移
def get_third_wednesday(year: int, month: int) -> datetime.date:
    """計算指定年月之第三個星期三（台指期月結算日）"""
    cal = calendar.monthcalendar(year, month)
    wednesdays = [week[calendar.WEDNESDAY] for week in cal if week[calendar.WEDNESDAY] != 0]
    return datetime.date(year, month, wednesdays[2])

def get_trading_day_offset(df: pd.DataFrame, target_date: datetime.date, offset: int) -> tuple:
    """取得目標日期偏移 offset 個交易日的日期、收盤價與成交量"""
    df_sorted = df.sort_index()
    past_dates = df_sorted.index[df_sorted.index.date <= target_date]
    if len(past_dates) == 0:
        return None, None, None
    
    base_idx = df_sorted.index.get_loc(past_dates[-1])
    target_idx = base_idx + offset
    
    if 0 <= target_idx < len(df_sorted):
        date_val = df_sorted.index[target_idx].date()
        price_val = df_sorted.iloc[target_idx]['Close']
        vol_val = df_sorted.iloc[target_idx]['Volume']
        return date_val, round(price_val, 2), vol_val
    return None, None, None

# 3. 通用資料抓取函數（支援上市 .TW 與上櫃 .TWO，並涵蓋足夠天數計算技術指標與結算歷史）
@st.cache_data(ttl=600)
def get_stock_data_universal(stock_id: str, days_back=500):
    clean_id = stock_id.replace(".TW", "").replace(".TWO", "").strip()
    suffixes = [".TW", ".TWO"] if not stock_id.endswith((".TW", ".TWO")) else [""]
    
    tz = datetime.timezone(datetime.timedelta(hours=8))
    end_dt = datetime.datetime.now(tz)
    start_dt = end_dt - datetime.timedelta(days=days_back)
    
    for suffix in suffixes:
        symbol = f"{clean_id}{suffix}"
        stock_obj = yf.Ticker(symbol)
        hist_df = stock_obj.history(start=start_dt.strftime('%Y-%m-%d'), end=(end_dt + datetime.timedelta(days=1)).strftime('%Y-%m-%d'))
        
        if not hist_df.empty:
            if isinstance(hist_df.columns, pd.MultiIndex):
                hist_df = hist_df.droplevel(1, axis=1)
            
            # 計算技術指標
            hist_df['MA5'] = hist_df['Close'].rolling(window=5).mean()
            hist_df['MA20'] = hist_df['Close'].rolling(window=20).mean()
            hist_df['MA60'] = hist_df['Close'].rolling(window=60).mean()
            
            info = stock_obj.info
            name = info.get('longName', info.get('shortName', f"台股 {clean_id}"))
            return hist_df, {"name": name, "symbol": symbol}
            
    return pd.DataFrame(), {}

def get_stock_display_name(stock_id: str, symbol: str) -> str:
    """動態取得股票中文/英文名稱"""
    name_map = {
        "3661": "世芯-KY",
        "2330": "台積電",
        "2454": "聯發科",
        "2317": "鴻海",
        "2308": "台達電",
        "2603": "長榮",
        "8299": "群聯",
        "2881": "富邦金",
        "2882": "國泰金",
        "6239": "力成"
    }
    clean_id = stock_id.replace(".TW", "").replace(".TWO", "").strip()
    if clean_id in name_map:
        return f"{name_map[clean_id]} ({clean_id})"
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        short_name = info.get('shortName') or info.get('longName')
        if short_name:
            return f"{short_name} ({clean_id})"
    except:
        pass
    
    return f"股票代號 {clean_id}"

# 12種價/量/融資綜合情境診斷矩陣數據庫
SCENARIO_MATRIX = {
    ('Up', 'High', 'Up'): {
        "title": "🔥 高檔過熱 / 散戶追高", "risk": "中高風險", "color": "warning",
        "desc": "股價上漲且成交量放大，但融資同步大幅增加，代表散戶與槓桿資金瘋狂追高。籌碼趨於凌亂，若遭遇突發利空容易引發高檔獲利了結賣壓。"
    },
    ('Up', 'High', 'Down'): {
        "title": "🚀 健康多頭 / 主力強勢吸籌", "risk": "低~中風險", "color": "success",
        "desc": "價漲量增且融資持續減少，屬於最健康的『法人/主力吸籌』格局！浮動籌碼被清洗乾淨，散戶退場，股價由聰明錢推升，續漲動能強勁。"
    },
    ('Up', 'Low', 'Up'): {
        "title": "⚠️ 虛漲背離 / 槓桿硬推", "risk": "中高風險", "color": "warning",
        "desc": "成交量並未放大，股價卻靠融資槓桿推升，呈現『價量背離』。缺乏實體資金支撐，容易形成假突破，追高需極度謹慎。"
    },
    ('Up', 'Low', 'Down'): {
        "title": "🌱 溫和整理上攻 / 籌碼安定", "risk": "低風險", "color": "success",
        "desc": "股價小幅推升，量能溫和，融資同步下降。代表無散戶浮躁追高，籌碼高度安定，屬於波段多頭中的健康休整期。"
    },
    ('Flat', 'High', 'Up'): {
        "title": "🧱 高檔出貨 / 多空劇烈分歧", "risk": "高風險", "color": "error",
        "desc": "股價滯漲盤整，但爆出巨量且融資大增。暗示主力正利用高檔交投熱絡大量拋售籌碼給散戶接盤，容易形成中期頭部。"
    },
    ('Flat', 'High', 'Down'): {
        "title": "🧲 籌碼洗盤換手 / 大戶逢低承接", "risk": "低風險", "color": "info",
        "desc": "股價平盤整理，帶量但融資顯著減少。代表散戶失去耐心停損出場，而大戶與法人則在盤下靜靜接走籌碼，利於後續築底完成。"
    },
    ('Flat', 'Low', 'Up'): {
        "title": "🫧 虛浮盤整 / 零星槓桿", "risk": "中度風險", "color": "warning",
        "desc": "市場交投清淡，股價無明確方向，但融資微幅爬升。顯示市場缺乏法人關注，僅剩少量散戶用槓桿博弈，走勢易受大盤拖累。"
    },
    ('Flat', 'Low', 'Down'): {
        "title": "💤 窒息沉澱 / 完全觀望", "risk": "低風險", "color": "info",
        "desc": "量能急凍、融資持續遞減，市場陷入極度冷清。這通常是籌碼落底前夕的『窒息量』特徵，待新買盤進駐即有反彈機會。"
    },
    ('Down', 'High', 'Up'): {
        "title": "🚨 極度危險 / 融資死摳與斷頭高危區", "risk": "極高風險", "color": "error",
        "desc": "股價重挫且帶量，融資卻不減反增！代表散戶不斷逢低『攤平』接刀。若股價繼續下探，將觸發融資維持率不足，引發連環斷頭踩踏賣壓！"
    },
    ('Down', 'High', 'Down'): {
        "title": "💥 恐慌殺多 / 斷頭洗盤築底", "risk": "中度風險（迎向築底）", "color": "warning",
        "desc": "帶量下殺且融資出現暴減，代表市場出現恐慌性停損與融資斷頭潮。雖然短線陣痛劇烈，但籌碼清洗最徹底，歷史上常是中長期落底訊號。"
    },
    ('Down', 'Low', 'Up'): {
        "title": "🩸 無量陰跌 / 槓桿套牢", "risk": "高風險", "color": "error",
        "desc": "成交量低迷，股價緩步陰跌，但融資並未退場。市場缺乏接盤買盤，籌碼持續被套牢，走勢極為孱弱。"
    },
    ('Down', 'Low', 'Down'): {
        "title": "📉 順勢陰跌整理 / 靜待止跌", "risk": "中高風險", "color": "warning",
        "desc": "無量下跌且融資同步退場，屬於散戶落跑、法人觀望的自然修正期。雖然無大爆量殺多風險，但仍需等待止跌訊號出現。"
    }
}

# --- 側邊欄控制面板 ---
st.sidebar.title("⚙️ 全功能控制面板")
stock_code = st.sidebar.text_input("輸入台股代號（如 3661, 2330, 8299）：", value="3661").strip()
refresh_rate = st.sidebar.slider("即時報價更新頻率 (秒)", min_value=5, max_value=60, value=10)

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ 融資與籌碼模擬參數")
margin_trend = st.sidebar.radio("今日估計融資變化：", options=["融資增加 (散戶進場/開槓桿)", "融資減少 (籌碼沉澱/退場)"], index=1)
short_ratio_level = st.sidebar.select_slider("當前券資比程度：", options=["低 (<10%)", "中 (10%~30%)", "高 (>30% 具強烈軋空潛力)"], value="中 (10%~30%)")

st.sidebar.markdown("---")
st.sidebar.subheader("🔍 賣壓模型設定")
model_mode = st.sidebar.radio(
    "選擇模型運算模式",
    ["自動動態校正（實務回檔與量價推算）", "手動參數微調（Sliders）"]
)
if model_mode == "手動參數微調（Sliders）":
    abandonment_rate = st.sidebar.slider("高檔套牢預估拋售率 (%)", min_value=10, max_value=90, value=45, step=5) / 100
    absorbed_ratio = st.sidebar.slider("每日有效籌碼淨換手率 (%)", min_value=10, max_value=90, value=35, step=5) / 100
else:
    abandonment_rate = None
    absorbed_ratio = None

# 自選股管理
st.sidebar.markdown("---")
st.sidebar.subheader("⭐ 自選投資組合管理")
new_stock = st.sidebar.text_input("新增股票代碼:", key="new_stock_input").strip()
if st.sidebar.button("加入組合"):
    if new_stock and new_stock not in st.session_state.portfolio:
        st.session_state.portfolio.append(new_stock)
        save_portfolio(st.session_state.portfolio)
        st.rerun()

for s in st.session_state.portfolio:
    cols = st.sidebar.columns([3, 1])
    cols[0].write(s)
    if cols[1].button("❌", key=f"remove_{s}"):
        st.session_state.portfolio.remove(s)
        save_portfolio(st.session_state.portfolio)
        st.rerun()

# --- 主畫面標題 ---
st.title("📊 台股全方位動態即時、籌碼與期指結算分析儀表板")

if not stock_code:
    st.warning("請在側邊欄輸入有效的股票代碼。")
else:
    df, info_dict = get_stock_data_universal(stock_code, days_back=500)
    
    if df.empty:
        st.error(f"❌ 無法取得股票代碼 `{stock_code}` 的數據，請確認代碼是否正確。")
    else:
        stock_symbol = info_dict["symbol"]
        stock_name = info_dict["name"]
        display_name = get_stock_display_name(stock_code, stock_symbol)
        
        # 建立多功能分頁
        tab1, tab2, tab3, tab4 = st.tabs([
            "⚡ 盤中即時量價與籌碼診斷", 
            "📈 歷史結算前後表現統計", 
            "🔍 籌碼賣壓消化模型 (Days to Cover)", 
            "⭐ 自選組合即時概覽"
        ])
        
        # -------------------------------------------------------------------------
        # TAB 1: 盤中即時量價與融資籌碼綜合診斷 (來自 app.py)
        # -------------------------------------------------------------------------
        with tab1:
            st.subheader(f"🔍 當前分析標的：{display_name}")
            
            @st.fragment(run_every=refresh_rate)
            def render_realtime_section(ticker_str, historical_df):
                try:
                    rt_stock = yf.Ticker(ticker_str)
                    rt_df = rt_stock.history(period="1d", interval="1m")
                    if not rt_df.empty:
                        if isinstance(rt_df.columns, pd.MultiIndex):
                            rt_df = rt_df.droplevel(1, axis=1)
                        current_price = round(rt_df.iloc[-1]['Close'], 2)
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

                st.markdown("### ⚡ 盤中即時價量與籌碼概況")
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric(label="即時成交價", value=f"${current_price} 元", delta=f"{price_change} 元")
                kpi2.metric(label="今日累計成交量", value=f"{current_volume // 1000:,} 張" if current_volume > 1000 else f"{current_volume} 股")
                kpi3.metric(label="20日月線 (MA20)", value=f"${ma20_val} 元", delta=f"月線乖離率 {bias_ma20}%")
                
                p_trend = "Up" if current_price > prev_price else ("Down" if current_price < prev_price else "Flat")
                v_trend = "High" if current_volume >= prev_volume else "Low"
                m_trend = "Up" if "增加" in margin_trend else "Down"

                diag_key = (p_trend, v_trend, m_trend)
                diag_info = SCENARIO_MATRIX.get(diag_key, {
                    "title": "綜合評估中", "risk": "中等", "color": "info", "desc": "資料更新中..."
                })

                kpi4.metric(label="籌碼與技術診斷", value=diag_info["title"].split(' ')[1] if ' ' in diag_info["title"] else diag_info["title"], delta=f"風險評估: {diag_info['risk']}")

                # 量價比對表
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

                # 診斷矩陣區塊
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
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.markdown("#### 1. 籌碼穩定度")
                    if m_trend == "Down" and p_trend in ["Up", "Flat"]:
                        st.success("🟢 **籌碼高度安定**：融資減、股價不跌，代表浮動籌碼順利流向法人與主力大戶手上。")
                    elif m_trend == "Up" and p_trend in ["Down", "Flat"]:
                        st.error("🔴 **籌碼趨於凌亂**：融資增、股價停滯或下跌，主力正在高檔出貨。")
                    else:
                        st.info("🟡 **籌碼平衡震盪**：無極端傾斜。")
                with col_b:
                    st.markdown("#### 2. 融資斷頭風險")
                    if p_trend == "Down" and m_trend == "Up":
                        st.error("🚨 **高危斷頭預警**：股價跌但融資增，極易誘發斷頭賣壓！")
                    elif p_trend == "Down" and v_trend == "High" and m_trend == "Down":
                        st.warning("⚡ **恐慌斷頭宣洩中**：融資快速減碼，屬沉澱落底過程。")
                    else:
                        st.success("✅ **融資風險安全**：無立即斷頭危險。")
                with col_c:
                    st.markdown("#### 3. 軋空潛力")
                    if "高" in short_ratio_level and p_trend == "Up":
                        st.success("🔥 **強烈軋空機會**：高券資比搭配上漲，逼迫空頭回補！")
                    else:
                        st.info("🔹 **軋空力道平緩**：券資比處常態範圍。")

                # 操作策略建議
                st.markdown("### 三、 綜合實戰操作策略建議")
                if bias_ma20 > 15:
                    st.error(f"🚨 **策略建議：【嚴禁追高】** 離月線高達 **{bias_ma20}%** 正乖離，隨時有技術面修正引力。")
                elif bias_ma20 > 0 and bias_ma20 <= 15:
                    if m_trend == "Down":
                        st.success("🎯 **策略建議：【分批逢低布局】** 月線之上且融資退場，量縮拉回是極佳買點。")
                    else:
                        st.warning("⚖️ **策略建議：【小量試單】** 多頭架構仍在，但散戶融資偏高。")
                else:
                    if p_trend == "Down" and m_trend == "Up":
                        st.error("📉 **策略建議：【觀望避開】** 跌破月線且融資逆勢增加，切勿接刀。")
                    else:
                        st.info("📉 **策略建議：【等待築底訊號】** 建議耐心等待量縮與融資大減。")

                st.caption(f"🔄 自動更新中 (頻率: {refresh_rate}s) 最新同步時間：{datetime.datetime.now().strftime('%H:%M:%S')}")

            render_realtime_section(stock_symbol, df)

            st.markdown("---")
            st.markdown("### 📈 歷史 K 線與中長期均線走勢圖")
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='日K線'))
            fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='orange', width=1.5), name='5日線'))
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='magenta', width=2), name='月線(20MA)'))
            fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='cyan', width=2), name='季線(60MA)'))
            fig.update_layout(xaxis_rangeslider_visible=False, height=450, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)

        # -------------------------------------------------------------------------
        # TAB 2: 歷史結算前後表現統計 (來自 appA.py)
        # -------------------------------------------------------------------------
        with tab2:
            st.subheader(f"📊 [{display_name}] 過去 12 個月結算日 (T) 至 結算後一週 (T+5) 歷史表現")
            
            today = datetime.date.today()
            current_settlement = get_third_wednesday(today.year, today.month)
            if today > current_settlement:
                base_year, base_month = today.year, today.month
            else:
                first_of_month = datetime.date(today.year, today.month, 1)
                prev_month = first_of_month - datetime.timedelta(days=1)
                base_year, base_month = prev_month.year, prev_month.month

            settlement_dates = []
            y, m = base_year, base_month
            for _ in range(12):
                settlement_dates.append(get_third_wednesday(y, m))
                y, m = (y - 1, 12) if m == 1 else (y, m - 1)
            settlement_dates.reverse()

            records = []
            pct_changes = []

            for s_date in settlement_dates:
                t0_date, t0_price, _ = get_trading_day_offset(df, s_date, 0)
                tm5_date, tm5_price, _ = get_trading_day_offset(df, s_date, -5)
                tm1_date, tm1_price, _ = get_trading_day_offset(df, s_date, -1)
                tp1_date, tp1_price, _ = get_trading_day_offset(df, s_date, 1)
                tp5_date, tp5_price, _ = get_trading_day_offset(df, s_date, 5)

                chg_pct = None
                if t0_price and tp5_price:
                    chg_pct = round(((tp5_price - t0_price) / t0_price) * 100, 2)
                    pct_changes.append(chg_pct)

                records.append({
                    "結算月份": f"{s_date.year}/{s_date.month:02d}",
                    "結算日(T)": t0_date,
                    "前一週(T-5)": tm5_price,
                    "結算前日(T-1)": tm1_price,
                    "結算當日(T)": t0_price,
                    "結算後日(T+1)": tp1_price,
                    "後一週(T+5)": tp5_price,
                    "結算後一週漲跌幅(%)": chg_pct
                })

            df_result = pd.DataFrame(records)
            latest_close = float(df.iloc[-1]['Close'])
            latest_date = df.index[-1].date()

            avg_change = sum(pct_changes) / len(pct_changes) if pct_changes else 0
            win_rate = (sum(1 for x in pct_changes if x > 0) / len(pct_changes)) * 100 if pct_changes else 0
            est_price_avg = round(latest_close * (1 + avg_change / 100), 2)

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("最新收盤價", f"{latest_close:.2f} 元", f"日期: {latest_date}")
            kpi2.metric("結算後一週平均漲跌幅", f"{avg_change:+.2f}%")
            kpi3.metric("結算後一週上漲勝率", f"{win_rate:.1f}%")
            kpi4.metric("預估結算後目標均值", f"{est_price_avg:.2f} 元")

            st.markdown("---")
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                x=df_result['結算月份'],
                y=df_result['結算後一週漲跌幅(%)'],
                name='T → T+5 漲跌幅 (%)',
                marker_color=['#2ecc71' if v is not None and v > 0 else '#e74c3c' for v in df_result['結算後一週漲跌幅(%)']]
            ))
            fig_bar.update_layout(title="過去 12 個月每月結算後一週績效 (%)", yaxis_title="漲跌幅 (%)", template="plotly_white")
            st.plotly_chart(fig_bar, use_container_width=True)

            st.subheader("📋 歷年結算前後股價明細表")
            st.dataframe(df_result, use_container_width=True)

        # -------------------------------------------------------------------------
        # TAB 3: 籌碼賣壓消化時間 (Days to Cover) 模型 (來自 appA.py)
        # -------------------------------------------------------------------------
        with tab3:
            st.subheader(f"🔍 [{display_name}] 籌碼集中度與賣壓消化時間（Days to Cover）模型")
            
            recent_20 = df.tail(20)
            high_price = float(recent_20['Close'].max())
            low_price = float(recent_20['Close'].min())
            max_drawdown_pct = ((high_price - latest_close) / high_price) * 100
            
            if model_mode == "自動動態校正（實務回檔與量價推算）":
                curr_abandonment = min(0.65, max(0.20, max_drawdown_pct / 30.0))
                avg_vol = recent_20['Volume'].mean()
                recent_vol_std = recent_20['Volume'].std()
                vol_spike_ratio = recent_vol_std / avg_vol if avg_vol > 0 else 1.0
                curr_absorbed = max(0.25, min(0.50, 0.45 - (vol_spike_ratio * 0.05)))
            else:
                curr_abandonment = abandonment_rate
                curr_absorbed = absorbed_ratio
            
            threshold_price = low_price + (high_price - low_price) * 0.6
            high_volume_data = recent_20[recent_20['Close'] >= threshold_price]
            total_high_volume = float(high_volume_data['Volume'].sum())
            avg_daily_volume = float(recent_20['Volume'].mean())

            estimated_overhang_shares = total_high_volume * curr_abandonment
            daily_absorbed_shares = avg_daily_volume * curr_absorbed

            if daily_absorbed_shares > 0:
                days_to_cover = estimated_overhang_shares / daily_absorbed_shares
                target_cleared_date = datetime.date.today()
                added_days = 0
                while added_days < round(days_to_cover):
                    target_cleared_date += datetime.timedelta(days=1)
                    if target_cleared_date.weekday() < 5:
                        added_days += 1

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("近高點最大回檔幅度", f"-{max_drawdown_pct:.1f}%")
                m2.metric("套牢預估拋售率", f"{curr_abandonment*100:.1f}%")
                m3.metric("有效換手率", f"{curr_absorbed*100:.1f}%")
                m4.metric("賣壓消化所需時間", f"{days_to_cover:.1f} 個交易日", f"預計沉澱日: {target_cleared_date}")

                st.markdown("---")
                c1, c2 = st.columns(2)
                with c1:
                    st.info(f"""
                    **模型詳細拆解**：
                    * **高檔套牢累積量**：約 `{int(total_high_volume/1000):,} 張`
                    * **預估實際拋售量**：約 `{int(estimated_overhang_shares/1000):,} 張`
                    * **每日真實沉澱買盤**：約 `{int(daily_absorbed_shares/1000):,} 張/天`
                    """)
                with c2:
                    st.success(f"""
                    **操作建議結論**：
                    依據當前量價與回檔深度模型推算，**{display_name}** 的解套賣壓預計在 **{target_cleared_date.strftime('%Y-%m-%d')}** 附近沉澱完畢。建議在賣壓消化完成前採取分批低接或量縮打底時再行佈局。
                    """)

                st.markdown("#### 近 20 交易日價格與成交量分佈 (Volume Profile)")
                fig_vol = px.bar(recent_20, x=recent_20.index, y='Volume', title="近 20 交易日成交量變化圖", labels={'Volume': '成交量', 'index': '日期'})
                st.plotly_chart(fig_vol, use_container_width=True)
            else:
                st.warning("成交量數據不足，無法計算賣壓模型。")

        # -------------------------------------------------------------------------
        # TAB 4: 自選組合即時概覽 (來自 app.py)
        # -------------------------------------------------------------------------
        with tab4:
            st.subheader("⭐ 自選組合即時與籌碼概覽")
            if not st.session_state.portfolio:
                st.info("目前自選組合為空，請從側邊欄加入股票。")
            else:
                @st.fragment(run_every=refresh_rate)
                def render_portfolio_overview():
                    portfolio_results = []
                    for code in st.session_state.portfolio:
                        try:
                            p_df, p_info = get_stock_data_universal(code, days_back=5)
                            if not p_df.empty:
                                curr_p = round(p_df.iloc[-1]['Close'], 2)
                                prev_p = round(p_df.iloc[-2]['Close'], 2) if len(p_df) > 1 else curr_p
                                chg = round(curr_p - prev_p, 2)
                                chg_pct = round((chg / prev_p) * 100, 2) if prev_p != 0 else 0
                                vol = int(p_df.iloc[-1]['Volume'])

                                portfolio_results.append({
                                    "代碼": code,
                                    "名稱": p_info.get("name", code),
                                    "現價": f"${curr_p}",
                                    "漲跌": f"{chg} ({chg_pct}%)",
                                    "成交量": f"{vol // 1000:,} 張" if vol > 1000 else f"{vol} 股",
                                    "盤面狀態": "多頭攻勢" if chg > 0 else ("壓回整理" if chg < 0 else "平盤觀望")
                                })
                            else:
                                portfolio_results.append({
                                    "代碼": code, "名稱": "N/A", "現價": "N/A", "漲跌": "N/A", "成交量": "N/A", "盤面狀態": "無數據"
                                })
                        except:
                            portfolio_results.append({
                                "代碼": code, "名稱": "Error", "現價": "Error", "漲跌": "Error", "成交量": "Error", "盤面狀態": "讀取失敗"
                            })

                    st.table(pd.DataFrame(portfolio_results))
                    st.caption(f"🔄 自選組合自動更新中... (頻率: {refresh_rate}s) 最新同步時間：{datetime.datetime.now().strftime('%H:%M:%S')}")

                render_portfolio_overview()