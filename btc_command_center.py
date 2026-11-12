import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import json
import threading
import time

API_BASE = "https://external-api.kalshi.com/trade-api/v2"
SERIES = "KXBTC15M"
POLL_SECONDS = 5

BG = "#061326"
PANEL = "#0B1F3A"
PANEL2 = "#102B4C"
BLUE = "#19BFFF"
CYAN = "#65DFFF"
WHITE = "#F1F8FF"
MUTED = "#8DAFCF"
GREEN = "#20F59A"
RED = "#FF426D"
YELLOW = "#FFD34E"

def parse_time(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def money(value):
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "Not posted"

def market_request():
    query = urlencode({"series_ticker": SERIES, "status": "open", "limit": 20})
    url = f"{API_BASE}/markets?{query}"
    req = Request(url, headers={"User-Agent": "BTC-Command-Center/0.1"})
    with urlopen(req, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))

def choose_market(payload):
    markets = payload.get("markets", [])
    now = datetime.now(timezone.utc)
    candidates = []
    for market in markets:
        status = str(market.get("status", "")).lower()
        close_dt = parse_time(market.get("close_time") or market.get("expected_expiration_time"))
        if status in ("active", "open", "") and close_dt and close_dt > now:
            candidates.append((close_dt, market))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]

class Dashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("BTC Command Center | Kalshi 15M")
        self.root.geometry("1220x790")
        self.root.minsize(980, 680)
        self.root.configure(bg=BG)
        self.market = None
        self.last_update = None
        self.running = True
        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_market()
        self.tick_clock()

    def panel(self, parent, title, value, subtitle="", accent=BLUE, value_size=26):
        frame = tk.Frame(parent, bg=PANEL, highlightbackground=accent, highlightthickness=1, bd=0)
        tk.Label(frame, text=title.upper(), bg=PANEL, fg=CYAN,
                 font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=16, pady=(13, 2))
        val = tk.Label(frame, text=value, bg=PANEL, fg=WHITE,
                       font=("Segoe UI Semibold", value_size))
        val.pack(anchor="w", padx=16, pady=(3, 0))
        sub = tk.Label(frame, text=subtitle, bg=PANEL, fg=MUTED,
                       font=("Segoe UI", 9))
        sub.pack(anchor="w", padx=16, pady=(1, 13))
        return frame, val, sub

    def build_ui(self):
        header = tk.Frame(self.root, bg="#081A31", highlightbackground=BLUE, highlightthickness=1)
        header.pack(fill="x", padx=18, pady=(16, 12))
        left = tk.Frame(header, bg="#081A31")
        left.pack(side="left", padx=18, pady=14)
        tk.Label(left, text="₿", bg="#081A31", fg="#FFB22E",
                 font=("Segoe UI Symbol", 38, "bold")).pack(side="left", padx=(0, 14))
        titlebox = tk.Frame(left, bg="#081A31")
        titlebox.pack(side="left")
        tk.Label(titlebox, text="BTC COMMAND CENTER", bg="#081A31", fg=WHITE,
                 font=("Segoe UI Semibold", 24, "bold")).pack(anchor="w")
        tk.Label(titlebox, text="KALSHI  •  15-MINUTE MARKETS  •  LIVE MARKET DISCOVERY",
                 bg="#081A31", fg=CYAN, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        right = tk.Frame(header, bg="#081A31")
        right.pack(side="right", padx=18, pady=18)
        self.conn_dot = tk.Label(right, text="●", bg="#081A31", fg=YELLOW, font=("Segoe UI", 16))
        self.conn_dot.pack(side="left")
        self.conn_text = tk.Label(right, text="CONNECTING TO KALSHI", bg="#081A31", fg=CYAN,
                                  font=("Segoe UI Semibold", 10))
        self.conn_text.pack(side="left", padx=8)

        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=18)
        self.price_frame, self.price_val, self.price_sub = self.panel(
            top, "BRTI settlement reference", "NOT CONNECTED", "Live benchmark feed is not yet configured", BLUE, 22)
        self.target_frame, self.target_val, self.target_sub = self.panel(
            top, "Automatically detected target", "SEARCHING...", "Kalshi KXBTC15M market strike", CYAN, 26)
        self.count_frame, self.count_val, self.count_sub = self.panel(
            top, "Market countdown", "--:--", "Time until contract close", BLUE, 28)
        for f in (self.price_frame, self.target_frame, self.count_frame):
            f.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.count_frame.pack_configure(padx=(0, 0))

        mid = tk.Frame(self.root, bg=BG)
        mid.pack(fill="x", padx=18, pady=12)
        self.direction_frame, self.direction_val, self.direction_sub = self.panel(
            mid, "Final direction", "WAITING FOR BRTI", "No direction until the official reference feed is connected", GREEN, 25)
        self.risk_frame, self.risk_val, self.risk_sub = self.panel(
            mid, "Flip risk", "UNAVAILABLE", "Requires live BRTI price history", YELLOW, 22)
        self.warning_frame, self.warning_val, self.warning_sub = self.panel(
            mid, "Flip warning", "DATA REQUIRED", "No unverified warning calculations", YELLOW, 22)
        for f in (self.direction_frame, self.risk_frame, self.warning_frame):
            f.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.warning_frame.pack_configure(padx=(0, 0))

        signals = tk.Frame(self.root, bg="#081A31", highlightbackground=BLUE, highlightthickness=1)
        signals.pack(fill="x", padx=18, pady=(0, 12))
        tk.Label(signals, text="SCALP SIGNAL CENTER", bg="#081A31", fg=WHITE,
                 font=("Segoe UI Semibold", 16)).pack(anchor="w", padx=16, pady=(13, 2))
        tk.Label(signals, text="Signals remain on WAIT until the correct BRTI feed and price history are connected.",
                 bg="#081A31", fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(0, 12))
        row = tk.Frame(signals, bg="#081A31")
        row.pack(fill="x", padx=14, pady=(0, 14))
        self.signal_labels = []
        for text, color in (("BUY YES", GREEN), ("WAIT", BLUE), ("BUY NO", RED)):
            box = tk.Frame(row, bg=PANEL2, highlightbackground=color, highlightthickness=2)
            box.pack(side="left", fill="both", expand=True, padx=5)
            lab = tk.Label(box, text=text, bg=PANEL2, fg=color,
                           font=("Segoe UI Semibold", 22, "bold"))
            lab.pack(pady=(14, 2))
            sub = tk.Label(box, text="NOT ACTIVE", bg=PANEL2, fg=MUTED, font=("Segoe UI", 9))
            sub.pack(pady=(0, 14))
            self.signal_labels.append((lab, sub))

        details = tk.Frame(self.root, bg=PANEL, highlightbackground="#1766A0", highlightthickness=1)
        details.pack(fill="x", padx=18, pady=(0, 10))
        self.market_text = tk.Label(details, text="MARKET: Discovering active KXBTC15M contract...",
                                    bg=PANEL, fg=CYAN, font=("Consolas", 10), anchor="w")
        self.market_text.pack(fill="x", padx=16, pady=(12, 5))
        self.contract_text = tk.Label(details, text="YES / NO quotes: waiting for market data",
                                      bg=PANEL, fg=WHITE, font=("Segoe UI", 10), anchor="w")
        self.contract_text.pack(fill="x", padx=16, pady=3)
        self.updated_text = tk.Label(details, text="Last update: --",
                                     bg=PANEL, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.updated_text.pack(fill="x", padx=16, pady=(3, 12))

        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=18, pady=(0, 12))
        tk.Label(footer, text="READ-ONLY MODE  •  NO ORDERS ARE PLACED  •  MARKET DATA MAY BE DELAYED",
                 bg=BG, fg="#7196BA", font=("Segoe UI", 8, "bold")).pack(side="left")
        tk.Button(footer, text="REFRESH MARKET", command=self.refresh_market,
                  bg="#0D4775", fg=WHITE, activebackground="#12649F",
                  activeforeground=WHITE, relief="flat", padx=16, pady=8,
                  font=("Segoe UI Semibold", 9)).pack(side="right")

    def refresh_market(self):
        if not self.running:
            return
        self.conn_text.config(text="CHECKING KALSHI...")
        self.conn_dot.config(fg=YELLOW)
        threading.Thread(target=self.fetch_worker, daemon=True).start()
        self.root.after(POLL_SECONDS * 1000, self.refresh_market)

    def fetch_worker(self):
        try:
            payload = market_request()
            market = choose_market(payload)
            self.root.after(0, lambda: self.update_market(market))
        except Exception as exc:
            msg = str(exc)[:120]
            self.root.after(0, lambda: self.connection_error(msg))

    def connection_error(self, message):
        self.conn_text.config(text="KALSHI CONNECTION ISSUE")
        self.conn_dot.config(fg=RED)
        self.market_text.config(text=f"Market data error: {message}")
        self.updated_text.config(text="Check internet access, then press REFRESH MARKET.")

    def update_market(self, market):
        if not market:
            self.conn_text.config(text="NO ACTIVE MARKET FOUND")
            self.conn_dot.config(fg=YELLOW)
            self.target_val.config(text="NOT POSTED")
            self.target_sub.config(text="Kalshi has not returned an active strike")
            self.market_text.config(text="MARKET: No currently open KXBTC15M contract found.")
            return
        self.market = market
        self.conn_text.config(text="KALSHI MARKET CONNECTED")
        self.conn_dot.config(fg=GREEN)
        strike = market.get("floor_strike")
        self.target_val.config(text=money(strike) if strike is not None else "NOT POSTED")
        self.target_sub.config(text=f"Target from Kalshi • {market.get('ticker', 'ticker unavailable')}")
        close_dt = parse_time(market.get("close_time") or market.get("expected_expiration_time"))
        self.count_sub.config(text="Contract close time (UTC converted to local display)")
        if close_dt:
            self.close_dt = close_dt
            self.update_countdown()
        self.market_text.config(text=f"MARKET: {market.get('ticker', 'Unknown')}   |   STATUS: {market.get('status', 'Unknown')}   |   SERIES: {SERIES}")
        yes_bid = market.get("yes_bid_dollars", market.get("yes_bid"))
        yes_ask = market.get("yes_ask_dollars", market.get("yes_ask"))
        no_bid = market.get("no_bid_dollars", market.get("no_bid"))
        no_ask = market.get("no_ask_dollars", market.get("no_ask"))
        self.contract_text.config(text=f"YES bid/ask: {yes_bid if yes_bid is not None else '--'} / {yes_ask if yes_ask is not None else '--'}     •     NO bid/ask: {no_bid if no_bid is not None else '--'} / {no_ask if no_ask is not None else '--'}")
        self.updated_text.config(text=f"Last market refresh: {datetime.now().astimezone().strftime('%Y-%m-%d %I:%M:%S %p %Z')}   •   Refreshes every {POLL_SECONDS}s")
        self.price_val.config(text="NOT CONNECTED")
        self.direction_val.config(text="WAITING FOR BRTI")
        self.risk_val.config(text="UNAVAILABLE")
        self.warning_val.config(text="DATA REQUIRED")

    def update_countdown(self):
        if not hasattr(self, "close_dt"):
            return
        seconds = max(0, int((self.close_dt - datetime.now(timezone.utc)).total_seconds()))
        mins, secs = divmod(seconds, 60)
        self.count_val.config(text=f"{mins:02d}:{secs:02d}")
        if seconds == 0:
            self.count_sub.config(text="Market close reached • waiting for next contract")
        else:
            self.count_sub.config(text="Time remaining until contract close")

    def tick_clock(self):
        if not self.running:
            return
        self.update_countdown()
        self.root.after(1000, self.tick_clock)

    def close(self):
        self.running = False
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = Dashboard(root)
    root.mainloop()
