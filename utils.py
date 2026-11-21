import time
from config import (JOBS, BUSINESSES, FARMS, PASSIVE_CAP_HOURS, BTC_PRICE)
import database as db

def fmt_full(n):
    """Полное число: 1.279.728$"""
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = int(float(n))
    s = str(abs(n))
    parts = []
    while len(s) > 3:
        parts.insert(0, s[-3:])
        s = s[:-3]
    parts.insert(0, s)
    return ("-" if n < 0 else "") + ".".join(parts)

def fmt_btc(n):
    if n < 0.01:
        return f"{n:.6f}"
    return f"{n:.4f}"

def parse_amount(s):
    """1к=1000, 1кк=1e6, 1ккк=1e9, 1кккк=1e12, 500, 1500000"""
    if not s:
        return None
    s = s.lower().strip().replace("$", "").replace(",", "").replace(" ", "").replace("btc", "")
    mult = 1
    if s.endswith("кккк") or s.endswith("kkkk"):
        mult, s = 10**12, s[:-4]
    elif s.endswith("ккк") or s.endswith("kkk"):
        mult, s = 10**9, s[:-3]
    elif s.endswith("кк") or s.endswith("kk"):
        mult, s = 10**6, s[:-2]
    elif s.endswith("к") or s.endswith("k"):
        mult, s = 10**3, s[:-1]
    try:
        return int(float(s) * mult)
    except (ValueError, TypeError):
        return None

def parse_list(s):
    return s.split(",") if s else []

def serialize_list(lst):
    return ",".join(lst)

async def process_passive(user_id):
    """Начисляет пассивный доход (макс 48 часов)."""
    user = await db.get_user(user_id)
    now = int(time.time())
    last = user["last_passive"] or now
    elapsed = min(now - last, PASSIVE_CAP_HOURS * 3600)
    if elapsed < 60:
        return 0, 0

    biz = parse_list(user["businesses"])
    farms = parse_list(user["farms"])
    biz_income = sum(BUSINESSES[b]["income"] for b in biz if b in BUSINESSES) * elapsed / 3600
    farm_btc = sum(FARMS[f]["btc_per_hour"] for f in farms if f in FARMS) * elapsed / 3600

    if biz_income > 0:
        await db.add_balance(user_id, int(biz_income))
    if farm_btc > 0:
        await db.update(user_id, btc=user["btc"] + farm_btc)

    await db.update(user_id, last_passive=now)
    return int(biz_income), farm_btc

# ============ БЛЭКДЖЕК ============
SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['2','3','4','5','6','7','8','9','10','J','Q','K','A']

def new_deck():
    return [f"{r}{s}" for r in RANKS for s in SUITS]

def hand_value(hand):
    val, aces = 0, 0
    for card in hand:
        rank = card[:-1]
        if rank in ('J', 'Q', 'K'):
            val += 10
        elif rank == 'A':
            val += 11; aces += 1
        else:
            val += int(rank)
    while val > 21 and aces > 0:
        val -= 10; aces -= 1
    return val

def dealer_play(dealer, deck):
    while hand_value(dealer) < 17:
        dealer.append(deck.pop())
    return dealer

def fmt_hand(hand):
    return " ".join(hand)

def is_blackjack(hand):
    return len(hand) == 2 and hand_value(hand) == 21
