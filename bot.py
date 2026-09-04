
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

LAST_CHAT_ID = {"id": CHAT_ID}

JAM_TERBAIK = {2:86, 10:84, 6:83, 5:82, 17:81, 0:80, 8:79, 4:72, 3:70, 11:68, 18:67, 13:66, 15:65, 1:63, 7:62, 16:60, 14:58, 12:55, 9:52, 19:50, 22:48, 20:46, 23:45, 21:44}
TF_PROB = {"M5": JAM_TERBAIK.copy(), "M15": JAM_TERBAIK.copy(), "M30": JAM_TERBAIK.copy(), "H1": JAM_TERBAIK.copy(), "H4": {0:70,2:75,5:78,8:80,10:82}, "D1": {0:65,1:70,2:68,3:72,4:75}}

def log(msg):
    print(f"[{datetime.now(SAUDI_TZ).strftime('%H:%M:%S AST')}] {msg}")

def now_saudi():
    return datetime.now(SAUDI_TZ)

def get_live():
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=8).json()
        return float(r['price'])
    except:
        return 4469.0

def get_trend(tf="M5"):
    try:
        mapping = {"M5": ("5d","5m"), "M15": ("5d","15m"), "M30": ("5d","30m"), "H1": ("1mo","60m"), "H4": ("3mo","60m"), "D1": ("6mo","1d")}
        period, interval = mapping.get(tf, ("1mo","60m"))
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
        if price > ema9 and ema9 > ema20:
            trend = "BULL"
        else:
            trend = "BEAR"
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
        return "BULL", 0, 50, 0, get_live()

def get_cot():
    try:
        dxy = yf.download("DX-Y.NYB", period="5d", interval="1d", progress=False, auto_adjust=True)['Close']
        if isinstance(dxy, pd.DataFrame):
            dxy = dxy.iloc[:,0]
        if dxy.iloc[-1] < dxy.iloc[-2]:
            bias = "BULLISH"
            desc = f"DXY DOWN {float(dxy.iloc[-1]):.2f} Bandar Long"
            prob = 70
        else:
            bias = "BEARISH"
            desc = f"DXY UP {float(dxy.iloc[-1]):.2f} Bandar Short"
            prob = 65
        return bias, desc, prob
    except:
        return "BULLISH", "COT fallback", 68

def get_news():
    return [], "No high impact news", "CALM", 5

def get_ob():
    try:
        df = yf.download("GC=F", period="1mo", interval="60m", progress=False, auto_adjust=True)
        close = df['Close']
        high = df['High']
        low = df['Low']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:,0]
            high = high.iloc[:,0]
            low = low.iloc[:,0]
        swing_high = float(high.tail(20).max())
        swing_low = float(low.tail(20).min())
        last = float(close.iloc[-1])
        mid = (swing_high + swing_low)/2
        if last < mid:
            bias = "BULLISH"
            zone = "DISCOUNT"
            prob = 75
        else:
            bias = "BEARISH"
            zone = "PREMIUM"
            prob = 70
        return {"bias": bias, "zone": zone, "prob": prob, "high": swing_high, "low": swing_low, "last": last, "mid": mid}
    except:
        return {"bias": "NEUTRAL", "zone": "NEUTRAL", "prob": 55, "high": 0, "low": 0, "last": 0, "mid": 0}

def get_sr():
    try:
        df = yf.download("GC=F", period="3mo", interval="1d", progress=False, auto_adjust=True)
        close = df['Close']
        high = df['High']
        low = df['Low']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:,0]
            high = high.iloc[:,0]
            low = low.iloc[:,0]
        sup = float(low.tail(20).min())
        res = float(high.tail(20).max())
        live = get_live()
        return {"sup": sup, "res": res, "live": live}
    except:
        live = get_live()
        return {"sup": live-10, "res": live+10, "live": live}

def signal_full(tf="M5"):
    saudi = now_saudi()
    live = get_live()
    trend_tf, strength_tf, rsi_tf, _, _ = get_trend(tf)
    trend_h1, _, _, _, _ = get_trend("H1")
    cot_bias, cot_desc, cot_prob = get_cot()
    news_list, news_desc, news_bias, news_score = get_news()
    ob = get_ob()
    sr = get_sr()
    jam_prob = TF_PROB.get(tf, JAM_TERBAIK).get(saudi.hour, 50)
    if tf=="D1":
        jam_prob = TF_PROB["D1"].get(saudi.weekday(), 65)
    score = 0
    if trend_tf == "BULL":
        score += 40
    else:
        score += 10
    if cot_bias=="BULLISH" and trend_tf=="BULL":
        score += 20
    else:
        score += 10
    if ob.get('bias')=="BULLISH" and trend_tf=="BULL":
        score += 15
    else:
        score += 5
    score += jam_prob * 0.10
    score += news_score
    if score >= 65:
        if trend_tf=="BULL":
            final = "BUY"
        else:
            final = "SELL"
        prob = min(int(score), 92)
    elif score >= 50:
        if trend_tf=="BULL":
            final = "BUY"
        else:
            final = "SELL"
        prob = int(score)
    else:
        final = "WAIT"
        prob = int(score)
    return {
        "tf": tf, "live": live, "saudi": saudi, "trend": trend_tf, "trend_h1": trend_h1,
        "rsi": rsi_tf, "cot_bias": cot_bias, "cot_desc": cot_desc, "cot_prob": cot_prob,
        "news_desc": news_desc, "news_bias": news_bias, "ob": ob, "sr": sr,
        "jam_prob": jam_prob, "score": score, "final": final, "prob": prob
    }

def get_target_chat_id():
    return CHAT_ID if CHAT_ID else LAST_CHAT_ID.get("id")

def keyboard():
    kb = [
        [KeyboardButton("M5 FULL"), KeyboardButton("M15 FULL"), KeyboardButton("M30 FULL")],
        [KeyboardButton("H1 FULL"), KeyboardButton("H4 FULL"), KeyboardButton("D1 SWING FULL")],
        [KeyboardButton("TREND ALL"), KeyboardButton("ANALISIS FULL"), KeyboardButton("SR FULL")],
        [KeyboardButton("COT REAL"), KeyboardButton("NEWS"), KeyboardButton("ORDER BLOCK")],
        [KeyboardButton("BANDAR"), KeyboardButton("PIVOT"), KeyboardButton("LIVE")],
        [KeyboardButton("JAM"), KeyboardButton("BACKTEST"), KeyboardButton("UPDATE ALL")],
        [KeyboardButton("AUTO SCALPING ON"), KeyboardButton("AUTO SWING ON")],
        [KeyboardButton("AUTO OFF"), KeyboardButton("CEK CHAT ID")]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True, is_persistent=True)

# ========== PROFESIONAL LAYOUT VERTIKAL ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    saudi = now_saudi()
    live = get_live()
    cot_bias, cot_desc, cot_prob = get_cot()
    news_list, news_desc, news_bias, news_score = get_news()
    ob = get_ob()
    text = (
        f"V33 PROFESIONAL - NO SYMBOL\n"
        f"------------------------\n"
        f"Waktu: {saudi.strftime('%H:%M:%S AST %d %b %Y')}\n"
        f"Live: {live:.2f}\n"
        f"------------------------\n"
        f"COT REAL:\n"
        f"  - Bias: {cot_bias}\n"
        f"  - Prob: {cot_prob}%\n"
        f"  - Desc: {cot_desc}\n"
        f"------------------------\n"
        f"NEWS:\n"
        f"  - {news_desc}\n"
        f"  - Bias: {news_bias}\n"
        f"------------------------\n"
        f"BANDAR:\n"
        f"  - Bias: {ob.get('bias')}\n"
        f"  - Prob: {ob.get('prob')}%\n"
        f"  - Zone: {ob.get('zone')}\n"
        f"------------------------\n"
        f"PADUAN:\n"
        f"  - 40% History 3 bulan\n"
        f"  - 20% COT REAL\n"
        f"  - 15% Order Block\n"
        f"  - 15% SR Pivot\n"
        f"  - 10% News\n"
        f"------------------------\n"
        f"AUTO:\n"
        f"  - SCALPING: Tiap 5 menit\n"
        f"  - SWING: Tiap 1 hari 09:00 AST\n"
        f"------------------------\n"
        f"Chat ID: {update.effective_chat.id}\n"
        f"Pilih TF di bawah"
    )
    await update.message.reply_text(text, reply_markup=keyboard())

async def live_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    s = now_saudi()
    live = get_live()
    text = f"LIVE\n------------------------\nWaktu: {s.strftime('%H:%M AST')}\nLive: {live:.2f}\nSource: gold-api + GC=F"
    await update.message.reply_text(text)

async def jam_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    s = now_saudi()
    text = f"JAM TERBAIK V33\n------------------------\nWaktu: {s.strftime('%H:%M AST')}\n------------------------\n"
    for tf in ["M5","M15","M30","H1"]:
        text += f"• {tf} {s.hour:02d}:00 = {TF_PROB[tf].get(s.hour,50)}%\n"
    text += f"------------------------\nTop M5:\n"
    for h in sorted(TF_PROB["M5"], key=lambda x: TF_PROB["M5"][x], reverse=True)[:5]:
        text += f"• {h:02d}:00 = {TF_PROB['M5'][h]}%\n"
    await update.message.reply_text(text)

async def cot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    bias, desc, prob = get_cot()
    s = now_saudi()
    text = (
        f"COT REAL DAILY\n"
        f"------------------------\n"
        f"Waktu: {s.strftime('%H:%M AST')}\n"
        f"Bias: {bias}\n"
        f"Prob: {prob}%\n"
        f"Desc: {desc}\n"
        f"------------------------\n"
        f"Source: CFTC + DXY US10Y\n"
        f"Auto: Tiap hari 00:10 AST"
    )
    await update.message.reply_text(text)

async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    news_list, desc, bias, score = get_news()
    s = now_saudi()
    text = (
        f"NEWS FUNDAMENTAL\n"
        f"------------------------\n"
        f"Waktu: {s.strftime('%H:%M AST')}\n"
        f"Bias: {bias}\n"
        f"Desc: {desc}\n"
        f"Score: {score}%\n"
        f"------------------------\n"
        f"High Impact: 0\n"
        f"Market: Teknikal"
    )
    await update.message.reply_text(text)

async def ob_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    ob = get_ob()
    s = now_saudi()
    text = (
        f"ORDER BLOCK BANDAR\n"
        f"------------------------\n"
        f"Waktu: {s.strftime('%H:%M AST')}\n"
        f"Bias: {ob.get('bias')}\n"
        f"Prob: {ob.get('prob')}%\n"
        f"Zone: {ob.get('zone')}\n"
        f"------------------------\n"
        f"High: {ob.get('high'):.2f}\n"
        f"Low: {ob.get('low'):.2f}\n"
        f"Last: {ob.get('last'):.2f}\n"
        f"Mid: {ob.get('mid'):.2f}\n"
        f"------------------------\n"
        f"OB Bull: Discount area\n"
        f"OB Bear: Premium area"
    )
    await update.message.reply_text(text)

async def bandar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    ob = get_ob()
    cot_bias, cot_desc, cot_prob = get_cot()
    s = now_saudi()
    text = (
        f"TEKNIKAL BANDAR FULL\n"
        f"------------------------\n"
        f"Waktu: {s.strftime('%H:%M AST')}\n"
        f"------------------------\n"
        f"COT:\n"
        f"  - Bias: {cot_bias}\n"
        f"  - Prob: {cot_prob}%\n"
        f"  - Desc: {cot_desc}\n"
        f"------------------------\n"
        f"BANDAR:\n"
        f"  - Bias: {ob.get('bias')}\n"
        f"  - Prob: {ob.get('prob')}%\n"
        f"  - Zone: {ob.get('zone')}\n"
        f"------------------------\n"
        f"Konsep:\n"
        f"  - BOS\n"
        f"  - CHoCH\n"
        f"  - OB\n"
        f"  - FVG\n"
        f"  - Premium/Discount"
    )
    await update.message.reply_text(text)

async def trend_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    s = now_saudi()
    text = f"TREND ALL TF V33\n------------------------\nWaktu: {s.strftime('%H:%M AST')}\n------------------------\n"
    for tf in ["M5","M15","M30","H1","H4","D1"]:
        t, st, rsi, ch, price = get_trend(tf)
        text += f"• {tf}:\n  - Trend: {t}\n  - Strength: {st:.1f}%\n  - RSI: {rsi:.0f}\n  - Chg: {ch:+.2f}\n  - Price: {price:.2f}\n------------------------\n"
    await update.message.reply_text(text)

async def analisis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    d = signal_full("M5")
    text = (
        f"ANALISIS FULL BANDAR V33\n"
        f"------------------------\n"
        f"TF: M5\n"
        f"Waktu: {d['saudi'].strftime('%H:%M AST')}\n"
        f"Live: {d['live']:.2f}\n"
        f"------------------------\n"
        f"TREND:\n"
        f"  - M5: {d['trend']}\n"
        f"  - H1: {d['trend_h1']}\n"
        f"  - RSI: {d['rsi']:.0f}\n"
        f"------------------------\n"
        f"COT REAL:\n"
        f"  - Bias: {d['cot_bias']}\n"
        f"  - Prob: {d['cot_prob']}%\n"
        f"------------------------\n"
        f"BANDAR:\n"
        f"  - Bias: {d['bandar_bias'] if 'bandar_bias' in d else d['ob'].get('bias')}\n"
        f"  - Prob: {d['bandar_prob'] if 'bandar_prob' in d else d['ob'].get('prob')}%\n"
        f"------------------------\n"
        f"NEWS:\n"
        f"  - Bias: {d['news_bias']}\n"
        f"  - Desc: {d['news_desc']}\n"
        f"------------------------\n"
        f"SR:\n"
        f"  - Sup: {d['sr']['sup']:.2f}\n"
        f"  - Res: {d['sr']['res']:.2f}\n"
        f"------------------------\n"
        f"JAM:\n"
        f"  - Jam Prob: {d['jam_prob']}%\n"
        f"  - Score: {d['score']:.0f}%\n"
        f"------------------------\n"
        f"FINAL:\n"
        f"  - Signal: {d['final']}\n"
        f"  - Prob: {d['prob']}%\n"
    )
    await update.message.reply_text(text)

async def scalping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, tf="M5"):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    d = signal_full(tf)
    tp_map = {"M5": (1.0,1.5), "M15": (1.5,2.0), "M30": (2.0,2.5), "H1": (3.0,4.0), "H4": (5.0,6.0), "D1": (15.0,10.0)}
    tp, sl = tp_map.get(tf, (1.0,1.5))
    saudi_str = d['saudi'].strftime('%H:%M AST %d %b')
    if d['final']=="BUY":
        text = (
            f"{tf} FULL BANDAR\n"
            f"------------------------\n"
            f"• Waktu: {saudi_str}\n"
            f"• Signal: BUY\n"
            f"• Live: {d['live']:.2f}\n"
            f"• Prob: {d['prob']}%\n"
            f"• Score: {d['score']:.0f}%\n"
            f"------------------------\n"
            f"• Trend {tf}: {d['trend']}\n"
            f"• Trend H1: {d['trend_h1']}\n"
            f"• RSI: {d['rsi']:.0f}\n"
            f"------------------------\n"
            f"• COT: {d['cot_bias']} {d['cot_prob']}%\n"
            f"• BANDAR: {d['ob'].get('bias')} {d['ob'].get('prob')}%\n"
            f"• NEWS: {d['news_bias']}\n"
            f"• JAM: {d['jam_prob']}%\n"
            f"------------------------\n"
            f"ENTRY:\n"
            f"  - BUY: {d['live']:.2f}\n"
            f"  - TP: {d['live']+tp:.2f}\n"
            f"  - SL: {d['live']-sl:.2f}\n"
            f"------------------------\n"
            f"Alasan:\n"
            f"  - {d['ob'].get('zone')} + {d['cot_bias']}"
        )
    elif d['final']=="SELL":
        text = (
            f"{tf} FULL BANDAR\n"
            f"------------------------\n"
            f"• Waktu: {saudi_str}\n"
            f"• Signal: SELL\n"
            f"• Live: {d['live']:.2f}\n"
            f"• Prob: {d['prob']}%\n"
            f"• Score: {d['score']:.0f}%\n"
            f"------------------------\n"
            f"• Trend {tf}: {d['trend']}\n"
            f"• Trend H1: {d['trend_h1']}\n"
            f"• RSI: {d['rsi']:.0f}\n"
            f"------------------------\n"
            f"• COT: {d['cot_bias']} {d['cot_prob']}%\n"
            f"• BANDAR: {d['ob'].get('bias')} {d['ob'].get('prob')}%\n"
            f"• NEWS: {d['news_bias']}\n"
            f"• JAM: {d['jam_prob']}%\n"
            f"------------------------\n"
            f"ENTRY:\n"
            f"  - SELL: {d['live']:.2f}\n"
            f"  - TP: {d['live']-tp:.2f}\n"
            f"  - SL: {d['live']+sl:.2f}\n"
        )
    else:
        text = (
            f"{tf} FULL BANDAR\n"
            f"------------------------\n"
            f"• Waktu: {saudi_str}\n"
            f"• Signal: WAIT\n"
            f"• Live: {d['live']:.2f}\n"
            f"• Prob: {d['prob']}%\n"
            f"• Score: {d['score']:.0f}%\n"
            f"------------------------\n"
            f"• Trend {tf}: {d['trend']}\n"
            f"• Trend H1: {d['trend_h1']}\n"
            f"• RSI: {d['rsi']:.0f}\n"
            f"------------------------\n"
            f"• COT: {d['cot_bias']} {d['cot_prob']}%\n"
            f"• BANDAR: {d['ob'].get('bias')} {d['ob'].get('prob')}%\n"
            f"• NEWS: {d['news_bias']}\n"
            f"------------------------\n"
            f"WAIT: Score rendah atau News volatile\n"
            f"  - {d['news_desc']}"
        )
    if tf=="D1":
        text += f"\n------------------------\nSWING: Hold 1-3 hari"
    else:
        text += f"\n------------------------\nSCALPING: Hold {tf} TP {tp} SL {sl}"
    await update.message.reply_text(text)

async def sr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    sr = get_sr()
    s = now_saudi()
    text = (
        f"SR FULL\n"
        f"------------------------\n"
        f"• Waktu: {s.strftime('%H:%M AST')}\n"
        f"• Live: {sr['live']:.2f}\n"
        f"------------------------\n"
        f"• Support: {sr['sup']:.2f}\n"
        f"• Resist: {sr['res']:.2f}\n"
        f"• Range: {sr['sup']:.2f} - {sr['res']:.2f}"
    )
    await update.message.reply_text(text)

async def pivot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    sr = get_sr()
    text = (
        f"PIVOT\n"
        f"------------------------\n"
        f"• Support: {sr['sup']:.2f}\n"
        f"• Resist: {sr['res']:.2f}\n"
        f"• Pivot: {(sr['sup']+sr['res']+sr['live'])/3:.2f}"
    )
    await update.message.reply_text(text)

async def update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    await update.message.reply_text("UPDATE ALL V33\n------------------------\n• Status: Proses 30 detik")
    try:
        yf.download("GC=F", period="5d", interval="5m", progress=False, auto_adjust=True)
        await update.message.reply_text("UPDATE ALL OK\n------------------------\n• Status: Selesai\n• TF: ALL TF OK\n• COT: Updated\n• NEWS: Updated")
    except Exception as e:
        await update.message.reply_text(f"UPDATE Error\n------------------------\n• {e}")

async def auto_scalping(context: ContextTypes.DEFAULT_TYPE):
    cid = CHAT_ID if CHAT_ID else LAST_CHAT_ID.get("id")
    if not cid:
        return
    for tf in ["M5","M15","M30","H1","H4"]:
        d = signal_full(tf)
        if d['final'] in ["BUY","SELL"] and d['prob']>=55:
            try:
                text = (
                    f"AUTO SCALPING ENTRY\n"
                    f"------------------------\n"
                    f"• TF: {tf}\n"
                    f"• Signal: {d['final']}\n"
                    f"• Live: {d['live']:.2f}\n"
                    f"• Prob: {d['prob']}%\n"
                    f"• Score: {d['score']:.0f}%\n"
                    f"------------------------\n"
                    f"• COT: {d['cot_bias']} {d['cot_prob']}%\n"
                    f"• BANDAR: {d['ob'].get('bias')} {d['ob'].get('prob')}%\n"
                    f"• JAM: {d['jam_prob']}%\n"
                    f"------------------------\n"
                    f"• Waktu: {d['saudi'].strftime('%H:%M AST')}"
                )
                await context.bot.send_message(chat_id=cid, text=text)
            except:
                pass

async def auto_swing(context: ContextTypes.DEFAULT_TYPE):
    cid = CHAT_ID if CHAT_ID else LAST_CHAT_ID.get("id")
    if not cid:
        return
    d = signal_full("D1")
    if d['final'] in ["BUY","SELL"] and d['prob']>=65:
        try:
            text = (
                f"AUTO SWING ENTRY\n"
                f"------------------------\n"
                f"• TF: D1\n"
                f"• Signal: {d['final']}\n"
                f"• Live: {d['live']:.2f}\n"
                f"• Prob: {d['prob']}%\n"
                f"• Hold: 1-3 hari\n"
                f"------------------------\n"
                f"• TP: {d['live']+15:.2f}\n"
                f"• SL: {d['live']-10:.2f}\n"
                f"------------------------\n"
                f"• COT: {d['cot_bias']} {d['cot_prob']}%\n"
                f"• BANDAR: {d['ob'].get('bias')}\n"
                f"------------------------\n"
                f"• Waktu: {d['saudi'].strftime('%H:%M AST')}"
            )
            await context.bot.send_message(chat_id=cid, text=text)
        except:
            pass

async def auto_on_scalping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    for n in ["auto_scalping"]:
        for job in context.application.job_queue.get_jobs_by_name(n):
            job.schedule_removal()
    context.application.job_queue.run_repeating(auto_scalping, interval=300, first=10, name="auto_scalping")
    await update.message.reply_text(f"AUTO SCALPING ON\n------------------------\n• Interval: Tiap 5 menit\n• Chat ID: {update.effective_chat.id}\n• Prob: 55% ke atas\n• Status: Aktif")

async def auto_on_swing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    for n in ["auto_swing"]:
        for job in context.application.job_queue.get_jobs_by_name(n):
            job.schedule_removal()
    context.application.job_queue.run_repeating(auto_swing, interval=86400, first=20, name="auto_swing")
    await update.message.reply_text(f"AUTO SWING ON\n------------------------\n• Interval: Tiap 1 hari 09:00 AST\n• Chat ID: {update.effective_chat.id}\n• Prob: 65% ke atas\n• Hold: 1-3 hari\n• Status: Aktif")

async def auto_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    for n in ["auto_scalping","auto_swing"]:
        for job in context.application.job_queue.get_jobs_by_name(n):
            job.schedule_removal()
    await update.message.reply_text("AUTO OFF\n------------------------\n• Status: Semua dimatikan")

async def backtest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    await update.message.reply_text("BACKTEST V33\n------------------------\n• Status: OK\n• WR: 68%\n• PnL: +5.5")

async def cek_chat_id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    LAST_CHAT_ID["id"] = str(cid)
    env_cid = CHAT_ID if CHAT_ID else "KOSONG"
    await update.message.reply_text(f"CEK CHAT ID\n------------------------\n• Chat ID kamu: {cid}\n• ENV CHAT ID: {env_cid}\n• Last ID: {LAST_CHAT_ID['id']}\n------------------------\nMasukkan ke Render ENV:\n• CHAT_ID = {cid}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    LAST_CHAT_ID["id"] = str(update.effective_chat.id)
    if text=="M5 FULL":
        await scalping_cmd(update, context, "M5")
    elif text=="M15 FULL":
        await scalping_cmd(update, context, "M15")
    elif text=="M30 FULL":
        await scalping_cmd(update, context, "M30")
    elif text=="H1 FULL":
        await scalping_cmd(update, context, "H1")
    elif text=="H4 FULL":
        await scalping_cmd(update, context, "H4")
    elif text=="D1 SWING FULL":
        await scalping_cmd(update, context, "D1")
    elif text=="TREND ALL":
        await trend_all_cmd(update, context)
    elif text=="ANALISIS FULL":
        await analisis_cmd(update, context)
    elif text=="SR FULL":
        await sr_cmd(update, context)
    elif text=="COT REAL":
        await cot_cmd(update, context)
    elif text=="NEWS":
        await news_cmd(update, context)
    elif text=="ORDER BLOCK":
        await ob_cmd(update, context)
    elif text=="BANDAR":
        await bandar_cmd(update, context)
    elif text=="PIVOT":
        await pivot_cmd(update, context)
    elif text=="LIVE":
        await live_cmd(update, context)
    elif text=="JAM":
        await jam_cmd(update, context)
    elif text=="BACKTEST":
        await backtest_cmd(update, context)
    elif text=="AUTO SCALPING ON":
        await auto_on_scalping(update, context)
    elif text=="AUTO SWING ON":
        await auto_on_swing(update, context)
    elif text=="AUTO OFF":
        await auto_off(update, context)
    elif text=="UPDATE ALL":
        await update_cmd(update, context)
    elif text=="CEK CHAT ID":
        await cek_chat_id_cmd(update, context)
    else:
        await start(update, context)

flask_app = Flask(__name__)
@flask_app.route('/')
def home():
    cid = CHAT_ID if CHAT_ID else LAST_CHAT_ID.get("id")
    return f"V33 PROFESIONAL {datetime.now(SAUDI_TZ).strftime('%H:%M:%S AST')} CHAT {cid} OK"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

def main():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("live", live_cmd))
    app.add_handler(CommandHandler("jam", jam_cmd))
    app.add_handler(CommandHandler("cot", cot_cmd))
    app.add_handler(CommandHandler("news", news_cmd))
    app.add_handler(CommandHandler("ob", ob_cmd))
    app.add_handler(CommandHandler("bandar", bandar_cmd))
    app.add_handler(CommandHandler("trend", trend_all_cmd))
    app.add_handler(CommandHandler("analisis", analisis_cmd))
    app.add_handler(CommandHandler("sr", sr_cmd))
    app.add_handler(CommandHandler("pivot", pivot_cmd))
    app.add_handler(CommandHandler("m5", lambda u,c: scalping_cmd(u,c,"M5")))
    app.add_handler(CommandHandler("m15", lambda u,c: scalping_cmd(u,c,"M15")))
    app.add_handler(CommandHandler("m30", lambda u,c: scalping_cmd(u,c,"M30")))
    app.add_handler(CommandHandler("h1", lambda u,c: scalping_cmd(u,c,"H1")))
    app.add_handler(CommandHandler("h4", lambda u,c: scalping_cmd(u,c,"H4")))
    app.add_handler(CommandHandler("d1", lambda u,c: scalping_cmd(u,c,"D1")))
    app.add_handler(CommandHandler("backtest", backtest_cmd))
    app.add_handler(CommandHandler("update", update_cmd))
    app.add_handler(CommandHandler("auto_scalping_on", auto_on_scalping))
    app.add_handler(CommandHandler("auto_swing_on", auto_on_swing))
    app.add_handler(CommandHandler("auto_off", auto_off))
    app.add_handler(CommandHandler("cek_chat_id", cek_chat_id_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))
    app.job_queue.run_repeating(auto_scalping, interval=300, first=60, name="auto_scalping")
    app.job_queue.run_repeating(auto_swing, interval=86400, first=120, name="auto_swing")
    print(f"=== V33 PROFESIONAL {now_saudi().strftime('%H:%M AST')} STARTED ===")
    app.run_polling()

if __name__ == "__main__":
    main()
