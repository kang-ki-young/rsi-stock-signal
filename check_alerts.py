"""Scheduled end-of-day Telegram alerts. Only sends new BUY/SELL/RISK signals."""
import os,json,sys
from datetime import datetime
import pandas as pd
import yfinance as yf
import requests

WATCH={'삼성전자':'005930.KS','SK하이닉스':'000660.KS','현대차':'005380.KS'}
STATE='alert_state.json'

def compute(raw):
    if isinstance(raw.columns,pd.MultiIndex):raw.columns=raw.columns.get_level_values(0)
    raw=raw.dropna(subset=['Close','Volume'])
    if len(raw)<65:return None
    close=raw['Close'];delta=close.diff();g=delta.clip(lower=0);l=-delta.clip(upper=0)
    ag=g.iloc[1:15].mean();al=l.iloc[1:15].mean();rsis=[float('nan')]*14
    def rsi(a,b):return 50. if a==0 and b==0 else (100. if b==0 else 100-100/(1+a/b))
    rsis.append(rsi(ag,al))
    for i in range(15,len(raw)):
        ag=(ag*13+g.iloc[i])/14;al=(al*13+l.iloc[i])/14;rsis.append(rsi(ag,al))
    prev,now=rsis[-2:];ma20=close.tail(20).mean();ma60=close.tail(60).mean();v20=raw['Volume'].tail(20).mean();current=raw.iloc[-1]
    if prev<=30<now and current.Close>ma20 and current.Volume>=v20:status='매수 관심'
    elif prev>=70>now:status='매도 관심'
    elif current.Close<ma60:status='위험 경고'
    else:status='관망'
    return str(raw.index[-1].date()),round(now,1),round(float(current.Close)),status

def main():
    token=os.environ['TELEGRAM_BOT_TOKEN'];chat=os.environ['TELEGRAM_CHAT_ID']
    try:state=json.load(open(STATE,encoding='utf-8'))
    except (FileNotFoundError,json.JSONDecodeError):state={}
    for name,ticker in WATCH.items():
        try:
            raw=yf.download(ticker,period='1y',interval='1d',auto_adjust=True,progress=False,threads=False)
            result=compute(raw)
            if not result:continue
            day,rsi,price,status=result
            key=f'{ticker}:{day}:{status}'
            if status!='관망' and state.get(ticker)!=key:
                msg=f'📈 RSI 신호 | {name}\n{day} | 종가 {price:,}원 | RSI {rsi}\n{status}\n일봉 종가 기준 참고용'
                response=requests.post(f'https://api.telegram.org/bot{token}/sendMessage',data={'chat_id':chat,'text':msg},timeout=15)
                response.raise_for_status()
                state[ticker]=key
                print('Sent',name,status)
        except Exception as e:
            print('Error',name,str(e),file=sys.stderr)
    with open(STATE,'w',encoding='utf-8') as f:json.dump(state,f,ensure_ascii=False,indent=2)
if __name__=='__main__':main()
