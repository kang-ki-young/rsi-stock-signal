import os
from datetime import datetime
import pandas as pd
import streamlit as st
import yfinance as yf
import requests

st.set_page_config(page_title='RSI 한국주식 신호', page_icon='📈', layout='centered')
st.markdown('''<style> .block-container{padding-top:1.3rem;max-width:760px} [data-testid="stMetricValue"]{font-size:1.55rem} button{min-height:44px} </style>''',unsafe_allow_html=True)
DEFAULT={'삼성전자':'005930.KS','SK하이닉스':'000660.KS','현대차':'005380.KS','LG전자':'066570.KS','LS ELECTRIC':'010120.KS','에이비엘바이오':'298380.KQ','알테오젠':'196170.KQ'}

def calc(df):
    df=df.copy()
    close=df['Close'].astype(float)
    delta=close.diff(); gain=delta.clip(lower=0); loss=-delta.clip(upper=0)
    # Wilder RSI: first smoothed average is the mean of the first 14 changes.
    n=14
    avg_g=pd.Series(float('nan'),index=df.index); avg_l=avg_g.copy()
    if len(df)>n:
        avg_g.iloc[n]=gain.iloc[1:n+1].mean();avg_l.iloc[n]=loss.iloc[1:n+1].mean()
        for i in range(n+1,len(df)):
            avg_g.iloc[i]=(avg_g.iloc[i-1]*(n-1)+gain.iloc[i])/n
            avg_l.iloc[i]=(avg_l.iloc[i-1]*(n-1)+loss.iloc[i])/n
    rs=avg_g/avg_l.replace(0,float('nan'))
    rsi=100-100/(1+rs)
    rsi=rsi.mask((avg_l==0)&(avg_g>0),100).mask((avg_g==0)&(avg_l>0),0).mask((avg_g==0)&(avg_l==0),50)
    df['RSI']=rsi;df['MA20']=close.rolling(20).mean();df['MA60']=close.rolling(60).mean();df['VOL20']=df['Volume'].rolling(20).mean()
    return df

@st.cache_data(ttl=900,show_spinner=False)
def load(symbol):
    raw=yf.download(symbol,period='1y',interval='1d',auto_adjust=True,progress=False,threads=False)
    if raw.empty: raise ValueError('가격 데이터가 없습니다. 종목코드/거래소를 확인하세요.')
    if isinstance(raw.columns,pd.MultiIndex):raw.columns=raw.columns.get_level_values(0)
    raw=raw.dropna(subset=['Close','Volume'])
    if len(raw)<65:raise ValueError('지표 계산에 필요한 데이터가 부족합니다.')
    return calc(raw)

def signal(df):
    p,c=df.iloc[-2],df.iloc[-1]
    if pd.isna(p.RSI) or pd.isna(c.RSI):return '데이터 부족','RSI 계산 불가'
    if p.RSI<=30 and c.RSI>30 and c.Close>c.MA20 and c.Volume>=c.VOL20:
        return '매수 관심','RSI 30 상향돌파 + 20일선 상회 + 거래량 확인'
    if p.RSI>=70 and c.RSI<70:return '매도 관심','RSI 70 하향돌파'
    if c.Close<c.MA60:return '위험 경고','종가가 60일 이동평균선 아래'
    return '관망','매수·매도 조건 미충족'

def notify(msg):
    token=os.getenv('TELEGRAM_BOT_TOKEN','')
    chat=os.getenv('TELEGRAM_CHAT_ID','')
    try:
        token=st.secrets.get('TELEGRAM_BOT_TOKEN',token)
        chat=st.secrets.get('TELEGRAM_CHAT_ID',chat)
    except Exception:pass
    if not token or not chat:return False,'텔레그램 토큰/채팅 ID가 설정되지 않았습니다.'
    try:
        r=requests.post(f'https://api.telegram.org/bot{token}/sendMessage',data={'chat_id':chat,'text':msg},timeout=12)
        r.raise_for_status();return True,'텔레그램 전송 완료'
    except Exception as e:return False,f'전송 실패: {str(e)[:120]}'

st.title('📈 RSI 한국주식 신호')
st.caption('일봉 종가 기준 · 15분 캐시 · 투자 권유가 아닌 참고 신호')
if 'symbols' not in st.session_state:st.session_state.symbols=DEFAULT.copy()
if 'watch' not in st.session_state:st.session_state.watch=list(DEFAULT)[:3]
with st.expander('➕ 관심종목 추가 / 삭제',expanded=False):
    name=st.text_input('표시 이름',placeholder='예: 기아')
    code=st.text_input('6자리 종목코드',placeholder='000270',max_chars=6)
    market=st.selectbox('거래소',['코스피 (.KS)','코스닥 (.KQ)'])
    if st.button('관심종목 추가'):
        if len(code)==6 and code.isdigit() and name.strip():
            st.session_state.symbols[name.strip()]=code+('.KS' if market.startswith('코스피') else '.KQ')
            if name.strip() not in st.session_state.watch:st.session_state.watch.append(name.strip())
            st.success('현재 접속 세션에 추가했습니다. 영구 저장은 별도 DB가 필요합니다.')
        else:st.error('종목 이름과 숫자 6자리를 입력하세요.')
    selected=st.multiselect('현재 관심종목',st.session_state.watch,default=st.session_state.watch)
    st.session_state.watch=selected
if st.button('🔄 시세 새로 조회'):
    load.clear();st.rerun()
results=[]
for name in st.session_state.watch:
    if name not in st.session_state.symbols:continue
    try:
        df=load(st.session_state.symbols[name]);last=df.iloc[-1];status,reason=signal(df)
        results.append({'종목':name,'코드':st.session_state.symbols[name],'날짜':str(df.index[-1].date()),'종가':round(float(last.Close)),'RSI':round(float(last.RSI),1),'신호':status,'사유':reason})
    except Exception as e:st.warning(f'{name}: {e}')
if results:
    st.subheader('📋 관심종목 신호')
    st.dataframe(pd.DataFrame(results)[['종목','날짜','종가','RSI','신호']],hide_index=True,use_container_width=True)
    choice=st.selectbox('상세 차트', [r['종목'] for r in results])
    item=next(r for r in results if r['종목']==choice)
    df=load(item['코드']);last=df.iloc[-1]
    a,b,c=st.columns(3)
    a.metric('종가',f"{item['종가']:,}원");b.metric('RSI(14)',item['RSI']);c.metric('판정',item['신호'])
    st.caption(f"{item['날짜']} | {item['사유']}")
    st.line_chart(df[['Close','MA20','MA60']].tail(90),height=230)
    chart=df[['RSI']].tail(90).copy();chart['과매수 70']=70;chart['과매도 30']=30
    st.line_chart(chart,height=230)
    st.caption('조정주가 기준 차트. 장중·지연·휴장 등으로 마지막 데이터가 최신 거래일이 아닐 수 있습니다.')
    if st.button('📨 현재 신호 텔레그램으로 보내기'):
        ok,msg=notify(f"[RSI 한국주식] {choice} ({item['코드']})\n{item['날짜']} 종가 {item['종가']:,}원 / RSI {item['RSI']}\n{item['신호']}: {item['사유']}")
        (st.success if ok else st.error)(msg)
    st.download_button('⬇️ 신호 CSV 저장',pd.DataFrame(results).to_csv(index=False).encode('utf-8-sig'),'rsi_signals.csv','text/csv')
st.divider()
st.info('알림 버튼은 수동 발송입니다. 자동 알림은 포함된 GitHub Actions 워크플로를 설정해야 합니다. 웹앱을 닫아도 작동하는 실시간 푸시 기능은 아직 없습니다.')
