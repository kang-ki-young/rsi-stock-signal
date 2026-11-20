
import os
import requests
import pandas as pd
import yfinance as yf

STOCKS = {
    "삼성전자": "005930.KS",
    "SK하이닉스": "000660.KS",
    "현대차": "005380.KS",
    "LG전자": "066570.KS",
    "LS ELECTRIC": "010120.KS",
    "에이비엘바이오": "298380.KQ",
    "알테오젠": "196170.KQ",
}

def calculate(df):
    close = df["Close"].astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    n = 14
    ag = pd.Series(float("nan"), index=df.index)
    al = ag.copy()
    if len(df) <= n:
        raise ValueError("RSI 데이터 부족")
    ag.iloc[n] = gain.iloc[1:n+1].mean()
    al.iloc[n] = loss.iloc[1:n+1].mean()
    for i in range(n+1, len(df)):
        ag.iloc[i] = (ag.iloc[i-1]*13 + gain.iloc[i])/14
        al.iloc[i] = (al.iloc[i-1]*13 + loss.iloc[i])/14
    rs = ag / al.replace(0, float("nan"))
    df["RSI"] = 100 - 100/(1+rs)
    df["RSI"] = df["RSI"].mask(
        (al == 0) & (ag > 0), 100
    ).mask(
        (ag == 0) & (al > 0), 0
    ).mask(
        (ag == 0) & (al == 0), 50
    )
    df["MA20"] = close.rolling(20).mean()
    df["VOL20"] = df["Volume"].rolling(20).mean()
    return df

def send(message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat = os.environ["TELEGRAM_CHAT_ID"]
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat, "text": message},
        timeout=15,
    )
    response.raise_for_status()

def main():
    if not os.getenv("TELEGRAM_BOT_TOKEN") or not os.getenv("TELEGRAM_CHAT_ID"):
        raise RuntimeError("텔레그램 설정이 없습니다.")
if os.getenv("TEST_ALERT") == "1":
    send("✅ RSI 주식 알림 테스트 성공!")
    return
    errors = []
    for name, ticker in STOCKS.items():
        try:
            df = yf.download(
                ticker, period="1y", interval="1d",
                auto_adjust=True, progress=False,
                threads=False,
            )
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.dropna(subset=["Close", "Volume"])
            if len(df) < 65:
                raise ValueError("가격 데이터 부족")

            df = calculate(df)
            previous, current = df.iloc[-2], df.iloc[-1]
            signal = None

            if (
                previous["RSI"] <= 30
                and current["RSI"] > 30
                and current["Close"] > current["MA20"]
                and current["Volume"] >= current["VOL20"]
            ):
                signal = "매수 관심"
            elif previous["RSI"] >= 70 and current["RSI"] < 70:
                signal = "매도 관심"

            if signal:
                message = (
                    f"[RSI 주식 알림]\n"
                    f"종목: {name}\n"
                    f"신호: {signal}\n"
                    f"날짜: {df.index[-1].date()}\n"
                    f"종가: {current['Close']:,.0f}원\n"
                    f"RSI: {current['RSI']:.1f}"
                )
                send(message)
                print(f"전송 완료: {name} {signal}")
            else:
                print(f"신호 없음: {name}")
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            print(f"오류: {name}: {exc}")

    if errors:
        raise RuntimeError("일부 종목 처리 실패: " + "; ".join(errors))

if __name__ == "__main__":
    main()
