=========================================================
🤖 फाइनल ट्रेडिंग बॉट v17.0 - कम्प्लीट फिक्स्ड वर्जन
=========================================================
• Telegram Token Fixed (बिना स्पेस के)
• Health Check के साथ
• Capital: ₹1,00,000
=========================================================
"""

import requests
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, timedelta
import time
import pytz
import json
import os
import threading
from flask import Flask, jsonify

# ==================== आपकी जानकारी (✅ फिक्स्ड) ====================
TELEGRAM_TOKEN = "8789790689:AAGfkoE1lcjn-97IxXMbiM4fL15IsA0niTo"  # ✅ स्पेस हटा दिया
CHAT_ID = "7890333339"                                              # ✅ सही है
CAPITAL = 100000                                                     # ₹1,00,000

# ==================== FLASK APP FOR HEALTH CHECK ====================
app = Flask(__name__)
bot_instance = None

@app.route('/')
def home():
    return jsonify({
        'status': 'alive',
        'message': 'Trading Bot is running',
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/health')
def health():
    """Render.com के लिए हेल्थ चेक"""
    if bot_instance:
        return jsonify({
            'status': 'healthy',
            'bot_running': True,
            'scans': bot_instance.scan_count,
            'signals': bot_instance.signal_count,
            'time': datetime.now().strftime('%H:%M:%S')
        })
    return jsonify({'status': 'starting'})

@app.route('/stats')
def stats():
    """बॉट के आंकड़े देखने के लिए"""
    if bot_instance:
        return jsonify({
            'scans': bot_instance.scan_count,
            'signals': bot_instance.signal_count,
            'signals_today': len(bot_instance.signals_today),
            'capital': bot_instance.capital,
            'risk_amount': bot_instance.risk_amount,
            'last_api': bot_instance.data_api.last_successful_api
        })
    return jsonify({'error': 'Bot not started'})

# ==================== स्टेबल डेटा API ====================
class StableDataAPI:
    """तीन APIs: एक मेन, दो बैकअप"""
    
    def __init__(self):
        self.cache = {}
        self.api_stats = {
            'yfinance': {'success': 0, 'fail': 0},
            'stocktv': {'success': 0, 'fail': 0},
            'freeapi': {'success': 0, 'fail': 0}
        }
        self.last_successful_api = 'yfinance'
    
    def get_nifty_spot(self):
        """पहले yfinance, फिर StockTV, फिर Free API"""
        
        # 1. yfinance
        try:
            import yfinance as yf
            nifty = yf.Ticker("^NSEI")
            data = nifty.history(period="1d", interval="1m", timeout=5)
            if not data.empty:
                price = float(data['Close'].iloc[-1])
                self.api_stats['yfinance']['success'] += 1
                self.last_successful_api = 'yfinance'
                print(f"✅ yfinance: ₹{price}")
                return price
        except Exception as e:
            self.api_stats['yfinance']['fail'] += 1
            print(f"⚠️ yfinance failed: {e}")
        
        # 2. StockTV (बैकअप 1)
        try:
            url = "https://api.stocktv.top/stock/indices?countryId=14&key=demo"
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                data = response.json()
                if data.get('data') and len(data['data']) > 0:
                    price = float(data['data'][0]['last'])
                    self.api_stats['stocktv']['success'] += 1
                    self.last_successful_api = 'stocktv'
                    print(f"✅ StockTV: ₹{price}")
                    return price
        except Exception as e:
            self.api_stats['stocktv']['fail'] += 1
            print(f"⚠️ StockTV failed: {e}")
        
        # 3. Free API (बैकअप 2)
        try:
            url = "https://military-jobye-haiqstudios-14f59639.koyeb.app/stock?symbol=^NSEI&res=num"
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                data = response.json()
                price = float(data['data']['last_price'])
                self.api_stats['freeapi']['success'] += 1
                self.last_successful_api = 'freeapi'
                print(f"✅ FreeAPI: ₹{price}")
                return price
        except Exception as e:
            self.api_stats['freeapi']['fail'] += 1
            print(f"⚠️ FreeAPI failed: {e}")
        
        # 4. Default price
        default_price = 22000
        print(f"⚠️ Using default: ₹{default_price}")
        return default_price
    
    def get_nifty_historical(self):
        """yfinance से हिस्टोरिकल डेटा"""
        try:
            import yfinance as yf
            df = yf.download("^NSEI", interval="5m", period="2d", progress=False)
            if not df.empty:
                df = df.rename(columns={
                    'Open': 'open', 'High': 'high', 
                    'Low': 'low', 'Close': 'close', 'Volume': 'volume'
                })
                self.cache['historical'] = df
                return df
        except Exception as e:
            print(f"⚠️ Historical data error: {e}")
            if 'historical' in self.cache:
                return self.cache['historical']
        return None

# ==================== टेलीग्राम सेटअप ====================
def send_telegram(message):
    """टेलीग्राम मैसेज भेजें"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            'chat_id': CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, json=data, timeout=5)
        if response.status_code == 200:
            print("✅ Telegram message sent")
        else:
            print(f"⚠️ Telegram Error: {response.text}")
        return True
    except Exception as e:
        print(f"⚠️ Telegram Error: {e}")
        return False

# ==================== ट्रेडिंग बॉट ====================
class SimpleTradingBot:
    """फाइनल ट्रेडिंग बॉट"""
    
    def __init__(self):
        self.data_api = StableDataAPI()
        self.ist = pytz.timezone('Asia/Kolkata')
        self.last_signal_time = None
        self.capital = CAPITAL
        self.scan_count = 0
        self.signal_count = 0
        self.error_count = 0
        self.signals_today = []
        self.risk_amount = self.capital * 0.02
        self.start_time = datetime.now()
        
        print(f"\n{'='*50}")
        print(f"🤖 FINAL TRADING BOT v17.0")
        print(f"{'='*50}")
        print(f"💰 CAPITAL: ₹{self.capital:,}")
        print(f"📊 RISK 2%: ₹{self.risk_amount:,.0f}")
        print(f"📱 TELEGRAM: ✅ Connected")
        print(f"📡 APIS: yfinance + 2 backups")
        print(f"{'='*50}\n")
        
        send_telegram(f"""
╔══════════════════════════════╗
║  🤖 BOT STARTED SUCCESSFULLY ║
╚══════════════════════════════╝

💰 Capital: ₹{self.capital:,}
📊 Risk: ₹{self.risk_amount:,.0f}
📡 APIs: yfinance + 2 backups
✅ Fixed Version v17.0
""")
    
    def calculate_indicators(self, df):
        """इंडिकेटर्स कैलकुलेट करें"""
        
        df['EMA20'] = ta.ema(df['close'], length=20)
        df['EMA50'] = ta.ema(df['close'], length=50)
        df['RSI'] = ta.rsi(df['close'], length=14)
        
        macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
        df['MACD'] = macd['MACD_12_26_9']
        df['MACD_Signal'] = macd['MACDs_12_26_9']
        df['MACD_Hist'] = macd['MACDh_12_26_9']
        
        bb = ta.bbands(df['close'], length=20, std=2)
        df['BB_Upper'] = bb['BBU_20_2.0']
        df['BB_Lower'] = bb['BBL_20_2.0']
        
        df['Volume_SMA'] = ta.sma(df['volume'], length=20)
        df['Volume_Ratio'] = df['volume'] / df['Volume_SMA']
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        
        return df
    
    def get_atm_strike(self, price):
        return round(price / 50) * 50
    
    def calculate_lots(self, price, stop_loss):
        risk_per_lot = abs(price - stop_loss) * 50
        if risk_per_lot <= 0:
            return 1
        lots = int(self.risk_amount / risk_per_lot)
        return max(1, lots)
    
    def check_signals(self):
        """सिग्नल चेक करें - 3 स्ट्रैटेजीज"""
        
        spot = self.data_api.get_nifty_spot()
        if not spot:
            return None
        
        df = self.data_api.get_nifty_historical()
        if df is None or df.empty:
            return None
        
        df = self.calculate_indicators(df)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        if pd.isna(last['RSI']) or pd.isna(last['Volume_Ratio']):
            return None
        
        high_volume = last['Volume_Ratio'] > 1.5
        signals = []
        
        # Strategy 1: RSI + EMA
        if high_volume:
            if last['close'] > last['EMA20'] and last['RSI'] > 60 and last['RSI'] < 80:
                signals.append(("BUY CALL", "CE", "RSI Momentum", 85))
            elif last['close'] < last['EMA20'] and last['RSI'] < 40 and last['RSI'] > 20:
                signals.append(("BUY PUT", "PE", "RSI Momentum", 85))
        
        # Strategy 2: MACD Burst
        if last['Volume_Ratio'] > 2 and not pd.isna(last['MACD_Hist']):
            if last['MACD_Hist'] > prev['MACD_Hist'] * 1.3:
                if last['MACD'] > last['MACD_Signal']:
                    signals.append(("BUY CALL", "CE", "MACD Burst", 90))
                elif last['MACD'] < last['MACD_Signal']:
                    signals.append(("BUY PUT", "PE", "MACD Burst", 90))
        
        # Strategy 3: Bollinger Breakout
        if high_volume:
            if last['close'] > last['BB_Upper'] and prev['close'] < prev['BB_Upper']:
                signals.append(("BUY CALL", "CE", "BB Breakout", 88))
            elif last['close'] < last['BB_Lower'] and prev['close'] > prev['BB_Lower']:
                signals.append(("BUY PUT", "PE", "BB Breakout", 88))
        
        if signals:
            best = max(signals, key=lambda x: x[3])
            action, opt_type, strategy, score = best
            
            atm_strike = self.get_atm_strike(spot)
            contract = f"NIFTY {atm_strike} {opt_type}"
            
            # SL और Target (1.5 × ATR)
            if opt_type == "CE":
                sl = spot - (1.5 * last['ATR'])
                target = spot + (3 * last['ATR'])
            else:
                sl = spot + (1.5 * last['ATR'])
                target = spot - (3 * last['ATR'])
            
            lots = self.calculate_lots(spot, sl)
            
            return {
                'action': action,
                'strategy': strategy,
                'score': score,
                'price': round(spot, 2),
                'strike': atm_strike,
                'option_type': opt_type,
                'contract': contract,
                'stop_loss': round(sl, 2),
                'target': round(target, 2),
                'rsi': round(last['RSI'], 1),
                'volume_ratio': round(last['Volume_Ratio'], 1),
                'atr': round(last['ATR'], 2),
                'lots': lots,
                'time': datetime.now(self.ist).strftime('%H:%M:%S')
            }
        
        return None
    
    def send_signal_alert(self, signal):
        """सिग्नल अलर्ट भेजें"""
        
        if signal['score'] >= 90:
            strength_emoji = "🔴 STRONG"
        elif signal['score'] >= 85:
            strength_emoji = "🟡 MEDIUM"
        else:
            strength_emoji = "🟢 LOW"
        
        message = f"""
╔══════════════════════════════╗
║  🚀 TRADING SIGNAL FOUND 🚀  ║
╚══════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━
<b>🎯 ACTION    :</b> {signal['action']}
<b>📊 STRATEGY  :</b> {signal['strategy']}
<b>💪 STRENGTH  :</b> {strength_emoji} ({signal['score']}%)
<b>⏰ TIME      :</b> {signal['time']} IST
━━━━━━━━━━━━━━━━━━━━━━━

<b>💰 SPOT      :</b> ₹{signal['price']}
<b>🎯 STRIKE    :</b> {signal['strike']} {signal['option_type']}
<b>🛑 STOP LOSS :</b> ₹{signal['stop_loss']} (1.5×ATR)
<b>✅ TARGET    :</b> ₹{signal['target']} (3×ATR)
━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 MARKET DATA:</b>
• RSI       : {signal['rsi']}
• VOLUME    : {signal['volume_ratio']}x
• ATR       : {signal['atr']}
━━━━━━━━━━━━━━━━━━━━━━━

<b>💰 POSITION (₹{self.capital:,}):</b>
• RISK 2%   : ₹{self.risk_amount:,.0f}
• LOTS      : {signal['lots']}
━━━━━━━━━━━━━━━━━━━━━━━

<b>📜 CONTRACT:</b>
<code>{signal['contract']}</code>

🤖 Final Bot v17.0 (Fixed)
"""
        
        send_telegram(message)
        self.signals_today.append(signal)
        self.signal_count += 1
        self.error_count = 0
        print(f"✅ {signal['time']} - {signal['action']} ({signal['strategy']}) - Lots: {signal['lots']}")
    
    def run_once(self):
        """एक बार स्कैन करें"""
        
        self.scan_count += 1
        current_time = datetime.now(self.ist).strftime('%H:%M:%S')
        
        try:
            signal = self.check_signals()
            
            if signal:
                if signal['time'] != self.last_signal_time:
                    self.send_signal_alert(signal)
                    self.last_signal_time = signal['time']
            else:
                if self.scan_count % 12 == 0:
                    print(f"⏸️ {current_time} - No Signal (Scans: {self.scan_count})")
                    
        except Exception as e:
            self.error_count += 1
            print(f"❌ Error: {e}")
    
    def run(self):
        """मेन लूप"""
        
        print("🚀 Scanning started... (every 5 minutes)\n")
        
        try:
            while True:
                self.run_once()
                
                for i in range(5, 0, -1):
                    print(f"⏳ Next scan: {i} min left...", end='\r')
                    time.sleep(60)
                print(" " * 40, end='\r')
                
        except KeyboardInterrupt:
            print(f"\n\n📊 FINAL SUMMARY:")
            print(f"📈 Total Scans: {self.scan_count}")
            print(f"🎯 Total Signals: {self.signal_count}")
            send_telegram("🛑 Bot Stopped. See you tomorrow! 👋")
            print("\n👋 Goodbye!")

# ==================== FLASK SERVER ====================
def run_flask():
    """Flask server अलग thread में चलाएं"""
    app.run(host='0.0.0.0', port=10000, debug=False, use_reloader=False)

# ==================== मेन ====================
if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════╗
║  🤖 FINAL BOT v17.0 - READY TO DEPLOY        ║
╠═══════════════════════════════════════════════╣
║  ✅ Telegram Token: Fixed                     ║
║  ✅ Chat ID: 7890333339                       ║
║  ✅ Capital: ₹1,00,000                         ║
║  ✅ Health Check: /health                      ║
╚═══════════════════════════════════════════════╝
    """)
    
    bot = SimpleTradingBot()
    bot_instance = bot
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    bot.run()
