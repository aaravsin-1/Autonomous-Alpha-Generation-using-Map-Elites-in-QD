import yfinance as yf

spy = yf.download("QQQ", start="2010-01-14", end="2026-04-13")
spy.to_csv("QQQ.csv")

print(spy.head())