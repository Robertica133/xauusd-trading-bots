import os
import sys
import time
import json
import threading
from datetime import datetime, timedelta

try:
    import requests
    import pandas as pd
    from ta.momentum import RSIIndicator
    from ta.trend import EMAIndicator, MACD
    from ta.volatility import BollingerBands, AverageTrueRange
except ImportError:
    print("Se instaleaza dependentele necesare...")
    os.system("pip install pandas ta requests --quiet")
    import requests
    import pandas as pd
    from ta.momentum import RSIIndicator
    from ta.trend import EMAIndicator, MACD
    from ta.volatility import BollingerBands, AverageTrueRange

# Enable ANSI colors on Windows
os.system('')

# ANSI Color Codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
WHITE = "\033[97m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
MAGENTA = "\033[95m"

class LivePriceFetcher:
    """Fetches LIVE XAU/USD price from multiple free sources"""
    
    def __init__(self):
        self.price = 0
        self.prev_price = 0
        self.prices_history = []
        self.last_update = None
        self.source = ""
    
    def fetch_price_source1(self):
        """Primary: frankfurter.app gold proxy via currency conversion"""
        try:
            url = "https://api.frankfurter.app/latest?from=XAU&to=USD"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if 'rates' in data and 'USD' in data['rates']:
                    return float(data['rates']['USD']), "Frankfurter API"
        except:
            pass
        return None, None
    
    def fetch_price_source2(self):
        """Secondary: metals.live API"""
        try:
            url = "https://api.metals.live/v1/spot/gold"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    return float(data[0].get('price', 0)), "Metals.live"
        except:
            pass
        return None, None
    
    def fetch_price_source3(self):
        """Tertiary: goldpricez via scraping"""
        try:
            url = "https://data-asg.goldprice.org/dbXRates/USD"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if 'items' in data and len(data['items']) > 0:
                    gold_price = data['items'][0].get('xauPrice', 0)
                    if gold_price > 0:
                        return float(gold_price), "GoldPrice.org"
        except:
            pass
        return None, None

    def fetch_price_source4(self):
        """Quaternary: Free forex API"""
        try:
            url = "https://open.er-api.com/v6/latest/XAU"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if 'rates' in data and 'USD' in data['rates']:
                    return float(data['rates']['USD']), "ExchangeRate API"
        except:
            pass
        return None, None
    
    def get_live_price(self):
        """Try multiple sources to get live gold price"""
        sources = [
            self.fetch_price_source3,
            self.fetch_price_source2,
            self.fetch_price_source1,
            self.fetch_price_source4,
        ]
        
        for source_func in sources:
            price, source_name = source_func()
            if price and price > 1000:  # Sanity check - gold should be > $1000
                self.prev_price = self.price
                self.price = price
                self.source = source_name
                self.last_update = datetime.now()
                self.prices_history.append({
                    'time': datetime.now(),
                    'price': price,
                    'high': price + 0.5,
                    'low': price - 0.5
                })
                # Keep last 200 price points for indicator calculations
                if len(self.prices_history) > 200:
                    self.prices_history = self.prices_history[-200:]
                return price
        
        return None
    
    def get_dataframe(self):
        """Convert price history to DataFrame for indicator calculations"""
        if len(self.prices_history) < 30:
            return None
        
        df = pd.DataFrame(self.prices_history)
        df['Close'] = df['price']
        df['High'] = df['high']
        df['Low'] = df['low']
        df['Open'] = df['price']
        df.set_index('time', inplace=True)
        return df


class TradingBot:
    def __init__(self):
        self.position = None
        self.entry_price = 0
        self.take_profit = 0
        self.stop_loss = 0
        self.entry_time = None
        self.history = []
        self.current_price = 0
        self.pnl = 0
        self.fetcher = LivePriceFetcher()
        self.refresh_count = 0
        self.indicators_ready = False

    def calculate_indicators(self, df):
        indicators = {}...
        # (truncated for brevity)
    
    def run(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"{CYAN}{BOLD}  ══════════════════════════════════════════════════{RESET}")
        # (rest of the function)

if __name__ == '__main__':
    # Entry point of the program
    bot = TradingBot()
    bot.run()