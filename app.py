import os, json, time, threading, requests, pytz
from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime, timedelta
from groq import Groq
import re

app = Flask(__name__, static_folder='static')
VERSION = "8.1"

TEHRAN = pytz.timezone("Asia/Tehran")

# ==================== متغیرهای محیطی ====================
GIST_TOKEN = os.environ.get("GIST_TOKEN", "")
GIST_ID_ALERTS = os.environ.get("GIST_ID", "")
GIST_ID_JOURNAL = os.environ.get("GIST_ID_JOURNAL", "")
ALERTS_FILE = "alerts.json"
JOURNAL_FILE = "journal_data.json"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

_cache_alerts = None
_cache_journal = None

def now_teh():
    return datetime.now(TEHRAN).strftime("%Y-%m-%d %H:%M:%S")

def now_pretty():
    return datetime.now(TEHRAN).strftime("%Y-%m-%d %H:%M:%S")

def get_pip_multiplier(symbol):
    sym_up = symbol.upper()
    crypto_list = ['BTC','ETH','SOL','BNB','XRP','ADA','DOGE','TRX','TON','AVAX','MATIC','DOT','LINK','UNI','ATOM','LTC','SHIB','OP','ARB','NEAR','FTM','SAND','MANA']
    if any(x in sym_up for x in crypto_list):
        return 1
    if "XAU" in sym_up or "XAG" in sym_up:
        return 10
    if "JPY" in sym_up:
        return 100
    return 10000

def is_crypto_symbol(sym):
    sym_up = sym.upper()
    crypto_list = ['BTC','ETH','SOL','BNB','XRP','ADA','DOGE','TRX','TON','AVAX','MATIC','DOT','LINK','UNI','ATOM','LTC','SHIB','OP','ARB','NEAR','FTM','SAND','MANA']
    return any(c in sym_up for c in crypto_list)

def _empty_alerts():
    return {
        "alerts": [], "archive": [], "telegram": {"bot_token": "", "chat_ids": []},
        "users": [], "errors": [], "last_update": None
    }

def fix_alerts(data):
    e = _empty_alerts()
    for k in e:
        if k not in data:
            data[k] = e[k]
    return data

def load_alerts():
    global _cache_alerts
    if _cache_alerts is not None:
        return _cache_alerts
    if GIST_ID_ALERTS and GIST_TOKEN:
        try:
            print(f"[alerts] Loading from Gist {GIST_ID_ALERTS}...")
            r = requests.get(f"https://api.github.com/gists/{GIST_ID_ALERTS}",
                             headers={"Authorization": f"token {GIST_TOKEN}"}, timeout=10)
            if r.status_code == 200:
                content = r.json()["files"][ALERTS_FILE]["content"]
                _cache_alerts = fix_alerts(json.loads(content))
                print(f"[alerts] Loaded from Gist")
                return _cache_alerts
            else:
                print(f"[alerts] Gist read failed: {r.status_code}")
        except Exception as e:
            print(f"[alerts] Exception: {e}")
    if os.path.exists(ALERTS_FILE):
        try:
            with open(ALERTS_FILE, "r", encoding="utf-8") as f:
                _cache_alerts = fix_alerts(json.load(f))
                print(f"[alerts] Loaded from local")
                return _cache_alerts
        except Exception as e:
            print(f"[alerts] Local error: {e}")
    _cache_alerts = _empty_alerts()
    return _cache_alerts

def save_alerts(data):
    global _cache_alerts
    _cache_alerts = data
    if GIST_ID_ALERTS and GIST_TOKEN:
        try:
            r = requests.patch(f"https://api.github.com/gists/{GIST_ID_ALERTS}",
                               headers={"Authorization": f"token {GIST_TOKEN}"},
                               json={"files": {ALERTS_FILE: {"content": json.dumps(data, indent=2, ensure_ascii=False)}}},
                               timeout=10)
            if r.status_code == 200:
                print(f"[alerts] Saved to Gist")
            else:
                print(f"[alerts] Gist save failed: {r.status_code}")
        except Exception as e:
            print(f"[alerts] Exception: {e}")
    with open(ALERTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_journal():
    global _cache_journal
    if _cache_journal is not None:
        return _cache_journal
    if GIST_ID_JOURNAL and GIST_TOKEN:
        try:
            print(f"[journal] Loading from Gist {GIST_ID_JOURNAL}...")
            r = requests.get(f"https://api.github.com/gists/{GIST_ID_JOURNAL}",
                             headers={"Authorization": f"token {GIST_TOKEN}"}, timeout=10)
            if r.status_code == 200:
                files = r.json().get("files", {})
                if JOURNAL_FILE in files:
                    content = files[JOURNAL_FILE]["content"]
                    _cache_journal = json.loads(content)
                    if not isinstance(_cache_journal, list):
                        _cache_journal = []
                    print(f"[journal] Loaded {len(_cache_journal)} trades from Gist")
                    return _cache_journal
                else:
                    print(f"[journal] File {JOURNAL_FILE} not found")
            else:
                print(f"[journal] Gist read failed: {r.status_code}")
        except Exception as e:
            print(f"[journal] Exception: {e}")
    if os.path.exists(JOURNAL_FILE):
        try:
            with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
                _cache_journal = json.load(f)
                if not isinstance(_cache_journal, list):
                    _cache_journal = []
                print(f"[journal] Loaded {len(_cache_journal)} trades from local")
                return _cache_journal
        except Exception as e:
            print(f"[journal] Local error: {e}")
    _cache_journal = []
    return _cache_journal

def save_journal(journal_list):
    global _cache_journal
    _cache_journal = journal_list
    if GIST_ID_JOURNAL and GIST_TOKEN:
        try:
            r = requests.patch(f"https://api.github.com/gists/{GIST_ID_JOURNAL}",
                               headers={"Authorization": f"token {GIST_TOKEN}"},
                               json={"files": {JOURNAL_FILE: {"content": json.dumps(journal_list, indent=2, ensure_ascii=False)}}},
                               timeout=10)
            if r.status_code == 200:
                print(f"[journal] Saved {len(journal_list)} trades to Gist")
            else:
                print(f"[journal] Gist save failed: {r.status_code}")
        except Exception as e:
            print(f"[journal] Exception: {e}")
    with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
        json.dump(journal_list, f, indent=2, ensure_ascii=False)

def log_error(msg):
    try:
        data = load_alerts()
        errs = data.get("errors", [])
        errs.append({"time": now_teh(), "msg": str(msg)})
        data["errors"] = errs[-20:]
        save_alerts(data)
    except:
        pass
    print(f"[ERR] {msg}")

def is_forex_market_open():
    now_utc = datetime.utcnow()
    wd = now_utc.weekday()
    if wd == 5: return False
    if wd == 6: return now_utc.hour >= 21
    return True

H = {"User-Agent": "Mozilla/5.0 (compatible; PriceBot/1.0)"}
_last_known = {}

def get_forex_prices_batch(symbols):
    if not symbols: return {}
    clean = [s.upper().replace("/", "").replace(" ", "") for s in symbols]
    qs = "&".join(f"symbols={s}" for s in clean)
    url = f"https://biquote.io/api/latest?{qs}"
    try:
        r = requests.get(url, timeout=12, headers=H)
        r.raise_for_status()
        raw = r.json()
        result = {}
        if isinstance(raw, list):
            for item in raw:
                sym = item.get("symbol","").upper().replace("/","")
                bid = item.get("bid") or item.get("price") or item.get("last")
                if sym and bid and float(bid) > 0:
                    result[sym] = float(bid)
                    _last_known[sym] = {"price": float(bid), "ts": now_teh(), "stale": False}
        elif isinstance(raw, dict):
            for sym, data in raw.items():
                if isinstance(data, dict):
                    bid = data.get("bid") or data.get("price") or data.get("last")
                elif isinstance(data, (int, float)):
                    bid = data
                else:
                    bid = None
                if bid and float(bid) > 0:
                    result[sym.upper()] = float(bid)
                    _last_known[sym.upper()] = {"price": float(bid), "ts": now_teh(), "stale": False}
        if result: return result
    except Exception: pass
    result = {}
    for sym in clean:
        if sym in _last_known:
            cached = _last_known[sym]
            _last_known[sym]["stale"] = True
            result[sym] = cached["price"]
        else:
            try:
                base, quote = sym[:3], sym[3:6]
                r3 = requests.get(f"https://api.frankfurter.app/latest?from={base}&to={quote}", timeout=7)
                if r3.ok:
                    rate = r3.json().get("rates", {}).get(quote)
                    if rate:
                        result[sym] = float(rate)
                        _last_known[sym] = {"price": float(rate), "ts": now_teh(), "stale": False}
            except Exception: pass
    return result

def get_forex_price(symbol):
    sym = symbol.upper().replace("/","").replace(" ","")
    batch = get_forex_prices_batch([sym])
    return batch.get(sym)

CG_MAP = {
    "BTC":"bitcoin","ETH":"ethereum","BNB":"binancecoin","SOL":"solana",
    "XRP":"ripple","ADA":"cardano","DOGE":"dogecoin","TRX":"tron",
    "TON":"toncoin","AVAX":"avalanche-2","LINK":"chainlink","DOT":"polkadot",
    "MATIC":"matic-network","UNI":"uniswap","ATOM":"cosmos","LTC":"litecoin",
    "SHIB":"shiba-inu","OP":"optimism","ARB":"arbitrum","NEAR":"near",
}

def _cg_price(base):
    gid = CG_MAP.get(base)
    if not gid: return None
    try:
        d = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={gid}&vs_currencies=usd", headers=H, timeout=8).json()
        return float(d[gid]["usd"])
    except:
        return None

def get_crypto_price(symbol):
    base = symbol.upper()
    for s in ["USDT","USDC","USD","BUSD"]:
        base = base.replace(s,"")
    base = base.replace("/","").strip()
    try:
        r = requests.get(f"https://biquote.io/api/latest?symbols={base}USD", timeout=8, headers=H)
        if r.ok:
            raw = r.json()
            bid = None
            if isinstance(raw, list) and raw:
                bid = raw[0].get("bid") or raw[0].get("price") or raw[0].get("last")
            elif isinstance(raw, dict):
                bid = raw.get("bid") or raw.get("price") or raw.get("last")
            if bid and float(bid) > 100:
                return float(bid)
    except Exception: pass
    sources = [
        ("OKX", lambda: float(requests.get(f"https://www.okx.com/api/v5/market/ticker?instId={base}-USDT", headers=H).json()["data"][0]["last"])),
        ("Binance-USDT", lambda: float(requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={base}USDT", headers=H).json()["price"])),
    ]
    for name, fn in sources:
        try:
            p = fn()
            if p and p > 0:
                return float(p)
        except: pass
    log_error(f"Crypto price failed for {symbol}")
    return None

def get_price(symbol, asset_type):
    if asset_type == "crypto":
        return get_crypto_price(symbol)
    return get_forex_price(symbol)

def send_tg(token, chat_id, text):
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": str(chat_id), "text": text, "parse_mode": "HTML"}, timeout=10, headers=H)
        return r.status_code == 200
    except: return False

def broadcast(token, chat_ids, text):
    return [send_tg(token, c, text) for c in chat_ids]

def _get_token_and_cids():
    data = load_alerts()
    tg = data.get("telegram", {})
    token = tg.get("bot_token", "")
    cids = list(tg.get("chat_ids", []))
    leg = tg.get("chat_id", "")
    if leg and leg not in [str(x) for x in cids]:
        cids.append(leg)
    return token, cids, data

def poll_telegram():
    last_id = 0
    while True:
        try:
            token, _, data = _get_token_and_cids()
            if not token:
                time.sleep(30)
                continue
            r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", params={"offset": last_id+1, "timeout": 20, "limit": 100}, timeout=30, headers=H)
            if r.status_code != 200:
                time.sleep(10)
                continue
            for upd in r.json().get("result", []):
                last_id = upd["update_id"]
                msg = upd.get("message", {})
                txt = msg.get("text", "")
                ch = msg.get("chat", {})
                cid = str(ch.get("id", ""))
                uname = ch.get("username", "") or ch.get("first_name", "")
                if txt.startswith("/start") and cid:
                    data = load_alerts()
                    users = data.get("users", [])
                    if cid not in [str(u["chat_id"]) for u in users]:
                        users.append({"chat_id": cid, "username": uname, "joined_at": now_teh()})
                        data["users"] = users
                        ids = data.get("telegram", {}).get("chat_ids", [])
                        if cid not in [str(x) for x in ids]:
                            ids.append(cid)
                        data["telegram"]["chat_ids"] = ids
                        save_alerts(data)
                        send_tg(token, cid, f"👋 سلام <b>{uname}</b>!\n✅ در سیستم آلارم ثبت شدید. 🔔")
        except Exception as e:
            print(f"[poll] {e}")
        time.sleep(5)

notified = set()
_loop_count = 0

def check_alerts():
    global _loop_count
    while True:
        try:
            _loop_count += 1
            global _cache_alerts
            _cache_alerts = None
            token, cids, data = _get_token_and_cids()
            active = [a for a in data.get("alerts", []) if a.get("active")]
            if not active:
                save_alerts(data)
                time.sleep(60)
                continue
            forex_open = is_forex_market_open()
            due_forex, due_crypto = [], []
            for a in active:
                sym = a["symbol"]
                atype = a.get("type", "crypto")
                if atype == "forex" and not forex_open:
                    continue
                if atype == "forex":
                    due_forex.append(sym)
                else:
                    due_crypto.append(sym)
            price_map = {}
            if due_forex:
                batch = get_forex_prices_batch(due_forex)
                for sym, p in batch.items():
                    price_map[(sym, "forex")] = p
            for sym in due_crypto:
                p = get_crypto_price(sym)
                price_map[(sym.upper(), "crypto")] = p
            fired = []
            for a in active:
                sym = a["symbol"]
                atype = a.get("type", "crypto")
                key = (sym.upper(), atype)
                if key not in price_map: continue
                cur = price_map[key]
                if cur is None: continue
                tgt = float(a["target_price"])
                cond = a.get("condition", "above")
                triggered = (cond == "above" and cur >= tgt) or (cond == "below" and cur <= tgt)
                if triggered and a["id"] not in notified:
                    notified.add(a["id"])
                    a["active"] = False
                    fired.append(a["id"])
                    if token and cids:
                        arrow = "📈 از هدف رد شد" if cond == "above" else "📉 به هدف رسید"
                        msg = f"🚨 آلارم {sym} {arrow}\nهدف: {tgt}\nقیمت: {cur}"
                        broadcast(token, cids, msg)
            if fired:
                arch = data.get("archive", [])
                for fid in fired:
                    obj = next((x for x in data["alerts"] if x["id"] == fid), None)
                    if obj: arch.append(obj)
                data["archive"] = arch
                data["alerts"] = [x for x in data["alerts"] if x["id"] not in fired]
            save_alerts(data)
        except Exception as e:
            log_error(f"check_alerts: {e}")
        time.sleep(60)

def fmt_price(p, sym=""):
    if p is None: return "—"
    v = float(p)
    su = sym.upper()
    if "XAU" in su or "XAG" in su:
        return f"${v:.2f}"
    if "JPY" in su:
        return f"{v:.3f}"
    return f"{v:.5f}"

def tehran_to_utc(tehran_str):
    try:
        parts = tehran_str.strip().split(" ")
        dparts = parts[0].split("-")
        tparts = (parts[1] if len(parts) > 1 else "00:00").split(":")
        y, m, d = int(dparts[0]), int(dparts[1]), int(dparts[2])
        h, mi = int(tparts[0]), int(tparts[1])
        dt_teh = datetime(y, m, d, h, mi)
        return dt_teh - timedelta(hours=3, minutes=30)
    except: return None

# ====================================================================
# تابع اصلی بررسی کندل‌ها – اصلاح شده: فقط SL یا 3R باعث بسته شدن می‌شود
# ====================================================================
def check_sltp_hit_with_details(symbol, tf, entry_time_str, direction, entry_price, sl_price, tp_price, size=1.0, max_post_sl_pips=300, r3_override=None):
    """
    بازگشت: (hit, hit_price, tp_hit, tp_hit_price, last_close, pnl, mfe_pip, mae_pip, candle_lines, found_3r,
             free_risk_was_possible, free_risk_saved, reached_1r_at, pullback_after_1r,
             post_sl_max_profit, post_sl_reached_1r, post_sl_reached_1_5r, post_sl_reached_2r, post_sl_reached_3r,
             mfe_before_sl, passed_1r, snapshot_bars)
    * hit: 'sl' یا 'tp3' (None اگر هنوز بسته نشده)
    * tp_hit: True اگر به TP رسیده باشد (حتی اگر بسته نشده)
    * snapshot_bars: کندل‌ها تا آخرین برخورد با SL یا 3R
    """
    try:
        tf_limits = {"1m":2000, "5m":1500, "15m":1000, "1h":700, "4h":500, "1d":300}
        bar_limit = tf_limits.get(tf, 700)
        url = f"https://biquote.io/api/{symbol}/ohlc?interval={tf}&limit={bar_limit}"
        r = requests.get(url, timeout=12, headers=H)
        if r.status_code != 200:
            return (None, None, False, None, None, None, None, None, [], False, False, False, None, False, None, False, False, False, False, 0.0, False, [])
        data = r.json()
        bars = data.get("bars") or data.get("data") or (data if isinstance(data, list) else [])
        if not bars:
            return (None, None, False, None, None, None, None, None, [], False, False, False, None, False, None, False, False, False, False, 0.0, False, [])

        entry_utc = tehran_to_utc(entry_time_str)
        if not entry_utc:
            return (None, None, False, None, None, None, None, None, [], False, False, False, None, False, None, False, False, False, False, 0.0, False, [])

        all_bars_sorted = []
        for b in bars:
            ts = b.get("openTime") or b.get("time") or b.get("timestamp")
            if not ts: continue
            if isinstance(ts, (int, float)):
                bdt = datetime.utcfromtimestamp(ts)
            else:
                try:
                    bdt = datetime.strptime(ts.replace("Z",""), "%Y-%m-%dT%H:%M:%S")
                except: continue
            all_bars_sorted.append((bdt, b))
        all_bars_sorted.sort(key=lambda x: x[0])

        entry_bar_idx = 0
        for i, (bdt, b) in enumerate(all_bars_sorted):
            if bdt >= entry_utc:
                entry_bar_idx = i
                break

        after = all_bars_sorted[entry_bar_idx:]
        if not after:
            return (None, None, False, None, None, None, None, None, [], False, False, False, None, False, None, False, False, False, False, 0.0, False, [])

        is_buy = (direction == "BUY")
        hit = None          # 'sl' یا 'tp3'
        hit_price = None
        tp_hit = False
        tp_hit_price = None
        mul = get_pip_multiplier(symbol)
        mfe_pip = 0.0
        mae_pip = 0.0
        candle_lines = []
        found_3r = False
        risk_pips = None
        if sl_price and entry_price:
            if is_buy:
                risk_pips = (entry_price - sl_price) * mul
            else:
                risk_pips = (sl_price - entry_price) * mul

        passed_1r = False
        reached_1r_at = None
        free_risk_was_possible = False
        free_risk_saved = False
        pullback_after_1r = False
        mae_stopped = False

        sl_hit_occurred = False
        post_sl_max_profit = 0.0
        post_sl_reached_1r = False
        post_sl_reached_1_5r = False
        post_sl_reached_2r = False
        post_sl_reached_3r = False
        mfe_before_sl = 0.0

        stop_price = None
        if sl_price and max_post_sl_pips > 0:
            if is_buy:
                stop_price = sl_price + (max_post_sl_pips / mul)
            else:
                stop_price = sl_price - (max_post_sl_pips / mul)

        _r3_price = r3_override if r3_override else (
            ((entry_price + 3*risk_pips/mul) if is_buy else (entry_price - 3*risk_pips/mul)) if risk_pips else None
        )

        snap_end_idx = len(after) - 1
        snap_resolved = False

        for i, (bar_dt_i, b) in enumerate(after):
            high = float(b.get("high", 0))
            low  = float(b.get("low",  0))
            close= float(b.get("close",0))
            open_= float(b.get("open", 0))

            if is_buy:
                profit_now = (high - entry_price) * mul
                if not mae_stopped and low < entry_price:
                    d = (entry_price - low) * mul
                    if d > mae_pip: mae_pip = d
            else:
                profit_now = (entry_price - low) * mul
                if not mae_stopped and high > entry_price:
                    d = (high - entry_price) * mul
                    if d > mae_pip: mae_pip = d

            mfe_pip = max(mfe_pip, profit_now)

            if hit is None:
                mfe_before_sl = max(mfe_before_sl, profit_now)

            if risk_pips and not passed_1r and profit_now >= risk_pips:
                passed_1r = True
                reached_1r_at = i
                mae_stopped = True

            if passed_1r and reached_1r_at is not None and i > reached_1r_at:
                if not free_risk_was_possible:
                    free_risk_was_possible = True
                if not pullback_after_1r:
                    if is_buy and low <= entry_price:
                        pullback_after_1r = True
                    elif not is_buy and high >= entry_price:
                        pullback_after_1r = True

            dt_teh = bar_dt_i + timedelta(hours=3, minutes=30)
            thr = dt_teh.strftime("%m/%d %H:%M")
            dir_c = "▲" if close >= open_ else "▼"
            body_p = abs(close - open_) * mul
            candle_lines.append(f"{thr}: {dir_c} {body_p:.1f}pip | H:{high:.5f} L:{low:.5f} C:{close:.5f}")

            # ===== تعیین برخورد با SL یا 3R (بسته شدن) =====
            if hit is None:
                if is_buy:
                    if sl_price is not None and low <= sl_price:
                        hit, hit_price = "sl", sl_price
                        sl_hit_occurred = True
                    elif _r3_price and high >= _r3_price:
                        hit, hit_price = "tp3", _r3_price
                        found_3r = True
                else:
                    if sl_price is not None and high >= sl_price:
                        hit, hit_price = "sl", sl_price
                        sl_hit_occurred = True
                    elif _r3_price and low <= _r3_price:
                        hit, hit_price = "tp3", _r3_price
                        found_3r = True

            # ===== تعیین برخورد با TP (فقط برای ثبت، بدون بستن) =====
            if not tp_hit and tp_price is not None:
                if is_buy and high >= tp_price:
                    tp_hit = True
                    tp_hit_price = tp_price
                elif not is_buy and low <= tp_price:
                    tp_hit = True
                    tp_hit_price = tp_price

            # ===== تعیین پایان snapshot (فقط SL یا 3R) =====
            if not snap_resolved:
                if is_buy:
                    if sl_price is not None and low <= sl_price:
                        snap_end_idx = i
                        snap_resolved = True
                    elif _r3_price and high >= _r3_price:
                        snap_end_idx = i
                        snap_resolved = True
                else:
                    if sl_price is not None and high >= sl_price:
                        snap_end_idx = i
                        snap_resolved = True
                    elif _r3_price and low <= _r3_price:
                        snap_end_idx = i
                        snap_resolved = True
                if not snap_resolved:
                    snap_end_idx = i

            # برگشت بعد SL
            if sl_hit_occurred:
                if is_buy:
                    if high > entry_price:
                        profit_after = (high - entry_price) * mul
                        if profit_after > post_sl_max_profit:
                            post_sl_max_profit = profit_after
                        if risk_pips:
                            if profit_after >= risk_pips: post_sl_reached_1r = True
                            if profit_after >= 1.5 * risk_pips: post_sl_reached_1_5r = True
                            if profit_after >= 2 * risk_pips: post_sl_reached_2r = True
                            if profit_after >= 3 * risk_pips: post_sl_reached_3r = True
                else:
                    if low < entry_price:
                        profit_after = (entry_price - low) * mul
                        if profit_after > post_sl_max_profit:
                            post_sl_max_profit = profit_after
                        if risk_pips:
                            if profit_after >= risk_pips: post_sl_reached_1r = True
                            if profit_after >= 1.5 * risk_pips: post_sl_reached_1_5r = True
                            if profit_after >= 2 * risk_pips: post_sl_reached_2r = True
                            if profit_after >= 3 * risk_pips: post_sl_reached_3r = True

            if sl_hit_occurred and stop_price is not None:
                if is_buy and high >= stop_price:
                    snap_end_idx = i
                    snap_resolved = True
                if not is_buy and low <= stop_price:
                    snap_end_idx = i
                    snap_resolved = True

            if snap_resolved and hit is not None and i > snap_end_idx + 5:
                break

        last_close = float(after[-1][1]["close"]) if not found_3r else (after[-1][1]["close"] if after else 0)
        pnl = None
        if hit:
            diff = (hit_price - entry_price) if is_buy else (entry_price - hit_price)
            pnl = diff * size

        if hit == "sl" and free_risk_was_possible:
            free_risk_saved = True

        snap_start = max(0, entry_bar_idx - 20)
        snap_end = entry_bar_idx + snap_end_idx + 1
        snapshot_bars = []
        for bar_dt_snap, b_snap in all_bars_sorted[snap_start:snap_end]:
            dt_teh_snap = bar_dt_snap + timedelta(hours=3, minutes=30)
            snapshot_bars.append({
                "t": dt_teh_snap.strftime("%Y-%m-%d %H:%M"),
                "o": float(b_snap.get("open", 0)),
                "h": float(b_snap.get("high", 0)),
                "l": float(b_snap.get("low", 0)),
                "c": float(b_snap.get("close", 0)),
            })

        return (hit, hit_price, tp_hit, tp_hit_price, last_close, pnl, mfe_pip, mae_pip, candle_lines, found_3r,
                free_risk_was_possible, free_risk_saved, reached_1r_at, pullback_after_1r,
                post_sl_max_profit, post_sl_reached_1r, post_sl_reached_1_5r, post_sl_reached_2r, post_sl_reached_3r,
                mfe_before_sl, passed_1r, snapshot_bars)
    except Exception as e:
        log_error(f"check_sltp_hit_with_details: {e}")
        return (None, None, False, None, None, None, None, None, [], False, False, False, None, False, None, False, False, False, False, 0.0, False, [])

def groq_analyze(prompt):
    if not GROQ_API_KEY:
        return "⚠️ کلید API Groq تنظیم نشده است."
    try:
        client = Groq(api_key=GROQ_API_KEY)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=800
        )
        return completion.choices[0].message.content
    except Exception as e:
        log_error(f"Groq error: {e}")
        return f"❌ خطا: {str(e)}"

# ==================== Routes ====================
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/journal")
def journal():
    return send_from_directory("static", "journal.html")

@app.route("/api/config", methods=["GET","POST"])
def config():
    data = load_alerts()
    if request.method == "POST":
        body = request.json or {}
        tg = data.get("telegram", {})
        if body.get("bot_token"):
            tg["bot_token"] = body["bot_token"]
        if body.get("chat_id"):
            cid = str(body["chat_id"])
            ids = [str(x) for x in tg.get("chat_ids", [])]
            if cid not in ids: ids.append(cid)
            tg["chat_ids"] = ids
            tg["chat_id"] = cid
        data["telegram"] = tg
        save_alerts(data)
        return jsonify({"ok": True})
    tg = data.get("telegram", {})
    return jsonify({
        "bot_token": tg.get("bot_token",""), "chat_id": tg.get("chat_id",""),
        "chat_ids": tg.get("chat_ids",[]), "user_count": len(data.get("users",[]))
    })

@app.route("/api/alerts", methods=["GET"])
def get_alerts():
    return jsonify(load_alerts().get("alerts", []))

@app.route("/api/alerts", methods=["POST"])
def add_alert():
    data = load_alerts()
    body = request.json or {}
    sym = body.get("symbol","").upper().strip()
    atype = body.get("type","crypto")
    tgt = float(body.get("target_price", 0))
    cur = get_price(sym, atype) if (atype!="forex" or is_forex_market_open()) else None
    a = {
        "id": str(int(time.time() * 1000)), "symbol": sym, "type": atype,
        "target_price": tgt, "condition": body.get("condition","above"),
        "comment": body.get("comment","").strip(), "active": True,
        "last_price": cur, "last_checked": now_teh() if cur else None,
        "created_at": now_teh()
    }
    data["alerts"].append(a)
    save_alerts(data)
    return jsonify({"ok": True, "alert": a})

@app.route("/api/alerts/<aid>", methods=["DELETE"])
def del_alert(aid):
    data = load_alerts()
    data["alerts"] = [a for a in data.get("alerts", []) if a["id"] != aid]
    save_alerts(data)
    return jsonify({"ok": True})

@app.route("/api/archive", methods=["GET"])
def get_archive():
    return jsonify(load_alerts().get("archive", []))

@app.route("/api/archive", methods=["DELETE"])
def clear_archive():
    data = load_alerts()
    data["archive"] = []
    save_alerts(data)
    return jsonify({"ok": True})

@app.route("/api/archive/<aid>", methods=["DELETE"])
def del_archive(aid):
    data = load_alerts()
    data["archive"] = [a for a in data.get("archive",[]) if a["id"] != aid]
    save_alerts(data)
    return jsonify({"ok": True})

@app.route("/api/users", methods=["GET"])
def get_users():
    return jsonify(load_alerts().get("users", []))

@app.route("/api/users/<cid>", methods=["DELETE"])
def del_user(cid):
    data = load_alerts()
    data["users"] = [u for u in data.get("users",[]) if str(u["chat_id"]) != str(cid)]
    data["telegram"]["chat_ids"] = [x for x in data["telegram"].get("chat_ids",[]) if str(x) != str(cid)]
    save_alerts(data)
    return jsonify({"ok": True})

@app.route("/api/price/<atype>/<symbol>")
def live_price(atype, symbol):
    sym = symbol.upper().replace("-","/")
    p = get_price(sym, atype)
    if p is None:
        return jsonify({"error": "قیمت پیدا نشد"}), 404
    return jsonify({"symbol": sym, "price": p})

@app.route("/api/test-telegram", methods=["POST"])
def test_tg():
    token, cids, _ = _get_token_and_cids()
    if not token or not cids:
        return jsonify({"ok": False, "error": "توکن یا chat_id ست نشده"})
    res = broadcast(token, cids, f"✅ تست موفق\n⏰ {now_pretty()}")
    return jsonify({"ok": any(res), "sent": sum(res), "total": len(cids)})

@app.route("/api/status")
def status():
    alerts = load_alerts()
    journal = load_journal()
    return jsonify({
        "status": "ok", "last_update": alerts.get("last_update"),
        "errors": alerts.get("errors", [])[-5:], "time_tehran": now_teh(),
        "alert_count": len(alerts.get("alerts",[])), "forex_open": is_forex_market_open(),
        "loop_count": _loop_count, "journal_count": len(journal)
    })

@app.route("/api/version")
def version():
    return jsonify({"version": VERSION})

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# ==================== ژورنال ====================
@app.route("/api/journal", methods=["GET"])
def get_journal():
    return jsonify(load_journal())

@app.route("/api/journal", methods=["POST"])
def add_journal():
    journal = load_journal()
    body = request.json or {}
    sym = body.get("sym", "").upper().strip()
    if not sym:
        return jsonify({"ok": False, "error": "sym الزامی است"}), 400
    entry = float(body.get("entry", 0))
    direction = body.get("direction", "BUY")
    size = 1.0
    sl_pips = body.get("sl_pips")
    tp_pips = body.get("tp_pips")
    sl_price = body.get("sl_price")
    tp_price = body.get("tp_price")

    mul = get_pip_multiplier(sym)
    if sl_price is None and sl_pips is not None:
        sl_diff = sl_pips / mul
        sl_price = entry - sl_diff if direction == "BUY" else entry + sl_diff
    if tp_price is None and tp_pips is not None:
        tp_diff = tp_pips / mul
        tp_price = entry + tp_diff if direction == "BUY" else entry - tp_diff
    if sl_pips is None and sl_price is not None:
        sl_pips = abs(entry - sl_price) * mul
    if tp_pips is None and tp_price is not None:
        tp_pips = abs(tp_price - entry) * mul

    trade = {
        "id": str(int(time.time() * 1000)), "sym": sym, "tf": body.get("tf", "1h"),
        "direction": direction, "entry": entry, "size": size,
        "sl_pips": round(sl_pips, 1) if sl_pips else None,
        "tp_pips": round(tp_pips, 1) if tp_pips else None,
        "sl_price": sl_price, "tp_price": tp_price,
        "note": body.get("note", "").strip(), "entryTime": body.get("entryTime", now_teh()),
        "createdAt": now_teh(), "status": "open", "exit": None, "exitTime": None,
        "candle_snapshot": [], "pending_check": True,
        "exitNote": None, "pnl": None, "outcome": None,
        "ai_analysis": None, "ai_summary": None,
        "review_mfe": None, "review_mae": None, "review_pullback": None, "review_note": None,
        "review_reversal_occurred": None, "review_reversal_from_sl": None, "review_reversal_target_pips": None,
        "found_3r": False, "mae_pip": 0, "mfe_pip": 0,
        "free_risk_was_possible": False, "free_risk_saved": False, "pullback_after_1r": False,
        "post_sl_max_profit": 0, "post_sl_reached_1r": False, "post_sl_reached_1_5r": False,
        "post_sl_reached_2r": False, "post_sl_reached_3r": False,
        "mfe_before_sl_pip": 0, "passed_1r": False,
        "tp_hit": False, "tp_hit_price": None
    }
    try:
        res = check_sltp_hit_with_details(sym, trade["tf"], trade["entryTime"], direction, entry, sl_price, tp_price, size, r3_override=None)
        (hit, hit_price, tp_hit, tp_hit_price, last_close, pnl, mfe_pip, mae_pip, candle_lines, found_3r,
         fr_possible, fr_saved, fr_at, pullback, post_max, post_1r, post_1_5r, post_2r, post_3r,
         mfe_before_sl, passed_1r, snapshot_bars) = res

        trade["tp_hit"] = tp_hit
        trade["tp_hit_price"] = tp_hit_price

        if hit:  # 'sl' یا 'tp3'
            trade["exit"] = hit_price
            trade["exitTime"] = now_teh()
            trade["exitNote"] = f"خودکار: {'استاپ لاس' if hit=='sl' else '3R کامل'}"
            trade["pnl"] = round(pnl, 2) if pnl is not None else 0
            trade["outcome"] = "win" if hit == "tp3" else "loss"
            trade["exit_type"] = hit
            trade["status"] = "closed"
            trade["pending_check"] = False
            trade["mfe_pip"] = round(mfe_pip, 1)
            trade["mae_pip"] = round(mae_pip, 1)
            trade["found_3r"] = found_3r
            trade["free_risk_was_possible"] = fr_possible
            trade["free_risk_saved"] = fr_saved
            trade["pullback_after_1r"] = pullback
            trade["post_sl_max_profit"] = round(post_max, 1) if post_max else 0
            trade["post_sl_reached_1r"] = post_1r
            trade["post_sl_reached_1_5r"] = post_1_5r
            trade["post_sl_reached_2r"] = post_2r
            trade["post_sl_reached_3r"] = post_3r
            trade["mfe_before_sl_pip"] = round(mfe_before_sl, 1) if mfe_before_sl else 0
            trade["passed_1r"] = passed_1r
            trade["candle_snapshot"] = snapshot_bars
        else:
            # هنوز بسته نشده (حتی اگر TP خورده باشد)
            trade["status"] = "open"
            trade["pending_check"] = True
            trade["candle_snapshot"] = snapshot_bars
            trade["last_poll"] = now_teh()
            if tp_hit:
                trade["exitNote"] = f"تارگت زده شد (در انتظار 3R یا SL)"
            else:
                trade["exitNote"] = None
    except Exception as e:
        log_error(f"auto check error: {e}")
        return jsonify({"ok": False, "error": f"خطا: {str(e)}"}), 500
    journal.insert(0, trade)
    save_journal(journal)
    return jsonify({"ok": True, "trade": trade})

def calc_exit_type(outcome, risk_pips, mfe_pip, found_3r=False, exit_type_stored=None):
    if exit_type_stored in ("sl", "tp3"):
        return exit_type_stored
    if outcome == "loss":
        return "sl"
    if found_3r:
        return "tp3"
    if risk_pips and risk_pips > 0 and mfe_pip:
        mfe_r = mfe_pip / risk_pips
        if mfe_r >= 3.0:
            return "tp3"
    return "tp"  # برد ولی نرسیده به 3R

@app.route("/api/journal/manual", methods=["POST"])
def add_journal_manual():
    journal = load_journal()
    body = request.json or {}
    sym = body.get("sym", "").upper().strip()
    if not sym:
        return jsonify({"ok": False, "error": "sym الزامی است"}), 400
    entry = float(body.get("entry", 0))
    direction = body.get("direction", "BUY")
    size = 1.0
    tf = body.get("tf", "1h")
    entryTime = body.get("entryTime", now_teh())
    note = body.get("note", "").strip()
    sl_price = body.get("sl_price")
    tp_price = body.get("tp_price")
    exit_price = body.get("exit")
    outcome = body.get("outcome")
    exitTime = body.get("exitTime", now_teh())
    exitNote = body.get("exitNote", "ثبت دستی")
    mul = get_pip_multiplier(sym)
    sl_pips = abs(entry - sl_price) * mul if sl_price else None
    tp_pips = abs(tp_price - entry) * mul if tp_price else None
    pnl = None
    if exit_price and entry:
        diff = (exit_price - entry) if direction == "BUY" else (entry - exit_price)
        pnl = diff * size
    review_mfe = body.get("review_mfe")
    review_mae = body.get("review_mae")
    review_pullback = body.get("review_pullback", False)
    review_note = body.get("review_note", "")
    review_reversal_occurred = body.get("review_reversal_occurred", False)
    review_reversal_from_sl = body.get("review_reversal_from_sl")
    review_reversal_target_pips = body.get("review_reversal_target_pips")
    review_free_risk_saved = body.get("review_free_risk_saved", False)
    is_crypto = is_crypto_symbol(sym)
    risk_pips = None
    if sl_price and entry:
        if direction == "BUY":
            risk_pips = (entry - sl_price) * mul
        else:
            risk_pips = (sl_price - entry) * mul
    if is_crypto:
        mfe_r = body.get("review_mfe_r")
        mae_r = body.get("review_mae_r")
        reversal_target_r = body.get("review_reversal_target_pips_r")
        if mfe_r is not None and risk_pips and risk_pips > 0:
            review_mfe = mfe_r * risk_pips
        if mae_r is not None and risk_pips and risk_pips > 0:
            review_mae = mae_r * risk_pips
        if reversal_target_r is not None and risk_pips and risk_pips > 0:
            review_reversal_target_pips = reversal_target_r * risk_pips
    trade = {
        "id": str(int(time.time() * 1000)), "sym": sym, "tf": tf,
        "direction": direction, "entry": entry, "size": size,
        "sl_pips": round(sl_pips, 1) if sl_pips else None,
        "tp_pips": round(tp_pips, 1) if tp_pips else None,
        "sl_price": sl_price, "tp_price": tp_price,
        "note": note, "entryTime": entryTime, "createdAt": now_teh(),
        "status": "closed", "exit": exit_price, "exitTime": exitTime, "exitNote": exitNote,
        "pnl": round(pnl, 2) if pnl is not None else 0, "outcome": outcome,
        "ai_analysis": None, "ai_summary": None,
        "review_mfe": review_mfe, "review_mae": review_mae,
        "review_pullback": review_pullback, "review_note": review_note,
        "review_reversal_occurred": review_reversal_occurred,
        "review_reversal_from_sl": review_reversal_from_sl,
        "review_reversal_target_pips": review_reversal_target_pips,
        "review_free_risk_saved": review_free_risk_saved,
        "found_3r": False, "mae_pip": review_mae if review_mae else 0,
        "mfe_pip": review_mfe if review_mfe else 0,
        "free_risk_was_possible": False, "free_risk_saved": review_free_risk_saved,
        "pullback_after_1r": review_pullback,
        "post_sl_max_profit": 0, "post_sl_reached_1r": False, "post_sl_reached_1_5r": False,
        "post_sl_reached_2r": False, "post_sl_reached_3r": False,
        "mfe_before_sl_pip": 0, "passed_1r": False, "candle_snapshot": [],
        "tp_hit": False, "tp_hit_price": None
    }
    mfe_for_calc = float(review_mfe) if review_mfe else 0
    trade["exit_type"] = calc_exit_type(outcome, risk_pips, mfe_for_calc)
    if trade.get("outcome") and not trade.get("candle_snapshot"):
        try:
            r3_guess = None
            if risk_pips and risk_pips > 0:
                if direction == "BUY":
                    r3_guess = entry + 3 * risk_pips / mul
                else:
                    r3_guess = entry - 3 * risk_pips / mul
            res_snap = check_sltp_hit_with_details(
                sym, tf, entryTime, direction, entry, sl_price,
                tp_price if tp_price else r3_guess,
                size, r3_override=r3_guess
            )
            trade["candle_snapshot"] = res_snap[21] if len(res_snap) > 21 else []
        except Exception as e:
            log_error(f"manual snapshot: {e}")
            trade["candle_snapshot"] = []
    journal.insert(0, trade)
    save_journal(journal)
    return jsonify({"ok": True, "trade": trade})

@app.route("/api/journal/<tid>/edit", methods=["PUT"])
def edit_trade(tid):
    journal = load_journal()
    trade = next((t for t in journal if t["id"] == tid), None)
    if not trade:
        return jsonify({"ok": False, "error": "ترید یافت نشد"}), 404
    body = request.json or {}
    for key in ["sym","direction","entry","exit","sl_price","tp_price","entryTime","exitTime","pnl","outcome","note","exitNote"]:
        if key in body:
            trade[key] = body[key] if key in ["note","exitNote","outcome","direction","sym"] else float(body[key]) if body[key] is not None else None
    for key in ["review_mfe","review_mae","review_pullback","review_note","review_reversal_occurred","review_reversal_from_sl","review_reversal_target_pips","review_free_risk_saved"]:
        if key in body:
            trade[key] = body[key]
    mul = get_pip_multiplier(trade["sym"])
    if trade.get("sl_price") and trade.get("entry"):
        trade["sl_pips"] = abs(trade["entry"] - trade["sl_price"]) * mul
    if trade.get("tp_price") and trade.get("entry"):
        trade["tp_pips"] = abs(trade["tp_price"] - trade["entry"]) * mul
    if trade.get("exit") and trade.get("entry"):
        diff = (trade["exit"] - trade["entry"]) if trade["direction"] == "BUY" else (trade["entry"] - trade["exit"])
        trade["pnl"] = diff * 1.0
    save_journal(journal)
    return jsonify({"ok": True, "trade": trade})

@app.route("/api/journal/<tid>/delete", methods=["DELETE"])
def delete_trade(tid):
    journal = load_journal()
    journal = [t for t in journal if t["id"] != tid]
    save_journal(journal)
    return jsonify({"ok": True})

@app.route("/api/journal/<tid>/review", methods=["POST"])
def review_trade(tid):
    journal = load_journal()
    trade = next((t for t in journal if t["id"] == tid), None)
    if not trade:
        return jsonify({"ok": False, "error": "ترید یافت نشد"}), 404
    body = request.json or {}
    sym = trade.get("sym", "")
    mul = get_pip_multiplier(sym)
    entry = float(trade.get("entry", 0))
    sl_px = trade.get("sl_price")
    risk_pips = abs(entry - float(sl_px)) * mul if sl_px and entry else None
    if "review_mfe" in body:
        mfe_val = body["review_mfe"]
        if mfe_val is not None and is_crypto_symbol(sym) and risk_pips and risk_pips > 0:
            trade["review_mfe"] = round(float(mfe_val) * risk_pips, 4)
        else:
            trade["review_mfe"] = mfe_val
    if "review_mae" in body:
        mae_val = body["review_mae"]
        if mae_val is not None and is_crypto_symbol(sym) and risk_pips and risk_pips > 0:
            trade["review_mae"] = round(float(mae_val) * risk_pips, 4)
        else:
            trade["review_mae"] = mae_val
    if "review_reversal_target_pips" in body:
        rt_val = body["review_reversal_target_pips"]
        if rt_val is not None and is_crypto_symbol(sym) and risk_pips and risk_pips > 0:
            trade["review_reversal_target_pips"] = round(float(rt_val) * risk_pips, 4)
        else:
            trade["review_reversal_target_pips"] = rt_val
    for f in ["review_pullback","review_note","review_reversal_occurred","review_reversal_from_sl","review_free_risk_saved"]:
        if f in body:
            trade[f] = body[f]
    save_journal(journal)
    return jsonify({"ok": True})

@app.route("/api/analyze/<trade_id>", methods=["GET"])
def analyze_trade(trade_id):
    journal = load_journal()
    trade = next((t for t in journal if t["id"] == trade_id), None)
    if not trade:
        return jsonify({"ok": False, "error": "ترید یافت نشد"}), 404
    symbol = trade["sym"]
    entry = float(trade["entry"])
    sl = trade.get("sl_price")
    direction = trade.get("direction", "BUY")
    outcome = trade.get("outcome", "")
    exit_px = trade.get("exit")
    mul = get_pip_multiplier(symbol)
    risk_pips = None
    if sl and entry:
        if direction == "BUY":
            risk_pips = (entry - sl) * mul
        else:
            risk_pips = (sl - entry) * mul
    risk_pips_safe = risk_pips if (risk_pips and risk_pips > 0) else 1.0
    taken_pips = abs(float(exit_px) - entry) * mul if exit_px else 0
    taken_r = round(taken_pips / risk_pips_safe, 2)
    mfe_pip = float(trade.get("review_mfe") or trade.get("mfe_pip") or 0)
    mfe_r = round(mfe_pip / risk_pips_safe, 2)
    left_pip = round(mfe_pip - taken_pips, 1) if mfe_pip > taken_pips else 0
    left_r = round(left_pip / risk_pips_safe, 2)
    mfe_bsl = float(trade.get("mfe_before_sl_pip") or 0)
    mfe_bsl_r = round(mfe_bsl / risk_pips_safe, 2)
    rev_occurred = trade.get("review_reversal_occurred", False)
    rev_target = trade.get("review_reversal_target_pips") or trade.get("post_sl_max_profit") or 0
    rev_target_r = round(float(rev_target) / risk_pips_safe, 2)
    passed_1r = trade.get("review_passed_1r", trade.get("passed_1r", False))
    fr_possible = trade.get("free_risk_was_possible", False)
    fr_done = trade.get("review_free_risk_saved", False)
    pullback = trade.get("review_pullback", trade.get("pullback_after_1r", False))
    lines = []
    if outcome == "loss":
        lines.append(f"استاپ خورد — ضرر {taken_r:.1f}R" if taken_r else "استاپ خورد — ضرر نامشخص")
    else:
        lines.append(f"تارگت زده شد — سود {taken_r:.1f}R" if taken_r else "تارگت زده شد — سود نامشخص")
    if outcome == "loss" and mfe_bsl_r > 0.05:
        lines.append(f"قبل از استاپ تا {mfe_bsl_r:.1f}R سود رفت")
    if outcome == "loss":
        if rev_occurred and rev_target_r > 0:
            lines.append(f"بعد از استاپ تا {rev_target_r:.1f}R برگشت")
    if outcome == "win" and left_r > 0.2:
        lines.append(f"حداکثر سود {mfe_r:.1f}R بود — {left_r:.1f}R روی میز ماند")
    if fr_done:
        lines.append("🛡️ فری‌ریسک انجام شد")
    elif passed_1r and fr_possible and outcome == "loss":
        if pullback:
            lines.append("بعد از 1R به ورود برگشت و دوباره رفت — فری‌ریسک نجات می‌داد")
        else:
            lines.append("بعد از 1R به ورود برگشت — فری‌ریسک نجات می‌داد")
    elif passed_1r and not fr_possible and outcome != "loss":
        lines.append("بعد از 1R به ورود برنگشت — فری‌ریسک نمی‌خورد")
    if mfe_r >= 1 and outcome != "win":
        lines.append(f"قیمت تا {mfe_r:.1f}R رفت")
    text = " | ".join(lines)
    trade["ai_analysis"] = text
    trade["ai_summary"] = text
    save_journal(journal)
    return jsonify({"ok": True, "analysis": text, "summary": text})

@app.route("/api/overall-analysis", methods=["GET"])
def overall_analysis():
    custom_prompt = request.args.get("custom_prompt","").strip()
    trades = load_journal()
    closed = [t for t in trades if t.get("status") == "closed" and t.get("outcome") in ("win", "loss")]
    if not closed:
        return jsonify({"ok": False, "error": "هیچ ترید بسته‌ای وجود ندارد"}), 404
    total = len(closed)
    wins = sum(1 for t in closed if t.get("outcome") == "win")
    losses = total - wins
    wr = round(wins/total*100, 1) if total else 0
    def _et(t):
        mul = get_pip_multiplier(t["sym"])
        rp = None
        if t.get("sl_price") and t.get("entry"):
            rp = abs(float(t["entry"]) - float(t["sl_price"])) * mul
        mfe = float(t.get("review_mfe") or t.get("mfe_pip") or 0)
        return t.get("exit_type") or calc_exit_type(t.get("outcome",""), rp, mfe, t.get("found_3r", False))
    win_tp_count = sum(1 for t in closed if _et(t) == "tp")
    win_3r_count = sum(1 for t in closed if _et(t) == "tp3")

    early_exit_count = 0
    early_exit_left_r_list = []
    sl_reversed_count = 0
    sl_reversed_1r = 0
    sl_reversed_1_5r = 0
    sl_reversed_2r = 0
    sl_reversed_3r = 0
    fr_missed_count = 0
    free_risk_done_count = 0
    reached_1r_count = 0
    reached_1_5r_count = 0
    reached_2r_count = 0
    reached_3r_count = 0
    taken_r_list = []
    mfe_r_list = []
    sym_stats = {}
    hour_stats = {}
    mae_ratio_list = []
    trade_details = []
    planned_rr_list, rr_gap_list = [], []
    rr_bucket = {"<1.5":{"w":0,"l":0},"1.5-2":{"w":0,"l":0},"2-3":{"w":0,"l":0},"3+":{"w":0,"l":0}}
    setup_stats = {}
    detail_1r, detail_2r, detail_3r, detail_sl_rev, detail_early = [], [], [], [], []
    detail_fr_missed, detail_fr_done = [], []
    post_sl_pip_list = []

    for idx_t, t in enumerate(closed):
        sym = t["sym"]
        mul = get_pip_multiplier(sym)
        entry = float(t["entry"])
        sl_px = t.get("sl_price")
        exit_px = t.get("exit")
        outcome = t["outcome"]
        direction = t["direction"]
        pnl = t.get("pnl", 0) or 0
        mfe_pip = float(t.get("review_mfe") or t.get("mfe_pip") or 0)
        mae_pip = float(t.get("review_mae") or t.get("mae_pip") or 0)
        post_sl_1r = t.get("post_sl_reached_1r", False)
        post_sl_1_5r = t.get("post_sl_reached_1_5r", False)
        post_sl_2r = t.get("post_sl_reached_2r", False)
        post_sl_3r = t.get("post_sl_reached_3r", False)
        post_sl_max = float(t.get("post_sl_max_profit", 0) or 0)
        rev_occurred = t.get("review_reversal_occurred", False)
        rev_target_pips = t.get("review_reversal_target_pips")
        fr_possible = t.get("free_risk_was_possible", False)
        passed_1r = t.get("passed_1r", False)
        found_3r = t.get("found_3r", False)
        entry_time = t.get("entryTime", "")
        free_risk_done = t.get("review_free_risk_saved", False)
        note_text = t.get("note", "")
        review_note_text = t.get("review_note", "")

        risk_pips = None
        if sl_px and entry:
            if direction == "BUY":
                risk_pips = (entry - sl_px) * mul
            else:
                risk_pips = (sl_px - entry) * mul
        risk_pips_safe = risk_pips if (risk_pips and risk_pips > 0) else 1.0
        taken_pips = abs(float(exit_px) - entry) * mul if exit_px else 0
        taken_r = round(taken_pips / risk_pips_safe, 2)
        mfe_r = round(mfe_pip / risk_pips_safe, 2)
        left_pip = round(mfe_pip - taken_pips, 1) if mfe_pip > taken_pips else 0
        left_r = round(left_pip / risk_pips_safe, 2)
        exit_type = t.get("exit_type") or calc_exit_type(
            outcome, risk_pips,
            float(t.get("review_mfe") or t.get("mfe_pip") or 0),
            t.get("found_3r", False)
        )
        exit_type_label = {"sl": "SL", "tp": "TP(زودخروج)", "tp3": "3R(کامل)"}.get(exit_type, exit_type)

        if taken_pips > 0: taken_r_list.append(taken_r)
        if mfe_pip > 0: mfe_r_list.append(mfe_r)
        if mae_pip and risk_pips_safe:
            mae_ratio_list.append(round(mae_pip / risk_pips_safe, 2))

        tp_px = t.get("tp_price")
        planned_rr = None
        if risk_pips_safe and tp_px and entry:
            tp_dist = abs(float(tp_px) - entry) * mul
            planned_rr = round(tp_dist / risk_pips_safe, 2)
            planned_rr_list.append(planned_rr)
            rr_gap_list.append(round(taken_r - planned_rr, 2))
        if planned_rr:
            bkt = "<1.5" if planned_rr<1.5 else "1.5-2" if planned_rr<2 else "2-3" if planned_rr<3 else "3+"
            if outcome=="win": rr_bucket[bkt]["w"]+=1
            else: rr_bucket[bkt]["l"]+=1

        stype = (t.get("setup_type","") or "نامشخص").strip()
        setup_stats.setdefault(stype,{"w":0,"l":0,"pnl":0})
        if outcome=="win": setup_stats[stype]["w"]+=1
        else: setup_stats[stype]["l"]+=1
        setup_stats[stype]["pnl"]+=pnl

        display_num = len(closed) - idx_t
        sl_pips_show = round(risk_pips, 1) if risk_pips else None
        tp_pips_show = round(abs(float(t.get("tp_price",0) or 0) - entry) * mul, 1) if t.get("tp_price") and entry else None
        entry_time_short = str(t.get("entryTime",""))[:16]
        is_manual_mfe = t.get("review_mfe") is not None
        tshort = {
            "idx": display_num, "tid": t["id"], "sym": sym, "dir": direction,
            "tf": t.get("tf",""), "outcome": outcome, "entry": entry,
            "exit": float(t.get("exit") or 0), "sl_price": t.get("sl_price"),
            "tp_price": t.get("tp_price"), "sl_pips": sl_pips_show,
            "tp_pips": tp_pips_show, "taken_r": taken_r, "mfe_r": mfe_r,
            "left_r": left_r, "entry_time": entry_time_short,
            "is_manual": is_manual_mfe, "note": (t.get("note") or "")[:80],
        }
        if outcome=="win":
            if mfe_r>=1.0 or t.get("passed_1r"):
                detail_1r.append({**tshort,"detail":f"MFE={mfe_pip:.0f}p taken={taken_r:.1f}R SL={sl_pips_show}p",
                    "extra": {"mfe_r": mfe_r, "taken_r": taken_r, "left_r": left_r, "is_manual": is_manual_mfe}})
            if mfe_r>=2.0:
                detail_2r.append({**tshort,"detail":f"MFE={mfe_pip:.0f}p taken={taken_r:.1f}R",
                    "extra": {"mfe_r": mfe_r, "taken_r": taken_r}})
            if t.get("found_3r") or mfe_r>=3.0:
                detail_3r.append({**tshort,"detail":f"MFE={mfe_pip:.0f}p taken={taken_r:.1f}R",
                    "extra": {"mfe_r": mfe_r}})
            if left_r>0.4:
                detail_early.append({**tshort,"detail":f"taken={taken_r:.1f}R | MFE={mfe_pip:.0f}p | {left_r:.1f}R جا موند",
                    "extra": {"taken_r": taken_r, "mfe_r": mfe_r, "left_r": left_r}})
        else:
            mbe = float(t.get("review_mfe") or t.get("mfe_before_sl_pip") or 0)
            mbe_r = round(mbe / risk_pips_safe, 2)
            if mbe >= (risk_pips or 0) and risk_pips:
                detail_1r.append({**tshort,"detail":f"MFE قبل SL={mbe:.0f}p ({mbe_r:.1f}R) SL={sl_pips_show}p",
                    "extra": {"mbe_r": mbe_r, "mfe_before_sl": mbe}})
            psl_manual = t.get("review_reversal_target_pips")
            psl_auto = float(t.get("post_sl_max_profit",0) or 0)
            psl = float(psl_manual) if psl_manual is not None else psl_auto
            psl_r = round(psl / risk_pips_safe, 2)
            rev_manual = t.get("review_reversal_occurred")
            rev_auto = t.get("post_sl_reached_1r", False)
            if rev_manual is True or (rev_manual is None and rev_auto):
                lvls = []
                if t.get("review_reversal_occurred") and psl_r >= 1.5: lvls.append("→1.5R")
                if t.get("review_reversal_occurred") and psl_r >= 2.0: lvls.append("→2R")
                if t.get("review_reversal_occurred") and psl_r >= 3.0: lvls.append("→3R")
                if not t.get("review_reversal_occurred"):
                    if t.get("post_sl_reached_1_5r"): lvls.append("→1.5R")
                    if t.get("post_sl_reached_2r"): lvls.append("→2R")
                    if t.get("post_sl_reached_3r"): lvls.append("→3R")
                lvl_str = " ".join(lvls)
                from_sl = t.get("review_reversal_from_sl")
                from_sl_str = f" از {from_sl:.0f}p بعد SL" if from_sl else ""
                detail_sl_rev.append({**tshort,
                    "detail":f"برگشت={psl:.0f}p ({psl_r:.1f}R){lvl_str}{from_sl_str}",
                    "extra": {"psl_r": psl_r, "psl_pips": psl, "is_manual": rev_manual is True, "from_sl": from_sl}})
                post_sl_pip_list.append(psl)

        mfe_bsl_pip = float(t.get("mfe_before_sl_pip", 0))
        mfe_bsl_r = mfe_bsl_pip / risk_pips_safe if outcome == "loss" else 0.0

        if outcome == "win":
            if mfe_r >= 1.0 or passed_1r: reached_1r_count += 1
            if mfe_r >= 1.5: reached_1_5r_count += 1
            if mfe_r >= 2.0: reached_2r_count += 1
            if found_3r or mfe_r >= 3.0: reached_3r_count += 1
        else:
            if rev_occurred and rev_target_pips is not None:
                rev_r = rev_target_pips / risk_pips_safe
                if rev_target_pips == 0:
                    rev_occurred = False
                else:
                    if rev_r >= 1.0: reached_1r_count += 1
                    if rev_r >= 1.5: reached_1_5r_count += 1
                    if rev_r >= 2.0: reached_2r_count += 1
                    if rev_r >= 3.0: reached_3r_count += 1
                    sl_reversed_count += 1
                    if rev_r >= 1.0: sl_reversed_1r += 1
                    if rev_r >= 1.5: sl_reversed_1_5r += 1
                    if rev_r >= 2.0: sl_reversed_2r += 1
                    if rev_r >= 3.0: sl_reversed_3r += 1
            else:
                if mfe_bsl_r >= 1.0 or post_sl_1r: reached_1r_count += 1
                if mfe_bsl_r >= 1.5 or post_sl_1_5r: reached_1_5r_count += 1
                if mfe_bsl_r >= 2.0 or post_sl_2r: reached_2r_count += 1
                if found_3r or post_sl_3r: reached_3r_count += 1
                if post_sl_1r and not rev_occurred:
                    sl_reversed_count += 1
                    sl_reversed_1r += 1
                if post_sl_1_5r and not rev_occurred: sl_reversed_1_5r += 1
                if post_sl_2r and not rev_occurred: sl_reversed_2r += 1
                if post_sl_3r and not rev_occurred: sl_reversed_3r += 1

        sym_stats[sym] = sym_stats.get(sym, {"wins": 0, "losses": 0, "pnl": 0})
        if outcome == "win":
            sym_stats[sym]["wins"] += 1
        else:
            sym_stats[sym]["losses"] += 1
        sym_stats[sym]["pnl"] += pnl

        try:
            et = str(entry_time).replace("T", " ").strip()
            if len(et) >= 13:
                hour = int(et[11:13])
                if 0 <= hour <= 23:
                    hour_stats[hour] = hour_stats.get(hour, {"wins": 0, "losses": 0})
                    if outcome == "win":
                        hour_stats[hour]["wins"] += 1
                    else:
                        hour_stats[hour]["losses"] += 1
        except:
            pass

        if outcome == "win" and left_r > 0.4:
            early_exit_count += 1
            early_exit_left_r_list.append(left_r)

        if outcome == "loss":
            if free_risk_done:
                free_risk_done_count += 1
                detail_fr_done.append({**tshort, "detail": f"SL={sl_pips_show}p | ورود: {entry_time_short}"})
            elif fr_possible:
                fr_missed_count += 1
                detail_fr_missed.append({**tshort, "detail": f"SL={sl_pips_show}p | ورود: {entry_time_short}"})

        mfe_r_str = f"{mfe_r:.2f}R" if mfe_r else "—"
        mae_r_str = f"{round(mae_pip/risk_pips_safe,2):.2f}R" if mae_pip else "—"
        mfe_bsl_str = f"{mfe_bsl_r:.2f}R" if mfe_bsl_r else "—"
        fr_str = "فری‌ریسک✓" if free_risk_done else ("فری‌ریسک✗(ممکن)" if fr_possible else "")
        pb_str = "pullback✓" if t.get("review_pullback") else ""
        rev_str = ""
        if outcome == "loss":
            if t.get("review_reversal_occurred"):
                rev_val = float(t.get("review_reversal_target_pips",0) or 0) / risk_pips_safe
                rev_str = f"برگشتSL:{rev_val:.1f}R" if rev_val else "برگشتSL✓"
            elif post_sl_1r:
                rev_val = post_sl_max / risk_pips_safe if post_sl_max else 0
                rev_str = f"برگشتSL:{rev_val:.1f}R" if rev_val else "برگشتSL✓"
        note_short = (t.get("review_note") or t.get("note") or "")[:60]
        detail_parts = [
            f"{sym}/{t.get('tf','?')} {direction}:{outcome}({exit_type_label})",
            f"entry={entry:.5g} SL={sl_pips_show}p TP={tp_pips_show}p",
            f"taken={taken_r:.2f}R MFE={mfe_r_str} MAE={mae_r_str}",
        ]
        if outcome == "loss":
            detail_parts.append(f"MFEbeforeSL={mfe_bsl_str}")
        if rev_str: detail_parts.append(rev_str)
        if fr_str: detail_parts.append(fr_str)
        if pb_str: detail_parts.append(pb_str)
        if note_short: detail_parts.append(f"note:{note_short}")
        trade_details.append(f"• {' | '.join(detail_parts)}")

    avg_taken_r = round(sum(taken_r_list)/len(taken_r_list), 2) if taken_r_list else 0
    avg_mfe_r = round(sum(mfe_r_list)/len(mfe_r_list), 2) if mfe_r_list else 0
    avg_planned_rr = round(sum(planned_rr_list)/len(planned_rr_list),2) if planned_rr_list else 0
    avg_rr_gap = round(sum(rr_gap_list)/len(rr_gap_list),2) if rr_gap_list else 0
    avg_post_sl_pip = round(sum(post_sl_pip_list)/len(post_sl_pip_list),1) if post_sl_pip_list else 0
    rr_bucket_lines = [f"R/R {b}: {round(v['w']/(v['w']+v['l'])*100)}% برد ({v['w']}/{v['w']+v['l']})" for b,v in rr_bucket.items() if v['w']+v['l']>0]
    setup_lines = [f"{st}: {round(v['w']/(v['w']+v['l'])*100)}% برد ({v['w']}/{v['w']+v['l']}) P&L:{v['pnl']:.1f}$" for st,v in sorted(setup_stats.items(),key=lambda x:-(x[1]['w']+x[1]['l'])) if v['w']+v['l']>0]
    trade_detail_data = {
        "r1": detail_1r, "r2": detail_2r, "r3": detail_3r,
        "sl_rev": detail_sl_rev, "early": detail_early,
        "fr_missed": detail_fr_missed, "fr_done": detail_fr_done,
        "avg_post_sl_pip": avg_post_sl_pip
    }
    avg_early_r = round(sum(early_exit_left_r_list)/len(early_exit_left_r_list), 2) if early_exit_left_r_list else 0
    avg_mae_r = round(sum(mae_ratio_list)/len(mae_ratio_list), 2) if mae_ratio_list else 0
    best_sym = max(sym_stats, key=lambda s: sym_stats[s]["pnl"]) if sym_stats else "—"
    worst_sym = min(sym_stats, key=lambda s: sym_stats[s]["pnl"]) if sym_stats else "—"
    best_hour = worst_hour = "—"
    if hour_stats:
        def hour_wr(h):
            s = hour_stats[h]
            tot = s["wins"] + s["losses"]
            return s["wins"]/tot if tot else 0
        best_hour = "%02d:00" % max(hour_stats, key=hour_wr)
        worst_hour = "%02d:00" % min(hour_stats, key=hour_wr)
    sym_lines = []
    for s, v in sym_stats.items():
        tot = v["wins"] + v["losses"]
        wr_s = round(v["wins"]/tot*100) if tot else 0
        sym_lines.append(f"{s}: {wr_s}% برد ({v['wins']}/{tot}) | P&L: {v['pnl']:.1f}$")
    numeric = {
        "total": total, "wins": wins, "losses": losses, "winrate": wr,
        "win_tp_count": win_tp_count, "win_3r_count": win_3r_count,
        "avg_taken_r": avg_taken_r, "avg_mfe_r": avg_mfe_r,
        "early_exit_count": early_exit_count, "early_exit_avg_pip": avg_early_r,
        "sl_reversed_count": sl_reversed_count,
        "sl_reversed_1r": sl_reversed_1r, "sl_reversed_1_5r": sl_reversed_1_5r,
        "sl_reversed_2r": sl_reversed_2r, "sl_reversed_3r": sl_reversed_3r,
        "fr_missed_count": fr_missed_count,
        "free_risk_done_count": free_risk_done_count,
        "reached_1r_count": reached_1r_count,
        "reached_1_5r_count": reached_1_5r_count,
        "reached_2r_count": reached_2r_count,
        "reached_3r_count": reached_3r_count,
        "avg_mae_ratio": avg_mae_r,
        "best_sym": best_sym, "worst_sym": worst_sym,
        "best_hour": best_hour, "worst_hour": worst_hour,
        "avg_planned_rr": avg_planned_rr, "avg_rr_gap": avg_rr_gap,
        "rr_bucket_lines": rr_bucket_lines, "setup_lines": setup_lines,
        "trade_detail_data": trade_detail_data,
    }
    prompt = (
        f"تو یک تحلیلگر حرفه‌ای داده ترید هستی. فقط بر اساس اعداد زیر تحلیل کن.\n\n"
        f"=== آمار کلی ===\n"
        f"تعداد: {total} | برد: {wins} | باخت: {losses} | نرخ برد: {wr}%\n"
        f"بردها: {win_3r_count} تا 3R کامل | {win_tp_count} تا زودخروج با TP (قبل از 3R)\n"
        f"میانگین R گرفته‌شده: {avg_taken_r}R | میانگین MFE: {avg_mfe_r}R\n"
        f"میانگین MAE: {avg_mae_r}R\n\n"
        f"=== رسیدن به سطوح ریوارد (بدون توجه به خروج) ===\n"
        f"رسیدن به 1R: {reached_1r_count} از {total} ترید\n"
        f"رسیدن به 1.5R: {reached_1_5r_count} از {total} ترید\n"
        f"رسیدن به 2R: {reached_2r_count} از {total} ترید\n"
        f"رسیدن به 3R: {reached_3r_count} از {total} ترید\n\n"
        f"=== مدیریت معامله ===\n"
        f"زود بستیم: {early_exit_count} تا (میانگین {avg_early_r}R روی میز موند)\n"
        f"SL خورد و برگشت به 1R: {sl_reversed_1r} تا\n"
        f"SL خورد و برگشت به 1.5R: {sl_reversed_1_5r} تا\n"
        f"SL خورد و برگشت به 2R: {sl_reversed_2r} تا\n"
        f"SL خورد و برگشت به 3R: {sl_reversed_3r} تا\n"
        f"فری‌ریسک ممکن بود ولی SL خورد: {fr_missed_count} تا\n"
        f"فری‌ریسک انجام شد: {free_risk_done_count} تا\n\n"
        f"=== نمادها ===\n" + "\n".join(sym_lines) + f"\n\n"
        f"=== ساعت: بهترین {best_hour} | بدترین {worst_hour} ===\n\n"
        f"=== خلاصه تریدها (با یادداشت‌ها) ===\n" + "\n".join(trade_details[:20]) + f"\n\n"
        f"گزارش فارسی بنویس (بدون مقدمه):\n"
        f"1. آمار کلی یک جمله\n"
        f"2. تحلیل سطوح ریوارد: چند درصد تریدها به 1R/2R/3R رسیدن\n"
        f"3. مشکل استاپ: با توجه به داده‌های برگشت بعد SL (به‌ویژه {sl_reversed_1r} ترید برگشت به 1R، {sl_reversed_1_5r} به 1.5R، {sl_reversed_2r} به 2R، {sl_reversed_3r} به 3R)، پیشنهاد بده که استاپ لاس را چند پیپ (یا چه درصدی از ریسک فعلی) عریض‌تر کنیم تا از خوردن استاپ جلوگیری شود. همچنین اگر از ورود پله‌ای استفاده کنیم چه تأثیری دارد؟\n"
        f"4. مشکل تارگت (زود بستن): با توجه به میانگین MFE ({avg_mfe_r}R) و میانگین R گرفته شده ({avg_taken_r}R)، پیشنهاد بده که تارگت را روی چه عددی (بر حسب R) تنظیم کنیم تا سود بیشتری جمع کنیم.\n"
        f"5. تأثیر تایم فریم و ساعت ورود: بر اساس داده‌های ورود (ساعت {best_hour} بهترین و {worst_hour} بدترین)، پیشنهاد بده که در چه ساعاتی اصلاً معامله نکنیم. همچنین آیا تایم فریم خاصی (از داده‌های تریدها) نتایج بهتری داشته؟ اگر داده کافی نیست، بگو «اطلاعات کافی نیست».\n"
        f"6. پیشنهاد عددی بهینه‌سازی: یک سناریوی شرطی بنویس که اگر استاپ را X% عریض‌تر کنیم (مثلاً {int((avg_mae_r+0.2)*100)}% یا عدد پیشنهادی خودت) و تارگت را روی {avg_mfe_r*0.85:.1f}R قرار دهیم، نرخ برد و میانگین R هر ترید چقدر می‌شود؟ (از روی داده‌ها تخمین بزن)\n"
        f"7. بهترین نماد و ساعت برای تمرکز: ترکیب {best_sym} در ساعت {best_hour} را پیشنهاد بده.\n"
        f"8. نمره کلی از 10 و جمع‌بندی نهایی.\n\n"
        f"مهم: اعداد دقیق و واقعی بده، فرضی ننویس. اگر داده برای تخمین کافی نیست، بگو «داده کافی نیست»."
    )
    if custom_prompt:
        data_block = (f"\n\n=== داده‌های آماری ===\nتعداد:{total}|برد:{wins}|باخت:{losses}|نرخ برد:{wr}%\n"
            f"R گرفته:{avg_taken_r}R|MFE:{avg_mfe_r}R|MAE:{avg_mae_r}R\n"
            f"R/R برنامه:{avg_planned_rr}|اختلاف:{avg_rr_gap:+.2f}R\nمیانگین پیپ برگشت بعد SL:{avg_post_sl_pip}\n"
            f"رسیدن 1R:{reached_1r_count}|2R:{reached_2r_count}|3R:{reached_3r_count}\n"
            f"SL برگشت 1R:{sl_reversed_1r}|2R:{sl_reversed_2r}|3R:{sl_reversed_3r}\n"
            f"فری‌ریسک ممکن:{fr_missed_count}|انجام شد:{free_risk_done_count}\n"
            f"نرخ برد R/R:{' | '.join(rr_bucket_lines)}\nستاپ‌ها:{' | '.join(setup_lines[:4])}\n"
            f"بهترین:{best_sym}|بدترین:{worst_sym}|بهترین ساعت:{best_hour}|بدترین:{worst_hour}\n"
            f"خلاصه:\n"+"\n".join(trade_details[:15]))
        final_prompt = custom_prompt + data_block
    else:
        final_prompt = prompt
    analysis = groq_analyze(final_prompt)
    return jsonify({"ok": True, "analysis": analysis, **numeric})

@app.route("/api/ohlc/<symbol>/<tf>", methods=["GET"])
def get_ohlc_proxy(symbol, tf):
    limit = request.args.get("limit", 200)
    url = f"https://biquote.io/api/{symbol.upper()}/ohlc?interval={tf}&limit={limit}"
    try:
        r = requests.get(url, timeout=12, headers=H)
        r.raise_for_status()
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 502

@app.route("/api/chart/<trade_id>", methods=["GET"])
def get_chart(trade_id):
    journal = load_journal()
    trade = next((t for t in journal if t["id"] == trade_id), None)
    if not trade:
        return jsonify({"ok": False, "error": "ترید پیدا نشد"}), 404
    sym = trade["sym"]
    tf = trade.get("tf", "1h")
    entry = float(trade["entry"])
    sl = trade.get("sl_price")
    tp = trade.get("tp_price")
    entry_time_str = trade.get("entryTime", "")
    direction = trade.get("direction", "BUY")
    outcome = trade.get("outcome", "")
    exit_px = trade.get("exit")
    mul = get_pip_multiplier(sym)
    status = trade.get("status", "closed")
    risk_pips = None
    reward_levels = {}
    if sl and entry:
        if direction == "BUY":
            risk_pips = (entry - float(sl)) * mul
            reward_levels = {"r1": entry + risk_pips / mul, "r2": entry + 2 * risk_pips / mul, "r3": entry + 3 * risk_pips / mul}
        else:
            risk_pips = (float(sl) - entry) * mul
            reward_levels = {"r1": entry - risk_pips / mul, "r2": entry - 2 * risk_pips / mul, "r3": entry - 3 * risk_pips / mul}
    snapshot = trade.get("candle_snapshot", [])
    candles = []
    if snapshot:
        entry_utc = tehran_to_utc(entry_time_str)
        entry_idx_snap = 0
        for i, b in enumerate(snapshot):
            try:
                bt = datetime.strptime(b["t"], "%Y-%m-%d %H:%M")
                bt_utc = bt - timedelta(hours=3, minutes=30)
                if bt_utc >= (entry_utc or datetime.utcfromtimestamp(0)):
                    entry_idx_snap = i
                    break
            except: pass
        for i, b in enumerate(snapshot):
            phase = "before" if i < entry_idx_snap else ("hit" if i == len(snapshot)-1 else "after")
            candles.append({"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "phase": phase})
    else:
        try:
            url = f"https://biquote.io/api/{sym}/ohlc?interval={tf}&limit=300"
            r = requests.get(url, timeout=12, headers=H)
            raw = r.json()
            bars = raw.get("bars") or raw.get("data") or (raw if isinstance(raw, list) else [])
        except Exception as e:
            return jsonify({"ok": False, "error": f"خطا در دریافت کندل: {e}"}), 502
        if not bars:
            return jsonify({"ok": False, "error": "کندلی دریافت نشد"}), 502
        def bar_dt(b):
            ts = b.get("openTime") or b.get("time") or b.get("timestamp") or ""
            try:
                if isinstance(ts, (int, float)):
                    return datetime.utcfromtimestamp(ts)
                return datetime.strptime(ts.replace("Z",""), "%Y-%m-%dT%H:%M:%S")
            except:
                return datetime.utcfromtimestamp(0)
        bars.sort(key=bar_dt)
        entry_utc = tehran_to_utc(entry_time_str)
        entry_idx = 0
        if entry_utc:
            for i, b in enumerate(bars):
                if bar_dt(b) >= entry_utc:
                    entry_idx = i
                    break
        end_idx = min(entry_idx + 100, len(bars) - 1)
        r3_price = reward_levels.get("r3") if reward_levels else None
        is_buy = direction == "BUY"
        for i in range(entry_idx, len(bars)):
            b = bars[i]
            high = float(b.get("high", 0))
            low  = float(b.get("low", 0))
            if is_buy:
                if sl and low <= float(sl):  end_idx = i; break
                if r3_price and high >= r3_price: end_idx = i; break
            else:
                if sl and high >= float(sl): end_idx = i; break
                if r3_price and low <= r3_price: end_idx = i; break
            end_idx = i
        start_idx = max(0, entry_idx - 20)
        visible = bars[start_idx:end_idx+1]
        rel_entry = entry_idx - start_idx
        for i, b in enumerate(visible):
            dt_teh = bar_dt(b) + timedelta(hours=3, minutes=30)
            phase = "before" if i < rel_entry else ("hit" if i == len(visible)-1 else "after")
            candles.append({"t": dt_teh.strftime("%Y-%m-%d %H:%M"), "o": float(b.get("open",0)), "h": float(b.get("high",0)), "l": float(b.get("low",0)), "c": float(b.get("close",0)), "phase": phase})
    return jsonify({
        "ok": True, "sym": sym, "tf": tf, "direction": direction, "outcome": outcome, "status": status,
        "entry": entry, "sl": float(sl) if sl else None, "tp": float(tp) if tp else None,
        "exit_px": float(exit_px) if exit_px else None, "risk_pips": round(risk_pips, 1) if risk_pips else None,
        "reward_levels": reward_levels, "candles": candles,
        "entry_candle_idx": next((i for i,c in enumerate(candles) if c["phase"] != "before"), 0),
    })

def poll_open_trades():
    time.sleep(30)
    while True:
        try:
            journal = load_journal()
            open_trades = [t for t in journal if t.get("status") == "open" and t.get("pending_check")]
            changed = False
            for trade in open_trades:
                sym = trade["sym"]
                tf = trade.get("tf", "1h")
                entry = float(trade["entry"])
                direction = trade.get("direction", "BUY")
                sl_price = trade.get("sl_price")
                mul = get_pip_multiplier(sym)
                if sl_price:
                    risk = abs(entry - float(sl_price)) * mul
                    if direction == "BUY":
                        tp3 = entry + 3 * risk / mul
                    else:
                        tp3 = entry - 3 * risk / mul
                else:
                    tp3 = trade.get("tp_price")
                try:
                    res = check_sltp_hit_with_details(sym, tf, trade["entryTime"], direction, entry, sl_price, None, 1.0, r3_override=tp3)
                    (hit, hit_price, tp_hit, tp_hit_price, last_close, pnl, mfe_pip, mae_pip, candle_lines,
                     found_3r, fr_possible, fr_saved, fr_at, pullback,
                     post_max, post_1r, post_1_5r, post_2r, post_3r,
                     mfe_before_sl, passed_1r, snapshot_bars) = res
                    trade["tp_hit"] = tp_hit
                    trade["tp_hit_price"] = tp_hit_price
                    if hit:
                        trade["exit"] = hit_price
                        trade["exitTime"] = now_teh()
                        trade["outcome"] = "win" if hit == "tp3" else "loss"
                        trade["exit_type"] = hit
                        trade["status"] = "closed"
                        trade["pending_check"] = False
                        trade["mfe_pip"] = round(mfe_pip, 1)
                        trade["mae_pip"] = round(mae_pip, 1)
                        trade["found_3r"] = found_3r
                        trade["free_risk_was_possible"] = fr_possible
                        trade["free_risk_saved"] = fr_saved
                        trade["pullback_after_1r"] = pullback
                        trade["post_sl_max_profit"] = round(post_max, 1) if post_max else 0
                        trade["post_sl_reached_1r"] = post_1r
                        trade["post_sl_reached_1_5r"] = post_1_5r
                        trade["post_sl_reached_2r"] = post_2r
                        trade["post_sl_reached_3r"] = post_3r
                        trade["mfe_before_sl_pip"] = round(mfe_before_sl, 1) if mfe_before_sl else 0
                        trade["passed_1r"] = passed_1r
                        diff = (hit_price - entry) if direction == "BUY" else (entry - hit_price)
                        trade["pnl"] = round(diff, 4)
                        trade["candle_snapshot"] = snapshot_bars
                        trade["snapshot_locked"] = True
                        changed = True
                        log_error(f"[poll_open] {sym} resolved: {hit} at {hit_price}")
                    else:
                        if not trade.get("snapshot_locked"):
                            trade["candle_snapshot"] = snapshot_bars
                        trade["last_poll"] = now_teh()
                        changed = True
                except Exception as e:
                    log_error(f"[poll_open] {sym}: {e}")
            if changed:
                save_journal(journal)
        except Exception as e:
            log_error(f"poll_open_trades: {e}")
        time.sleep(7200)

threading.Thread(target=check_alerts, daemon=True).start()
threading.Thread(target=poll_telegram, daemon=True).start()
threading.Thread(target=poll_open_trades, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)