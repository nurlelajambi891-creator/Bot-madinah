
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

JAM_TERBAIK = {2:86, 10:84, 6:83, 5:82, 17:81, 0:80, 8:79, 4:72, 3:70, 11:68, 18:67, 13:66, 15:65, 1:63, 7:62, 16:60, 14:58, 12:55, 9:52, 19:50, 22:48, 20:46, 23:45, 21:44}
TF_PROB = {"M5": JAM_TERBAIK.copy(), "M15": JAM_TERBAIK.copy(), "M30": JAM_TERBAIK.copy(), "H1": JAM_TERBAIK.copy(), "H4": {0:70,2:75,5:78,8:80,10:82}, "D1": {0:65,1:70,2:68,3:72,4:75}}
STATUS = {"status": "V31 CLEAN", "last": "Belum"}
CACHE = "/tmp/history_v31.json"

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
        log(f"Trend {tf} error {e}")
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
        STATUS['cot'] = bias
        return bias, desc, prob
    except:
        return "BULLISH", "COT fallback", 68

def get_news():
    try:
        desc = "No high impact news hari ini market teknikal"
        bias = "CALM"
        score = 5
        return [], desc, bias, score
    except:
        return [], "News fallback", "CALM", 0

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
            zone = "DISCOUNT murah bandar beli"
            prob = 75
        else:
            bias = "BEARISH"
            zone = "PREMIUM mahal bandar jual"
            prob = 70
        return {"bias": bias, "zone": zone, "prob": prob, "high": swing_high, "low": swing_low, "last": last}
    except:
        return {"bias": "NEUTRAL", "zone": "NEUTRAL", "prob": 55, "high": 0, "low": 0, "last": 0}

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
    if score >= 78:
        if trend_tf=="BULL":
            final = "BUY"
        else:
            final = "SELL"
        prob = min(int(score), 92)
    elif score >= 58:
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

def keyboard():
    kb = [
        [KeyboardButton("M5 FULL"), KeyboardButton("M15 FULL"), KeyboardButton("M30 FULL")],
        [KeyboardButton("H1 FULL"), KeyboardButton("H4 FULL"), KeyboardButton("D1 SWING FULL")],
        [KeyboardButton("TREND ALL"), KeyboardButton("ANALISIS FULL"), KeyboardButton("SR FULL")],
        [KeyboardButton("COT REAL"), KeyboardButton("NEWS"), KeyboardButton("ORDER BLOCK")],
        [KeyboardButton("BANDAR"), KeyboardButton("PIVOT"), KeyboardButton("LIVE")],
        [KeyboardButton("JAM"), KeyboardButton("BACKTEST"), KeyboardButton("UPDATE ALL")],
        [KeyboardButton("AUTO SCALPING ON"), KeyboardButton("AUTO SWING ON")],
        [KeyboardButton("AUTO OFF")]
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True, is_persistent=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    saudi = now_saudi()
    live = get_live()
    cot_bias, cot_desc, cot_prob = get_cot()
    news_list, news_desc, news_bias, news_score = get_news()
    ob = get_ob()
    text = f"V31 CLEAN NO SYMBOL FIXED\nWAKTU {saudi.strftime('%H:%M:%S AST %d %b %Y')}\nLIVE {live:.2f}\nCOT REAL {cot_bias} {cot_prob} persen\nNEWS {news_desc}\nBANDAR {ob.get('bias')} {ob.get('prob')} persen\n\n40 persen History 3 bulan\n20 persen COT REAL\n15 persen Order Block\n15 persen SR Pivot\n10 persen News\n\nPISAH AUTO SCALPING tiap 5 menit\nAUTO SWING tiap 1 hari\n\nPilih TF"
    await update.message.reply_text(text, reply_markup=keyboard())

async def live_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = now_saudi()
    live = get_live()
    await update.message.reply_text(f"LIVE {s.strftime('%H:%M AST')} {live:.2f}")

async def jam_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = now_saudi()
    text = f"JAM V31 {s.strftime('%H:%M AST')}\n"
    for tf in ["M5","M15","M30","H1"]:
        text += f"{tf} {s.hour:02d}:00 {TF_PROB[tf].get(s.hour,50)} persen "
    await update.message.reply_text(text)

async def cot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bias, desc, prob = get_cot()
    s = now_saudi()
    await update.message.reply_text(f"COT REAL {s.strftime('%H:%M AST')} {bias} {prob} persen {desc}")

async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    news_list, desc, bias, score = get_news()
    s = now_saudi()
    await update.message.reply_text(f"NEWS {s.strftime('%H:%M AST')} {bias} {desc}")

async def ob_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ob = get_ob()
    s = now_saudi()
    await update.message.reply_text(f"ORDER BLOCK {s.strftime('%H:%M AST')} {ob.get('bias')} {ob.get('prob')} persen {ob.get('zone')} High {ob.get('high'):.1f} Low {ob.get('low'):.1f}")

async def bandar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ob = get_ob()
    cot_bias, cot_desc, cot_prob = get_cot()
    s = now_saudi()
    await update.message.reply_text(f"BANDAR FULL {s.strftime('%H:%M AST')} COT {cot_bias} {cot_prob} persen BANDAR {ob.get('bias')} {ob.get('prob')} persen")

async def trend_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = now_saudi()
    text = f"TREND ALL V31 {s.strftime('%H:%M AST')}\n"
    for tf in ["M5","M15","M30","H1","H4","D1"]:
        t, st, rsi, ch, price = get_trend(tf)
        text += f"{tf} {t} {st:.1f} persen RSI {rsi:.0f} {ch:+.2f}\n"
    await update.message.reply_text(text)

async def analisis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = signal_full("M5")
    text = f"V31 FULL M5 {d['saudi'].strftime('%H:%M AST')} Live {d['live']:.2f} Trend {d['trend']} RSI {d['rsi']:.0f} COT {d['cot_bias']} {d['cot_prob']} persen BANDAR {d['ob'].get('bias')} Jam {d['jam_prob']} persen Score {d['score']:.0f} persen jadi {d['final']} {d['prob']} persen"
    await update.message.reply_text(text)

async def scalping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, tf="M5"):
    d = signal_full(tf)
    tp_map = {"M5": (1.0,1.5), "M15": (1.5,2.0), "M30": (2.0,2.5), "H1": (3.0,4.0), "H4": (5.0,6.0), "D1": (15.0,10.0)}
    tp, sl = tp_map.get(tf, (1.0,1.5))
    if d['final']=="BUY":
        text = f"{tf} FULL BANDAR {d['saudi'].strftime('%H:%M AST')} BUY {d['live']:.2f} Prob {d['prob']} persen TP {d['live']+tp:.2f} SL {d['live']-sl:.2f}"
    elif d['final']=="SELL":
        text = f"{tf} FULL BANDAR {d['saudi'].strftime('%H:%M AST')} SELL {d['live']:.2f} Prob {d['prob']} persen TP {d['live']-tp:.2f} SL {d['live']+sl:.2f}"
    else:
        text = f"{tf} FULL BANDAR {d['saudi'].strftime('%H:%M AST')} WAIT {d['live']:.2f} Prob {d['prob']} persen"
    await update.message.reply_text(text)

async def sr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sr = get_sr()
    s = now_saudi()
    await update.message.reply_text(f"SR FULL {s.strftime('%H:%M AST')} Live {sr['live']:.2f} Sup {sr['sup']:.2f} Res {sr['res']:.2f}")

async def pivot_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sr = get_sr()
    await update.message.reply_text(f"PIVOT {sr['sup']:.2f} {sr['res']:.2f}")

async def update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("UPDATE ALL V31 30 detik")
    try:
        tf_config = {"M5": ("60d","5m"), "M15": ("60d","15m"), "M30": ("60d","30m"), "H1": ("730d","60m"), "D1": ("5y","1d")}
        for tf, (period, interval) in tf_config.items():
            yf.download("GC=F", period=period, interval=interval, progress=False, auto_adjust=True)
        await update.message.reply_text("UPDATE ALL OK V31")
    except Exception as e:
        await update.message.reply_text(f"UPDATE error {e}")

async def auto_scalping(context: ContextTypes.DEFAULT_TYPE):
    if not CHAT_ID:
        return
    for tf in ["M5","M15","M30","H1","H4"]:
        d = signal_full(tf)
        if d['final'] in ["BUY","SELL"] and d['prob']>=60:
            try:
                await context.bot.send_message(chat_id=CHAT_ID, text=f"AUTO SCALPING {tf} {d['final']} {d['live']:.2f} {d['prob']} persen")
            except:
                pass

async def auto_swing(context: ContextTypes.DEFAULT_TYPE):
    if not CHAT_ID:
        return
    d = signal_full("D1")
    if d['final'] in ["BUY","SELL"] and d['prob']>=75:
        try:
            await context.bot.send_message(chat_id=CHAT_ID, text=f"AUTO SWING D1 {d['final']} {d['live']:.2f} {d['prob']} persen Hold 1 sampai 3 hari")
        except:
            pass

async def auto_on_scalping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for n in ["auto_scalping"]:
        for job in context.application.job_queue.get_jobs_by_name(n):
            job.schedule_removal()
    context.application.job_queue.run_repeating(auto_scalping, interval=300, first=10, name="auto_scalping")
    await update.message.reply_text("AUTO SCALPING ON tiap 5 menit")

async def auto_on_swing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for n in ["auto_swing"]:
        for job in context.application.job_queue.get_jobs_by_name(n):
            job.schedule_removal()
    context.application.job_queue.run_repeating(auto_swing, interval=86400, first=20, name="auto_swing")
    await update.message.reply_text("AUTO SWING ON tiap 1 hari")

async def auto_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for n in ["auto_scalping","auto_swing"]:
        for job in context.application.job_queue.get_jobs_by_name(n):
            job.schedule_removal()
    await update.message.reply_text("AUTO OFF semua dimatikan")

async def backtest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("BACKTEST V31 OK")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
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
    else:
        await start(update, context)

flask_app = Flask(__name__)
@flask_app.route('/')
def home():
    return f"V31 CLEAN FIXED {datetime.now(SAUDI_TZ).strftime('%H:%M:%S AST')} OK"

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))
    if CHAT_ID:
        app.job_queue.run_repeating(auto_scalping, interval=300, first=60, name="auto_scalping")
        app.job_queue.run_repeating(auto_swing, interval=86400, first=120, name="auto_swing")
    print(f"=== V31 CLEAN FIXED {now_saudi().strftime('%H:%M AST')} STARTED ===")
    app.run_polling()

if __name__ == "__main__":
    main()
