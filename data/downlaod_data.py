import yfinance as yf

spy = yf.download("SPY", start="2010-01-14", end="2026-04-13")
spy.to_csv("SPY.csv")

print(spy.head())