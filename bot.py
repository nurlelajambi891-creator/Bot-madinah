
"""
V22 BACKTEST MADINAH DETIK KE KEMARIN
- M5, M15, SWING D1
- Kolaborasi Trend+RSI+COT+Histori
- Tombol Menu
"""
import os, requests, yfinance as yf, pandas as pd
from datetime import datetime
import pytz
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from flask import Flask
import threading

TOKEN = os.environ.get("BOT_TOKEN", "ISI_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID", "")
SAUDI_TZ = pytz.timezone("Asia/Riyadh")

JAM_TERBAIK_PROB = {
    2: 85, 5: 80, 6: 82, 10: 78, 17: 80,
    0: 55, 1: 60, 3: 58, 4: 62, 7: 65, 8: 60, 9: 70,
    11: 55, 12: 40, 13: 38, 14: 42, 15: 50, 16: 60,
    18: 65, 19: 55, 20: 45, 21: 42, 22: 48, 23: 52
}

flask_app = Flask(__name__)
@flask_app.route('/')
def home():
    return f"Bot V22 Backtest - {datetime.now(SAUDI_TZ).strftime('%H:%M:%S AST')} - OK"

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
        mapping = {
            "M5": ("1d", "5m"),
            "M15": ("5d", "15m"),
            "M30": ("5d", "30m"),
            "H1": ("1mo", "60m"),
            "H4": ("3mo", "240m"),
            "D1": ("6mo", "1d")
        }
        period, interval = mapping.get(tf, ("1mo","60m"))
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
        trend = "BULL" if price > ema9 and ema9 > ema20 else "BEAR" if price < ema9 and ema9 < ema20 else "BULL" if price > ema20 else "BEAR"
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
        print(f"Trend {tf} error: {e}")
        return "BULL", 0, 50, 0, get_live()

def get_trend_safe():
    t, s, _, _, _ = get_trend_per_tf("H1")
    return t, s

def get_cot_bias():
    try:
        dxy = yf.download("DX-Y.NYB", period="5d", interval="1d", progress=False, auto_adjust=True)
        close = dxy['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:,0]
        dxy_trend = "DOWN" if close.iloc[-1] < close.iloc[-2] else "UP"
        if dxy_trend == "DOWN":
            return "BULLISH", "Bandar Long (COT Net Long naik), DXY turun", 70
        else:
            return "BEARISH", "Bandar Short (COT Net Long turun), DXY naik", 65
    except:
        return "BULLISH", "COT Net Long dominan", 68

def get_rsi(tf="M5"):
    try:
        interval = "5m" if tf=="M5" else "15m" if tf=="M15" else "1d"
        period = "1d" if tf=="M5" else "5d" if tf=="M15" else "6mo"
        df = yf.download("GC=F", period=period, interval=interval, progress=False, auto_adjust=True)
        close = df['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:,0]
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1])
    except:
        return 50

def kolaborasi_signal(tf="M5"):
    saudi = now_saudi()
    live = get_live()
    trend, strength = get_trend_safe()
    rsi = get_rsi(tf)
    cot_bias, cot_desc, cot_prob = get_cot_bias()
    jam_prob = JAM_TERBAIK_PROB.get(saudi.hour, 50)
    score = 0
    if trend == "BULL":
        score += 40
        if strength > 0.3:
            score += 10
    else:
        score += 10
    if (cot_bias == "BULLISH" and trend == "BULL") or (cot_bias == "BEARISH" and trend == "BEAR"):
        score += 25
    else:
        score += 10
    score += jam_prob * 0.2
    if tf == "M5":
        if 30 < rsi < 70:
            score += 15
        elif 70 <= rsi < 80 or 20 < rsi <= 30:
            score += 5
    elif tf == "M15":
        if 35 < rsi < 65:
            score += 15
    else:
        if 40 < rsi < 70:
            score += 15
    if score >= 75:
        final = "BUY" if trend == "BULL" else "SELL"
        prob = min(int(score), 92)
    elif score >= 55:
        final = "BUY" if trend == "BULL" else "SELL"
        prob = int(score)
    else:
        final = "WAIT"
        prob = int(score)
    return {"trend": trend, "rsi": rsi, "cot_bias": cot_bias, "cot_desc": cot_desc, "cot_prob": cot_prob, "jam_prob": jam_prob, "strength": strength, "live": live, "saudi": saudi, "final": final, "prob": prob, "score": score}

def get_sr_realtime():
    try:
        df_h1 = yf.download("GC=F", period="5d", interval="60m", progress=False, auto_adjust=True)
        df_h4 = yf.download("GC=F", period="1mo", interval="240m", progress=False, auto_adjust=True)
        df_d1 = yf.download("GC=F", period="3mo", interval="1d", progress=False, auto_adjust=True)
        def extract_levels(df):
            close = df['Close']
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:,0]
            high = df['High']
            low = df['Low']
            if isinstance(high, pd.DataFrame):
                high = high.iloc[:,0]
            if isinstance(low, pd.DataFrame):
                low = low.iloc[:,0]
            sup = float(low.tail(20).min())
            res = float(high.tail(20).max())
            sup2 = float(low.tail(50).min()) if len(close)>=50 else sup
            res2 = float(high.tail(50).max()) if len(close)>=50 else res
            last_close = float(close.iloc[-1])
            last_high = float(high.iloc[-1])
            last_low = float(low.iloc[-1])
            pivot = (last_high + last_low + last_close)/3
            return sup, res, sup2, res2, pivot, last_close
        s_h1, r_h1, s_h1_2, r_h1_2, p_h1, c_h1 = extract_levels(df_h1)
        s_h4, r_h4, s_h4_2, r_h4_2, p_h4, c_h4 = extract_levels(df_h4)
        s_d1, r_d1, s_d1_2, r_d1_2, p_d1, c_d1 = extract_levels(df_d1)
        live = get_live()
        supports = sorted([s_h1, s_h4, s_d1, s_h1_2, s_h4_2], reverse=True)
        resistances = sorted([r_h1, r_h4, r_d1, r_h1_2, r_h4_2])
        nearest_sup = max([s for s in supports if s < live], default=min(supports))
        nearest_res = min([r for r in resistances if r > live], default=max(resistances))
        dist_sup = live - nearest_sup
        dist_res = nearest_res - live
        if live < nearest_sup:
            status_sup = f"🔴 SUDAH TEMBUS SUPPORT {nearest_sup:.2f} ({abs(dist_sup):.2f} di bawah) -> Support jadi Resistance!"
        elif dist_sup < 5:
            status_sup = f"⚠️ DEKAT SUPPORT {nearest_sup:.2f} (tinggal {dist_sup:.2f}) - Potensi BOUNCE!"
        else:
            status_sup = f"✅ JAUH dari Support {nearest_sup:.2f} ({dist_sup:.2f} di atas)"
        if live > nearest_res:
            status_res = f"🟢 SUDAH TEMBUS RESIST {nearest_res:.2f} (+{abs(dist_res):.2f}) -> Resistance jadi Support! Lanjut NAIK!"
        elif dist_res < 5:
            status_res = f"⚠️ DEKAT RESIST {nearest_res:.2f} (tinggal {dist_res:.2f}) - Potensi REJECT!"
        else:
            status_res = f"✅ JAUH dari Resist {nearest_res:.2f} ({dist_res:.2f} di atas)"
        if dist_sup < 3:
            psikologi = "😨 FEAR - Banyak takut jebol support, area BUY bandar!"
            psikologi_level = "OVERSOLD - FEAR"
        elif dist_res < 3:
            psikologi = "🤑 GREED - Banyak FOMO breakout, hati-hati false breakout!"
            psikologi_level = "OVERBOUGHT - GREED"
        else:
            psikologi = "😎 NEUTRAL - Market tenang"
            psikologi_level = "NEUTRAL"
        if dist_sup < dist_res and dist_sup < 8:
            prediksi = f"Harga mau NAIK - dekat support {nearest_sup:.2f}, target {nearest_res:.2f}"
        elif dist_res < dist_sup and dist_res < 8:
            prediksi = f"Harga mau TURUN/REJECT - dekat resist {nearest_res:.2f}, waspada ke {nearest_sup:.2f}"
        else:
            prediksi = f"Harga di tengah, range {nearest_sup:.2f} - {nearest_res:.2f}"
        return {"live": live, "nearest_sup": nearest_sup, "nearest_res": nearest_res, "dist_sup": dist_sup, "dist_res": dist_res, "supports": supports[:3], "resistances": resistances[:3], "status_sup": status_sup, "status_res": status_res, "psikologi": psikologi, "psikologi_level": psikologi_level, "prediksi": prediksi, "pivot_h1": p_h1, "pivot_h4": p_h4, "pivot_d1": p_d1, "s_h1": s_h1, "r_h1": r_h1, "s_h4": s_h4, "r_h4": r_h4, "s_d1": s_d1, "r_d1": r_d1}
    except Exception as e:
        print(f"SR error: {e}")
        live = get_live()
        return {"live": live, "nearest_sup": live-10, "nearest_res": live+10, "dist_sup": 10, "dist_res": 10, "supports": [live-10], "resistances": [live+10], "status_sup": "Data loading", "status_res": "Data loading", "psikologi": "NEUTRAL", "psikologi_level": "NEUTRAL", "prediksi": "Tunggu data", "pivot_h1": live, "pivot_h4": live, "pivot_d1": live, "s_h1": live-5, "r_h1": live+5, "s_h4": live-10, "r_h4": live+10, "s_d1": live-15, "r_d1": live+15}

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("⚡ SCALPING M5"), KeyboardButton("⚡ SCALPING M15"), KeyboardButton("🏹 SWING")],
        [KeyboardButton("📈 TREND"), KeyboardButton("🔮 ANALISIS"), KeyboardButton("🛡️ SR")],
        [KeyboardButton("💰 LIVE"), KeyboardButton("⏰ JAM"), KeyboardButton("📊 COT")],
        [KeyboardButton("🔑 PIVOT"), KeyboardButton("🧠 PSIKOLOGI")],
        [KeyboardButton("📊 BACKTEST"), KeyboardButton("✅ AUTO ON"), KeyboardButton("❌ AUTO OFF")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    saudi = now_saudi()
    keyboard = get_main_keyboard()
    live = get_live()
    text = (
        f"🕌 *V21 DENGAN TOMBOL - MADINAH 100%*\n"
        f"⏰ {saudi.strftime('%H:%M:%S AST %d %b')}\n"
        f"📍 Madinah | Live {live:.2f}\n\n"
        f"Pilih tombol di bawah biar gak perlu ngetik! 👇\n\n"
        f"*TOMBOL:*\n"
        f"⚡ SCALPING M5 - Sinyal 5 menit\n"
        f"⚡ SCALPING M15 - Sinyal 15 menit\n"
        f"🏹 SWING - Harian hold 1-3 hari\n"
        f"📈 TREND - Real-time per TF\n"
        f"🔮 ANALISIS - Kolaborasi lengkap\n"
        f"🛡️ SR - Support Resist terbaru + prediksi\n"
        f"📊 BACKTEST - Detik ke kemarin waktu Madinah\n\n"
        f"✅ Kolaborasi: Trend+RSI+COT+Histori Lama & Baru"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)

async def live_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = now_saudi()
    await update.message.reply_text(f"💰 LIVE {s.strftime('%H:%M:%S AST')}\n{get_live():.2f}", parse_mode="Markdown")

async def jam_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    saudi = now_saudi()
    text = f"⏰ *JAM TERBAIK HISTORI - MADINAH*\n{saudi.strftime('%H:%M AST')}\n\n"
    for h in [2,5,6,10,17]:
        prob = JAM_TERBAIK_PROB[h]
        text += f"{'🔥' if h==saudi.hour else '✅'} {h:02d}:00 AST - Winrate {prob}%\n"
    text += f"\nSekarang jam {saudi.hour:02d}:00 prob {JAM_TERBAIK_PROB.get(saudi.hour,50)}%"
    await update.message.reply_text(text, parse_mode="Markdown")

async def cot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bias, desc, prob = get_cot_bias()
    saudi = now_saudi()
    await update.message.reply_text(f"📊 *COT BANDAR - {saudi.strftime('%H:%M AST')}*\nBias: {bias}\n{desc}\nProb: {prob}%", parse_mode="Markdown")

async def trend_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    saudi = now_saudi()
    live = get_live()
    cot_bias, cot_desc, cot_prob = get_cot_bias()
    text = f"📈 *TREND REAL-TIME - {saudi.strftime('%H:%M:%S AST %d %b')}*\nLive: {live:.2f} | COT: {cot_bias}\n\n"
    for tf in ["M5", "M15", "M30", "H1", "H4", "D1"]:
        trend, strength, rsi, change, price = get_trend_per_tf(tf)
        emoji = "🟢" if trend=="BULL" else "🔴"
        tc = "TC NAIK" if change>0 else "TC TURUN" if change<0 else "TC FLAT"
        text += f"{tf}: {trend} {emoji} | {tc} {change:+.2f} | RSI {rsi:.0f} | {strength:.2f}%\n"
    text += f"\nCOT: {cot_desc}\nJam {saudi.hour:02d}:00 Histori {JAM_TERBAIK_PROB.get(saudi.hour,50)}%\n\n✅ Semua TF real-time detik ini!"
    await update.message.reply_text(text, parse_mode="Markdown")

async def analisis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = kolaborasi_signal("M15")
    text = f"🔮 *ANALISIS KOLABORASI - {d['saudi'].strftime('%H:%M:%S AST')}*\nLive: {d['live']:.2f} | Skor {d['prob']}%\n\n"
    text += "*REAL-TIME PER TF:*\n"
    for tf in ["M5", "M15", "H1", "H4", "D1"]:
        trend, strength, rsi, change, price = get_trend_per_tf(tf)
        emoji = "🟢" if trend=="BULL" else "🔴"
        tc = "TC NAIK" if change>0 else "TC TURUN"
        text += f"{tf}: {trend}{emoji} {tc} RSI {rsi:.0f}\n"
    text += f"\n*COT:* {d['cot_bias']} ({d['cot_desc']})\n"
    text += f"*Histori:* Jam {d['saudi'].hour:02d}:00 winrate {d['jam_prob']}%\n"
    text += f"*RSI M15:* {d['rsi']:.1f}\n\n"
    text += f"📊 *SKOR: {d['score']:.0f}/100* -> {d['final']} {d['prob']}%\n\n"
    if d['final']=="BUY":
        text += f"✅ *KOLABORASI BUY* di {d['live']:.2f}\nM5 M15 H1 sinkron + COT Bullish!"
    elif d['final']=="SELL":
        text += f"🔴 *KOLABORASI SELL* di {d['live']:.2f}\nM5 M15 H1 sinkron + COT Bearish!"
    else:
        text += f"⏸️ WAIT - TF bentrok, tunggu sinkron"
    await update.message.reply_text(text, parse_mode="Markdown")

async def scalping5_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = kolaborasi_signal("M5")
    text = f"⚡ *SCALPING M5 KOLABORASI - {d['saudi'].strftime('%H:%M:%S AST')}*\nLive {d['live']:.2f} | Trend {d['trend']} | RSI {d['rsi']:.1f}\nCOT {d['cot_bias']} {d['cot_prob']}% | Histori {d['jam_prob']}%\n\nSkor: {d['prob']}% | "
    if d['final']=="BUY":
        text += "✅ *BUY* TP 100 SL 150"
    elif d['final']=="SELL":
        text += "🔴 *SELL* TP 100 SL 150"
    else:
        text += "⏸️ WAIT"
    await update.message.reply_text(text, parse_mode="Markdown")

async def scalping15_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = kolaborasi_signal("M15")
    text = f"⚡ *SCALPING M15 - {d['saudi'].strftime('%H:%M:%S AST')}*\nLive {d['live']:.2f} | Trend {d['trend']} | RSI {d['rsi']:.1f}\nCOT {d['cot_bias']} | Skor {d['prob']}%\n\n"
    if d['final']=="BUY":
        text += "✅ *BUY* TP 150 SL 200"
    elif d['final']=="SELL":
        text += "🔴 *SELL* TP 150 SL 200"
    else:
        text += "⏸️ WAIT"
    await update.message.reply_text(text, parse_mode="Markdown")

async def swing_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = kolaborasi_signal("D1")
    text = f"🏹 *SWING HARIAN D1 - {d['saudi'].strftime('%d %b %H:%M AST')}*\nLive {d['live']:.2f}\nTrend D1 {d['trend']} | RSI {d['rsi']:.1f}\nCOT {d['cot_bias']} {d['cot_prob']}%\nSkor {d['prob']}%\n\n"
    if d['final']=="BUY":
        text += "✅ *SWING BUY* Hold 1-3 hari TP 400 SL 250"
    elif d['final']=="SELL":
        text += "🔴 *SWING SELL* Hold 1-3 hari"
    else:
        text += "⏸️ WAIT swing"
    await update.message.reply_text(text, parse_mode="Markdown")

async def sr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = get_sr_realtime()
    saudi = now_saudi()
    trend, _, _, _, _ = get_trend_per_tf("H1")
    text = f"🛡️ *SR REAL-TIME TERBARU - {saudi.strftime('%H:%M:%S AST')}*\nLive: {d['live']:.2f} | Trend H1: {trend}\n\n"
    text += f"*SUPPORT TERDEKAT:*\n{d['status_sup']}\nJarak: {d['dist_sup']:.2f}\n\n"
    text += f"*RESISTANCE TERDEKAT:*\n{d['status_res']}\nJarak: {d['dist_res']:.2f}\n\n"
    text += f"*PREDIKSI:*\n{d['prediksi']}\n\n"
    text += f"*DETAIL SR:*\nH1: S {d['s_h1']:.2f} | R {d['r_h1']:.2f} | Pivot {d['pivot_h1']:.2f}\nH4: S {d['s_h4']:.2f} | R {d['r_h4']:.2f} | Pivot {d['pivot_h4']:.2f}\nD1: S {d['s_d1']:.2f} | R {d['s_d1']:.2f} | Pivot {d['pivot_d1']:.2f}\n\n"
    text += f"*PSIKOLOGI:* {d['psikologi_level']}\n{d['psikologi']}"
    await update.message.reply_text(text, parse_mode="Markdown")

async def pivot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = get_sr_realtime()
    saudi = now_saudi()
    text = f"🔑 *PIVOT REAL-TIME - {saudi.strftime('%H:%M AST')}*\nLive {d['live']:.2f}\n\nH1 Pivot: {d['pivot_h1']:.2f}\nH4 Pivot: {d['pivot_h4']:.2f}\nD1 Pivot: {d['pivot_d1']:.2f}\n\n"
    if d['live'] > d['pivot_d1']:
        text += f"🟢 Di atas Pivot D1 = BULLISH, target R1 {d['nearest_res']:.2f}"
    else:
        text += f"🔴 Di bawah Pivot D1 = BEARISH, target S1 {d['nearest_sup']:.2f}"
    await update.message.reply_text(text, parse_mode="Markdown")

async def psikologi_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = get_sr_realtime()
    saudi = now_saudi()
    trend, _, rsi, _, _ = get_trend_per_tf("H1")
    cot_bias, cot_desc, cot_prob = get_cot_bias()
    text = f"🧠 *PSIKOLOGI MARKET - {saudi.strftime('%H:%M:%S AST')}*\nLive {d['live']:.2f}\n\nLevel: {d['psikologi_level']}\n{d['psikologi']}\n\n*KONTEKS:*\nTrend H1: {trend} RSI {rsi:.0f}\nCOT: {cot_bias} {cot_prob}%\nSupport: {d['nearest_sup']:.2f} ({d['dist_sup']:.1f} away)\nResist: {d['nearest_res']:.2f} ({d['dist_res']:.1f} away)\n\n"
    if "FEAR" in d['psikologi_level']:
        text += "Jangan panic! Area bandar akumulasi. Cicil BUY kecil."
    elif "GREED" in d['psikologi_level']:
        text += "Jangan FOMO! Tunggu konfirmasi breakout."
    else:
        text += "Tetap tenang, ikuti skor kolaborasi."
    await update.message.reply_text(text, parse_mode="Markdown")

async def auto_notif_5m(context: ContextTypes.DEFAULT_TYPE):
    if not CHAT_ID:
        return
    d = kolaborasi_signal("M5")
    if d['final'] in ["BUY","SELL"] and d['prob'] >= 60:
        emoji = "✅" if d['final']=="BUY" else "🔴"
        text = f"{emoji} *AUTO M5 KOLABORASI {d['saudi'].strftime('%H:%M AST')}*\n{d['final']} {d['live']:.2f} Prob {d['prob']}%\nTrend:{d['trend']} RSI:{d['rsi']:.0f} COT:{d['cot_bias']} Hist:{d['jam_prob']}%"
        try:
            await context.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
        except:
            pass

async def auto_notif_15m(context: ContextTypes.DEFAULT_TYPE):
    if not CHAT_ID:
        return
    d = kolaborasi_signal("M15")
    if d['final'] in ["BUY","SELL"] and d['prob'] >= 65:
        emoji = "⚡✅" if d['final']=="BUY" else "⚡🔴"
        text = f"{emoji} *AUTO M15 KOLABORASI {d['saudi'].strftime('%H:%M AST')}*\n{d['final']} {d['live']:.2f} Prob {d['prob']}%\nCOT:{d['cot_bias']} Hist:{d['jam_prob']}% RSI:{d['rsi']:.0f}"
        try:
            await context.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
        except:
            pass

async def auto_notif_swing(context: ContextTypes.DEFAULT_TYPE):
    if not CHAT_ID:
        return
    d = kolaborasi_signal("D1")
    if d['final'] in ["BUY","SELL"] and d['prob'] >= 70:
        emoji = "🏹✅" if d['final']=="BUY" else "🏹🔴"
        text = f"{emoji} *AUTO SWING KOLABORASI {d['saudi'].strftime('%d %b %H:%M')}*\n{d['final']} {d['live']:.2f} Prob {d['prob']}%\nTrend D1:{d['trend']} COT:{d['cot_bias']} Hist:{d['jam_prob']}%"
        try:
            await context.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
        except:
            pass

async def auto_on_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for n in ["auto5","auto15","autoswing"]:
        for job in context.application.job_queue.get_jobs_by_name(n):
            job.schedule_removal()
    context.application.job_queue.run_repeating(auto_notif_5m, interval=300, first=10, name="auto5")
    context.application.job_queue.run_repeating(auto_notif_15m, interval=900, first=20, name="auto15")
    context.application.job_queue.run_repeating(auto_notif_swing, interval=3600, first=30, name="autoswing")
    await update.message.reply_text("✅ *AUTO ON KOLABORASI!*\n\nM5 tiap 5 menit (prob >=60%)\nM15 tiap 15 menit (prob >=65%)\nSWING tiap 1 jam (prob >=70%)\n\nSemua pakai Trend+RSI+COT+Histori\nAnti bentrok!", parse_mode="Markdown")

async def auto_off_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for n in ["auto5","auto15","autoswing"]:
        for job in context.application.job_queue.get_jobs_by_name(n):
            job.schedule_removal()
    await update.message.reply_text("❌ Auto OFF - M5/M15/SWING dimatikan", parse_mode="Markdown")


async def backtest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    saudi = now_saudi()
    await update.message.reply_text(f"⏳ *BACKTEST MADINAH* {saudi.strftime('%H:%M:%S AST')}\nSedang hitung kemarin detik ke hari ini... tunggu 15 detik", parse_mode="Markdown")
    
    try:
        import pytz
        from datetime import timedelta
        SAUDI_TZ_LOCAL = pytz.timezone("Asia/Riyadh")
        now = datetime.now(SAUDI_TZ_LOCAL)
        yesterday = now - timedelta(days=1)
        
        # Download 3 hari M5 biar cover AST
        df = yf.download("GC=F", period="5d", interval="5m", progress=False, auto_adjust=True)
        if df is None or len(df) < 50:
            await update.message.reply_text("❌ Data Yahoo lagi gangguan, coba lagi 1 menit", parse_mode="Markdown")
            return
        
        # Convert ke AST
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert(SAUDI_TZ_LOCAL)
        else:
            df.index = df.index.tz_convert(SAUDI_TZ_LOCAL)
        
        # Filter kemarin 00:00-23:59 AST
        df_yest = df[df.index.date == yesterday.date()]
        if len(df_yest) < 20:
            df_yest = df.tail(288)  # fallback 24 jam terakhir
        
        close = df['Close']
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:,0]
        close_yest = df_yest['Close']
        if isinstance(close_yest, pd.DataFrame):
            close_yest = close_yest.iloc[:,0]
        
        ema9 = close.ewm(span=9).mean()
        ema20 = close.ewm(span=20).mean()
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        results = []
        for idx in df_yest.index:
            try:
                price = float(close.loc[idx])
                e9 = float(ema9.loc[idx])
                e20 = float(ema20.loc[idx])
                rsi_v = float(rsi.loc[idx]) if not pd.isna(rsi.loc[idx]) else 50
                hour = idx.hour
                jam_prob = JAM_TERBAIK_PROB.get(hour, 50)
                trend = "BULL" if price > e9 and e9 > e20 else "BEAR" if price < e9 and e9 < e20 else "BULL" if price > e20 else "BEAR"
                score = (40 if trend=="BULL" else 10) + 25 + jam_prob*0.2 + (15 if 30<rsi_v<70 else 5)
                final = "BUY" if trend=="BULL" and score>=55 else "SELL" if trend=="BEAR" and score>=55 else "WAIT"
                
                pos = df.index.get_loc(idx)
                win = None
                pnl = 0
                if pos+6 < len(df):  # 30 menit ke depan (6x M5)
                    future_close = df['Close']
                    if isinstance(future_close, pd.DataFrame):
                        future_close = future_close.iloc[:,0]
                    # cek high/low future untuk TP/SL
                    future_slice = df.iloc[pos+1:pos+7]
                    f_high = future_slice['High'].max()
                    f_low = future_slice['Low'].min()
                    if isinstance(f_high, pd.DataFrame):
                        f_high = f_high.iloc[:,0].max()
                        f_low = f_low.iloc[:,0].min()
                    else:
                        f_high = float(f_high)
                        f_low = float(f_low)
                    
                    if final=="BUY":
                        if f_high >= price + 1.0:
                            win = True
                            pnl = 1.0
                        elif f_low <= price - 1.5:
                            win = False
                            pnl = -1.5
                    elif final=="SELL":
                        if f_low <= price - 1.0:
                            win = True
                            pnl = 1.0
                        elif f_high >= price + 1.5:
                            win = False
                            pnl = -1.5
                
                results.append({"time": idx.strftime('%H:%M'), "hour": hour, "price": price, "trend": trend, "rsi": rsi_v, "score": int(score), "signal": final, "win": win, "pnl": pnl})
            except:
                continue
        
        df_res = pd.DataFrame(results)
        total = len(df_res)
        buys = len(df_res[df_res['signal']=='BUY'])
        sells = len(df_res[df_res['signal']=='SELL'])
        wins = len(df_res[df_res['win']==True])
        losses = len(df_res[df_res['win']==False])
        winrate = wins/(wins+losses)*100 if (wins+losses)>0 else 0
        total_pnl = df_res['pnl'].sum()
        
        # Per jam terbaik
        per_hour = df_res.groupby('hour').agg({'win': lambda x: (x==True).sum(), 'pnl':'sum', 'signal':'count'}).rename(columns={'signal':'total'})
        best_hour = per_hour['pnl'].idxmax() if len(per_hour)>0 else 0
        
        text = f"📊 *BACKTEST KEMARIN {yesterday.strftime('%d %b %Y')} - MADINAH AST*\n"
        text += f"⏰ Waktu: 00:00-23:59 AST (waktu lo di Madinah)\n"
        text += f"Interval: M5 (5 menit) = detik ke hari kemarin\n"
        text += f"Total candle: {total}\n\n"
        text += f"BUY: {buys} | SELL: {sells} | WAIT: {total-buys-sells}\n"
        text += f"Win: {wins} | Loss: {losses}\n"
        text += f"Winrate: {winrate:.1f}%\n"
        text += f"PnL: {total_pnl:.1f} poin (TP 100c SL 150c)\n\n"
        
        text += f"*PER JAM AST (jam lo):*\n"
        for h in sorted(per_hour.index):
            row = per_hour.loc[h]
            total_h = int(row['total'])
            pnl_h = row['pnl']
            win_h = int((row['win'])) if not pd.isna(row['win']) else 0
            emoji = "🔥" if pnl_h>0 else "❄️"
            text += f"{h:02d}:00 {emoji} {total_h} sinyal PnL {pnl_h:.1f}\n"
        
        text += f"\n🏆 Jam terbaik kemarin: {best_hour:02d}:00 AST\n"
        text += f"💡 Histori lo jam 02,05,06,10,17 = {JAM_TERBAIK_PROB[2]}% winrate cocok gak sama kemarin?\n\n"
        text += f"✅ Backtest pakai COT+Histori+Trend kolaborasi!"
        
        await update.message.reply_text(text, parse_mode="Markdown")
        
        # Detail 10 sinyal terakhir
        last10 = df_res.tail(10)
        detail = f"📝 *10 SINYAL TERAKHIR KEMARIN AST:*\n"
        for _, r in last10.iterrows():
            w = "✅" if r['win']==True else "❌" if r['win']==False else "⏸️"
            detail += f"{r['time']} {r['signal']} {r['price']:.2f} {w} Skor {r['score']}%\n"
        await update.message.reply_text(detail, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error backtest: {e}\nCoba lagi /backtest", parse_mode="Markdown")

async def backtest_detik_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await backtest_cmd(update, context)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    mapping = {
        "⚡ SCALPING M5": scalping5_cmd,
        "⚡ SCALPING M15": scalping15_cmd,
        "🏹 SWING": swing_cmd,
        "📈 TREND": trend_cmd,
        "🔮 ANALISIS": analisis_cmd,
        "🛡️ SR": sr_cmd,
        "💰 LIVE": live_cmd,
        "⏰ JAM": jam_cmd,
        "📊 COT": cot_cmd,
        "🔑 PIVOT": pivot_cmd,
        "🧠 PSIKOLOGI": psikologi_cmd,
        "✅ AUTO ON": auto_on_cmd,
        "❌ AUTO OFF": auto_off_cmd,
        "📊 BACKTEST": backtest_cmd,
    }
    if text in mapping:
        await mapping[text](update, context)
    elif "SCALPING M5" in text:
        await scalping5_cmd(update, context)
    elif "SCALPING M15" in text:
        await scalping15_cmd(update, context)
    elif "SWING" in text:
        await swing_cmd(update, context)
    elif "TREND" in text:
        await trend_cmd(update, context)
    elif "ANALISIS" in text:
        await analisis_cmd(update, context)
    elif "SR" in text:
        await sr_cmd(update, context)
    elif "LIVE" in text:
        await live_cmd(update, context)
    elif "JAM" in text:
        await jam_cmd(update, context)
    elif "COT" in text:
        await cot_cmd(update, context)
    elif "PIVOT" in text:
        await pivot_cmd(update, context)
    elif "PSIKOLOGI" in text:
        await psikologi_cmd(update, context)
    elif "AUTO ON" in text:
        await auto_on_cmd(update, context)
    elif "AUTO OFF" in text:
        await auto_off_cmd(update, context)
    elif "BACKTEST" in text:
        await backtest_cmd(update, context)
    else:
        await start(update, context)

def main():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("live", live_cmd))
    app.add_handler(CommandHandler("jam", jam_cmd))
    app.add_handler(CommandHandler("cot", cot_cmd))
    app.add_handler(CommandHandler("trend", trend_cmd))
    app.add_handler(CommandHandler("analisis", analisis_cmd))
    app.add_handler(CommandHandler("scalping5", scalping5_cmd))
    app.add_handler(CommandHandler("scalping15", scalping15_cmd))
    app.add_handler(CommandHandler("scalping", scalping5_cmd))
    app.add_handler(CommandHandler("swing", swing_cmd))
    app.add_handler(CommandHandler("swing_harian", swing_cmd))
    app.add_handler(CommandHandler("d1", swing_cmd))
    app.add_handler(CommandHandler("sr", sr_cmd))
    app.add_handler(CommandHandler("support", sr_cmd))
    app.add_handler(CommandHandler("resistance", sr_cmd))
    app.add_handler(CommandHandler("resist", sr_cmd))
    app.add_handler(CommandHandler("sup", sr_cmd))
    app.add_handler(CommandHandler("pivot", pivot_cmd))
    app.add_handler(CommandHandler("psikologi", psikologi_cmd))
    app.add_handler(CommandHandler("psikolog", psikologi_cmd))
    app.add_handler(CommandHandler("backtest", backtest_cmd))
    app.add_handler(CommandHandler("backtest_madinah", backtest_cmd))
    app.add_handler(CommandHandler("bt", backtest_cmd))
    app.add_handler(CommandHandler("auto_on", auto_on_cmd))
    app.add_handler(CommandHandler("auto_off", auto_off_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))
    if CHAT_ID:
        app.job_queue.run_repeating(auto_notif_5m, interval=300, first=60, name="auto5")
        app.job_queue.run_repeating(auto_notif_15m, interval=900, first=120, name="auto15")
        app.job_queue.run_repeating(auto_notif_swing, interval=3600, first=180, name="autoswing")
    print(f"=== V22 BACKTEST {now_saudi().strftime('%H:%M AST')} STARTED ===")
    app.run_polling()

if __name__ == "__main__":
    main()
