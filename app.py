import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import stock_advisor
import concurrent.futures
import importlib

# Ensure stock_advisor is reloaded to reflect changes
# Ensure stock_advisor is reloaded to reflect changes
importlib.reload(stock_advisor) # Reload is necessary for logic updates

# 1. 페이지 설정 (반드시 가장 먼저 호출)
st.set_page_config(
    page_title="Weekly Signal 주식 분석기",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="collapsed" # Mobile optimization
)

# ------------------------------------------------------------------
# [Fix] Restore KOREAN_TICKER_MAP from session_state if available
# This ensures that names found in the bulk analysis (rec_data) are
# recognized even if the module was reloaded or connection reset.
# ------------------------------------------------------------------
if "rec_data" in st.session_state and st.session_state.rec_data:
    for market, stocks in st.session_state.rec_data.items():
        for s in stocks:
            stock_advisor.KOREAN_TICKER_MAP[s['name']] = s['ticker']


# 2. 스타일 커스텀 (Light Theme & Toss Style)
st.markdown("""
    <style>
    /* 전체 배경 및 폰트 */
    .stApp {
        background-color: #f9fafb; /* Light Gray Background */
        color: #333333;
    }
    
    /* 헤더 스타일 */
    .main-header {
        font-size: 32px; 
        font-weight: 800;
        color: #333d4b; /* Dark Navy/Gray */
        margin-bottom: 20px;
    }
    
    /* 카드 스타일 (Stock List Item) */
    .stock-card {
        background-color: white;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        padding: 15px;
        margin-bottom: 10px;
        transition: transform 0.2s;
        cursor: pointer;
        border: 1px solid #e5e8eb;
    }
    .stock-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        border-color: #333d4b;
    }
    
    /* 상세 정보 카드 */
    .info-card {
        background-color: white;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        margin-bottom: 20px;
        border: 1px solid #e5e8eb;
    }
    
    /* 점수 텍스트 강조 */
    .score-text {
        font-size: 16px;
        font-weight: bold;
    }
    .score-high { color: #dc3545; } /* High Score Red */
    .score-mid { color: #333d4b; }
    
    /* 버튼 스타일 오버라이드 (Mobile Touch Friendly) */
    .stButton button {
        border-radius: 8px;
        font-weight: 600;
        border: none;
        background-color: #f2f4f6;
        color: #333d4b;
        padding: 12px 20px; /* Larger touch target */
        margin-bottom: 8px; /* Spacing between list items */
    }
    .stButton button:hover {
        background-color: #e5e8eb;
        color: #333d4b;
    }

    /* AI 관심도 카드 스타일 */
    .interest-card {
        background-color: #f0f7ff; /* Light Blue */
        border: 2px solid #3b77ff;
        border-radius: 12px;
        padding: 15px;
        text-align: center;
        margin-top: 10px;
        margin-bottom: 10px;
    }
    .interest-title {
        font-size: 14px;
        color: #333d4b;
        font-weight: bold;
        margin-bottom: 5px;
    }
    .interest-score {
        font-size: 24px;
        color: #3b77ff;
        font-weight: 900;
    }
    .interest-grade {
        font-size: 14px;
        color: #555;
    }
    </style>
    """, unsafe_allow_html=True)

# 3. Helper Functions (분석 로직)

@st.cache_data(ttl=3600)
def analyze_single_stock(ticker, version=14): # version=14 Exact Match Interest Logic
    try:
        df = stock_advisor.get_stock_data(ticker)
        if df is not None:
            return stock_advisor.analyze_stock(ticker, df)
    except:
        pass
    return None

def analyze_all_concurrently(progress_bar=None, status_text=None):
    # 대상 종목 수집
    kospi_tickers = stock_advisor.get_top_stocks("KOSPI", 100)
    kosdaq_tickers = stock_advisor.get_top_stocks("KOSDAQ", 50)
    nasdaq_tickers = stock_advisor.get_top_stocks("NASDAQ", 100)
    
    all_tickers = kospi_tickers + kosdaq_tickers + nasdaq_tickers
    total_tickers = len(all_tickers)
    
    results_map = {} # ticker -> result
    completed_count = 0
    
    if status_text:
        status_text.caption(f"전체 {total_tickers}개 종목 분석 중... (잠시만 기다려주세요)")
        
    # Reduce workers to avoid rate limiting
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_to_ticker = {executor.submit(analyze_single_stock, ticker): ticker for ticker in all_tickers}
        
        for future in concurrent.futures.as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                data = future.result()
                if data:
                    results_map[ticker] = data
            except Exception as e:
                pass
                
            completed_count += 1
            if progress_bar:
                progress_bar.progress(completed_count / total_tickers)
            if status_text:
                status_text.caption(f"분석 중... ({completed_count}/{total_tickers})")

    # 결과 분류
    kospi_recs = []
    kosdaq_recs = []
    nasdaq_recs = []
    
    def create_rec_list(source_tickers, dest_list):
        for ticker in source_tickers:
            if ticker in results_map:
                res = results_map[ticker]
                # 필터 기준 완화: 점수 60점 이상 또는 매수/보유 신호(1 이상) 있는 종목
                if res['score'] >= 60 or res['signal_strength'] >= 1:
                    stock_name = ticker
                    for name, code in stock_advisor.KOREAN_TICKER_MAP.items():
                        if code == ticker:
                            stock_name = name
                            break
                    dest_list.append({
                        'name': stock_name,
                        'ticker': ticker,
                        'score': res['score'],
                        'current_price': res['current_price']
                    })
        dest_list.sort(key=lambda x: x['score'], reverse=True)

    create_rec_list(kospi_tickers, kospi_recs)
    create_rec_list(kosdaq_tickers, kosdaq_recs)
    create_rec_list(nasdaq_tickers, nasdaq_recs)
    
    return {'KOSPI': kospi_recs, 'KOSDAQ': kosdaq_recs, 'NASDAQ': nasdaq_recs}


# 4. 메인 레이아웃 및 로직

# 레이아웃 분할 (1:2.5 비율)
left_col, right_col = st.columns([1, 2.5])

# ------------------------------------------------------------------
# [Left Column] 종목 검색 및 리스트
# ------------------------------------------------------------------
with left_col:
    c_home_1, c_home_2 = st.columns([3, 1])
    with c_home_1: st.markdown("### 🔍 종목 탐색")
    with c_home_2:
        if st.button("🏠", help="홈으로 이동"):
            st.session_state.search_input = ""
            st.session_state.search_box = ""
            st.rerun()
    
    # 검색창
    if "search_input" not in st.session_state:
        st.session_state.search_input = ""
        
    # on_change 콜백 사용을 위해 key 할당
    user_input = st.text_input("종목명/티커 검색", placeholder="삼성전자, TSLA...", key="search_box", 
                               value=st.session_state.search_input)
    
    # 사용자가 입력한 내용을 session_state.search_input와 동기화
    if user_input != st.session_state.search_input:
        st.session_state.search_input = user_input
        st.rerun()

    st.markdown("---")
    
    # 추천 종목 로드 로직
    if "rec_data" not in st.session_state:
        st.session_state.rec_data = None

    if st.button("🚀 전체 종목 분석 업데이트", use_container_width=True):
        status_text = st.empty()
        progress_bar = st.progress(0)
        
        try:
            st.session_state.rec_data = analyze_all_concurrently(progress_bar, status_text)
            status_text.success("분석 완료!")
        except Exception as e:
            status_text.error(f"Error: {e}")
            
    st.markdown("#### 🔥 실시간 분석 순위")
    
    if st.session_state.rec_data:
        # 탭으로 시장 구분
        tab1, tab2, tab3 = st.tabs(["KOSPI", "KOSDAQ", "NASDAQ"])
        
        def update_search_state(new_name):
            st.session_state.search_input = new_name
            st.session_state.search_box = new_name

        def display_stock_list(market_key):
            stocks = st.session_state.rec_data.get(market_key, [])
            if not stocks:
                st.info("추천 종목이 없습니다.")
                return
            
            # [Logic] Top 20 + Ties
            # 1. Determine cutoff score (score of 20th item)
            limit = 20
            cutoff_score = -1
            
            if len(stocks) > limit:
                cutoff_score = stocks[limit-1]['score']
            
            count = 0
            for i, stock in enumerate(stocks):
                # If we passed rank 20 and the score is lower than cutoff, stop
                if i >= limit and stock['score'] < cutoff_score:
                    break
                    
                score = stock['score']
                emoji = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}위"
                
                # 버튼 클릭 시 search_input 업데이트 (Callback 사용)
                btn_label = f"{emoji} {stock['name']}  |  {score}점"
                st.button(btn_label, key=f"btn_{market_key}_{stock['ticker']}", 
                          use_container_width=True,
                          on_click=update_search_state,
                          args=(stock['name'],))
                count += 1
                
            if len(stocks) > count:
                st.caption(f"외 {len(stocks) - count}개 종목 생략됨...")

        with tab1: display_stock_list('KOSPI')
        with tab2: display_stock_list('KOSDAQ')
        with tab3: display_stock_list('NASDAQ')
    else:
        st.caption("버튼을 눌러 분석을 시작하세요.")


# ------------------------------------------------------------------
# [Right Column] 상세 분석 대시보드
# ------------------------------------------------------------------
with right_col:
    # 헤더
    st.markdown('<div class="main-header">🐶 반려주식 종합 건강검진</div>', unsafe_allow_html=True)

    target_ticker = st.session_state.search_input
    
    if target_ticker:
        # 티커 변환
        if target_ticker in stock_advisor.KOREAN_TICKER_MAP:
            ticker = stock_advisor.KOREAN_TICKER_MAP[target_ticker]
        else:
            ticker = target_ticker.upper()

        # 데이터 분석 실행
        with st.spinner(f"'{ticker}' 분석 중..."):
            df = stock_advisor.get_stock_data(ticker)

        if df is not None:
            result = stock_advisor.analyze_stock(ticker, df)
            
            # --- 상단 메트릭 카드 영역 ---
            with st.container():
                st.markdown('<div class="info-card">', unsafe_allow_html=True)
                
                # 차트 제목용 종목명
                chart_name = ticker
                for name, code in stock_advisor.KOREAN_TICKER_MAP.items():
                    if code == ticker:
                        chart_name = name
                        break
                
                # [Mobile Optimized] Header Layout
                # Stack Title, Price, Score naturally on mobile, side-by-side on desktop
                top_c1, top_c2 = st.columns([2, 1])
                
                with top_c1:
                   st.markdown(f"## {chart_name}")
                   st.caption(f"Code: {ticker}")
                   
                with top_c2:
                   # Use HTML for better control over alignment
                   st.markdown(f"""
                   <div style="text-align: right;">
                       <span style="font-size: 14px; color: gray;">현재가</span><br>
                       <span style="font-size: 24px; font-weight: bold;">{result['current_price']:,.0f}원</span>
                   </div>
                   <div style="text-align: right; margin-top: 5px;">
                        <span style="font-size: 14px; color: gray;">종합 점수</span><br>
                        <span style="font-size: 28px; font-weight: 900; color: #3b77ff;">{result['score']}점</span>
                   </div>
                   """, unsafe_allow_html=True)
                
                st.divider()
                
                # 2열: 상세 지표 (기술적)
                d_col1, d_col2, d_col3, d_col4 = st.columns(4)
                with d_col1:
                    trend_icon = "📈" if result['is_ema_uptrend'] else "📉"
                    st.metric("추세 (30주)", trend_icon)
                with d_col2:
                    st.metric("이격도", f"{result['disparity']:.1f}%")
                with d_col3:
                    stage_info = result['stage_info']
                    st.markdown(f"**상태**<br><span style='color:{stage_info['color']}'>{stage_info['emoji']} {stage_info['stage']}</span><br><span style='font-size:12px; color:gray'>({stage_info['desc']})</span>", unsafe_allow_html=True)
                with d_col4:
                    # Recommendation Styling (Strong Buy 추가)
                    rec_color = "gray"
                    if result['signal_strength'] == 3:
                        rec_color = "#8854d0" # Purple for Strong Buy
                    elif result['signal_strength'] == 2:
                        rec_color = "#e23f3f" # Red for Buy
                    elif result['signal_strength'] == -1:
                        rec_color = "#3b77ff" # Blue for Sell
                        
                    st.markdown(f"**제안**<br><span style='color:{rec_color}; font-weight:bold'>{result['recommendation']}</span>", unsafe_allow_html=True)
                
                # 3열: 심화 분석 지표 (VCP & Fundamentals)
                st.divider()
                f_col1, f_col2, f_col3 = st.columns(3)
                
                # 안전한 키 접근을 위해 .get() 사용 (캐시된 구버전 데이터 호환)
                is_vcp = result.get('is_vcp', False)
                eps_growth = result.get('eps_growth', 0)
                is_leader = result.get('is_leader', False)
                
                # 3열: 점수 세부 분석 (Breakdown)
                st.divider()
                st.markdown("##### 📊 종합 점수 분석 (Total 100점)")
                
                sb = result.get('score_breakdown', {'trend':0, 'fundamental':0, 'timing':0})
                
                # 1. 실적 (Fundamental)
                with st.container():
                     c1, c2 = st.columns([1, 4])
                     with c1: st.markdown("**💰 실적 (30)**")
                     with c2: 
                        st.progress(min(100, int(sb['fundamental'] / 30 * 100)), text=f"{sb['fundamental']}점 / 30점")
                        if 'fundamental_grade' in result and result['fundamental_grade']:
                             st.caption(f"{result['fundamental_grade']}")
                
                st.markdown("---")
                
                # 2. 추세 (Trend)
                with st.container():
                    c1, c2 = st.columns([1, 4])
                    with c1: st.markdown("**📈 추세 (40)**")
                    with c2: 
                        st.progress(min(100, int(sb['trend'] / 40 * 100)), text=f"{sb['trend']}점 / 40점")
                        if 'trend_grade' in result and result['trend_grade']:
                            st.caption(f"{result['trend_grade']}")

                st.markdown("---")
                
                # 3. AI 관심도 (Interest)
                st.markdown('<div class="interest-card">', unsafe_allow_html=True)
                
                interest_score = sb.get('interest', 0)
                grade_text = result.get('interest_grade', '데이터 없음')
                
                # Title
                st.markdown(f'<div class="interest-title">🤖 AI 관심도 (30점 만점)</div>', unsafe_allow_html=True)
                
                # Split Score and Desc to avoid overlap
                # Use st.columns inside the card if needed, or just block divs
                st.markdown(f'''
                    <div style="margin-top: 10px; margin-bottom: 5px;">
                        <span class="interest-score">{interest_score}점</span>
                    </div>
                    <div style="margin-bottom: 10px;">
                        <span class="interest-grade">{grade_text}</span>
                    </div>
                ''', unsafe_allow_html=True)
                
                # Progress bar
                st.progress(min(100, int(interest_score / 30 * 100)))
                st.markdown('</div>', unsafe_allow_html=True)

                st.markdown('</div>', unsafe_allow_html=True)

            # --- 차트 영역 ---
            st.markdown('<div class="info-card">', unsafe_allow_html=True)
            
            # 차트 생성 (Plotly White Theme)
            candlestick = go.Candlestick(
                x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                name="Price", increasing_line_color='#e23f3f', decreasing_line_color='#3b77ff' # 한국형 빨강/파랑
            )
            ema_line = go.Scatter(
                x=df.index, y=df['EMA_30'], mode='lines', name='30w EMA',
                line=dict(color='#ff9f43', width=2)
            )
            
            # Score Line (Right Axis)
            marker_colors = ['#FF4500' if s >= 80 else '#9370DB' for s in df['Score']]
            marker_sizes = [10 if s >= 80 else 6 for s in df['Score']]
            
            score_line = go.Scatter(
                x=df.index, y=df['Score'], mode='lines+markers', name='Score', yaxis='y2',
                line=dict(color='#9c88ff', width=2, dash='solid'),
                marker=dict(size=marker_sizes, color=marker_colors, symbol='circle', line=dict(width=1, color='white'), opacity=0.5)
            )
            
            fig = go.Figure(data=[candlestick, ema_line, score_line])
            fig.update_layout(
                title_text="", # Explicitly set empty string to avoid 'undefined'
                yaxis_title="주가 (KRW)", 
                height=500,
                margin=dict(l=20, r=20, t=20, b=20),
                template="plotly_white", # Light Theme
                xaxis_rangeslider_visible=False,
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1, xanchor="right", x=1),
                yaxis=dict(showgrid=True, gridcolor='#f1f3f5'),
                yaxis2=dict(
                    title_text="", # Empty string for secondary axis title
                    overlaying='y', side='right', range=[0, 100], showgrid=False
                )
            )
            st.plotly_chart(fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            # --- 상세 분석 텍스트 ---
            with st.expander("📝 상세 분석 리포트 확인하기", expanded=True):
                 for detail in result['details']:
                    st.write(f"- {detail}")

        else:
            if ticker:
                st.error("데이터를 찾을 수 없습니다. (미국 주식은 영문 티커(예: PLTR)로 검색해 보세요)")
    else:
        # 초기 화면 (검색 전)
        st.info("👈 왼쪽에서 종목을 검색하거나 추천 리스트를 확인하세요.")
        st.markdown("""
        <div class="info-card">
            <h3>🐶 반려주식 감별 기준 (Total 100점)</h3>
            <p>전설적인 투자 대가들의 기준과 최신 AI 데이터를 통합하여 평가합니다.</p>
            <br>
            <ul>
                <li><strong>💰 실적 (30점)</strong>: 돈 잘 버는 우량한 기업인가? (EPS/수익성)</li>
                <li><strong>📈 추세 (40점)</strong>: 강력한 상승 추세에 올라탔는가? (30주선/정배열)</li>
                <li><strong>🤖 AI 관심도 (30점)</strong>: 시장과 AI가 주목하는 종목인가? (언급량)</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
