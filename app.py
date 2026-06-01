import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import plotly.graph_objects as go

# 設定網頁標題與佈局
st.set_page_config(page_title="台股量價動態分析儀表板", layout="wide")

st.title("📊 台股上市櫃股票 - 量價籌碼動態分析儀表板")
st.markdown("根據即時市場數據，自動生成量價對比、籌碼解析與進場綜合評估。")

# 側邊欄：使用者輸入代碼
st.sidebar.header("輸入參數")
stock_code = st.sidebar.text_input("請輸入台股代碼（例如：6239 或 2330）：", value="6239").strip()

if stock_code:
    # 處理台股代碼格式 (上市與上櫃在 yfinance 後綴多為 .TW 或 .TWO，此處統一嘗試常見的 .TW，若無數據再試 .TWO)
    ticker_symbol = f"{stock_code}.TW"
    
    with st.spinner('正在讀取 Yahoo Finance 即時市場數據...'):
        try:
            # 抓取最近 3 個月的歷史數據以計算月線與天量
            end_date = datetime.datetime.now()
            start_date = end_date - datetime.timedelta(days=90)
            
            stock = yf.Ticker(ticker_symbol)
            df = stock.history(start=start_date, end=end_date)
            
            # 如果 .TW 沒資料，嘗試 .TWO (上櫃)
            if df.empty:
                ticker_symbol = f"{stock_code}.TWO"
                stock = yf.Ticker(ticker_symbol)
                df = stock.history(start=start_date, end=end_date)
                
            if df.empty:
                st.error(f"找不到代碼 {stock_code} 的數據，請檢查代碼是否正確。")
            else:
                # 獲取基本資訊
                stock_info = stock.info
                stock_name = stock_info.get('longName', stock_info.get('shortName', f"台股 {stock_code}"))
                
                # 計算關鍵技術指標
                df['MA5'] = df['Close'].rolling(window=5).mean()
                df['MA20'] = df['Close'].rolling(window=20).mean()
                df['MA60'] = df['Close'].rolling(window=60).mean()
                
                # 取得最新交易日（今日）與前一日數據
                latest_data = df.iloc[-1]
                prev_data = df.iloc[-2] if len(df) > 1 else latest_data
                
                # 尋找過去一段時間的波段天量
                max_volume_row = df.loc[df['Volume'].idxmax()]
                
                # 提取關鍵變數
                today_price = round(latest_data['Close'], 2)
                today_volume = int(latest_data['Volume'])
                prev_price = round(prev_data['Close'], 2)
                prev_volume = int(prev_data['Volume'])
                
                ma5_val = round(latest_data['MA5'], 2) if not pd.isna(latest_data['MA5']) else "計算中"
                ma20_val = round(latest_data['MA20'], 2) if not pd.isna(latest_data['MA20']) else "計算中"
                ma60_val = round(latest_data['MA60'], 2) if not pd.isna(latest_data['MA60']) else "計算中"
                
                max_vol = int(max_volume_row['Volume'])
                max_vol_date = max_volume_row.name.strftime('%Y-%m-%d')
                max_vol_price = round(max_volume_row['Close'], 2)
                
                # 計算乖離率
                bias_ma20 = round(((today_price - latest_data['MA20']) / latest_data['MA20']) * 100, 2) if not pd.isna(latest_data['MA20']) else 0
                
                # 顯示個股抬頭
                st.subheader(f"🔍 當前分析標的：{stock_code} {stock_name}")
                
                # 頂部 KPI 卡片
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric(label="今日收盤/最新價", value=f"${today_price} 元", delta=f"{round(today_price - prev_price, 2)} 元")
                kpi2.metric(label="今日成交量", value=f"{today_volume:,} 張" if today_volume > 1000 else f"{today_volume} 股")
                kpi3.metric(label="20日平均線 (月線)", value=f"${ma20_val} 元", delta=f"正乖離 {bias_ma20}%" if bias_ma20 > 0 else f"負乖離 {bias_ma20}%")
                kpi4.metric(label="波段最高天量", value=f"{max_vol:,} 張" if max_vol > 1000 else f"{max_vol} 股", delta=f"日期: {max_vol_date}")
                
                # K線與成交量圖表
                st.markdown("### 📈 近期K線與均線走勢圖")
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線'))
                if not isinstance(ma5_val, str): fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], line=dict(color='orange', width=1.5), name='5日線'))
                if not isinstance(ma20_val, str): fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='magenta', width=2), name='月線(20MA)'))
                if not isinstance(ma60_val, str): fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='cyan', width=2), name='季線(60MA)'))
                fig.update_layout(xaxis_rangeslider_visible=False, height=400, margin=dict(l=20, r=20, t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("---")
                
                # 一、 量價關係對比彙總表
                st.markdown("### 一、 量價關係對比彙總表")
                
                summary_data = {
                    "日期/項目": ["波段最高天量日", "前一交易日", "今日即時/結算"],
                    "股價位置": [f"${max_vol_price} 元", f"${prev_price} 元", f"${today_price} 元"],
                    "成交量 (張/股)": [f"{max_vol:,}", f"{prev_volume:,}", f"{today_volume:,}"],
                    "盤面技術與籌碼意涵": [
                        f"爆出近期歷史天量（{max_vol_date}），屬於多空劇烈震盪或主力強攻換手區。",
                        "前一日量能狀態，作為今日量能是否萎縮的對比基準。",
                        "當前最新盤面交易結果，呈現最新多空表態。"
                    ]
                }
                st.table(pd.DataFrame(summary_data))
                
                st.markdown("---")
                
                # 二、 今日「量縮」的籌碼面與操作解析
                st.markdown("### 二、 今日「量縮」的籌碼面與操作解析")
                
                # 動態判斷量縮邏輯
                is_vol_shrunk_prev = today_volume < prev_volume
                is_vol_shrunk_max = today_volume < (max_vol * 0.4) # 小於天量的40%定義為極度萎縮
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("#### 🔄 量能對比現況")
                    if is_vol_shrunk_prev:
                        st.success(f"✅ **今日成交量較前一日減少**：今日 {today_volume:,} 對比昨日 {prev_volume:,}，量能出現萎縮。")
                    else:
                        st.warning(f"⚠️ **今日成交量較前一日放大**：今日 {today_volume:,} 對比昨日 {prev_volume:,}，短線動能仍在釋放。")
                        
                    if is_vol_shrunk_max:
                        st.info(f"❄️ **量能極度急凍**：當前量能已不及波段最高天量（{max_vol:,}）的四成，短線熱錢、當沖與隔日沖資金出現明顯撤離跡象。")
                
                with col2:
                    st.markdown("#### 🧠 籌碼面解讀說明")
                    if today_price >= prev_price and is_vol_shrunk_prev:
                        st.markdown("> **量縮橫盤/小漲：** 顯示高檔追高意願雖然降低，但也**沒有恐慌性賣壓**（良性量縮）。持股信心尚存，籌碼正處於高檔換手後的沈澱期。")
                    elif today_price < prev_price and is_vol_shrunk_prev:
                        st.markdown("> **量縮下跌：** 屬於多頭架構下的良性拉回。技術面「掉下來的刀子」尚未爆量踩踏，代表主力並未在此處不計代價出貨，純屬買盤縮手的修正。")
                    else:
                        st.markdown("> **帶量震盪：** 盤面震盪幅度與量能同步放大，多空雙方在此價格區間仍有分歧，籌碼尚未完全沈澱。")

                st.markdown("---")

                # 三、 綜合結論：今天適合進場嗎？
                st.markdown("### 三、 綜合結論：今天適合進場嗎？")
                
                # 核心分析邏輯判斷
                if bias_ma20 > 15:
                    conclusion_text = f"""
                    🚨 **策略建議：目前「極度不適合」盲目追高，請保持「準備進場」的耐心。**
                    
                    * **原因分析：** 目前最新股價（${today_price}元）距離下方的月線平均價（${ma20_val}元）存在高達 **{bias_ma20}%** 的**巨大正乖離**。
                    * **技術慣性：** 股價在技術面上離移動平均線太遠，隨時會因為獲利回吐賣壓而引發向月線「靠攏」的修正引力。即使今日量縮，也只是懸浮在高空「漲不動、也跌不深」。
                    * **最佳操作：** 資金按兵不動。建議「以盤代跌」或「小幅緩跌」讓高檔股價去等待月線慢慢靠攏，等乖離率修正到 5-10% 以內且量能持續低迷時，才是高勝率買點。
                    """
                    st.error(conclusion_text)
                elif bias_ma20 > 0 and bias_ma20 <= 15:
                    conclusion_text = f"""
                    ⚖️ **策略建議：適合「小量試單」或「分批逢低布局」，風險相對可控。**
                    
                    * **原因分析：** 股價（${today_price}元）在月線（${ma20_val}元）之上，維持多頭架構。且正乖離率（{bias_ma20}%）已修正至相對合理的安全範圍。
                    * **技術慣性：** 配合今日的量縮，顯示短線賣壓已經逐步出清。股價回測短期均線（5日線或10日線）若能踩穩，是技術面上標準的「拉回找買點」。
                    * **最佳操作：** 適合先投入 10-20% 的測試資金。不需要一把買滿，保留資金等股價確立止跌紅K出現時再加碼。
                    """
                    st.warning(conclusion_text)
                else:
                    conclusion_text = f"""
                    📉 **策略建議：股價已跌破月線，需等待「左側量縮止穩」或「右側重回月線」訊號。**
                    
                    * **原因分析：** 目前股價（${today_price}元）低於月線平均價（${ma20_val}元），短線趨勢偏弱或正處於中線修正期。
                    * **最佳操作：** 不要一看到跌就盲目伸手接刀。建議等待成交量出現連續 2-3 天的「極度窒息量」，或者股價帶量重新站回月線上方時，才是中波段的安全切入點。
                    """
                    st.info(conclusion_text)
                    
            st.caption(f"數據更新時間：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 本分析完全基於量價指標模型動態產出，不構成實質投資建議。")
            
        except Exception as e:
            st.error(f"讀取數據時發生錯誤：{str(e)}。請確認網路連線或換個代碼試試看。")
