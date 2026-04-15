"""
broker/broker.py
Unified broker interface.
The rest of the system only calls this file.
It handles paper trading, Zerodha, Upstox, and Angel Broking.

SWITCHING BROKERS:
  Change BROKER in config.py. Nothing else changes.
  paper   → all trades simulated, no real money
  zerodha → Zerodha Kite Connect API
  upstox  → Upstox API v2
  angel   → Angel Broking SmartAPI
"""

import json
import datetime
from pathlib import Path
from abc import ABC, abstractmethod


# ══════════════════════════════════════════════════════════════════════════════
# BASE CLASS — all brokers implement this interface
# ══════════════════════════════════════════════════════════════════════════════

class BrokerBase(ABC):

    @abstractmethod
    def get_quote(self, symbol: str) -> dict:
        """Returns {symbol, ltp, open, high, low, close, volume}"""
        pass

    @abstractmethod
    def get_positions(self) -> list:
        """Returns list of open positions"""
        pass

    @abstractmethod
    def place_order(self, symbol: str, side: str,
                    qty: int, order_type: str = "MARKET",
                    price: float = 0) -> dict:
        """
        side: "BUY" or "SELL"
        order_type: "MARKET" or "LIMIT"
        Returns order confirmation dict
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        pass

    @abstractmethod
    def get_funds(self) -> dict:
        """Returns {available_cash, used_margin, total}"""
        pass

    def calculate_quantity(self, symbol: str, capital_inr: float,
                           position_pct: float) -> int:
        """How many shares to buy given capital and position size."""
        deploy = capital_inr * position_pct
        quote  = self.get_quote(symbol)
        ltp    = quote.get("ltp", 0)
        if ltp <= 0:
            return 0
        qty = int(deploy / ltp)
        return max(qty, 1)


# ══════════════════════════════════════════════════════════════════════════════
# PAPER BROKER — simulates everything locally
# ══════════════════════════════════════════════════════════════════════════════

class PaperBroker(BrokerBase):
    """
    Fully simulated broker. No real money. No API calls.
    Reads prices from your CSV file.
    Stores positions and orders in paper_state.json.
    """

    STATE_FILE = Path("journal/paper_state.json")

    def __init__(self, csv_path: str = "data/NIFTYBEES.csv",
                 initial_capital: float = 100000):
        self.csv_path        = csv_path
        self.initial_capital = initial_capital
        self._state          = self._load_state()

    def _load_state(self) -> dict:
        if self.STATE_FILE.exists():
            with open(self.STATE_FILE) as f:
                return json.load(f)
        return {
            "cash":      self.initial_capital,
            "positions": {},    # {symbol: {qty, avg_price, entry_date}}
            "orders":    [],
            "trades":    [],
        }

    def _save_state(self):
        self.STATE_FILE.parent.mkdir(exist_ok=True)
        with open(self.STATE_FILE, "w") as f:
            json.dump(self._state, f, indent=2)

    def get_quote(self, symbol: str) -> dict:
        """Gets the latest price from the CSV file."""
        try:
            import pandas as pd
            # Try the CSV file
            csv = Path(self.csv_path)
            if not csv.exists():
                # Try NSE symbol mapping
                clean = symbol.replace(".NS","").replace("^","")
                csv = Path(f"data/{clean}.csv")

            if csv.exists():
                df  = pd.read_csv(csv, index_col=0, parse_dates=True)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                # Sort and get latest row
                df  = df.sort_index()
                row = df.iloc[-1]

                close_col = next((c for c in df.columns if "close" in c.lower()), df.columns[0])
                ltp = float(row[close_col])

                return {
                    "symbol": symbol,
                    "ltp":    ltp,
                    "close":  ltp,
                    "open":   float(row.get("Open", ltp)),
                    "high":   float(row.get("High", ltp)),
                    "low":    float(row.get("Low",  ltp)),
                    "volume": int(row.get("Volume", 0)),
                    "date":   str(df.index[-1].date()),
                }
        except Exception as e:
            print(f"  [paper] Quote error: {e}")

        # Fallback — try yfinance live
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            hist   = ticker.history(period="2d")
            if not hist.empty:
                ltp = float(hist["Close"].iloc[-1])
                return {"symbol": symbol, "ltp": ltp, "close": ltp,
                        "date": str(hist.index[-1].date())}
        except Exception:
            pass

        return {"symbol": symbol, "ltp": 0.0, "error": "no_data"}

    def get_positions(self) -> list:
        positions = []
        for symbol, pos in self._state["positions"].items():
            quote  = self.get_quote(symbol)
            ltp    = quote.get("ltp", pos["avg_price"])
            pnl    = (ltp - pos["avg_price"]) * pos["qty"]
            pnl_pct = (ltp - pos["avg_price"]) / pos["avg_price"] * 100
            positions.append({
                "symbol":     symbol,
                "qty":        pos["qty"],
                "avg_price":  pos["avg_price"],
                "ltp":        ltp,
                "pnl":        round(pnl, 2),
                "pnl_pct":    round(pnl_pct, 2),
                "value":      round(ltp * pos["qty"], 2),
                "entry_date": pos.get("entry_date", ""),
            })
        return positions

    def place_order(self, symbol: str, side: str,
                    qty: int, order_type: str = "MARKET",
                    price: float = 0) -> dict:
        if qty <= 0:
            return {"status": "REJECTED", "reason": "qty <= 0"}

        quote = self.get_quote(symbol)
        ltp   = quote.get("ltp", 0)
        if ltp <= 0:
            return {"status": "REJECTED", "reason": "no_price"}

        exec_price = ltp
        # Apply slippage for paper trading realism
        from config import SLIPPAGE
        if side == "BUY":
            exec_price = ltp * (1 + SLIPPAGE)
        else:
            exec_price = ltp * (1 - SLIPPAGE)

        cost = exec_price * qty

        order_id = f"PAPER-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

        if side == "BUY":
            if self._state["cash"] < cost:
                return {"status": "REJECTED",
                        "reason": f"insufficient funds (need Rs {cost:.0f}, have Rs {self._state['cash']:.0f})"}
            self._state["cash"] -= cost
            if symbol in self._state["positions"]:
                pos = self._state["positions"][symbol]
                total_qty   = pos["qty"] + qty
                avg_price   = (pos["avg_price"] * pos["qty"] + exec_price * qty) / total_qty
                pos["qty"]  = total_qty
                pos["avg_price"] = avg_price
            else:
                self._state["positions"][symbol] = {
                    "qty":        qty,
                    "avg_price":  exec_price,
                    "entry_date": str(datetime.date.today()),
                }

        elif side == "SELL":
            if symbol not in self._state["positions"]:
                return {"status": "REJECTED", "reason": "no_position"}
            pos     = self._state["positions"][symbol]
            sell_qty = min(qty, pos["qty"])
            proceeds = exec_price * sell_qty
            pnl      = (exec_price - pos["avg_price"]) * sell_qty

            self._state["cash"] += proceeds
            pos["qty"] -= sell_qty
            if pos["qty"] <= 0:
                del self._state["positions"][symbol]

            # Record trade
            self._state["trades"].append({
                "date":       str(datetime.date.today()),
                "symbol":     symbol,
                "side":       "SELL",
                "qty":        sell_qty,
                "price":      round(exec_price, 2),
                "pnl":        round(pnl, 2),
                "pnl_pct":    round(pnl / (pos["avg_price"] * sell_qty) * 100, 2),
            })

        # Log order
        order = {
            "order_id":    order_id,
            "symbol":      symbol,
            "side":        side,
            "qty":         qty,
            "price":       round(exec_price, 2),
            "status":      "COMPLETE",
            "timestamp":   datetime.datetime.now().isoformat(),
        }
        self._state["orders"].append(order)
        self._save_state()

        print(f"  [PAPER ORDER] {side} {qty} {symbol} @ Rs {exec_price:.2f}  "
              f"(Order: {order_id})")
        return order

    def cancel_order(self, order_id: str) -> bool:
        return True   # Paper orders are instant, nothing to cancel

    def get_funds(self) -> dict:
        positions = self.get_positions()
        position_value = sum(p["value"] for p in positions)
        total = self._state["cash"] + position_value
        return {
            "available_cash":  round(self._state["cash"], 2),
            "position_value":  round(position_value, 2),
            "total":           round(total, 2),
            "initial_capital": self.initial_capital,
            "pnl":             round(total - self.initial_capital, 2),
            "pnl_pct":         round((total - self.initial_capital) / self.initial_capital * 100, 2),
        }


# ══════════════════════════════════════════════════════════════════════════════
# ZERODHA BROKER
# ══════════════════════════════════════════════════════════════════════════════

class ZerodhaBroker(BrokerBase):
    """
    Zerodha Kite Connect integration.
    Install: pip install kiteconnect
    Get API key from: https://kite.trade/
    """

    def __init__(self, api_key: str, api_secret: str, access_token: str = None):
        try:
            from kiteconnect import KiteConnect
        except ImportError:
            raise ImportError("Install kiteconnect: pip install kiteconnect")

        self.kite = KiteConnect(api_key=api_key)
        if access_token:
            self.kite.set_access_token(access_token)
        else:
            print("  [Zerodha] No access token. Call generate_session() first.")

    def generate_session(self, request_token: str, api_secret: str) -> str:
        """
        Call this once per day to get a fresh access token.
        request_token comes from the Kite login URL redirect.
        """
        data = self.kite.generate_session(request_token, api_secret=api_secret)
        access_token = data["access_token"]
        self.kite.set_access_token(access_token)
        # Save for today
        token_file = Path("broker/zerodha_token.json")
        token_file.parent.mkdir(exist_ok=True)
        with open(token_file, "w") as f:
            json.dump({"token": access_token,
                       "date":  str(datetime.date.today())}, f)
        return access_token

    def _nse_symbol(self, symbol: str) -> str:
        """Convert yfinance symbol to Zerodha NSE symbol."""
        return symbol.replace(".NS", "").replace("^NSEI", "NIFTY 50")

    def get_quote(self, symbol: str) -> dict:
        nse_sym = self._nse_symbol(symbol)
        try:
            quote = self.kite.quote(f"NSE:{nse_sym}")
            data  = quote[f"NSE:{nse_sym}"]
            return {
                "symbol": symbol,
                "ltp":    data["last_price"],
                "open":   data["ohlc"]["open"],
                "high":   data["ohlc"]["high"],
                "low":    data["ohlc"]["low"],
                "close":  data["ohlc"]["close"],
                "volume": data.get("volume", 0),
            }
        except Exception as e:
            return {"symbol": symbol, "ltp": 0, "error": str(e)}

    def get_positions(self) -> list:
        try:
            positions = self.kite.positions()
            result    = []
            for pos in positions.get("net", []):
                if pos["quantity"] != 0:
                    result.append({
                        "symbol":    pos["tradingsymbol"],
                        "qty":       pos["quantity"],
                        "avg_price": pos["average_price"],
                        "ltp":       pos["last_price"],
                        "pnl":       pos["pnl"],
                        "pnl_pct":   pos["pnl"] / (pos["average_price"] * abs(pos["quantity"])) * 100
                                     if pos["average_price"] > 0 else 0,
                        "value":     pos["last_price"] * pos["quantity"],
                    })
            return result
        except Exception as e:
            print(f"  [Zerodha] get_positions error: {e}")
            return []

    def place_order(self, symbol: str, side: str,
                    qty: int, order_type: str = "MARKET",
                    price: float = 0) -> dict:
        from kiteconnect import KiteConnect
        nse_sym    = self._nse_symbol(symbol)
        trans_type = self.kite.TRANSACTION_TYPE_BUY if side == "BUY" \
                     else self.kite.TRANSACTION_TYPE_SELL
        try:
            order_id = self.kite.place_order(
                variety       = self.kite.VARIETY_REGULAR,
                exchange      = self.kite.EXCHANGE_NSE,
                tradingsymbol = nse_sym,
                transaction_type = trans_type,
                quantity      = qty,
                product       = self.kite.PRODUCT_CNC,   # CNC = delivery (not intraday)
                order_type    = self.kite.ORDER_TYPE_MARKET if order_type == "MARKET"
                                else self.kite.ORDER_TYPE_LIMIT,
                price         = price if order_type == "LIMIT" else None,
            )
            print(f"  [Zerodha ORDER] {side} {qty} {nse_sym}  OrderID={order_id}")
            return {"order_id": order_id, "status": "PLACED", "symbol": symbol,
                    "side": side, "qty": qty}
        except Exception as e:
            print(f"  [Zerodha] place_order error: {e}")
            return {"status": "REJECTED", "reason": str(e)}

    def cancel_order(self, order_id: str) -> bool:
        try:
            self.kite.cancel_order(variety=self.kite.VARIETY_REGULAR,
                                   order_id=order_id)
            return True
        except Exception:
            return False

    def get_funds(self) -> dict:
        try:
            margins = self.kite.margins()
            equity  = margins.get("equity", {})
            return {
                "available_cash": equity.get("available", {}).get("cash", 0),
                "used_margin":    equity.get("utilised", {}).get("debits", 0),
                "total":          equity.get("net", 0),
            }
        except Exception as e:
            return {"error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# ANGEL BROKING (SmartAPI — free, good for beginners)
# ══════════════════════════════════════════════════════════════════════════════

class AngelBroker(BrokerBase):
    """
    Angel Broking SmartAPI integration.
    Free API. Install: pip install smartapi-python
    Register at: smartapi.angelbroking.com
    """

    def __init__(self, api_key: str, client_id: str,
                 password: str, totp_secret: str = None):
        try:
            from SmartApi import SmartConnect
            import pyotp
        except ImportError:
            raise ImportError("Install: pip install smartapi-python pyotp")

        import pyotp
        self.obj = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now() if totp_secret else input("Enter TOTP: ")
        data = self.obj.generateSession(client_id, password, totp)
        if data["status"]:
            self.auth_token    = data["data"]["jwtToken"]
            self.refresh_token = data["data"]["refreshToken"]
            print(f"  [Angel] Logged in as {client_id}")
        else:
            raise Exception(f"Angel login failed: {data['message']}")

    def get_quote(self, symbol: str) -> dict:
        clean = symbol.replace(".NS", "")
        try:
            data = self.obj.ltpData("NSE", clean, None)
            ltp  = data["data"]["ltp"]
            return {"symbol": symbol, "ltp": ltp, "close": ltp}
        except Exception as e:
            return {"symbol": symbol, "ltp": 0, "error": str(e)}

    def get_positions(self) -> list:
        try:
            data = self.obj.position()
            return data.get("data", []) or []
        except Exception:
            return []

    def place_order(self, symbol: str, side: str,
                    qty: int, order_type: str = "MARKET",
                    price: float = 0) -> dict:
        clean = symbol.replace(".NS", "")
        try:
            params = {
                "variety":         "NORMAL",
                "tradingsymbol":   clean,
                "symboltoken":     self._get_token(clean),
                "transactiontype": side,
                "exchange":        "NSE",
                "ordertype":       order_type,
                "producttype":     "DELIVERY",
                "duration":        "DAY",
                "price":           str(price) if order_type == "LIMIT" else "0",
                "quantity":        str(qty),
            }
            resp = self.obj.placeOrder(params)
            return {"order_id": resp["data"]["orderid"],
                    "status": "PLACED", "symbol": symbol}
        except Exception as e:
            return {"status": "REJECTED", "reason": str(e)}

    def _get_token(self, symbol: str) -> str:
        """Look up symbol token for Angel API."""
        # In production, maintain a symbol→token mapping
        # Download from: https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json
        return "0"   # placeholder — implement with full symbol master

    def cancel_order(self, order_id: str) -> bool:
        try:
            self.obj.cancelOrder(order_id, "NORMAL")
            return True
        except Exception:
            return False

    def get_funds(self) -> dict:
        try:
            data = self.obj.rmsLimit()
            d    = data.get("data", {})
            return {
                "available_cash": float(d.get("availablecash", 0)),
                "used_margin":    float(d.get("utiliseddebits", 0)),
                "total":          float(d.get("net", 0)),
            }
        except Exception as e:
            return {"error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# FACTORY — returns the right broker based on config
# ══════════════════════════════════════════════════════════════════════════════

def get_broker(broker_name: str = None) -> BrokerBase:
    """
    Returns the appropriate broker instance based on config.BROKER.
    Usage:
        broker = get_broker()
        quote  = broker.get_quote("NIFTYBEES.NS")
        broker.place_order("NIFTYBEES.NS", "BUY", 10)
    """
    try:
        import config as cfg
    except ImportError:
        class cfg:
            BROKER              = broker_name or "paper"
            ZERODHA_API_KEY     = ""
            ZERODHA_API_SECRET  = ""
            ANGEL_API_KEY       = ""
            ANGEL_CLIENT_ID     = ""
            ANGEL_PASSWORD      = ""
            ANGEL_TOTP_SECRET   = ""
            MAX_CAPITAL_INR     = 100000
            PRIMARY_TICKER      = "NIFTYBEES.NS"

    name = (broker_name or cfg.BROKER).lower()

    if name == "paper":
        csv_path = f"data/{cfg.PRIMARY_TICKER.replace('.NS','')}.csv"
        return PaperBroker(csv_path=csv_path,
                           initial_capital=cfg.MAX_CAPITAL_INR)

    elif name == "zerodha":
        if not cfg.ZERODHA_API_KEY:
            raise ValueError("Set ZERODHA_API_KEY in config.py")
        # Load saved token if available
        token_file = Path("broker/zerodha_token.json")
        access_token = None
        if token_file.exists():
            with open(token_file) as f:
                data = json.load(f)
            import datetime
            if data.get("date") == str(datetime.date.today()):
                access_token = data["token"]
        return ZerodhaBroker(cfg.ZERODHA_API_KEY, cfg.ZERODHA_API_SECRET,
                             access_token)

    elif name == "angel":
        if not cfg.ANGEL_API_KEY:
            raise ValueError("Set ANGEL_API_KEY in config.py")
        return AngelBroker(cfg.ANGEL_API_KEY, cfg.ANGEL_CLIENT_ID,
                           cfg.ANGEL_PASSWORD, cfg.ANGEL_TOTP_SECRET)

    else:
        raise ValueError(f"Unknown broker: {name}. Use 'paper', 'zerodha', or 'angel'")
