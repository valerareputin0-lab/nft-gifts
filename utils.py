import time
from config import (BUSINESSES, FARMS, FARM_CAP_HOURS, CASH_CAP_HOURS,
                    CASH_COLLECT_COOLDOWN, BUSINESS_LEVEL_MULT)
import database as db

def fmt_full(n):
    try: n = int(n)
    except (TypeError, ValueError): n = int(float(n))
    s = str(abs(n)); parts = []
    while len(s) > 3:
        parts.insert(0, s[-3:]); s = s[:-3]
    parts.insert(0, s)
    return ("-" if n < 0 else "") + ".".join(parts)

def fmt_short(n):
    n = int(n)
    if n >= 10**9:  return f"{n/10**9:.2f} млрд".rstrip('0').rstrip('.') + " "
    if n >= 10**6:  return f"{n/10**6:.2f} млн".rstrip('0').rstrip('.') + " "
    if n >= 10**3:  return f"{n/10**3:.2f} тыс".rstrip('0').rstrip('.') + " "
    return f"{n} "

def fmt_btc(n):
    if n == 0: return "0"
    return f"{n:.2f}"

def parse_amount(s):
    if not s: return None
    s = s.lower().strip().replace("$", "").replace(",", "").replace(" ", "").replace("btc", "")
    mult = 1
    if s.endswith("кккк") or s.endswith("kkkk"): mult, s = 10**12, s[:-4]
    elif s.endswith("ккк") or s.endswith("kkk"): mult, s = 10**9, s[:-3]
    elif s.endswith("кк") or s.endswith("kk"): mult, s = 10**6, s[:-2]
    elif s.endswith("к") or s.endswith("k"): mult, s = 10**3, s[:-1]
    try: return int(float(s) * mult)
    except (ValueError, TypeError): return None

def parse_list(s):
    return [x for x in s.split(",") if x] if s else []

def serialize_list(lst):
    return ",".join(lst)

def parse_businesses(s):
    result = {}
    if not s: return result
    for item in s.split(","):
        if not item: continue
        if ":" in item:
            k, v = item.split(":")
            try: result[k] = int(v)
            except ValueError: result[k] = 1
        else:
            result[item] = 1
    return result

def serialize_businesses(d):
    return ",".join(f"{k}:{v}" for k, v in d.items())

def business_income(bid, level):
    base = BUSINESSES[bid]["income"]
    return int(base * BUSINESS_LEVEL_MULT.get(level, 1.0))

def total_business_income(biz_dict):
    return sum(business_income(b, lvl) for b, lvl in biz_dict.items() if b in BUSINESSES)

def total_farm_income(farms_list):
    return sum(FARMS[f]["btc_per_hour"] for f in farms_list if f in FARMS)

def farm_income_per_minute(farms_list):
    return total_farm_income(farms_list) / 60.0

def calc_business_cash(u):
    biz = parse_businesses(u["businesses"])
    if not biz: return 0, 0, 0
    bid = list(biz.keys())[0]
    lvl = biz[bid]
    income = business_income(bid, lvl)
    cap = income * CASH_CAP_HOURS
    last = u.get("business_last_collect") or int(time.time())
    elapsed = int(time.time()) - last
    cash = min(cap, int(income * elapsed / 3600))
    return cash, cap, income

async def collect_business(user_id):
    u = await db.get_user(user_id)
    cash, _, _ = calc_business_cash(u)
    now = int(time.time())
    last = u.get("business_last_collect") or now
    elapsed = now - last
    if elapsed < CASH_COLLECT_COOLDOWN: return 0, CASH_COLLECT_COOLDOWN - elapsed
    if cash <= 0: return 0, 0
    await db.add_balance(user_id, cash)
    await db.update(user_id, business_last_collect=now)
    return cash, 0

async def process_farms(user_id):
    """Начисляет BTC с ферм за прошедшее время (до 48ч)."""
    user = await db.get_user(user_id)
    now = int(time.time())
    last = user["last_passive"] or now
    elapsed = min(now - last, FARM_CAP_HOURS * 3600)
    farms = parse_list(user["farms"])
    if not farms:
        await db.update(user_id, last_passive=now)
        return 0
    if elapsed < 1:
        return 0
    farm_btc = total_farm_income(farms) * elapsed / 3600
    if farm_btc > 0:
        await db.update(user_id, btc=user["btc"] + farm_btc)
    await db.update(user_id, last_passive=now)
    return farm_btc

# ============ БЛЭКДЖЕК ============
SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['2','3','4','5','6','7','8','9','10','J','Q','K','A']

def new_deck(): return [f"{r}{s}" for r in RANKS for s in SUITS]

def hand_value(hand):
    val, aces = 0, 0
    for card in hand:
        rank = card[:-1]
        if rank in ('J', 'Q', 'K'): val += 10
        elif rank == 'A': val += 11; aces += 1
        else: val += int(rank)
    while val > 21 and aces > 0: val -= 10; aces -= 1
    return val

def dealer_play(dealer, deck):
    while hand_value(dealer) < 17: dealer.append(deck.pop())
    return dealer

def fmt_hand(hand): return " ".join(hand)
def is_blackjack(hand): return len(hand) == 2 and hand_value(hand) == 21
