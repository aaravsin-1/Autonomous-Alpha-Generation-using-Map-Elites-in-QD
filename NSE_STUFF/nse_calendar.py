"""
nse_calendar.py
NSE market calendar for India.
Checks if today is a trading day, handles IST timezone.
"""

import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

# NSE trading hours
MARKET_OPEN_HOUR   = 9
MARKET_OPEN_MIN    = 15
MARKET_CLOSE_HOUR  = 15
MARKET_CLOSE_MIN   = 30

# NSE holidays 2025-2026
# Source: NSE India official holiday calendar
NSE_HOLIDAYS = {
    # 2025
    datetime.date(2025, 1, 26),   # Republic Day
    datetime.date(2025, 2, 26),   # Mahashivratri
    datetime.date(2025, 3, 14),   # Holi
    datetime.date(2025, 3, 31),   # Id-Ul-Fitr (Ramzan Eid)
    datetime.date(2025, 4, 10),   # Shri Ram Navami
    datetime.date(2025, 4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    datetime.date(2025, 4, 18),   # Good Friday
    datetime.date(2025, 5, 1),    # Maharashtra Day
    datetime.date(2025, 8, 15),   # Independence Day
    datetime.date(2025, 8, 27),   # Ganesh Chaturthi
    datetime.date(2025, 10, 2),   # Gandhi Jayanti / Dussehra
    datetime.date(2025, 10, 24),  # Diwali Laxmi Pujan (Muhurat trading day — special)
    datetime.date(2025, 10, 25),  # Diwali Balipratipada
    datetime.date(2025, 11, 5),   # Prakash Gurpurb Sri Guru Nanak Dev Ji
    datetime.date(2025, 12, 25),  # Christmas
    # 2026
    datetime.date(2026, 1, 26),   # Republic Day
    datetime.date(2026, 3, 20),   # Holi
    datetime.date(2026, 4, 3),    # Good Friday
    datetime.date(2026, 4, 14),   # Dr. Baba Saheb Ambedkar Jayanti
    datetime.date(2026, 4, 17),   # Shri Ram Navami
    datetime.date(2026, 5, 1),    # Maharashtra Day
    datetime.date(2026, 8, 15),   # Independence Day
    datetime.date(2026, 10, 2),   # Gandhi Jayanti
    datetime.date(2026, 12, 25),  # Christmas
}


def now_ist() -> datetime.datetime:
    return datetime.datetime.now(IST)


def today_ist() -> datetime.date:
    return now_ist().date()


def is_trading_day(date: datetime.date = None) -> bool:
    if date is None:
        date = today_ist()
    # Weekends
    if date.weekday() >= 5:
        return False
    # NSE holidays
    if date in NSE_HOLIDAYS:
        return False
    return True


def is_market_open() -> bool:
    """Is the NSE market currently open?"""
    now = now_ist()
    if not is_trading_day(now.date()):
        return False
    open_time  = now.replace(hour=MARKET_OPEN_HOUR,  minute=MARKET_OPEN_MIN,  second=0)
    close_time = now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MIN, second=0)
    return open_time <= now <= close_time


def is_pre_market() -> bool:
    """Is it pre-market session (9:00-9:15 AM IST)?"""
    now = now_ist()
    if not is_trading_day(now.date()):
        return False
    pre_open = now.replace(hour=9, minute=0, second=0)
    open_time = now.replace(hour=9, minute=15, second=0)
    return pre_open <= now < open_time


def minutes_to_open() -> int:
    """Minutes until market opens. Negative if already open."""
    now = now_ist()
    open_time = now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MIN, second=0)
    delta = open_time - now
    return int(delta.total_seconds() / 60)


def minutes_to_close() -> int:
    """Minutes until market closes."""
    now = now_ist()
    close_time = now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MIN, second=0)
    delta = close_time - now
    return int(delta.total_seconds() / 60)


def next_trading_day(from_date: datetime.date = None) -> datetime.date:
    if from_date is None:
        from_date = today_ist()
    d = from_date + datetime.timedelta(days=1)
    while not is_trading_day(d):
        d += datetime.timedelta(days=1)
    return d


def last_trading_day(from_date: datetime.date = None) -> datetime.date:
    if from_date is None:
        from_date = today_ist()
    d = from_date - datetime.timedelta(days=1)
    while not is_trading_day(d):
        d -= datetime.timedelta(days=1)
    return d


if __name__ == "__main__":
    print(f"Today (IST)    : {today_ist()}")
    print(f"Trading day    : {is_trading_day()}")
    print(f"Market open now: {is_market_open()}")
    if is_trading_day():
        print(f"Mins to open   : {minutes_to_open()}")
        print(f"Mins to close  : {minutes_to_close()}")
    print(f"Next trade day : {next_trading_day()}")
