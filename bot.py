
"""
V29 FULL BANDAR NO SYMBOL - MURNI HURUF DAN ANGKA - PISAH SCALPING DAN SWING
- Tombol murni huruf dan angka tanpa simbol logo emoji
- Chat murni huruf dan angka
- Auto pisah: AUTO SCALPING (tiap 5 menit) dan AUTO SWING (tiap 1 hari)
- ALL TF M5 M15 M30 H1 H4 D1
- COT REAL + NEWS + ORDER BLOCK + BANDAR + PIVOT SR + HISTORY 3 BULAN
"""

import os, requests, yfinance as yf, pandas as pd, json, re
from datetime import datetime, timedelta
import pytz
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from flask import Flask
import threading

TOKEN = os.environ.get("BOT_TOKEN", "ISI_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID", "")
SAUDI_TZ = pytz.timezone("Asia/Riyadh")

JAM_TERBAIK_PROB = {
    2: 86, 10: 84, 6: 83, 5: 82, 17: 81, 0: 80, 8: 79, 4: 72, 3: 70,
    11: 68, 18: 67, 13: 66, 15: 65, 1: 63, 7: 62, 16: 60, 14: 58,
    12: 55, 9: 52, 19: 50, 22: 48, 20: 46, 23: 45, 21: 44,
}
TF_PROB = {
    "M5": JAM_TERBAIK_PROB.copy(),
    "M15": JAM_TERBAIK_PROB.copy(),
    "M30": JAM_TERBAIK_PROB.copy(),
    "H1": JAM_TERBAIK_PROB.copy(),
    "H4": {0:70, 2:75, 5:78, 8:80, 10:82, 14:70, 17:77, 20:60},
    "D1": {0:65, 1:70, 2:68, 3:72, 4:75, 5:60, 6:55}
}

HISTORI_SUMBER = {
    "status": "V29 FULL BANDAR NO SYMBOL",
    "last_check": "Belum",
    "cot": "Belum",
    "news": "Belum",
    "ob": "Belum"
}

CACHE_FILE = "/tmp/history_all_tf_v29.json"
COT_CACHE = "/tmp/cot_real.json"
NEWS_CACHE = "/tmp/news_fundamental.json"

def log(msg):
    print(f"[{datetime.now(SAUDI_TZ).strftime('%H:%M:%S AST')}] {msg}")

def auto_download_all_tf():
    global JAM_TERBAIK_PROB, TF_PROB, HISTORI_SUMBER
    try:
        log("V29 AUTO DOWNLOAD ALL TF M5 M15 M30 H1 H4 D1")
        tf_config = {"M5": ("60d","5m"), "M15": ("60d","15m"), "M30": ("60d","30m"), "H1": ("730d","60m"), "D1": ("5y","1d")}
        all_data = {}
        for tf, (period, interval) in tf_config.items():
            try:
                df = yf.download("GC=F", period=period, interval=interval, progress=False, auto_adjust=True)
                if df is not None and len(df) > 20:
                    if df.index.tz is None:
                        df.index = df.index.tz_localize('UTC').tz_convert(SAUDI_TZ)
                    else:
                        df.index = df.index.tz_convert(SAUDI_TZ)
                    df_reset = df.reset_index()
                    time_col = df_reset.columns[0]
                    df_reset.rename(columns={time_col: 'Waktu'}, inplace=True)
                    for col in ['Open','High','Low','Close']:
                        try:
                            df_reset[col] = df_reset[col].astype(float)
                        except:
                            pass
                    df_reset['Waktu'] = pd.to_datetime(df_reset['Waktu']).dt.tz_localize(None)
                    df_reset['hour'] = pd.to_datetime(df_reset['Waktu']).dt.hour
                    df_reset['Trend'] = df_reset['Close'].diff().apply(lambda x: 'BUY' if x>0 else 'SELL')
                    csv_path = f"/tmp/XAUUSD_{tf}_AUTO.csv"
                    df_reset.to_csv(csv_path, index=False)
                    all_data[tf] = df_reset
                    HISTORI_SUMBER[tf] = f"{len(df_reset)} {df_reset['Waktu'].iloc[0]}->{df_reset['Waktu'].iloc[-1]}"
                    if tf in ["M5","M15","M30","H1"]:
                        per_hour = df_reset.groupby('hour').agg(total=('Close','count'), buy=('Trend', lambda x: (x=='BUY').sum()), avg_range=('Close', lambda x: x.max() - x.min()))
                        max_range = per_hour['avg_range'].max() if len(per_hour)>0 else 1
                        new_prob = {}
                        for h in range(24):
                            if h in per_hour.index:
                                row = per_hour.loc[h]
                                buy_ratio = row['buy']/row['total']*100 if row['total']>0 else 50
                                range_score = (row['avg_range']/max_range*20) if max_range>0 else 0
                                prob = 50 + (buy_ratio-50)*0.3 + range_score
                                if h in [2,5,6,10,17]:
                                    prob += 12
                                new_prob[h] = max(40, min(90, int(prob)))
                            else:
                                new_prob[h] = 50
                        for h in range(24):
                            TF_PROB[tf][h] = int(TF_PROB[tf].get(h,50)*0.7 + new_prob.get(h,50)*0.3)
                        if tf=="M5":
                            JAM_TERBAIK_PROB.update(TF_PROB[tf])
            except Exception as e:
                log(f"{tf} error {e}")
        try:
            if "H1" in all_data:
                df_h1 = all_data["H1"]
                df_h4 = df_h1.set_index('Waktu').resample('4H').agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna().reset_index()
                df_h4['Trend'] = df_h4['Close'].diff().apply(lambda x: 'BUY' if x>0 else 'SELL')
                all_data["H4"] = df_h4
                HISTORI_SUMBER["H4"] = f"{len(df_h4)} H4 resample"
        except Exception as e:
            log(f"H4 error {e}")
        with open(CACHE_FILE,'w') as f:
            json.dump({"tf_prob": TF_PROB, "jam": JAM_TERBAIK_PROB, "sumber": HISTORI_SUMBER, "updated": datetime.now(SAUDI_TZ).isoformat()}, f)
        HISTORI_SUMBER["last_check"] = f"{datetime.now(SAUDI_TZ).strftime('%d %b %H:%M')} ALL TF OK"
        log("ALL TF OK")
        return True
    except Exception as e:
        log(f"ALL TF gagal {e}")
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE,'r') as f:
                    data=json.load(f)
                    TF_PROB.update(data.get("tf_prob",{}))
                    JAM_TERBAIK_PROB.update(data.get("jam",{}))
        except:
            pass
        return False

def get_cot_real_daily():
    try:
        cot_data = {}
        try:
            url = "https://publicreporting.cftc.gov/resource/jun7-fc8e.json?$where=commodity_subgroup_name='PRECIOUS' AND commodity_name='GOLD'&$order=report_date_as_yyyy_mm_dd DESC&$limit=2"
            r = requests.get(url, timeout=10)
            if r.status_code==200 and len(r.json())>0:
                j = r.json()[0]
                noncomm_long = float(j.get('commercial_long_all',0) or j.get('noncommercial_long_all',0) or 0)
                noncomm_short = float(j.get('commercial_short_all',0) or j.get('noncommercial_short_all',0) or 0)
                net_long = noncomm_long - noncomm_short
                cot_data['source'] = 'CFTC REAL'
                cot_data['net_long'] = net_long
                cot_data['report_date'] = j.get('report_date_as_yyyy_mm_dd','')
                bias = "BULLISH" if net_long > 0 else "BEARISH"
                desc = f"CFTC REAL {cot_data['report_date']} NonComm Net Long {net_long:,.0f} Bandar Long" if net_long>0 else f"CFTC REAL {cot_data['report_date']} Net Short {net_long:,.0f}"
                prob = 75 if net_long>0 else 70
                cot_data['bias'] = bias
                cot_data['desc'] = desc
                cot_data['prob'] = prob
                with open(COT_CACHE,'w') as f:
                    json.dump(cot_data,f)
                HISTORI_SUMBER['cot'] = f"CFTC REAL {cot_data['report_date']} Net {net_long:,.0f}"
                return bias, desc, prob, cot_data
        except Exception as e:
            log(f"CFTC API error {e}")
        try:
            dxy = yf.download("DX-Y.NYB", period="5d", interval="1d", progress=False, auto_adjust=True)['Close']
            us10y = yf.download("^TNX", period="5d", interval="1d", progress=False, auto_adjust=True)['Close']
            if isinstance(dxy, pd.DataFrame):
                dxy = dxy.iloc[:,0]
                us10y = us10y.iloc[:,0] if isinstance(us10y, pd.DataFrame) else us10y
            dxy_trend = "DOWN" if dxy.iloc[-1] < dxy.iloc[-2] else "UP"
            us10y_trend = "DOWN" if us10y.iloc[-1] < us10y.iloc[-2] else "UP"
            score = 0
            if dxy_trend=="DOWN":
                score += 30
            if us10y_trend=="DOWN":
                score += 25
            bias = "BULLISH" if score>=50 else "BEARISH"
            desc = f"Bandar Long DXY {dxy_trend} {float(dxy.iloc[-1]):.2f} US10Y {us10y_trend} {float(us10y.iloc[-1]):.2f}" if score>=50 else f"Bandar Short DXY {dxy_trend} US10Y {us10y_trend}"
            prob = 70 if score>=50 else 65
            cot_data = {"source": "DXY US10Y proxy daily", "bias": bias, "desc": desc, "prob": prob}
            with open(COT_CACHE,'w') as f:
                json.dump(cot_data,f)
            HISTORI_SUMBER['cot'] = f"{bias} DXY {dxy_trend} US10Y {us10y_trend}"
            return bias, desc, prob, cot_data
        except Exception as e:
            log(f"COT fallback error {e}")
            return "BULLISH", "COT Net Long dominan fallback", 68, {}
    except Exception as e:
        log(f"COT error {e}")
        return "BULLISH", "COT fallback", 68, {}

def get_news_fundamental():
    try:
        news_list = []
        try:
            r = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json", timeout=10)
            if r.status_code==200:
                data = r.json()
                today_str = datetime.now(SAUDI_TZ).strftime('%Y-%m-%d')
                for n in data:
                    date = n.get('date','')[:10]
                    if date == today_str or date == (datetime.now(SAUDI_TZ)-timedelta(days=1)).strftime('%Y-%m-%d'):
                        impact = n.get('impact','')
                        title = n.get('title','')
                        country = n.get('country','')
                        if country in ['USD','GOLD','ALL'] or 'Fed' in title or 'CPI' in title or 'NFP' in title or 'FOMC' in title or 'Gold' in title:
                            if impact in ['High','Medium'] or 'USD'==country:
                                news_list.append(n)
        except Exception as e:
            log(f"FF news error {e}")
        if not news_list:
            dow = datetime.now(SAUDI_TZ).weekday()
            if dow == 4:
                news_list = [{"title":"NFP US Jobs","impact":"High","country":"USD","time":"15:30 AST","desc":"NFP hari ini volatilitas tinggi"}]
        with open(NEWS_CACHE,'w') as f:
            json.dump(news_list,f)
        if news_list:
            high = [n for n in news_list if n.get('impact')=='High']
            if high:
                desc = f"HIGH IMPACT HARI INI {len(high)} news "
                for n in high[:3]:
                    desc += f"{n.get('title','')} {n.get('time','')} "
                bias = "VOLATILE"
                score = -10
            else:
                desc = f"{len(news_list)} medium news hari ini market normal"
                bias = "NORMAL"
                score = 0
        else:
            desc = "No high impact news hari ini market teknikal"
            bias = "CALM"
            score = 5
        HISTORI_SUMBER['news'] = f"{len(news_list)} news {datetime.now(SAUDI_TZ).strftime('%d %b')}: {desc[:80]}"
        return news_list, desc, bias, score
    except Exception as e:
        log(f"News error {e}")
        return [], "News fallback", "CALM", 0

def get_order_block_and_bandarm():
    try:
        df_h1 = yf.download("GC=F", period="1mo", interval="60m", progress=False, auto_adjust=True)
        df_h4 = yf.download("GC=F", period="3mo", interval="60m", progress=False, auto_adjust=True)
        df_d1 = yf.download("GC=F", period="6mo", interval="1d", progress=False, auto_adjust=True)
        def detect_ob(df, tf_name):
            try:
                close = df['Close']
                high = df['High']
                low = df['Low']
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:,0]
                    high = high.iloc[:,0]
                    low = low.iloc[:,0]
                swing_high = float(high.tail(20).max())
                swing_low = float(low.tail(20).min())
                last_close = float(close.iloc[-1])
                prev_high = float(high.tail(50).max())
                prev_low = float(low.tail(50).min())
                bos_bull = last_close > prev_high
                bos_bear = last_close < prev_low
                choch_bull = False
                choch_bear = False
                if len(close)>=20:
                    if close.iloc[-1] > close.iloc[-10] and low.iloc[-1] > low.iloc[-10]:
                        choch_bull = True
                    if close.iloc[-1] < close.iloc[-10] and high.iloc[-1] < high.iloc[-10]:
                        choch_bear = True
                ob_bull = None
                ob_bear = None
                try:
                    for i in range(len(df)-10, len(df)-2):
                        o = float(df['Open'].iloc[i])
                        c = float(df['Close'].iloc[i])
                        next_c = float(df['Close'].iloc[i+1])
                        if c > o and next_c < c:
                            ob_bear = (float(low.iloc[i]), float(high.iloc[i]))
                        if c < o and next_c > c:
                            ob_bull = (float(low.iloc[i]), float(high.iloc[i]))
                except:
                    pass
                fvg_bull = []
                fvg_bear = []
                try:
                    for i in range(len(df)-3, len(df)-1):
                        low1 = float(low.iloc[i-1])
                        high1 = float(high.iloc[i-1])
                        low3 = float(low.iloc[i+1])
                        high3 = float(high.iloc[i+1])
                        if low3 > high1:
                            fvg_bull.append((high1, low3))
                        if high3 < low1:
                            fvg_bear.append((high3, low1))
                except:
                    pass
                range_mid = (swing_high + swing_low)/2
                if last_close > range_mid:
                    zone = "PREMIUM mahal bandar jual"
                    bias_ob = "BEARISH"
                else:
                    zone = "DISCOUNT murah bandar beli"
                    bias_ob = "BULLISH"
                return {
                    "tf": tf_name,
                    "swing_high": swing_high,
                    "swing_low": swing_low,
                    "last": last_close,
                    "bos_bull": bos_bull,
                    "bos_bear": bos_bear,
                    "choch_bull": choch_bull,
                    "choch_bear": choch_bear,
                    "ob_bull": ob_bull,
                    "ob_bear": ob_bear,
                    "fvg_bull": fvg_bull[:2],
                    "fvg_bear": fvg_bear[:2],
                    "zone": zone,
                    "bias": bias_ob,
                    "mid": range_mid
                }
            except Exception as e:
                return {"tf": tf_name, "error": str(e), "bias": "NEUTRAL", "zone": "NEUTRAL"}
        ob_h1 = detect_ob(df_h1, "H1")
        ob_h4 = detect_ob(df_h4, "H4")
        ob_d1 = detect_ob(df_d1, "D1")
        bullish_count = sum([1 for ob in [ob_h1, ob_h4, ob_d1] if ob.get('bias')=='BULLISH'])
        bearish_count = sum([1 for ob in [ob_h1, ob_h4, ob_d1] if ob.get('bias')=='BEARISH'])
        bos_bull_all = any([ob.get('bos_bull') for ob in [ob_h1, ob_h4, ob_d1]])
        bos_bear_all = any([ob.get('bos_bear') for ob in [ob_h1, ob_h4, ob_d1]])
        if bos_bull_all and bullish_count>=2:
            bandar_bias = "BULLISH STRONG"
            desc = f"Bandar BUY BOS BULL H4 D1 Discount zone OB Bull {ob_h4.get('ob_bull')} Smart Money long"
            prob = 80
        elif bos_bear_all and bearish_count>=2:
            bandar_bias = "BEARISH STRONG"
            desc = f"Bandar SELL BOS BEAR Premium zone OB Bear Smart Money short"
            prob = 78
        elif bullish_count >=2:
            bandar_bias = "BULLISH"
            desc = f"Bandar BUY Discount zone H1 H4 OB Bull FVG Bull akumulasi"
            prob = 72
        elif bearish_count >=2:
            bandar_bias = "BEARISH"
            desc = f"Bandar SELL Premium zone OB Bear FVG Bear distribusi"
            prob = 70
        else:
            bandar_bias = "NEUTRAL"
            desc = f"Bandar NEUTRAL range {ob_h1.get('swing_low',0):.1f} {ob_h1.get('swing_high',0):.1f} tengah"
            prob = 55
        result = {
            "h1": ob_h1,
            "h4": ob_h4,
            "d1": ob_d1,
            "bandar_bias": bandar_bias,
            "bandar_desc": desc,
            "bandar_prob": prob,
            "bullish_count": bullish_count,
            "bearish_count": bearish_count
        }
        HISTORI_SUMBER['ob'] = f"{bandar_bias} {desc[:80]}"
        return result
    except Exception as e:
        log(f"OB bandar error {e}")
        return {"bandar_bias": "NEUTRAL", "bandar_desc": "OB fallback", "bandar_prob": 55, "h1": {}, "h4": {}, "d1": {}}

def load_history_on_startup():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE,'r') as f:
                data=json.load(f)
                TF_PROB.update(data.get("tf_prob",{}))
                JAM_TERBAIK_PROB.update(data.get("jam",{}))
        auto_download_all_tf()
        get_cot_real_daily()
        get_news_fundamental()
        get_order_block_and_bandarm()
    except Exception as e:
        log(f"Startup V29 error {e}")

flask_app = Flask(__name__)
@flask_app.route('/')
def home():
    return f"V29 NO SYMBOL - {datetime.now(SAUDI_TZ).strftime('%H:%M:%S AST')} - {HISTORI_SUMBER.get('last_check','')} COT {HISTORI_SUMBER.get('cot','')} - OK"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

def now_saudi():
    return datetime.now(SAUDI_TZ)

def get_live():
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=8).json()
        return float(r['price'])
    except:
        return 4473.0

def get_trend_per_tf(tf="M5"):
    try:
        mapping = {"M5": ("5d","5m"), "M15": ("5d","15m"), "M30": ("5d","30m"), "H1": ("1mo","60m"), "H4": ("3mo","60m"), "D1": ("6mo","1d")}
        period, interval = mapping.get(tf, ("1mo","60m"))
        cache_path = f"/tmp/XAUUSD_{tf}_AUTO.csv"
        if os.path.exists(cache_path) and tf in ["M5","M15","M30","H1"]:
            try:
                df = pd.read_csv(cache_path)
                close = df['Close']
                ema9 = close.ewm(span=9).mean().iloc[-1]
                ema20 = close.ewm(span=20).mean().iloc[-1]
                price = float(close.iloc[-1])
                prev = float(close.iloc[-2]) if len(close)>=2 else price
                trend = "BULL" if price > ema9 and ema9 > ema20 else "BEAR" if price < ema9 and ema9 < ema20 else "BULL" if price > ema20 else "BEAR"
                strength = abs(price - ema20) / ema20 * 100 if ema20!=0 else 0
                delta = close.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                rsi_val = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50
                change = price - prev
                return trend, strength, rsi_val, change, price
            except:
                pass
        df = yf.download("GC=F", period=period, interval=interval, progress=False, auto_adjust=True)
        if df is None or len(df) < 20:
            return "BULL", 0, 50, 0, 0
        close = df['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:,0]
        ema9 = close.ewm(span=9).mean().iloc[-1]
        ema20 = close.ewm(span=20).mean().iloc[-1]
        price = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        trend = "BULL" if price > ema9 and ema9 > ema20 else "BEAR" if price < e
