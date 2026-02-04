import yfinance as yf
import pandas as pd
import sys
from datetime import datetime

import json
import os

# 관심도 데이터 로드 (JSON)
def load_interest_data():
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, 'interest_data.json')
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load interest_data.json: {e}")
    return {}

MENTION_COUNTS = load_interest_data()

def get_stock_data(ticker):
    """
    yfinance를 사용하여 주식 데이터를 가져오고 주봉(Weekly)으로 변환합니다.
    """
    print(f"\n[{ticker}] 데이터 수집 중...")
    try:
        # 최근 2년치 데이터 가져오기 (30주 이동평균 계산을 위해 충분한 기간 필요)
        stock = yf.Ticker(ticker)
        df = stock.history(period="2y")
        
        if df.empty:
            print(f"Error: {ticker}에 대한 데이터를 찾을 수 없습니다. 티커를 확인해주세요.")
            return None

        # 주봉(Weekly)으로 리샘플링 (금요일 기준)
        # 'W-FRI'는 매주 금요일을 끝으로 하는 주봉
        weekly_df = df.resample('W-FRI').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        })
        
        # 데이터가 없는 주 제거
        weekly_df.dropna(inplace=True)
        
        if len(weekly_df) < 30:
            print(f"[주의] 데이터 부족: 30주 이동평균을 계산하기 위해 최소 30주 이상의 데이터가 필요합니다. (현재: {len(weekly_df)}주)")
            return None

        return weekly_df

    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def analyze_stock(ticker, df):
    """
    황금 세팅 전략에 맞춰 주식을 분석하고 결과를 반환합니다.
    """
    # 1. 지표 및 추세 설정
    # 30주 EMA (지수이동평균)
    df['EMA_30'] = df['Close'].ewm(span=30, adjust=False).mean()
    # 20주 EMA (정배열 확인용)
    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
    # 5주 EMA (단기 추세 확인용)
    df['EMA_5'] = df['Close'].ewm(span=5, adjust=False).mean()
    
    # 거래량 20주 평균 (거래량 급증 확인용)
    df['Vol_Avg_20'] = df['Volume'].rolling(window=20).mean()
    
    # 최근 데이터 기준 (가장 마지막 주)
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    current_price = latest['Close']
    current_ema30 = latest['EMA_30']
    prev_ema30 = prev['EMA_30']
    current_volume = latest['Volume']
    avg_volume = latest['Vol_Avg_20'] if pd.notnull(latest['Vol_Avg_20']) else 0
    
    # 이격도 (현재 주가와 30주 EMA의 거리 %)
    disparity = ((current_price - current_ema30) / current_ema30) * 100
    
    # ---------------------------------------------------------
    # [Added for Error Handling] Define missing variables
    # ---------------------------------------------------------
    slope = current_ema30 - prev_ema30
    
    # 1. EPS Growth (Try to fetch from Yahoo Finance)
    # -------------------------------------------------------------------------
    # 1. Fundamental Data Fetching with Fallback logic
    # -------------------------------------------------------------------------
    eps_growth = 0.0
    roe = 0.0
    operating_margins = 0.0
    trailing_pe = 0.0
    dividend_yield = 0.0
    
    data_status = "OK" # OK, MISSING, PARTIAL
    missing_fields = []

    try:
        tk = yf.Ticker(ticker)
        info = tk.info
        
        # Helper for safe float conversion
        def safe_get(key, default=None):
            val = info.get(key)
            if val is None:
                return default
            try:
                return float(val)
            except:
                return default
        
        # 1. EPS Growth: Try Quarterly -> Annual (earningsGrowth) -> 0
        gw = safe_get('earningsQuarterlyGrowth')
        if gw is None:
            gw = safe_get('earningsGrowth') # Fallback to Annual/TTM
            
        if gw is not None:
             eps_growth = gw * 100
        else:
             missing_fields.append('EPS Growth')
             
        # 2. Profitability
        roe_val = safe_get('returnOnEquity')
        if roe_val is not None:
            roe = roe_val * 100
        else:
            missing_fields.append('ROE')
            
        op_margins = safe_get('operatingMargins')
        if op_margins is not None:
            operating_margins = op_margins * 100
        
        # 3. Valuation
        trailing_pe = safe_get('trailingPE')
        dividend_yield = safe_get('dividendYield', 0.0)
        if dividend_yield is not None:
            dividend_yield = dividend_yield * 100
            
    except Exception as e:
        print(f"Fundamental Data Error: {e}")
        data_status = "ERROR"
        # Keep defaults as 0
        pass

    # 2. VCP Pattern (Placeholder)
    is_vcp = False # Implement VCP logic if needed
    
    # 3. Market Leader (Placeholder)
    is_leader = False
    
    # 4. Stage Analysis (Simplified)
    if current_price > current_ema30 and slope > 0:
        stage = "Stage 2"
        stage_desc = "상승 국면 (Markup)"
        stage_color = "#ff4b4b" 
        stage_emoji = "📈"
    elif current_price < current_ema30 and slope < 0:
         stage = "Stage 4"
         stage_desc = "하락 국면 (Decline)"
         stage_color = "#0000ff"
         stage_emoji = "📉"
    else:
        stage = "Stage 1/3"
        stage_desc = "보합/조정 (Base/Top)"
        stage_color = "#808080"
        stage_emoji = "⏸️"
    # ---------------------------------------------------------
    
    # 2. 분석 로직
    details = []
    
    # (1) 상승 추세 정의
    # ① 30주 EMA가 우상향 (기울기 > 0)
    is_ema_uptrend = current_ema30 > prev_ema30
    # ② 현재 주가가 30주 EMA 위에 있음
    is_price_above_ema = current_price >= current_ema30
    
    is_uptrend = is_ema_uptrend and is_price_above_ema
    
    # (2) 매수 로직 (Buy Signal)
    recommendation = "관망 (Wait)" # 기본값
    signal_strength = 0 # 0: 없음, 1: 보통, 2: 강력
    
    if is_uptrend:
        # 눌림목 타점: 상승 추세에서 30주 EMA 부근 (±2% 이내)까지 조정
        if abs(disparity) <= 2.0:
            recommendation = "매수 (Buy) - 눌림목 타점"
            details.append("[눌림목] 상승 추세 속에서 주가가 30주 EMA 지지선 부근에 왔습니다.")
            signal_strength = 2
        
        # 돌파 타점: 거래량 급증 (평균 대비 1.5배 이상)
        elif avg_volume > 0 and current_volume >= (avg_volume * 1.5):
            recommendation = "매수 (Buy) - 거래량 실린 상승"
            details.append(f"[거래량 급증] 평균 대비 {current_volume/avg_volume:.1f}배의 거래량이 터졌습니다.")
            signal_strength = 2
        else:
            recommendation = "보유 (Hold)"
            details.append("[유지] 상승 추세가 유지되고 있습니다.")
            signal_strength = 1

    # (3) 매도 로직 (Sell Signal) / 추세 이탈
    # 주가가 30주 EMA를 하향 돌파 (종가 기준)
    if current_price < current_ema30:
        recommendation = "매도 (Sell) - 추세 이탈"
        details.append("[경고] 주가가 30주 EMA 아래로 떨어졌습니다. (데드크로스)")
        details.append("   → 상승 추세가 꺾였으므로 전량 매도를 고려하세요.")
        signal_strength = -1
    
    # (4) 점수 계산 (0~100점) - Revised: Trend(50) + Fundamental(30) + Timing(20)
    
    score_trend = 0
    score_fundamental = 0
    score_timing = 0
    
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # 1. 추세 점수 (Total 40점) - Refactored
    # ---------------------------------------------------------
    
    # [Fix] Define variables explicitely to avoid NameError
    try:
        current_ema30 = df['EMA_30'].iloc[-1]
        prev_ema30 = df['EMA_30'].iloc[-2]
        current_ema20 = df['EMA_20'].iloc[-1]
        current_ema5 = df['EMA_5'].iloc[-1]
    except Exception:
        current_ema30 = 0
        current_ema20 = 0
        current_ema5 = 0
        
    score_trend = 0
    
    # A. 30주 EMA 방향성 (20점)
    if current_ema30 > prev_ema30: 
        score_trend += 20 # 우상향
    elif current_ema30 >= prev_ema30 * 0.999:
        score_trend += 10 # 횡보
    else:
        score_trend += 0 # 하락
        
    # B. 이동평균선 정배열 (10점)
    if current_ema5 > current_ema20 > current_ema30:
        score_trend += 10
        
    # C. 이격도 안정성 (10점)
    # 0% ~ 20% 이내에 있으면 안정적 상승세
    disparity_pct = (current_price - current_ema30) / current_ema30 * 100 if current_ema30 > 0 else 0
    
    if 0 <= disparity_pct <= 20:
        score_trend += 10
    elif disparity_pct > 20:
        # 과열 구간 (점수 없음 or 감점? User said 'Fill 40pts with 20+10+10')
        # Let's give 5 pts for overheating instead of 0? Or 0.
        # User prompt: "이격도 안정성(10점)" implies binary or strict.
        # But previously we deducted. Let's stick to 0 if overheated or negative.
        pass 
        
    # 추세 등급 산정
    trend_grade = ""
    if score_trend >= 35:
        trend_grade = "🔥 추세 폭발 종목"
    elif score_trend >= 20:
        trend_grade = "📈 상승 추세 지속"
    else:
        trend_grade = "➡️ 횡보/전환 중"

    # ---------------------------------------------------------
    # 2. 펀더멘털 점수 (Total 30점) - Kept Same
    # ---------------------------------------------------------
    # (Checking logical bounds)
    # Reuse existing code block for fundamentals...
    # (Just passing through here to reach the next part, but need to ensure 'score_fundamental' is calculated)
    # Since I am replacing the block '1. Trend', I should ensure I don't delete Fundamental start.
    # Actually the replacement chunking for Fundamental is tricky if I don't include it. 
    # Let's just modify the variables above 'Fundamental' section by closing the Trend block.
    
    # 추세 등급 산정
    trend_grade = ""
    if score_trend >= 45:
        trend_grade = "🔥 추세 폭발 종목"
    elif score_trend <= 30:
        trend_grade = "횡보 및 추세 전환 중"
    else:
        trend_grade = "📈 상승 추세 지속"
    
    # ---------------------------------------------------------
    # 2. 펀더멘털 점수 (Total 30점) - Diversified for Blue Chips
    # ---------------------------------------------------------
    # (1) 이익 성장성 (15점)
    score_growth = 0
    if eps_growth >= 20:
        score_growth = 15
    elif eps_growth >= 10:
        score_growth = 10
    elif eps_growth >= 0:
        score_growth = 5
    else:
        score_growth = 0
        
    # (2) 수익성 및 효율성 (10점)
    score_profitability = 0
    # ROE 10% 이상 OR 영업이익률 10% 이상 (제조업 기준 양호)
    if roe >= 10 or operating_margins >= 10:
        score_profitability = 10
    elif roe > 0: # 흑자는 냄
        score_profitability = 5
        
    # (3) 밸류에이션 및 안정성 (5점)
    # (3) 밸류에이션 및 안정성 (5점)
    score_value = 0
    # PER이 적정 수준(예: 30 이하) 이거나 배당을 지급함
    # Note: 업종 평균 PER 데이터가 없으므로 절대 기준 적용 (성장주/가치주 혼합 고려 25~30)
    
    # Safe checks for None
    has_dividend = (dividend_yield is not None and dividend_yield > 0)
    
    # PER Check: Must be not None and within range
    is_undervalued = False
    if trailing_pe is not None and 0 < trailing_pe < 25:
        is_undervalued = True
    
    if is_undervalued or has_dividend:
        score_value = 5
        
    # 최종 합산
    score_fundamental = score_growth + score_profitability + score_value
    
    # 데이터 부족 알림
    fundamental_note = ""
    # 만약 성장성 지표가 누락되었는데 점수가 낮다면?
    if 'EPS Growth' in missing_fields:
        fundamental_note = "추정치 (데이터 부족)"
        
    # 등급 산정
    fundamental_grade = ""
    if score_fundamental >= 25:
        fundamental_grade = "💎 다이아몬드 (우량/고성장)"
    elif score_fundamental >= 15:
        fundamental_grade = "🥇 골드 (양호)"
    elif score_fundamental >= 10:
        fundamental_grade = "🥈 실버 (보통)"
    else:
        fundamental_grade = "🌱 성장 기대"
        
    if fundamental_note:
        fundamental_grade = f"{fundamental_grade} - {fundamental_note}"

    # ---------------------------------------------------------
    # 3. AI 관심도 점수 (Total 30점) - New Logic
    # ---------------------------------------------------------
    score_interest = 0
    mention_count = 0
    
    # Find matching name in MENTION_COUNTS using STRICT matching
    # 1. Get all aliases for current ticker
    aliases = {k for k, v in KOREAN_TICKER_MAP.items() if v == ticker}
    aliases.add(ticker) 
    
    # 2. Iterate through MENTION_COUNTS and check for EXACT match
    for m_name, m_count in MENTION_COUNTS.items():
        # Clean mention name (remove spaces, upper case)
        clean_m_name = m_name.replace(" ", "").upper()
        
        is_match = False
        for alias in aliases:
            # Clean alias
            clean_alias = alias.replace(" ", "").upper()
            
            # STRICT EQUALITY MATCH
            if clean_alias == clean_m_name:
                is_match = True
                break
                
        if is_match:
            # Keep max count if multiple matches (though exact match implies unique usually)
            if m_count > mention_count:
                mention_count = m_count
                
    if mention_count >= 50:
        score_interest = 30
    elif mention_count >= 20:
        score_interest = 30
    elif mention_count >= 20:
        score_interest = 20
    elif mention_count >= 1:
        score_interest = 10
    else:
        score_interest = 0
        
    interest_grade = f"{mention_count}회 언급" if mention_count > 0 else "데이터 없음"

    # Final Score Calculation
    final_score = int(score_trend + score_fundamental + score_interest)
    
    # DataFrame용 Score ("Trend + Timing" only for generic chart history, simplified)
    # 과거 데이터 차트용 점수는 추세+이격도 위주로 단순화 (펀더멘털은 시계열 데이터 부족)
    
    # [Added] Vectorized definitions for DataFrame Score
    trend_condition = (df['EMA_30'] > df['EMA_30'].shift(1)) & (df['Close'] > df['EMA_30'])
    disparity_series = ((df['Close'] - df['EMA_30']) / df['EMA_30']) * 100
    
    df['Score'] = 0.0
    # Vectorized Trend (Approximate using 50 pts base for perfect trend)
    # Since specific history conditions are complex, we map simple uptrend to a good score base
    # Trend (50): 30 pts for EMA Rising + Price > EMA (Simplified)
    vec_trend = trend_condition.astype(int) * 40 # Give 40 for good trend in history
    
    # Vectorized Timing (Approx based on Disparity)
    # Max 20 pts -> Disparity nice + Volume nice
    vec_disp = (20 - disparity_series.abs()).clip(lower=0) 
    
    # Simple Volume approximation (Max 10)
    vec_vol = ((df['Volume'] / df['Vol_Avg_20'].replace(0, 1) - 1.0) * 10).clip(lower=0, upper=10)
    
    df['Score'] = vec_trend + vec_disp + vec_vol # Fundamentals missing in history
    # Normalize to not exceed 100 (though without fundamentals it won't)
    df['Score'] = df['Score'].clip(upper=100)
    
    df['Score'] = vec_trend + vec_disp + vec_vol
    # 현재 시점 Score는 정교한 계산값으로 덮어쓰기
    if not df.empty:
        df.iloc[-1, df.columns.get_loc('Score')] = final_score

    return {
        'ticker': ticker,
        'date': latest.name,
        'current_price': current_price,
        'current_ema30': current_ema30,
        'is_ema_uptrend': is_ema_uptrend,
        'disparity': disparity,
        'recommendation': recommendation,
        'details': details,
        'signal_strength': signal_strength,
        'score': final_score,
        'df': df,
        'is_vcp': is_vcp,
        'eps_growth': eps_growth,
        'is_leader': is_leader,
        'fundamental_grade': fundamental_grade, 
        'trend_grade': trend_grade, 
        'interest_grade': interest_grade, # Added Interest Grade
        'fundamental_data': { 
            'eps_growth': eps_growth,
            'roe': roe,
            'pe': trailing_pe,
            'dividend': dividend_yield,
            'missing': missing_fields
        },
        'stage_info': {
            'stage': stage,
            'desc': stage_desc,
            'color': stage_color,
            'emoji': stage_emoji,
            'slope': slope
        },
        'score_breakdown': {
            'trend': score_trend,
            'fundamental': score_fundamental,
            'interest': score_interest
        }
    }

def print_analysis_result(result):
    """
    분석 결과를 출력합니다.
    """
    print(f"\n{'='*50}")
    print(f"[{result['ticker']}] Weekly Signal 분석 결과")
    print(f"   기준일: {result['date'].strftime('%Y-%m-%d')}")
    print(f"{'='*50}")
    
    print(f"1. 현재 주가   : {result['current_price']:,.2f}")
    print(f"2. 30주 EMA    : {result['current_ema30']:,.2f} ({'우상향' if result['is_ema_uptrend'] else '하락/보합'})")
    print(f"3. 이격도      : {result['disparity']:+.2f}% (30주 EMA와의 거리)")
    print(f"4. 종합 상태   : [{result['recommendation']}]")
    
    print(f"{'-'*50}")
    print("상세 분석 코멘트:")
    for detail in result['details']:
        print(f" - {detail}")
        
    # 익절 가이드 (제거됨)
    print(f"{'='*50}\n")


# 한글 종목명 -> 티커 매핑 (KOSPI Top 100 포함)
KOREAN_TICKER_MAP = {
    "삼성전자": "005930.KS", "삼전": "005930.KS",
    "SK하이닉스": "000660.KS", "하이닉스": "000660.KS",
    "LG에너지솔루션": "373220.KS", "LG엔솔": "373220.KS",
    "삼성바이오로직스": "207940.KS", "삼바": "207940.KS",
    "현대차": "005380.KS",
    "기아": "000270.KS",
    "셀트리온": "068270.KS",
    "KB금융": "105560.KS",
    "POSCO홀딩스": "005490.KS", "포스코홀딩스": "005490.KS",
    "NAVER": "035420.KS", "네이버": "035420.KS",
    "신한지주": "055550.KS",
    "삼성물산": "028260.KS",
    "현대모비스": "012330.KS",
    "삼성SDI": "006400.KS",
    "카카오": "035720.KS",
    "LG화학": "051910.KS",
    "하나금융지주": "086790.KS",
    "삼성생명": "032830.KS",
    "메리츠금융지주": "138040.KS",
    "LG전자": "066570.KS",
    "한국전력": "015760.KS",
    "두산에너빌리티": "034020.KS",
    "HMM": "011200.KS",
    "포스코퓨처엠": "003670.KS",
    "HD현대중공업": "329180.KS",
    "고려아연": "010130.KS",
    "삼성화재": "000810.KS",
    "우리금융지주": "316140.KS",
    "HD한국조선해양": "009540.KS",
    "기업은행": "024110.KS",
    "KT": "030200.KS", "케이티": "030200.KS",
    "SK": "034730.KS", "에스케이": "034730.KS",
    "대한항공": "003490.KS",
    "한화에어로스페이스": "012450.KS",
    "SK이노베이션": "096770.KS",
    "크래프톤": "259960.KS",
    "LG": "003550.KS",
    "삼성에스디에스": "018260.KS", "삼성SDS": "018260.KS",
    "SK텔레콤": "017670.KS",
    "하이브": "352820.KS",
    "KT&G": "033780.KS",
    "에코프로머티": "450080.KS",
    "한화오션": "042660.KS",
    "S-Oil": "010950.KS", "에쓰오일": "010950.KS",
    "HD현대일렉트릭": "267260.KS",
    "카카오뱅크": "323410.KS",
    "DB손해보험": "005830.KS",
    "LIG넥스원": "079550.KS",
    "삼성전기": "009150.KS",
    "SK스퀘어": "402340.KS",
    "아모레퍼시픽": "090430.KS",
    "현대글로비스": "086280.KS",
    "한화시스템": "272210.KS",
    "한국금융지주": "071050.KS",
    "두산밥캣": "241560.KS",
    "LG이노텍": "011070.KS",
    "LG생활건강": "051910.KS", 
    "HD현대": "267250.KS",
    "금호석유": "011780.KS",
    "롯데케미칼": "011170.KS",
    "CJ제일제당": "097950.KS",
    "맥쿼리인프라": "088980.KS",
    "SK바이오사이언스": "302440.KS",
    "SK바이오팜": "326030.KS",
    "한미반도체": "042700.KS",
    "LG유플러스": "032640.KS",
    "현대제철": "004020.KS",
    "엔씨소프트": "036570.KS",
    "오리온": "271560.KS",
    "넷마블": "251270.KS",
    "카카오페이": "377300.KS",
    "현대오토에버": "307950.KS",
    "삼성중공업": "010140.KS",
    "유한양행": "000100.KS",
    "한화솔루션": "009830.KS",
    "현대건설": "000720.KS",
    "강원랜드": "035250.KS",
    "코웨이": "021240.KS",
    "F&F": "383220.KS",
    "한국타이어앤테크놀로지": "161390.KS",
    "롯데지주": "004990.KS",
    "삼성엔지니어링": "028050.KS", "삼성E&A": "028050.KS",
    "CS윈드": "112610.KS",
    "팬오션": "028670.KS",
    "한진칼": "180640.KS",
    "현대미포조선": "010620.KS", "HD현대미포": "010620.KS",
    "호텔신라": "008770.KS",
    "키움증권": "039490.KS",
    "BGF리테일": "282330.KS",
    "한온시스템": "018880.KS",
    "GS": "078930.KS",
    "OCI홀딩스": "010060.KS",
    "이마트": "139480.KS",
    "LS": "006260.KS",
    "농심": "004370.KS",
    "현대해상": "001450.KS",
    "BNK금융지주": "138930.KS",
    "동부하이텍": "000990.KS", "DB하이텍": "000990.KS",
    "에스원": "012750.KS",
    "제일기획": "030000.KS",
    "신세계": "004170.KS",
    "휠라홀딩스": "081660.KS", 
    # US Tech & Growth
    "애플": "AAPL", "테슬라": "TSLA", "마이크로소프트": "MSFT", 
    "구글": "GOOGL", "알파벳": "GOOGL", "아마존": "AMZN", 
    "엔비디아": "NVDA", "AMD": "AMD", "메타": "META", "페이스북": "META",
    "넷플릭스": "NFLX", "아이온큐": "IONQ", "팔란티어": "PLTR",
    "유니티": "U", "로블록스": "RBLX", "코인베이스": "COIN",
    "우버": "UBER", "에어비앤비": "ABNB", "쿠팡": "CPNG",
    "인텔": "INTC", "퀄컴": "QCOM", "브로드컴": "AVGO",
    "티에스엠씨": "TSM", "TSMC": "TSM", "암": "ARM",
    "슈퍼마이크로": "SMCI", "사운드하운드": "SOUN", "C3AI": "AI"
}

from pykrx import stock
import time

# 캐싱용 전역 변수 (시장별 분리)
_CACHED_TOP_STOCKS = {}

# NASDAQ 100 Tickers (Hardcoded for stability)
# NASDAQ 100 Tickers (Hardcoded for stability)
# [Modified] Removed 'GOOG' (duplicate of GOOGL) and ensure no other duplicates
NASDAQ_100_TICKERS = [
    "AAPL", "MSFT", "AMZN", "AVGO", "META", "TSLA", "GOOGL", "NVDA", "PEP",
    "COST", "CSCO", "TMUS", "CMCSA", "INTC", "AMD", "QCOM", "TXN", "AMGN", "HON",
    "INTU", "SBUX", "BKNG", "NFLX", "ADBE", "MDLZ", "ADP", "GILD", "ISRG", "VRTX",
    "REGN", "PYPL", "FISV", "LRCX", "ATVI", "MELI", "PANW", "MNST", "CSX", "ORLY",
    "KLAC", "SNPS", "CDNS", "MAR", "ASML", "NXPI", "CTAS", "CHTR", "DXCM", "FTNT",
    "KDP", "ADSK", "KHC", "PAYX", "PCAR", "ROST", "IDXX", "AEP", "LULU", "EXC",
    "ODFL", "AZN", "EA", "CTSH", "FAST", "XEL", "BKR", "GFS", "GEHC", "ALGN",
    "CPRT", "MRVL", "CSGP", "DLTR", "WBD", "PDD", "SIRI", "ANSS", "TEAM", "VRSK",
    "FANG", "EBAY", "ILMN", "WBA", "ZM", "ENPH", "JD", "CRWD", "WDAY", "ZS",
    "LCID", "RIVN", "DDOG", "MRNA", "BIIB", "MCHP", "ON", "CDW", "CCEP", "TTD"
]

def get_top_stocks(market="KOSPI", top_n=100):
    """
    pykrx를 사용하여 지정된 시장(KOSPI/KOSDAQ)의 시가총액 상위 종목 티커를 반환합니다.
    NASDAQ의 경우 하드코딩된 리스트를 반환합니다.
    Yahoo Finance 형식(.KS, .KQ)으로 변환하며 KOREAN_TICKER_MAP을 업데이트합니다.
    """
    global _CACHED_TOP_STOCKS
    
    cache_key = f"{market}_{top_n}"
    
    # 이미 캐싱된 값이 있으면 반환
    if cache_key in _CACHED_TOP_STOCKS:
        return _CACHED_TOP_STOCKS[cache_key]
    
    # --- NASDAQ 처리 ---
    if market.upper() == "NASDAQ":
        # Deduplicate list just in case
        tickers = list(dict.fromkeys(NASDAQ_100_TICKERS[:top_n]))
        _CACHED_TOP_STOCKS[cache_key] = tickers
        return tickers

    print(f"\n[System] KRX에서 {market} 시가총액 상위 {top_n}개 종목을 조회합니다...")
    
    try:
        today = datetime.now().strftime("%Y%m%d")
        
        try:
             df = stock.get_market_cap_by_ticker(today, market=market)
        except:
             import datetime as dt
             yesterday = (datetime.now() - dt.timedelta(days=1)).strftime("%Y%m%d")
             df = stock.get_market_cap_by_ticker(yesterday, market=market)
             
        # 시가총액 기준 내림차순 정렬
        df = df.sort_values(by="시가총액", ascending=False)
        
        # 상위 N개 추출
        # [Modified] Fetch more (Top 300) to account for filtered items (Preferred, ETF)
        # 상위 N개 추출 전 넉넉하게 가져옴
        top_df = df.head(300)
        
        tickers_formatted = []
        
        # 시장별 접미사 설정 (Yahoo Finance)
        suffix = ".KS" if market.upper() == "KOSPI" else ".KQ"
        
        print(f"[System] {market} 종목명 매핑 정보를 업데이트 중입니다...")
        
        filtered_count = 0
        
        for ticker in top_df.index:
            try:
                name = stock.get_market_ticker_name(ticker)
                
                # 1. 우선주 및 파생상품 제거
                # 이름 끝이 '우', '우B', '우C' 등으로 끝나거나 '1우' 등을 포함
                if name.endswith('우') or '우B' in name or '우C' in name or name.endswith('우(전환)'):
                    continue
                    
                # 2. ETF/ETN/스팩 제거
                # KODEX, TIGER, ETN, 스팩, ACE, KBSTAR, HANARO, SOL, KOIN, ARIRANG, 
                # 레버리지, 인버스, 선물 등 키워드 포함 시 제거
                keywords = ['KODEX', 'TIGER', 'ETN', '스팩', 'ACE', 'KBSTAR', 'HANARO', 'SOL', 
                            'KOIN', 'ARIRANG', '레버리지', '인버스', '선물', 'TIMEFOLIO']
                
                if any(k in name for k in keywords):
                    continue
                
                yf_ticker = f"{ticker}{suffix}"
                tickers_formatted.append(yf_ticker)
                
                # Update Map (Only if safe)
                if name not in KOREAN_TICKER_MAP:
                    KOREAN_TICKER_MAP[name] = yf_ticker
                    
                filtered_count += 1
                if filtered_count >= top_n:
                    break
                    
            except Exception:
                continue
                
        _CACHED_TOP_STOCKS[cache_key] = tickers_formatted
        print(f"[System] {market} Top {top_n} 리스트 및 종목명 생성 완료. (Selected from Top 300)")
        
        return tickers_formatted
            
        _CACHED_TOP_STOCKS[cache_key] = tickers_formatted
        print(f"[System] {market} Top {top_n} 리스트 및 종목명 생성 완료.")
        
        return tickers_formatted
        
    except Exception as e:
        print(f"Error fetching {market} Top {top_n}: {e}")
        return []

def main():
    print("\n" + "=" * 60)
    print("      Weekly Signal 주식 분석기 (Weekly 30EMA)")
    print(f"{'=' * 60}")
    print(" * 30주 EMA와 거래량을 기반으로 매수/매도 타이밍을 분석합니다.")
    print(" * 종료하려면 'q'를 입력하세요.")
    
    while True:
        user_input = input("\n🔍 종목명 또는 티커 입력 (예: 삼성전자, AAPL): ").strip()
        
        if user_input.upper() == 'Q':
            print("프로그램을 종료합니다. 성투하세요!")
            break
            
        if not user_input:
            continue

        # 한글 종목명 매핑 확인
        if user_input in KOREAN_TICKER_MAP:
            ticker = KOREAN_TICKER_MAP[user_input]
            print(f"'{user_input}' -> '{ticker}' (으)로 분석을 시작합니다.")
        else:
            ticker = user_input.upper()
            
        df = get_stock_data(ticker)
        if df is not None:
            result = analyze_stock(ticker, df)
            print_analysis_result(result)

if __name__ == "__main__":
    main()
