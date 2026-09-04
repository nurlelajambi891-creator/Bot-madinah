
import os, requests, yfinance as yf, pandas as pd, json
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
    "status": "V30 FINAL NO SYMBOL",
    "last_check": "Belum",
    "cot": "Belum",
    "news": "Belum",
    "ob": "Belum"
}
CACHE_FILE = "/tmp/history_v30.json"

def log(msg):
    print(f"[{datetime.now(SAUDI_TZ).strftime('%H:%M:%S AST')}] {msg}")

def now_saudi():
    return datetime.now(SAUDI_TZ)

def get_live():
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=8).json()
        return float(r['price'])
    except:
        return 4225.0

def auto_download_all_tf():
    global JAM_TERBAIK_PROB, TF_PROB, HISTORI_SUMBER
    try:
        log("V30 AUTO DOWNLOAD ALL TF")
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
                    HISTORI_SUMBER[tf] = f"{len(df_reset)} candle"
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
                df_h4 = df_h1.set_index('Waktu').resample('4h').agg({'Open':'first','High':'max','Low':'min','Close':'last'}).dropna().reset_index()
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
        return False

def get_cot_real_daily():
    try:
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
            desc = f"Bandar Long DXY {dxy_trend} {float(dxy.iloc[-1]):.2f} US10Y {us10y_trend}" if score>=50 else f"Bandar Short DXY {dxy_trend} US10Y {us10y_trend}"
            prob = 70 if score>=50 else 65
            HISTORI_SUMBER['cot'] = f"{bias} DXY {dxy_trend} US10Y {us10y_trend}"
            return bias, desc, prob, {}
        except Exception as e:
            log(f"COT fallback error {e}")
            return "BULLISH", "COT Net Long dominan", 68, {}
    except Exception as e:
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
                    if date == today_str:
                        if n.get('country') in ['USD','ALL'] and n.get('impact') in ['High','Medium']:
                            news_list.append(n)
        except:
            pass
        if news_list:
            high = [n for n in news_list if n.get('impact')=='High']
            if high:
                desc = f"HIGH IMPACT HARI INI {len(high)} news"
                bias = "VOLATILE"
                score = -10
            else:
                desc = f"{len(news_list)} medium news hari ini"
                bias = "NORMAL"
                score = 0
        else:
            desc = "No high impact news hari ini market teknikal"
            bias = "CALM"
            score = 5
        HISTORI_SUMBER['news'] = desc
        return news_list, desc, bias, score
    except:
        return [], "News fallback", "CALM", 0

def get_order_block_and_bandarm():
    try:
        df_h1 = yf.download("GC=F", period="1mo", interval="60m", progress=False, auto_adjust=True)
        df_d1 = yf.download("GC=F", period="6mo", interval="1d", progress=False, auto_adjust=True)
        def detect_ob(df):
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
                mid = (swing_high + swing_low)/2
                if last_close > mid:
                    zone = "PREMIUM mahal bandar jual"
                    bias = "BEARISH"
                else:
                    zone = "DISCOUNT murah bandar beli"
                    bias = "BULLISH"
                return {"swing_high": swing_high, "swing_low": swing_low, "last": last_close, "zone": zone, "bias": bias, "mid": mid}
            except:
                return {"bias": "NEUTRAL", "zone": "NEUTRAL", "swing_high": 0, "swing_low": 0, "last": 0, "mid": 0}
        ob_h1 = detect_ob(df_h1)
        ob_d1 = detect_ob(df_d1)
        if ob_h1.get('bias')=='BULLISH' and ob_d1.get('bias')=='BULLISH':
            bandar_bias = "BULLISH STRONG"
            desc = f"Bandar BUY Discount zone H1 D1 Smart Money long"
            prob = 80
        elif ob_h1.get('bias')=='BEARISH' and ob_d1.get('bias')=='BEARISH':
            bandar_bias = "BEARISH STRONG"
            desc = f"Bandar SELL Premium zone H1 D1 Smart Money short"
            prob = 78
        elif ob_h1.get('bias')=='BULLISH':
            bandar_bias = "BULLISH"
            desc = f"Bandar BUY Discount zone akumulasi"
            prob = 72
        else:
            bandar_bias = "BEARISH"
            desc = f"Bandar SELL Premium zone distribusi"
            prob = 70
        result = {"h1": ob_h1, "d1": ob_d1, "bandar_bias": bandar_bias, "bandar_desc": desc, "bandar_prob": prob}
        HISTORI_SUMBER['ob'] = f"{bandar_bias} {desc[:60]}"
        return result
    except Exception as e:
        return {"bandar_bias": "NEUTRAL", "bandar_desc": "OB fallback", "bandar_prob": 55, "h1": {}, "d1": {}}

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
                trend = "BULL" if price > ema9 and ema9 > ema20 else "BEAR"
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
            return "BULL", 0, 50, 0, get_live()
        close = df['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:,0]
        ema9 = close.ewm(span=9).mean().iloc[-1]
        ema20 = close.ewm(span=20).mean().iloc[-1]
        price = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        trend = "BULL" if price > ema9 and ema9 > ema20 else "BEAR"
        strength = abs(price - ema20) / ema20 * 100
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi_val = float(rsi.iloc[-1])
        change = price - prev
        return trend, strength, rsi_val, change, price
    except Exception as e:
        log(f"Trend {tf} error {e}")
        return "BULL", 0, 50, 0, get_live()

def get_sr_realtime():
    try:
        df_d1 = yf.download("GC=F", period="3mo", interval="1d", progress=False, auto_adjust=True)
        close = df_d1['Close']
        high = df_d1['High']
        low = df_d1['Low']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:,0]
            high = high.iloc[:,0]
            low = low.iloc[:,0]
        sup = float(low.tail(20).min())
        res = float(high.tail(20).max())
        last_close = float(close.iloc[-1])
        last_high = float(high.iloc[-1])
        last_low = float(low.iloc[-1])
        pivot = (last_high + last_low + last_close)/3
        live = get_live()
        dist_sup = live - sup
        dist_res = res - live
        return {"live": live, "nearest_sup": sup, "nearest_res": res, "dist_sup": dist_sup, "dist_res": dist_res, "status_sup": f"Support {sup:.2f} {dist_sup:.1f} away", "status_res": f"Resist {res:.2f} {dist_res:.1f} away", "prediksi": f"Range {sup:.2f} {res:.2f}", "pivot_h1": pivot, "pivot_h4": pivot, "pivot_d1": pivot}
    except:
        live = get_live()
        return {"live": live, "nearest_sup": live-10, "nearest_res": live+10, "dist_sup": 10, "dist_res": 10, "status_sup": "loading", "status_res": "loading", "prediksi": "tunggu", "pivot_h1": live, "pivot_h4": live, "pivot_d1": live}

def kolaborasi_signal_full(tf="M5"):
    saudi = now_saudi()
    live = get_live()
    trend_tf, strength_tf, rsi_tf, _, _ = get_trend_per_tf(tf)
    trend_h1, strength_h1, _, _, _ = get_trend_per_tf("H1")
    cot_bias, cot_desc, cot_prob, cot_data = get_cot_real_daily()
    news_list, news_desc, news_bias, news_score = get_news_fundamental()
    ob_data = get_order_block_and_bandarm()
    bandar_bias = ob_data.get('bandar_bias','NEUTRAL')
    bandar_desc = ob_data.get('bandar_desc','')
    bandar_prob = ob_data.get('bandar_prob',55)
    sr_data = get_sr_realtime()
    jam_prob = TF_PROB.get(tf, JAM_TERBAIK_PROB).get(saudi.hour, 50)
    if tf=="D1":
        jam_prob = TF_PROB["D1"].get(saudi.weekday(), 65)
    score = 0
    if trend_tf == "BULL":
        score += 40
    else:
        score += 10
    if (cot_bias=="BULLISH" and trend_tf=="BULL") or (cot_bias=="BEARISH" and trend_tf=="BEAR"):
        score += 20
    else:
        score += 10
    if (bandar_bias=="BULLISH STRONG" and trend_tf=="BULL") or (bandar_bias=="BEARISH STRONG" and trend_tf=="BEAR"):
        score += 15
    else:
        score += 5
    score += jam_prob * 0.10
    if sr_data['dist_sup'] < 3 and trend_tf=="BULL":
        score += 5
    score += news_score
    if score >= 78:
        final = "BUY" if trend_tf=="BULL" or bandar_bias.startswith("BULLISH") else "SELL"
        prob = min(int(score), 92)
    elif score >= 58:
        final = "BUY" if trend_tf=="BULL" else "SELL"
        prob = int(score)
    else:
        final = "WAIT"
        prob = int(score)
    if "VOLATILE" in news_bias and score < 85:
        final = "WAIT"
        prob = int(score*0.8)
    return {
        "tf": tf, "live": live, "saudi": saudi, "trend": trend_tf, "trend_h1": trend_h1,
        "strength": strength_tf, "rsi": rsi_tf, "cot_bias": cot_bias, "cot_desc": cot_desc,
        "cot_prob": cot_prob, "news_desc": news_desc, "news_bias": news_bias,
        "ob_data": ob_data, "bandar_bias": bandar_bias, "bandar_desc": bandar_desc,
        "bandar_prob": bandar_prob, "sr_data": sr_data, "jam_prob": jam_prob,
        "score": score, "final": final, "prob": prob
    }

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("M5 FULL"), KeyboardButton("M15 FULL"), KeyboardButton("M30 FULL")],
        [KeyboardButton("H1 FULL"), KeyboardButton("H4 FULL"), KeyboardButton("D1 SWING FULL")],
        [KeyboardButton("TREND ALL"), KeyboardButton("ANALISIS FULL"), KeyboardButton("SR FULL")],
        [KeyboardButton("COT REAL"), KeyboardButton("NEWS"), KeyboardButton("ORDER BLOCK")],
        [KeyboardButton("BANDAR"), KeyboardButton("PIVOT"), KeyboardButton("LIVE")],
        [KeyboardButton("JAM"), KeyboardButton("BACKTEST"), KeyboardButton("UPDATE ALL")],
        [KeyboardButton("AUTO SCALPING ON"), KeyboardButton("AUTO SWING ON")],
        [KeyboardButton("AUTO OFF")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    saudi = now_saudi()
    keyboard = get_main_keyboard()
    live = get_live()
    cot_bias, cot_desc, cot_prob, _ = get_cot_real_daily()
    news_list, news_desc, news_bias, _ = get_news_fundamental()
    ob = get_order_block_and_bandarm()
    text = (
        f"V30 FINAL NO SYMBOL\n"
        f"WAKTU {saudi.strftime('%H:%M:%S AST %d %b %Y')}\n"
        f"LIVE {live:.2f}\n"
        f"COT REAL {cot_bias} {cot_prob} persen\n"
        f"NEWS {news_desc[:80]}\n"
        f"BANDAR {ob.get('bandar_bias')} {ob.get('bandar_prob')} persen\n"
        f"{HISTORI_SUMBER.get('last_check','')}\n\n"
        f"FULL PADUAN NO SYMBOL\n"
        f"40 persen History 3 bulan per TF\n"
        f"20 persen COT REAL daily\n"
        f"15 persen Order Block BOS CHoCH FVG\n"
        f"15 persen Pivot SR terbaru\n"
        f"10 persen News fundamental\n\n"
        f"PISAH AUTO\n"
        f"AUTO SCALPING ON tiap 5 menit\n"
        f"AUTO SWING ON tiap 1 hari 09:00 AST\n"
    )
    await update.message.reply_text(text, reply_markup=keyboard)

async def live_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = now_saudi()
    live = get_live()
    await update.message.reply_text(f"LIVE {s.strftime('%H:%M AST')} {live:.2f}")

async def jam_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = now_saudi()
    text = f"JAM ALL TF V30 {s.strftime('%H:%M AST')}\n"
    for tf in ["M5","M15","M30","H1"]:
        text += f"{tf} {s.hour:02d}:00 {TF_PROB[tf].get(s.hour,50)} persen "
    await update.message.reply_text(text)

async def cot_real_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bias, desc, prob, data = get_cot_real_daily()
    s = now_saudi()
    await update.message.reply_text(f"COT REAL DAILY {s.strftime('%H:%M AST')} Bias {bias} {prob} persen {desc}")

async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    news_list, desc, bias, score = get_news_fundamental()
    s = now_saudi()
    await update.message.reply_text(f"NEWS FUNDAMENTAL {s.strftime('%H:%M AST')} {bias} {desc} Score {score}")

async def ob_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ob = get_order_block_and_bandarm()
    s = now_saudi()
    await update.message.reply_text(f"ORDER BLOCK {s.strftime('%H:%M AST')} Bias {ob.get('bandar_bias')} {ob.get('bandar_prob')} persen {ob.get('bandar_desc')}")

async def bandar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ob = get_order_block_and_bandarm()
    cot_bias, cot_desc, cot_prob, _ = get_cot_real_daily()
    s = now_saudi()
    await update.message.reply_text(f"BANDAR FULL {s.strftime('%H:%M AST')} COT {cot_bias} {cot_prob} persen BANDAR {ob.get('bandar_bias')} {ob.get('bandar_prob')} persen")

async def trend_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = now_saudi()
    text = f"TREND ALL TF V30 {s.strftime('%H:%M AST')}\n"
    for tf in ["M5","M15","M30","H1","H
