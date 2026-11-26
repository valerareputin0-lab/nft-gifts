import asyncio
import time
import random
import os
from datetime import datetime

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import config
import database as db
from utils import (fmt_full, fmt_short, fmt_btc, parse_amount, parse_list,
                   serialize_list, parse_businesses, serialize_businesses,
                   business_income, total_business_income, total_farm_income,
                   farm_income_per_minute, process_farms, calc_business_cash,
                   collect_business, new_deck, hand_value, dealer_play,
                   fmt_hand, is_blackjack)
from keyboards import (main_kb, main_reply_kb, back_kb, profile_kb,
                       biz_shop_kb, biz_confirm_kb, biz_manage_kb, farms_kb,
                       houses_kb, garage_kb, wardrobe_kb, shop_kb, rewards_kb,
                       bank_kb, deposits_kb, casino_kb, bj_kb, rl_choice_kb,
                       dice_choice_kb, admin_main_kb, admin_money_kb,
                       admin_btc_kb, admin_prop_kb, admin_ban_kb,
                       admin_global_kb, admin_promo_menu_kb, admin_confirm_kb,
                       admin_house_select_kb, admin_biz_select_kb,
                       admin_farm_select_kb, admin_perms_kb, admin_vip_kb,
                       admin_luck_kb, ADMIN_PERMS)
from groups import register_group_handlers
from config import (BUSINESSES, FARMS, HOUSES, CARS, SKINS, DEPOSITS,
                    MIN_BET, MAX_BET, WITHDRAW_FEE, BTC_PRICE, ADMIN_ID,
                    FARM_CAP_HOURS, CASH_CAP_HOURS, CASH_COLLECT_COOLDOWN,
                    SELL_PERCENT, BONUS_PERCENT, BONUS_MIN, BONUS_MAX,
                    BONUS_COOLDOWN, GARAGE_PERCENT, BUSINESS_UPGRADE_COST_MULT,
                    NICK_MIN, NICK_MAX, FARMS_LIMIT)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

BTC_CURRENT = BTC_PRICE
MAX_AMOUNT = 999_999_999_999_999_999

class St(StatesGroup):
    bj_bet = State(); bj_play = State()
    rl_bet = State()
    dice_bet = State()
    bank_in = State(); bank_out = State()
    dep_amount = State()
    sell_btc = State()
    farm_buy_qty = State()
    farm_sell_qty = State()
    promo_enter = State()
    nick_input = State()
    adm_give_money = State(); adm_take_money = State()
    adm_give_btc = State(); adm_take_btc = State()
    adm_give_all = State(); adm_take_all = State()
    adm_view_profile = State()
    adm_ban = State(); adm_unban = State()
    adm_prop_target = State()
    adm_btc_price = State()
    adm_promo_create = State(); adm_promo_delete = State()
    adm_give_admin = State()
    adm_give_vip = State()
    adm_luck_target = State()
    adm_luck_view = State()

def is_main_admin(uid): return uid == ADMIN_ID

def has_perm(user, perm):
    if user["user_id"] == ADMIN_ID: return True
    if not user.get("is_admin"): return False
    perms = (user.get("admin_perms") or "").split(",")
    return perm in perms

def is_admin_any(user):
    return user["user_id"] == ADMIN_ID or bool(user.get("is_admin"))

async def check_banned(uid):
    u = await db.get_user(uid)
    if not u.get("is_banned"): return None
    until = u.get("ban_until", 0)
    now = int(time.time())
    if until == 0: return "🚫 Ты забанен навсегда."
    if until > now:
        date = datetime.fromtimestamp(until).strftime("%d.%m.%Y %H:%M")
        return f"🚫 Ты забанен до {date}."
    await db.update(uid, is_banned=0, ban_until=0)
    return None

def apply_luck(win: bool, luck: int) -> bool:
    if luck >= 100: return True
    if luck <= 0: return False
    if win:
        p = min(1.0, luck / 50.0)
        return random.random() < p
    else:
        p = max(0.0, (luck - 50) / 50.0)
        return random.random() < p

# ============ НИК ============
async def ask_nick(m, state, source="start"):
    await state.set_state(St.nick_input)
    await state.update_data(nick_from=source)
    await m.answer(
        f"🎭 Придумай ник\n\n• {NICK_MIN}–{NICK_MAX} символов\n• Только буквы и цифры\n• Должен быть уникальным")

@dp.message(St.nick_input)
async def process_nick(m: Message, state: FSMContext):
    nick = m.text.strip()
    if not (NICK_MIN <= len(nick) <= NICK_MAX):
        await m.answer(f"❌ Длина: {NICK_MIN}–{NICK_MAX}"); return
    if not nick.isalnum():
        await m.answer("❌ Только буквы и цифры"); return
    if await db.is_nick_taken(nick, m.from_user.id):
        await m.answer("❌ Ник занят"); return
    await db.set_nick(m.from_user.id, nick)
    data = await state.get_data(); await state.clear()
    if data.get("nick_from") == "change":
        await m.answer(f"✅ Ник: <b>{nick}</b>", parse_mode="HTML")
        await show_profile(m.from_user.id, m, is_cb=False)
    else:
        await m.answer(f"✅ Ник: <b>{nick}</b>", parse_mode="HTML")
        await show_profile(m.from_user.id, m, is_cb=False)

# ============ СТАРТ ============
@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    u = await db.get_user(m.from_user.id, m.from_user.username)
    await db.touch_active(m.from_user.id)
    ban = await check_banned(m.from_user.id)
    if ban: await m.answer(ban); return
    if not u.get("nick"):
        await ask_nick(m, state, "start"); return
    await show_profile(m.from_user.id, m, is_cb=False, with_reply_kb=True)

# ============ REPLY-КНОПКИ ============
@dp.message(F.text == "👤 Профиль")
async def reply_profile(m: Message):
    await show_profile(m.from_user.id, m, is_cb=False)

@dp.message(F.text == "🎰 Казино")
async def reply_casino(m: Message):
    ban = await check_banned(m.from_user.id)
    if ban: await m.answer(ban); return
    await process_farms(m.from_user.id)
    await m.answer(
        "🎰 <b>Казино</b>\n\n"
        "🎯 Рулетка — угадай цвет/число (x2–x30)\n"
        "🃏 Блэкджек — набери 21 (x2)\n"
        "🎲 Кости — угадай число (x2–x5)\n\nВыбери:",
        reply_markup=casino_kb(), parse_mode="HTML")

@dp.message(F.text == "🏠 Дом")
async def reply_houses(m: Message):
    await show_houses(m.from_user.id, m, is_cb=False)

@dp.message(F.text == "💼 Бизнес")
async def reply_biz(m: Message):
    await show_biz(m.from_user.id, m, is_cb=False)

@dp.message(F.text == "⛏ Фермы")
async def reply_farms(m: Message):
    await show_farms(m.from_user.id, m, is_cb=False)

@dp.message(F.text == "🛒 Магазин")
async def reply_shop(m: Message):
    await show_shop(m.from_user.id, m, is_cb=False)

@dp.message(F.text == "🏦 Банк")
async def reply_bank(m: Message):
    ban = await check_banned(m.from_user.id)
    if ban: await m.answer(ban); return
    u = await db.get_user(m.from_user.id)
    has_dep = u["deposit_amount"] > 0
    ready = has_dep and u["deposit_end"] <= time.time()
    lines = [f"🏦 <b>БАНК</b>", "", f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>",
             f"🏦 Счёт: <b>{fmt_full(u['bank_wallet'])}$</b>"]
    if has_dep:
        lines.append(""); lines.append(f"📈 Вклад: <b>{fmt_full(u['deposit_amount'])}$</b>")
    lines.append(""); lines.append("💸 Комиссия снятия: 3%")
    await m.answer("\n".join(lines), reply_markup=bank_kb(has_dep, ready), parse_mode="HTML")

@dp.message(F.text == "🎁 Награды")
async def reply_rewards(m: Message):
    ban = await check_banned(m.from_user.id)
    if ban: await m.answer(ban); return
    await m.answer("🎁 <b>Награды</b>", reply_markup=rewards_kb(), parse_mode="HTML")

@dp.message(F.text == "🏆 Топ")
async def reply_top(m: Message):
    ban = await check_banned(m.from_user.id)
    if ban: await m.answer(ban); return
    top = await db.get_top(10)
    rank = await db.get_user_rank(m.from_user.id)
    digits = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    lines = [f"💲 Топ игроков:", ""]
    for i in range(10):
        if i < len(top):
            u = top[i]; lines.append(f"{digits[i]} {u.get('nick') or 'Игрок'} — {fmt_full(u['balance'])}$")
        else:
            lines.append(f"{digits[i]} —")
    lines.append(""); lines.append(f"🌍 Твоя позиция: #{rank}")
    await m.answer("\n".join(lines), parse_mode="HTML")

@dp.message(F.text == "✏️ Сменить ник")
async def reply_change_nick(m: Message, state: FSMContext):
    ban = await check_banned(m.from_user.id)
    if ban: await m.answer(ban); return
    await ask_nick(m, state, "change")

# ============ ПРОФИЛЬ ============
async def show_profile(uid, m_or_c, is_cb=False, with_reply_kb=False):
    ban = await check_banned(uid)
    if ban:
        if is_cb: await m_or_c.answer(ban, show_alert=True)
        else: await m_or_c.answer(ban)
        return
    await db.touch_active(uid)
    await process_farms(uid)
    u = await db.get_user(uid)
    rank = await db.get_user_rank(uid)
    biz = parse_businesses(u["businesses"]); biz = {k:v for k,v in biz.items() if k in BUSINESSES}
    lst_f = parse_list(u["farms"]); ftype = lst_f[0] if lst_f else None; fcount = len(lst_f)
    houses = parse_list(u["houses"]); cars = parse_list(u["garage"])

    reg_ts = u.get("registered_at") or int(time.time())
    days = int((time.time() - reg_ts) // 86400)
    if days == 0: reg_str = "сегодня"
    else:
        lt, lo = days % 100, days % 10
        if 11 <= lt <= 14: w = "дней"
        elif lo == 1: w = "день"
        elif 2 <= lo <= 4: w = "дня"
        else: w = "дней"
        reg_str = f"{days} {w} назад"

    if u['btc'] == 0: btc_str = "0"
    else: btc_str = fmt_btc(u['btc'])
    btc_usd = int(u['btc'] * BTC_CURRENT)

    if u.get('btc_wallet', 0) == 0: wallet_str = "0"
    else: wallet_str = fmt_btc(u['btc_wallet'])

    vip_line = ""
    if u.get("is_vip"):
        vip_line = f"\n⭐ VIP: <b>{u.get('vip_level') or 'ADMIN'}</b>"

    imush = []
    if biz:
        bid = list(biz.keys())[0]
        imush.append(f"⠀🚀 Бизнес: {BUSINESSES[bid]['name'].split(' ',1)[-1]} ({biz[bid]} lvl)")
    if ftype:
        imush.append(f"⠀🔋 Ферма: {FARMS[ftype]['name'].split(' ',1)[-1]} ({fcount} шт)")
    if houses:
        imush.append(f"⠀🏠 Дом: {HOUSES[houses[0]]['name'].split(' ',1)[-1]}")
    if cars:
        imush.append(f"⠀🚗 Машина: {CARS[cars[-1]]['name'].split(' ',1)[-1]}")

    lines = [
        f"👻 {u.get('nick') or 'Игрок'}, профиль:{vip_line}", "",
        f"🔎 Игровой ID: {u.get('game_id') or '—'}",
        f"💰 Баланс: {fmt_full(u['balance'])}$",
        f"🏦 Счет: {fmt_full(u['bank_wallet'])}$",
        f"₿ Bitcoin: {btc_str} (~{fmt_full(btc_usd)}$)",
        f"👛 Кошелёк BTC: {wallet_str}",
        f"👑 Рейтинг в топе: {rank}", ""]
    if imush:
        lines.append("🗄 Имущество:"); lines.extend(imush)
    else:
        lines.append("🗄 Имущество: пока нету")
    lines.append(""); lines.append(f"⌚ Регистрация: {reg_str}")

    adm = is_admin_any(u)
    kb = profile_kb(adm)
    text = "\n".join(lines)
    if is_cb:
        await m_or_c.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await m_or_c.answer(text, reply_markup=kb, parse_mode="HTML")
        if with_reply_kb:
            await m_or_c.answer("👇", reply_markup=main_reply_kb(adm))

@dp.callback_query(F.data == "profile")
async def cb_profile(c: CallbackQuery):
    await show_profile(c.from_user.id, c, is_cb=True)

@dp.callback_query(F.data == "menu")
async def cb_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    await show_profile(c.from_user.id, c, is_cb=True)

@dp.callback_query(F.data == "change_nick")
async def cb_change_nick(c: CallbackQuery, state: FSMContext):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    await ask_nick(c.message, state, "change"); await c.answer()

@dp.callback_query(F.data == "top")
async def cb_top(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    await db.touch_active(c.from_user.id)
    top = await db.get_top(10)
    rank = await db.get_user_rank(c.from_user.id)
    digits = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    lines = [f"💲 {c.from_user.first_name or 'Игрок'}, топ самых лучших игроков:", ""]
    for i in range(10):
        if i < len(top):
            u = top[i]; lines.append(f"{digits[i]} {u.get('nick') or 'Игрок'} — {fmt_full(u['balance'])}$")
        else:
            lines.append(f"{digits[i]} —")
    lines.append(""); lines.append(f"🌍 Ваша позиция: #{rank}")
    await c.message.edit_text("\n".join(lines), reply_markup=back_kb("profile"), parse_mode="HTML")

# ============ БИЗНЕСЫ ============
async def show_biz(uid, m_or_c, is_cb=False):
    ban = await check_banned(uid)
    if ban:
        if is_cb: await m_or_c.answer(ban, show_alert=True)
        else: await m_or_c.answer(ban)
        return
    await db.touch_active(uid)
    await process_farms(uid)
    u = await db.get_user(uid)
    biz = parse_businesses(u["businesses"]); biz = {k:v for k,v in biz.items() if k in BUSINESSES}
    if biz:
        bid = list(biz.keys())[0]; lvl = biz[bid]; b = BUSINESSES[bid]
        cash, cap, income = calc_business_cash(u)
        text = (f"🚀 {u['nick']}, статистика «{b['name'].split(' ',1)[-1]}»:\n\n"
                f"💸 Доход: {fmt_short(income // 60)}$в минуту\n"
                f"💰 В кассе: {fmt_short(cash)}$ из {fmt_short(cap)}$\n"
                f"📊 Уровень: {lvl}/3\n\n━━━━━━━━━━━━━━━\n"
                f"💼 Бизнес продаётся с комиссией 5%")
        kb = biz_manage_kb(bid, lvl, cash > 0)
    else:
        lines = [f"💼 {u['nick']}, обеспечь себя ДЕНЬГАМИ! Список бизнесов:", ""]
        for i, (key, b) in enumerate(BUSINESSES.items(), 1):
            lines.append(f"{i}. {b['name']}")
            lines.append(f"⠀• Цена: {fmt_short(b['price'])}$")
            lines.append(f"⠀• Прибыль: {fmt_short(b['income'])}$ в час")
            lines.append("")
        lines.append(f"💰 Твой баланс: {fmt_full(u['balance'])}$")
        text = "\n".join(lines)
        kb = biz_shop_kb()
    if is_cb:
        await m_or_c.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await m_or_c.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "biz")
async def cb_biz(c: CallbackQuery):
    await show_biz(c.from_user.id, c, True)

@dp.callback_query(F.data.startswith("biz_info_"))
async def cb_biz_info(c: CallbackQuery):
    bid = c.data.split("_")[2]
    if bid not in BUSINESSES: return
    b = BUSINESSES[bid]; u = await db.get_user(c.from_user.id)
    can = u["balance"] >= b["price"]
    text = (f"{b['name']}\n\n💵 Цена: {fmt_short(b['price'])}$\n"
            f"📈 Прибыль: {fmt_short(b['income'])}$ в час\n\n"
            f"💰 Твой баланс: {fmt_full(u['balance'])}$\n\n"
            f"{'✅ Можешь купить!' if can else '❌ Не хватает'}")
    await c.message.edit_text(text, reply_markup=biz_confirm_kb(bid), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buybiz_"))
async def cb_buy_biz(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    bid = c.data.split("_")[1]
    if bid not in BUSINESSES: return
    b = BUSINESSES[bid]; u = await db.get_user(c.from_user.id)
    biz = parse_businesses(u["businesses"]); biz = {k:v for k,v in biz.items() if k in BUSINESSES}
    if biz: await c.answer("Уже есть бизнес!", show_alert=True); return
    if u["balance"] < b["price"]: await c.answer("❌ Мало!", show_alert=True); return
    await db.add_balance(c.from_user.id, -b["price"])
    await db.update(c.from_user.id, businesses=serialize_businesses({bid: 1}), business_last_collect=int(time.time()))
    await c.answer(f"✅ {b['name']}!", show_alert=True); await show_biz(c.from_user.id, c, True)

@dp.callback_query(F.data.startswith("upbiz_"))
async def cb_upgrade_biz(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    bid = c.data.split("_")[1]
    if bid not in BUSINESSES: return
    b = BUSINESSES[bid]; u = await db.get_user(c.from_user.id)
    biz = parse_businesses(u["businesses"]); biz = {k:v for k,v in biz.items() if k in BUSINESSES}
    if bid not in biz: await c.answer("Нет бизнеса", show_alert=True); return
    lvl = biz[bid]
    if lvl >= 3: await c.answer("Максимум!", show_alert=True); return
    cost = int(b["price"] * BUSINESS_UPGRADE_COST_MULT[lvl + 1])
    if u["balance"] < cost: await c.answer(f"❌ {fmt_short(cost)}$", show_alert=True); return
    await db.add_balance(c.from_user.id, -cost)
    await db.update(c.from_user.id, businesses=serialize_businesses({bid: lvl + 1}), business_last_collect=int(time.time()))
    await c.answer(f"✅ Lvl {lvl+1}!", show_alert=True); await show_biz(c.from_user.id, c, True)

@dp.callback_query(F.data == "biz_collect")
async def cb_biz_collect(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    amount, cd = await collect_business(c.from_user.id)
    if cd > 0: await c.answer(f"⏳ {cd} сек", show_alert=True); return
    if amount == 0: await c.answer("Пусто", show_alert=True); return
    await c.answer(f"💰 +{fmt_full(amount)}$", show_alert=True); await show_biz(c.from_user.id, c, True)

@dp.callback_query(F.data.startswith("sellbiz_"))
async def cb_sell_biz(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    bid = c.data.split("_")[1]
    if bid not in BUSINESSES: return
    u = await db.get_user(c.from_user.id)
    biz = parse_businesses(u["businesses"]); biz = {k:v for k,v in biz.items() if k in BUSINESSES}
    if bid not in biz: await c.answer("Нет", show_alert=True); return
    cash, _, _ = calc_business_cash(u)
    sell = int(BUSINESSES[bid]["price"] * (1 - SELL_PERCENT))
    await db.add_balance(c.from_user.id, cash + sell)
    await db.update(c.from_user.id, businesses="", business_last_collect=0)
    await c.answer(f"💸 +{fmt_full(cash + sell)}$", show_alert=True); await show_biz(c.from_user.id, c, True)

# ============ ФЕРМЫ ============
async def show_farms(uid, m_or_c, is_cb=False):
    ban = await check_banned(uid)
    if ban:
        if is_cb: await m_or_c.answer(ban, show_alert=True)
        else: await m_or_c.answer(ban)
        return
    await db.touch_active(uid)
    await process_farms(uid)
    u = await db.get_user(uid)
    lst = parse_list(u["farms"]); ftype = lst[0] if lst else None; fcount = len(lst)
    if ftype:
        f = FARMS[ftype]
        total_hour = total_farm_income(lst)
        total_min = farm_income_per_minute(lst)
        text = (f"⛏️ Ферма {f['name'].split(' ',1)[-1]} ({fcount}шт)\n\n"
                f"💰 Заработок в минуту: <b>{total_min:.2f}฿</b>\n"
                f"📈 В час: {total_hour:.0f}฿\n"
                f"₿ Курс Bitcoin: {fmt_short(BTC_CURRENT)}$\n\n"
                f"💵 На фермах: <b>{fmt_btc(u['btc'])}₿</b> (≈{fmt_full(int(u['btc']*BTC_CURRENT))}$)\n"
                f"👛 В кошельке: {fmt_btc(u.get('btc_wallet',0))}₿")
    else:
        lines = [f"🌐 {u['nick']}, список ферм:", ""]
        for i, (key, f) in enumerate(FARMS.items(), 1):
            lines.append(f"{i}. {f['name']}")
            lines.append(f"⠀• Цена: {fmt_short(f['price'])}$")
            lines.append(f"⠀• Прибыль: {f['btc_per_hour']}฿/час")
            lines.append(f"⠀• В наличии: 0 шт.")
            lines.append("")
        lines.append(f"💰 Твой баланс: {fmt_full(u['balance'])}$")
        lines.append(f"₿ Курс: {fmt_short(BTC_CURRENT)}$")
        text = "\n".join(lines)
    kb = farms_kb(ftype, fcount)
    if is_cb:
        await m_or_c.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await m_or_c.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "farms")
async def cb_farms(c: CallbackQuery):
    await show_farms(c.from_user.id, c, True)

@dp.callback_query(F.data.startswith("buyfarm_"))
async def cb_buy_farm_choose(c: CallbackQuery, state: FSMContext):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    key = c.data.split("_")[1]
    if key not in FARMS: return
    u = await db.get_user(c.from_user.id)
    lst = parse_list(u["farms"]); ftype = lst[0] if lst else None
    if ftype and ftype != key: await c.answer("❌ Только твой тип!", show_alert=True); return
    f = FARMS[key]
    await state.update_data(farm_key=key); await state.set_state(St.farm_buy_qty)
    await c.message.edit_text(f"➕ {f['name']}\n\n💵 {fmt_short(f['price'])}$\n💰 {fmt_full(u['balance'])}$\n\nСколько?")

@dp.message(St.farm_buy_qty)
async def cb_buy_farm_qty(m: Message, state: FSMContext):
    try: qty = int(m.text.strip())
    except: await m.answer("❌ Число"); return
    if qty <= 0: await m.answer("❌ > 0"); return
    data = await state.get_data(); key = data["farm_key"]; f = FARMS[key]
    u = await db.get_user(m.from_user.id)
    lst = parse_list(u["farms"]); ftype = lst[0] if lst else None; fcount = len(lst)
    if ftype and ftype != key: await m.answer("❌ Только твой!"); await state.clear(); return
    if fcount + qty > FARMS_LIMIT: await m.answer("❌ Много"); await state.clear(); return
    total = f["price"] * qty
    if u["balance"] < total: await m.answer(f"❌ Нужно {fmt_full(total)}$"); await state.clear(); return
    await db.add_balance(m.from_user.id, -total)
    lst = lst + [key] * qty
    await db.update(m.from_user.id, farms=serialize_list(lst))
    await state.clear()
    await m.answer(f"✅ {qty} × {f['name']} за {fmt_full(total)}$")
    await show_farms(m.from_user.id, m, False)

@dp.callback_query(F.data == "farm_buy_menu")
async def cb_farm_buy_menu(c: CallbackQuery, state: FSMContext):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    u = await db.get_user(c.from_user.id)
    lst = parse_list(u["farms"]); ftype = lst[0] if lst else None
    if not ftype: await c.answer("Купи тип!", show_alert=True); return
    f = FARMS[ftype]
    await state.update_data(farm_key=ftype); await state.set_state(St.farm_buy_qty)
    await c.message.edit_text(f"➕ {f['name']}\n\n💵 {fmt_short(f['price'])}$\n💰 {fmt_full(u['balance'])}$\n\nСколько?")

@dp.callback_query(F.data == "farm_sell_menu")
async def cb_farm_sell_menu(c: CallbackQuery, state: FSMContext):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    u = await db.get_user(c.from_user.id)
    lst = parse_list(u["farms"]); ftype = lst[0] if lst else None; fcount = len(lst)
    if not ftype or fcount == 0: await c.answer("Нет", show_alert=True); return
    f = FARMS[ftype]; sp = int(f["price"] * (1 - SELL_PERCENT))
    await state.set_state(St.farm_sell_qty)
    await c.message.edit_text(f"➖ {f['name']}\n\n💵 {fmt_short(sp)}$ (-5%)\n⛏️ Есть: {fcount}\n\nСколько?")

@dp.message(St.farm_sell_qty)
async def cb_sell_farm_qty(m: Message, state: FSMContext):
    try: qty = int(m.text.strip())
    except: await m.answer("❌ Число"); return
    if qty <= 0: await m.answer("❌ > 0"); return
    u = await db.get_user(m.from_user.id)
    lst = parse_list(u["farms"]); ftype = lst[0] if lst else None; fcount = len(lst)
    if not ftype or fcount == 0: await m.answer("❌ Нет"); await state.clear(); return
    if qty > fcount: await m.answer(f"❌ Только {fcount}"); await state.clear(); return
    await process_farms(m.from_user.id); u = await db.get_user(m.from_user.id)
    f = FARMS[ftype]; total = int(f["price"] * (1 - SELL_PERCENT)) * qty
    await db.add_balance(m.from_user.id, total)
    lst = parse_list(u["farms"])
    for _ in range(qty):
        if lst: lst.pop()
    await db.update(m.from_user.id, farms=serialize_list(lst))
    await state.clear()
    await m.answer(f"✅ {qty} × {f['name']} за {fmt_full(total)}$")
    await show_farms(m.from_user.id, m, False)

@dp.callback_query(F.data == "farms_withdraw")
async def cb_farms_withdraw(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    await process_farms(c.from_user.id)
    u = await db.get_user(c.from_user.id)
    if u["btc"] < 0.01:
        await c.answer("Нечего снимать (минимум 0.01₿)", show_alert=True); return
    amount = u["btc"]
    await db.update(c.from_user.id, btc=0, btc_wallet=(u.get("btc_wallet",0) + amount))
    await c.answer(f"✅ Снято {fmt_btc(amount)}₿ в кошелёк", show_alert=True)
    await show_farms(c.from_user.id, c, True)

@dp.callback_query(F.data == "farms_sellbtc")
async def cb_farms_sellbtc(c: CallbackQuery, state: FSMContext):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    u = await db.get_user(c.from_user.id)
    if u.get("btc_wallet", 0) < 0.01:
        await c.answer("В кошельке мало BTC. Сними с ферм.", show_alert=True); return
    await state.set_state(St.sell_btc)
    await c.message.edit_text(
        f"₿ В кошельке: {fmt_btc(u['btc_wallet'])}₿\n"
        f"Курс: {fmt_full(BTC_CURRENT)}$\n\nСколько продать?")

@dp.message(St.sell_btc)
async def cb_sell_btc_amount(m: Message, state: FSMContext):
    try: amount = float(m.text.strip().replace(",", "."))
    except: await m.answer("❌ Число"); return
    u = await db.get_user(m.from_user.id)
    if amount <= 0 or amount > u.get("btc_wallet", 0):
        await m.answer("❌ Неверное"); return
    money = int(amount * BTC_CURRENT)
    await db.update(m.from_user.id, btc_wallet=u["btc_wallet"] - amount)
    await db.add_balance(m.from_user.id, money); await state.clear()
    await m.answer(f"✅ {amount:.2f}₿ → {fmt_full(money)}$")
    await show_farms(m.from_user.id, m, False)

# ============ ДОМА ============
async def show_houses(uid, m_or_c, is_cb=False):
    ban = await check_banned(uid)
    if ban:
        if is_cb: await m_or_c.answer(ban, show_alert=True)
        else: await m_or_c.answer(ban)
        return
    await db.touch_active(uid)
    u = await db.get_user(uid)
    houses = parse_list(u["houses"])
    if houses:
        hid = houses[0]; h = HOUSES[hid]
        text = f"🏠 <b>Твой дом</b>\n\n{h['name']}\n\n💰 {fmt_full(u['balance'])}$"
        kb = houses_kb(True, hid, bool(u["garage_bought"]))
    else:
        lines = [f"🏠 {u['nick']}, приобрети НЕДВИЖИМОСТЬ!", ""]
        for i, (key, h) in enumerate(HOUSES.items(), 1):
            lines.append(f"{i}. {h['name']} — {fmt_short(h['price'])}$")
        lines.append(""); lines.append(f"💳 Баланс: {fmt_full(u['balance'])}$")
        text = "\n".join(lines); kb = houses_kb(False, None, False)
    if is_cb:
        await m_or_c.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await m_or_c.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "houses")
async def cb_houses(c: CallbackQuery):
    await show_houses(c.from_user.id, c, True)

@dp.callback_query(F.data.startswith("buyhouse_"))
async def cb_buy_house(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    key = c.data.split("_")[1]
    if key not in HOUSES: return
    h = HOUSES[key]; u = await db.get_user(c.from_user.id)
    if parse_list(u["houses"]): await c.answer("Уже есть!", show_alert=True); return
    if u["balance"] < h["price"]: await c.answer("❌ Мало!", show_alert=True); return
    await db.add_balance(c.from_user.id, -h["price"])
    await db.update(c.from_user.id, houses=key, garage_bought=0, garage="")
    await c.answer(f"✅ {h['name']}!", show_alert=True); await show_houses(c.from_user.id, c, True)

@dp.callback_query(F.data.startswith("sellhouse_"))
async def cb_sell_house(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    key = c.data.split("_")[1]
    if key not in HOUSES: return
    u = await db.get_user(c.from_user.id)
    if key not in parse_list(u["houses"]): await c.answer("Нет", show_alert=True); return
    sell = int(HOUSES[key]["price"] * SELL_PERCENT)
    await db.add_balance(c.from_user.id, sell)
    await db.update(c.from_user.id, houses="", garage_bought=0, garage="")
    await c.answer(f"💸 +{fmt_full(sell)}$", show_alert=True); await show_houses(c.from_user.id, c, True)

# ============ ГАРАЖ ============
@dp.callback_query(F.data == "garage")
async def cb_garage(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    u = await db.get_user(c.from_user.id)
    if not parse_list(u["houses"]): await c.answer("Купи дом!", show_alert=True); return
    if not u["garage_bought"]: await c.answer("Купи гараж!", show_alert=True); return
    cars = parse_list(u["garage"])
    if cars:
        text = f"🚗 <b>Гараж</b>\n\nМашина: <b>{CARS[cars[0]]['name']}</b>\n\n💰 {fmt_full(u['balance'])}$"
    else:
        lines = [f"🚗 {u['nick']}, выбери машину:", ""]
        for key, c_info in CARS.items():
            lines.append(f"{c_info['name']} — {fmt_short(c_info['price'])}$")
        lines.append(""); lines.append(f"💰 {fmt_full(u['balance'])}$")
        text = "\n".join(lines)
    await c.message.edit_text(text, reply_markup=garage_kb(cars), parse_mode="HTML")

@dp.callback_query(F.data == "buygarage")
async def cb_buy_garage(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    u = await db.get_user(c.from_user.id)
    if u["garage_bought"]: await c.answer("Уже!", show_alert=True); return
    houses = parse_list(u["houses"])
    if not houses: await c.answer("Купи дом!", show_alert=True); return
    price = int(HOUSES[houses[0]]["price"] * GARAGE_PERCENT)
    if u["balance"] < price: await c.answer(f"❌ {fmt_short(price)}$", show_alert=True); return
    await db.add_balance(c.from_user.id, -price)
    await db.update(c.from_user.id, garage_bought=1)
    await c.answer(f"✅ Гараж за {fmt_short(price)}$", show_alert=True); await show_houses(c.from_user.id, c, True)

@dp.callback_query(F.data.startswith("buycar_"))
async def cb_buy_car(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    key = c.data.split("_")[1]
    if key not in CARS: return
    car = CARS[key]; u = await db.get_user(c.from_user.id)
    if not u["garage_bought"]: await c.answer("Купи гараж!", show_alert=True); return
    if parse_list(u["garage"]): await c.answer("Уже есть!", show_alert=True); return
    if u["balance"] < car["price"]: await c.answer("❌ Мало!", show_alert=True); return
    await db.add_balance(c.from_user.id, -car["price"])
    await db.update(c.from_user.id, garage=key)
    await c.answer(f"✅ {car['name']}!", show_alert=True); await cb_garage(c)

@dp.callback_query(F.data.startswith("sellcar_"))
async def cb_sell_car(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    key = c.data.split("_")[1]
    if key not in CARS: return
    u = await db.get_user(c.from_user.id); cars = parse_list(u["garage"])
    if not cars or cars[0] != key: await c.answer("Нет", show_alert=True); return
    sell = int(CARS[key]["price"] * SELL_PERCENT)
    await db.add_balance(c.from_user.id, sell)
    await db.update(c.from_user.id, garage="")
    await c.answer(f"💸 {fmt_full(sell)}$", show_alert=True); await cb_garage(c)

# ============ ШКАФ ============
@dp.callback_query(F.data == "wardrobe")
async def cb_wardrobe(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    u = await db.get_user(c.from_user.id)
    if not parse_list(u["houses"]): await c.answer("Купи дом!", show_alert=True); return
    await c.message.edit_text(f"👔 <b>Шкаф</b>\n\n💰 {fmt_full(u['balance'])}$",
        reply_markup=wardrobe_kb(parse_list(u["wardrobe"]), parse_list(u["clothes_worn"])), parse_mode="HTML")

@dp.callback_query(F.data.startswith("wear_"))
async def cb_wear(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    key = c.data.split("_")[1]
    if key not in SKINS: return
    u = await db.get_user(c.from_user.id); worn = parse_list(u["clothes_worn"])
    if key in worn: worn.remove(key); await c.answer("Снято", show_alert=True)
    else: worn = [key]; await c.answer("Надето!", show_alert=True)
    await db.update(c.from_user.id, clothes_worn=serialize_list(worn)); await cb_wardrobe(c)

# ============ МАГАЗИН ============
async def show_shop(uid, m_or_c, is_cb=False):
    ban = await check_banned(uid)
    if ban:
        if is_cb: await m_or_c.answer(ban, show_alert=True)
        else: await m_or_c.answer(ban)
        return
    await db.touch_active(uid)
    u = await db.get_user(uid)
    lines = [f"🛒 Магазин скинов", "", f"💰 {fmt_full(u['balance'])}$", ""]
    for i, (key, skin) in enumerate(SKINS.items(), 1):
        lines.append(f"{i}. {skin['name']} — {fmt_short(skin['price'])}$")
    lines.append(""); lines.append("Выбери:")
    text = "\n".join(lines); kb = shop_kb(parse_list(u["wardrobe"]))
    if is_cb:
        await m_or_c.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await m_or_c.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "shop")
async def cb_shop(c: CallbackQuery):
    await show_shop(c.from_user.id, c, True)

@dp.callback_query(F.data.startswith("buyskin_"))
async def cb_buy_skin(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    key = c.data.split("_")[1]
    if key not in SKINS: return
    skin = SKINS[key]; u = await db.get_user(c.from_user.id); owned = parse_list(u["wardrobe"])
    if key in owned: await c.answer("Уже!", show_alert=True); return
    if u["balance"] < skin["price"]: await c.answer("❌ Мало!", show_alert=True); return
    await db.add_balance(c.from_user.id, -skin["price"]); owned.append(key)
    await db.update(c.from_user.id, wardrobe=serialize_list(owned))
    await c.answer(f"✅ {skin['name']}!", show_alert=True); await show_shop(c.from_user.id, c, True)

# ============ НАГРАДЫ ============
@dp.callback_query(F.data == "rewards")
async def cb_rewards(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    await db.touch_active(c.from_user.id)
    await c.message.edit_text(
        "🎁 <b>Награды</b>\n\n🎁 Бонус — 5% от баланса (мин 50.000, макс 1 млрд) каждые 12ч\n🎟 Промокод",
        reply_markup=rewards_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "bonus")
async def cb_bonus(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    u = await db.get_user(c.from_user.id); now = int(time.time()); diff = now - u["last_bonus"]
    if diff < BONUS_COOLDOWN:
        left = BONUS_COOLDOWN - diff
        await c.answer(f"⏰ {left//3600}ч {(left%3600)//60}м", show_alert=True); return
    b = int(u["balance"] * BONUS_PERCENT)
    if b < BONUS_MIN: b = BONUS_MIN
    if b > BONUS_MAX: b = BONUS_MAX
    await db.add_balance(c.from_user.id, b)
    await db.update(c.from_user.id, last_bonus=now)
    await c.answer(f"🎁 +{fmt_full(b)}$!", show_alert=True)

@dp.callback_query(F.data == "enter_promo")
async def cb_enter_promo(c: CallbackQuery, state: FSMContext):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    await state.set_state(St.promo_enter); await c.message.edit_text("🎟 Введи промокод:")

@dp.message(St.promo_enter)
async def cb_promo_submit(m: Message, state: FSMContext):
    code = m.text.strip().upper(); p = await db.get_promo(code)
    if not p: await m.answer("❌ Не найден"); await state.clear(); return
    if not p.get("active", 1): await m.answer("❌ Неактивен"); await state.clear(); return
    if p["used"] >= p["limit_total"]: await m.answer("❌ Исчерпан"); await state.clear(); return
    if await db.user_used_promo(code, m.from_user.id): await m.answer("❌ Уже активирован"); await state.clear(); return
    if p["amount"] > 0:
        await db.add_balance(m.from_user.id, p["amount"])
    if p.get("vip_level"):
        await db.update(m.from_user.id, is_vip=1, vip_level=p["vip_level"])
    await db.use_promo(code, m.from_user.id)
    await state.clear()
    extra = f"\n⭐ VIP: {p['vip_level']}" if p.get("vip_level") else ""
    amt = f"+{fmt_full(p['amount'])}$" if p["amount"] > 0 else ""
    await m.answer(f"🎉 {amt}{extra}".strip())

# ============ БАНК ============
@dp.callback_query(F.data == "bank")
async def cb_bank(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    await db.touch_active(c.from_user.id)
    u = await db.get_user(c.from_user.id)
    has_dep = u["deposit_amount"] > 0
    ready = has_dep and u["deposit_end"] <= time.time()
    lines = [f"🏦 <b>БАНК</b>", ""]
    lines.append(f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>")
    lines.append(f"🏦 Счёт: <b>{fmt_full(u['bank_wallet'])}$</b>")
    if has_dep:
        profit = int(u["deposit_amount"] * u["deposit_rate"])
        lines.append(""); lines.append(f"📈 Вклад: <b>{fmt_full(u['deposit_amount'])}$</b>")
        lines.append(f"💵 Доход: <b>+{fmt_full(profit)}$</b>")
        if ready: lines.append(f"✅ <b>Готов!</b>")
        else: lines.append(f"📅 До: <b>{datetime.fromtimestamp(u['deposit_end']).strftime('%d.%m.%Y')}</b>")
    lines.append(""); lines.append("💸 Комиссия снятия: 3%")
    await c.message.edit_text("\n".join(lines), reply_markup=bank_kb(has_dep, ready), parse_mode="HTML")

@dp.callback_query(F.data == "bank_dep_in")
async def cb_bank_in(c: CallbackQuery, state: FSMContext):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    await state.set_state(St.bank_in); await c.message.edit_text("💵 Введи сумму:")

@dp.message(St.bank_in)
async def cb_bank_in_amount(m: Message, state: FSMContext):
    amount = parse_amount(m.text)
    if not amount or amount <= 0: await m.answer("❌ Сумма"); return
    if amount > MAX_AMOUNT: await m.answer(f"❌ Макс {fmt_full(MAX_AMOUNT)}$"); return
    u = await db.get_user(m.from_user.id)
    if u["balance"] < amount: await m.answer("❌ Мало"); await state.clear(); return
    await db.add_balance(m.from_user.id, -amount)
    await db.update(m.from_user.id, bank_wallet=u["bank_wallet"] + amount)
    await state.clear(); await m.answer(f"✅ +{fmt_full(amount)}$")

@dp.callback_query(F.data == "bank_dep_out")
async def cb_bank_out(c: CallbackQuery, state: FSMContext):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    u = await db.get_user(c.from_user.id)
    fee_pct = 0 if (u.get("is_vip") and u.get("vip_level") == "ADMIN") else int(WITHDRAW_FEE*100)
    await state.set_state(St.bank_out)
    await c.message.edit_text(f"💸 Сумма для снятия (комиссия {fee_pct}%):")

@dp.message(St.bank_out)
async def cb_bank_out_amount(m: Message, state: FSMContext):
    amount = parse_amount(m.text)
    if not amount or amount <= 0: await m.answer("❌ Сумма"); return
    if amount > MAX_AMOUNT: await m.answer(f"❌ Макс"); return
    u = await db.get_user(m.from_user.id)
    if u["bank_wallet"] < amount: await m.answer("❌ Мало"); await state.clear(); return
    fee_rate = 0 if (u.get("is_vip") and u.get("vip_level") == "ADMIN") else WITHDRAW_FEE
    fee = int(amount * fee_rate); net = amount - fee
    await db.update(m.from_user.id, bank_wallet=u["bank_wallet"] - amount)
    await db.add_balance(m.from_user.id, net); await state.clear()
    await m.answer(f"✅ {fmt_full(amount)}$\n💸 {fmt_full(fee)}$\n💰 {fmt_full(net)}$")

@dp.callback_query(F.data == "bank_open")
async def cb_bank_open(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    u = await db.get_user(c.from_user.id)
    if u["deposit_amount"] > 0: await c.answer("❌ Уже есть вклад", show_alert=True); return
    await c.message.edit_text("📈 <b>Вклады</b>\n\n• 1 день — +1%\n• 7 дней — +10%\n• 30 дней — +35%",
        reply_markup=deposits_kb(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("dep_"))
async def cb_dep(c: CallbackQuery, state: FSMContext):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    key = c.data.split("_")[1]
    if key not in DEPOSITS: return
    u = await db.get_user(c.from_user.id)
    if u["deposit_amount"] > 0: await c.answer("❌ Уже есть", show_alert=True); return
    d = DEPOSITS[key]; await state.update_data(dep_key=key); await state.set_state(St.dep_amount)
    await c.message.edit_text(f"{d['name']} — +{int(d['rate']*100)}%\n\n💰 Счёт: {fmt_full(u['bank_wallet'])}$\n\nСумма?")

@dp.message(St.dep_amount)
async def cb_dep_amount(m: Message, state: FSMContext):
    amount = parse_amount(m.text)
    if not amount or amount < 100: await m.answer("❌ Мин 100$"); return
    data = await state.get_data(); d = DEPOSITS[data["dep_key"]]
    u = await db.get_user(m.from_user.id)
    if u["bank_wallet"] < amount: await m.answer("❌ Мало"); await state.clear(); return
    await db.update(m.from_user.id, bank_wallet=u["bank_wallet"] - amount, deposit_amount=amount,
        deposit_end=int(time.time()) + d["seconds"], deposit_rate=d["rate"])
    await state.clear()
    await m.answer(f"✅ {fmt_full(amount)}$\n💵 +{fmt_full(int(amount*d['rate']))}$")

@dp.callback_query(F.data == "bank_view")
async def cb_bank_view(c: CallbackQuery):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    u = await db.get_user(c.from_user.id)
    if u["deposit_amount"] == 0: await c.answer("Нет вклада", show_alert=True); return
    left = int(u["deposit_end"] - time.time())
    if left > 0:
        d = left // 86400; h = (left % 86400) // 3600
        await c.answer(f"⏳ {d}д {h}ч", show_alert=True); return
    total = int(u["deposit_amount"] * (1 + u["deposit_rate"]))
    await db.add_balance(c.from_user.id, total)
    await db.update(c.from_user.id, deposit_amount=0, deposit_end=0, deposit_rate=0)
    await c.answer(f"✅ +{fmt_full(total)}$", show_alert=True); await cb_bank(c)

# ============ КАЗИНО ============
@dp.callback_query(F.data == "casino")
async def cb_casino(c: CallbackQuery, state: FSMContext):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    await db.touch_active(c.from_user.id)
    await process_farms(c.from_user.id)
    await state.clear()
    await c.message.edit_text(
        "🎰 <b>Казино</b>\n\n"
        "🎯 Рулетка — угадай цвет/число (x2–x30)\n"
        "🃏 Блэкджек — набери 21 (x2)\n"
        "🎲 Кости — угадай число (x2–x5)\n\nВыбери:",
        reply_markup=casino_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "rl_info")
async def cb_rl_info(c: CallbackQuery):
    await c.message.edit_text(
        "🎯 <b>Рулетка</b>\n\n🎯 0-36\n🔴 Красное x2 | ⚫ Чёрное x2 | 🟢 Зеро x30\nЧёт x2 | Нечет x2\n1-12 x3 | 13-24 x3 | 25-36 x3\n\nВведи ставку:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Играть", callback_data="rl_start")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="casino")]]),
        parse_mode="HTML")

@dp.callback_query(F.data == "bj_info")
async def cb_bj_info(c: CallbackQuery):
    await c.message.edit_text(
        "🃏 <b>Блэкджек</b>\n\nЦель — 21, не перебрать.\nБлэкджек → x2.5\nПобеда → x2\nНичья → возврат\n\nВведи ставку:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Играть", callback_data="bj_start")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="casino")]]),
        parse_mode="HTML")

@dp.callback_query(F.data == "dice_info")
async def cb_dice_info(c: CallbackQuery):
    await c.message.edit_text(
        "🎲 <b>Кости</b>\n\nЧисло (1-6) → x5\nМеньше (1-3) → x2\nБольше (4-6) → x2\n\nВведи ставку:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Играть", callback_data="dice_start")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="casino")]]),
        parse_mode="HTML")

@dp.callback_query(F.data == "bj_start")
async def cb_bj_start(c: CallbackQuery, state: FSMContext):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    await state.set_state(St.bj_bet)
    await c.message.edit_text(f"🃏 Блэкджек\n\nМин: 1.000$ | Макс: {fmt_full(MAX_AMOUNT)}$\n\nСтавка:")

@dp.message(St.bj_bet)
async def cb_bj_bet(m: Message, state: FSMContext):
    bet = parse_amount(m.text)
    if not bet or bet < MIN_BET: await m.answer("❌ Мин. 1.000$"); return
    if bet > MAX_AMOUNT: await m.answer(f"❌ Макс {fmt_full(MAX_AMOUNT)}$"); return
    u = await db.get_user(m.from_user.id)
    if u["balance"] < bet: await m.answer("❌ Мало"); await state.clear(); return
    await db.add_balance(m.from_user.id, -bet)
    deck = new_deck(); random.shuffle(deck)
    player = [deck.pop(), deck.pop()]; dealer = [deck.pop(), deck.pop()]
    await state.set_state(St.bj_play)
    await state.update_data(bet=bet, player=player, dealer=dealer, deck=deck, doubled=False, luck=u.get("luck", 50))
    pv = hand_value(player)
    if is_blackjack(player):
        if is_blackjack(dealer):
            await db.add_balance(m.from_user.id, bet); await state.clear()
            await m.answer("🃏 Блэкджек у обоих — ничья", reply_markup=casino_kb()); return
        win = int(bet * 2.5); await db.add_balance(m.from_user.id, win)
        await db.update(m.from_user.id, wins=u["wins"]+1); await state.clear()
        await m.answer(f"🎉 БЛЭКДЖЕК! +{fmt_full(win-bet)}$", reply_markup=casino_kb(), parse_mode="HTML"); return
    await m.answer(f"🃏 {fmt_full(bet)}$\n\n👤 {fmt_hand(player)} = <b>{pv}</b>\n🤖 {dealer[0]} ?",
        reply_markup=bj_kb(), parse_mode="HTML")

@dp.callback_query(St.bj_play, F.data == "bj_hit")
async def cb_bj_hit(c: CallbackQuery, state: FSMContext):
    data = await state.get_data(); data["player"].append(data["deck"].pop())
    pv = hand_value(data["player"])
    if pv > 21:
        u = await db.get_user(c.from_user.id)
        await db.update(c.from_user.id, losses=u["losses"]+1); await state.clear()
        await c.message.edit_text(f"💥 Перебор!\n👤 {fmt_hand(data['player'])} = {pv}\n❌ -{fmt_full(data['bet'])}$",
            reply_markup=casino_kb(), parse_mode="HTML"); return
    await state.update_data(**data)
    await c.message.edit_text(
        f"👤 {fmt_hand(data['player'])} = <b>{pv}</b>\n🤖 {data['dealer'][0]} ?\n💰 {fmt_full(data['bet'])}$",
        reply_markup=bj_kb(), parse_mode="HTML")

@dp.callback_query(St.bj_play, F.data == "bj_stand")
async def cb_bj_stand(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await c.message.edit_text("🤖 <b>Дилер думает...</b>")
    await asyncio.sleep(2); await finish_bj(c, state, data)

@dp.callback_query(St.bj_play, F.data == "bj_double")
async def cb_bj_double(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if len(data["player"]) != 2 or data["doubled"]:
        await c.answer("Только в начале", show_alert=True); return
    u = await db.get_user(c.from_user.id)
    if u["balance"] < data["bet"]: await c.answer("Мало", show_alert=True); return
    await db.add_balance(c.from_user.id, -data["bet"])
    data["bet"] *= 2; data["doubled"] = True
    data["player"].append(data["deck"].pop()); await state.update_data(**data)
    if hand_value(data["player"]) > 21:
        await db.update(c.from_user.id, losses=u["losses"]+1); await state.clear()
        await c.message.edit_text(f"💥 Перебор! -{fmt_full(data['bet'])}$", reply_markup=casino_kb(), parse_mode="HTML"); return
    await c.message.edit_text("🤖 <b>Дилер думает...</b>")
    await asyncio.sleep(2); await finish_bj(c, state, data)

async def finish_bj(c, state, data):
    data["dealer"] = dealer_play(data["dealer"], data["deck"])
    pv, dv, bet = hand_value(data["player"]), hand_value(data["dealer"]), data["bet"]
    luck = data.get("luck", 50)
    u = await db.get_user(c.from_user.id)
    if pv == dv:
        if luck > 50 and random.random() < (luck - 50) / 50.0:
            await db.add_balance(c.from_user.id, bet * 2)
            await db.update(c.from_user.id, wins=u["wins"]+1)
            table = f"👤 {fmt_hand(data['player'])} = {pv}\n🤖 {fmt_hand(data['dealer'])} = {dv}\n\n"
            await state.clear()
            await c.message.edit_text(table + f"🎉 +{fmt_full(bet)}$", reply_markup=casino_kb(), parse_mode="HTML")
            return
        await db.add_balance(c.from_user.id, bet)
        text = f"👤 {fmt_hand(data['player'])} = {pv}\n🤖 {fmt_hand(data['dealer'])} = {dv}\n\n🤝 Ничья"
        await state.clear()
        await c.message.edit_text(text, reply_markup=casino_kb(), parse_mode="HTML")
        return
    raw_win = (dv > 21 or pv > dv)
    final_win = apply_luck(raw_win, luck)
    table = f"👤 {fmt_hand(data['player'])} = {pv}\n🤖 {fmt_hand(data['dealer'])} = {dv}\n\n"
    if final_win:
        await db.add_balance(c.from_user.id, bet * 2)
        await db.update(c.from_user.id, wins=u["wins"]+1)
        text = table + f"🎉 +{fmt_full(bet)}$"
    else:
        await db.update(c.from_user.id, losses=u["losses"]+1)
        text = table + f"❌ -{fmt_full(bet)}$"
    await state.clear()
    await c.message.edit_text(text, reply_markup=casino_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "rl_start")
async def cb_rl_start(c: CallbackQuery, state: FSMContext):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    await state.set_state(St.rl_bet)
    await c.message.edit_text(f"🎯 Рулетка\n\nМин: 1.000$ | Макс: {fmt_full(MAX_AMOUNT)}$\n\nСтавка:")

@dp.message(St.rl_bet)
async def cb_rl_bet(m: Message, state: FSMContext):
    bet = parse_amount(m.text)
    if not bet or bet < MIN_BET: await m.answer("❌ Мин. 1.000$"); return
    if bet > MAX_AMOUNT: await m.answer(f"❌ Макс {fmt_full(MAX_AMOUNT)}$"); return
    u = await db.get_user(m.from_user.id)
    if u["balance"] < bet: await m.answer("❌ Мало"); await state.clear(); return
    await db.add_balance(m.from_user.id, -bet)
    await state.update_data(bet=bet, luck=u.get("luck", 50))
    await m.answer(f"🎯 {fmt_full(bet)}$", reply_markup=rl_choice_kb())

@dp.callback_query(St.rl_bet, F.data.startswith("rl_"))
async def cb_rl_result(c: CallbackQuery, state: FSMContext):
    if c.data in ("rl_start", "rl_info"): return
    choice = c.data.split("_")[1]; data = await state.get_data(); bet = data["bet"]; luck = data.get("luck", 50); await state.clear()
    num = random.randint(0, 36)
    color = "green" if num == 0 else ("red" if num in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36] else "black")
    win, mult = False, 0
    if choice == "red" and color == "red": win, mult = True, 2
    elif choice == "black" and color == "black": win, mult = True, 2
    elif choice == "green" and color == "green": win, mult = True, 30
    elif choice == "even" and num != 0 and num % 2 == 0: win, mult = True, 2
    elif choice == "odd" and num != 0 and num % 2 == 1: win, mult = True, 2
    elif choice == "low" and 1 <= num <= 12: win, mult = True, 3
    elif choice == "mid" and 13 <= num <= 24: win, mult = True, 3
    elif choice == "high" and 25 <= num <= 36: win, mult = True, 3
    final_win = apply_luck(win, luck)
    u = await db.get_user(c.from_user.id); emoji = {"red": "🔴", "black": "⚫", "green": "🟢"}[color]
    if final_win:
        payout = bet * mult
        await db.add_balance(c.from_user.id, payout)
        await db.update(c.from_user.id, wins=u["wins"]+1)
        text = f"🎯 {emoji} <b>{num}</b>\n\n✅ +{fmt_full(payout - bet)}$ (x{mult})"
    else:
        await db.update(c.from_user.id, losses=u["losses"]+1)
        text = f"🎯 {emoji} <b>{num}</b>\n\n❌ -{fmt_full(bet)}$"
    await c.message.edit_text(text, reply_markup=casino_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "dice_start")
async def cb_dice_start(c: CallbackQuery, state: FSMContext):
    ban = await check_banned(c.from_user.id)
    if ban: await c.answer(ban, show_alert=True); return
    await state.set_state(St.dice_bet)
    await c.message.edit_text(f"🎲 Кости\n\nМин: 1.000$ | Макс: {fmt_full(MAX_AMOUNT)}$\n\nСтавка:")

@dp.message(St.dice_bet)
async def cb_dice_bet(m: Message, state: FSMContext):
    bet = parse_amount(m.text)
    if not bet or bet < MIN_BET: await m.answer("❌ Мин. 1.000$"); return
    if bet > MAX_AMOUNT: await m.answer(f"❌ Макс {fmt_full(MAX_AMOUNT)}$"); return
    u = await db.get_user(m.from_user.id)
    if u["balance"] < bet: await m.answer("❌ Мало"); await state.clear(); return
    await db.add_balance(m.from_user.id, -bet)
    await state.update_data(bet=bet, luck=u.get("luck", 50))
    await m.answer(f"🎲 {fmt_full(bet)}$\nВыбери:", reply_markup=dice_choice_kb())

@dp.callback_query(St.dice_bet, F.data.startswith("dice_"))
async def cb_dice_result(c: CallbackQuery, state: FSMContext):
    if c.data == "dice_start": return
    choice = c.data.split("_")[1]; data = await state.get_data(); bet = data["bet"]; luck = data.get("luck", 50); await state.clear()
    roll = random.randint(1, 6); u = await db.get_user(c.from_user.id); win, mult = False, 0
    if choice.isdigit():
        if int(choice) == roll: win, mult = True, 5
    elif choice == "low" and roll in [1,2,3]: win, mult = True, 2
    elif choice == "high" and roll in [4,5,6]: win, mult = True, 2
    final_win = apply_luck(win, luck)
    if final_win:
        payout = bet * mult
        await db.add_balance(c.from_user.id, payout)
        await db.update(c.from_user.id, wins=u["wins"]+1)
        text = f"🎲 <b>{roll}</b>\n\n🎉 +{fmt_full(payout - bet)}$ (x{mult})"
    else:
        await db.update(c.from_user.id, losses=u["losses"]+1)
        text = f"🎲 <b>{roll}</b>\n\n❌ -{fmt_full(bet)}$"
    await c.message.edit_text(text, reply_markup=casino_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "noop")
async def cb_noop(c: CallbackQuery): await c.answer()

# ============ АДМИНКА ============
async def show_admin_panel(uid, m_or_c, is_cb=True):
    u = await db.get_user(uid)
    if not is_admin_any(u):
        if is_cb: await m_or_c.answer("Только админ", show_alert=True)
        else: await m_or_c.answer("Только админ")
        return
    rows = []
    if is_main_admin(uid):
        rows = admin_main_kb().inline_keyboard
    else:
        p = (u.get("admin_perms") or "").split(",")
        if "money" in p: rows.append([InlineKeyboardButton(text="💰 Деньги", callback_data="adm_money_menu")])
        if "btc" in p: rows.append([InlineKeyboardButton(text="₿ BTC", callback_data="adm_btc_menu")])
        if "prop" in p: rows.append([InlineKeyboardButton(text="🏢 Имущество", callback_data="adm_prop_menu")])
        if "ban" in p: rows.append([InlineKeyboardButton(text="🚫 Блокировка", callback_data="adm_ban_menu")])
        if "stats" in p: rows.append([InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")])
        if "promo" in p: rows.append([InlineKeyboardButton(text="🎟 Промокоды", callback_data="adm_promo_menu")])
        if "view" in p: rows.append([InlineKeyboardButton(text="👤 Профиль", callback_data="adm_view_profile")])
        if "admins" in p: rows.append([InlineKeyboardButton(text="👑 Выдать админку", callback_data="adm_give_admin")])
        if "luck" in p: rows.append([InlineKeyboardButton(text="🍀 Удача", callback_data="adm_luck_menu")])
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="profile")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    text = "👑 <b>Админ-панель</b>"
    if is_cb:
        await m_or_c.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await m_or_c.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(c: CallbackQuery):
    await show_admin_panel(c.from_user.id, c, True)

async def check_admin_perm(c, perm):
    if is_main_admin(c.from_user.id): return True
    u = await db.get_user(c.from_user.id)
    if not has_perm(u, perm):
        await c.answer("❌ Нет прав", show_alert=True); return False
    return True

@dp.callback_query(F.data == "adm_money_menu")
async def cb_adm_money_menu(c: CallbackQuery):
    if not await check_admin_perm(c, "money"): return
    await c.message.edit_text("💰 <b>Деньги</b>", reply_markup=admin_money_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_btc_menu")
async def cb_adm_btc_menu(c: CallbackQuery):
    if not await check_admin_perm(c, "btc"): return
    await c.message.edit_text(f"₿ <b>BTC</b>\nКурс: {fmt_full(BTC_CURRENT)}$", reply_markup=admin_btc_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_prop_menu")
async def cb_adm_prop_menu(c: CallbackQuery):
    if not await check_admin_perm(c, "prop"): return
    await c.message.edit_text("🏢 <b>Имущество</b>", reply_markup=admin_prop_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_ban_menu")
async def cb_adm_ban_menu(c: CallbackQuery):
    if not await check_admin_perm(c, "ban"): return
    await c.message.edit_text("🚫 <b>Блокировка</b>", reply_markup=admin_ban_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_global_menu")
async def cb_adm_global_menu(c: CallbackQuery):
    if not is_main_admin(c.from_user.id):
        await c.answer("Только главный", show_alert=True); return
    await c.message.edit_text("⚙️ <b>Глобальные</b>", reply_markup=admin_global_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_promo_menu")
async def cb_adm_promo_menu(c: CallbackQuery):
    if not await check_admin_perm(c, "promo"): return
    await c.message.edit_text("🎟 <b>Промокоды</b>", reply_markup=admin_promo_menu_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_give_vip")
async def cb_adm_give_vip(c: CallbackQuery):
    if not is_main_admin(c.from_user.id): await c.answer("Только главный", show_alert=True); return
    await c.message.edit_text("⭐ <b>VIP</b>", reply_markup=admin_vip_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_luck_menu")
async def cb_adm_luck_menu(c: CallbackQuery):
    if not await check_admin_perm(c, "luck"): return
    await c.message.edit_text("🍀 <b>Удача</b>", reply_markup=admin_luck_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "adm_stats")
async def cb_adm_stats(c: CallbackQuery):
    if not await check_admin_perm(c, "stats"): return
    total = await db.count_all(); banned = await db.count_banned()
    online = await db.get_online(300)
    lines = [f"📊 <b>Статистика</b>", "", f"👥 Всего: <b>{total}</b>",
             f"🚫 Забанено: <b>{banned}</b>", f"🟢 Онлайн: <b>{len(online)}</b>", ""]
    if online:
        lines.append("🟢 <b>Онлайн:</b>")
        for o in online[:20]:
            lines.append(f"  #{o['game_id']} {o['nick'] or 'Игрок'}")
    await c.message.edit_text("\n".join(lines), reply_markup=back_kb("admin_panel"), parse_mode="HTML")

@dp.callback_query(F.data == "adm_view_profile")
async def cb_adm_view_profile(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "view"): return
    await state.set_state(St.adm_view_profile); await c.message.edit_text("👤 Введи игровой ID:")

@dp.message(St.adm_view_profile)
async def cb_adm_view_profile_do(m: Message, state: FSMContext):
    try: gid = int(m.text.strip())
    except: await m.answer("❌ Число"); return
    u = await db.get_user_by_game_id(gid)
    if not u: await m.answer("❌ Не найден"); await state.clear(); return
    biz = parse_businesses(u["businesses"]); biz = {k:v for k,v in biz.items() if k in BUSINESSES}
    lst = parse_list(u["farms"]); ftype = lst[0] if lst else "—"; fcount = len(lst)
    houses = parse_list(u["houses"]); cars = parse_list(u["garage"])
    ban_status = "✅ Нет"
    if u.get("is_banned"):
        if u.get("ban_until", 0) == 0: ban_status = "🚫 Навсегда"
        elif u["ban_until"] > time.time():
            ban_status = f"🚫 До {datetime.fromtimestamp(u['ban_until']).strftime('%d.%m.%Y')}"
    vip = f"⭐ {u.get('vip_level')}" if u.get("is_vip") else "—"
    luck = u.get("luck", 50)
    lines = [f"👤 <b>Профиль #{u['game_id']}</b>", "",
             f"🎭 {u['nick'] or '—'}", f"🆔 <code>{u['user_id']}</code>",
             f"🚫 Бан: {ban_status}",
             f"👑 Админ: {'✅ ' + (u.get('admin_perms') or '') if u.get('is_admin') else '❌'}",
             f"⭐ VIP: {vip}", f"🍀 Удача: <b>{luck}%</b>", "",
             f"💰 {fmt_full(u['balance'])}$", f"🏦 {fmt_full(u['bank_wallet'])}$",
             f"₿ {fmt_btc(u['btc'])}", f"👛 {fmt_btc(u.get('btc_wallet',0))}",
             f"💼 {list(biz.keys())[0] if biz else '—'}",
             f"⛏ {ftype} ({fcount})", f"🏠 {houses[0] if houses else '—'}",
             f"🚗 {cars[0] if cars else '—'}", f"🎮 {u['wins']}W/{u['losses']}L"]
    await m.answer("\n".join(lines), reply_markup=back_kb("admin_panel"), parse_mode="HTML")
    await state.clear()

# --- Удача ---
@dp.callback_query(F.data == "adm_luck_set")
async def cb_adm_luck_set(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "luck"): return
    await state.set_state(St.adm_luck_target)
    await c.message.edit_text("🍀 <code>ID шанс</code>\nПример: <code>1001 80</code>\n0 — всегда проигрыш, 50 — обычный, 100 — всегда победа")

@dp.message(St.adm_luck_target)
async def cb_adm_luck_target_do(m: Message, state: FSMContext):
    parts = m.text.split()
    if len(parts) != 2: await m.answer("❌ ID шанс"); return
    try:
        gid = int(parts[0]); luck = int(parts[1])
    except: await m.answer("❌ Числа"); return
    if luck < 0 or luck > 100: await m.answer("❌ Шанс 0-100"); return
    u = await db.get_user_by_game_id(gid)
    if not u: await m.answer("❌ Не найден"); await state.clear(); return
    await db.set_luck(u["user_id"], luck)
    await m.answer(f"✅ Удача #{gid}: <b>{luck}%</b>", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "adm_luck_view")
async def cb_adm_luck_view(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "luck"): return
    await state.set_state(St.adm_luck_view)
    await c.message.edit_text("📊 Введи игровой ID:")

@dp.message(St.adm_luck_view)
async def cb_adm_luck_view_do(m: Message, state: FSMContext):
    try: gid = int(m.text.strip())
    except: await m.answer("❌ Число"); return
    u = await db.get_user_by_game_id(gid)
    if not u: await m.answer("❌ Не найден"); await state.clear(); return
    await m.answer(
        f"🍀 <b>Удача игрока #{gid}</b>\n\n🎭 {u['nick']}\n🍀 Шанс: <b>{u.get('luck',50)}%</b>",
        parse_mode="HTML")
    await state.clear()

# --- Деньги ---
@dp.callback_query(F.data == "adm_give_money")
async def cb_adm_give_money(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "money"): return
    await state.set_state(St.adm_give_money)
    await c.message.edit_text(f"💰 <code>ID сумма</code>\nМакс: {fmt_full(MAX_AMOUNT)}$")

@dp.message(St.adm_give_money)
async def cb_adm_give_money_do(m: Message, state: FSMContext):
    parts = m.text.split()
    if len(parts) != 2: await m.answer("❌ ID сумма"); return
    try: gid = int(parts[0])
    except: await m.answer("❌ ID"); return
    amount = parse_amount(parts[1])
    if not amount or amount <= 0: await m.answer("❌ Сумма"); return
    if amount > MAX_AMOUNT: await m.answer(f"❌ Макс"); return
    u = await db.get_user_by_game_id(gid)
    if not u: await m.answer("❌ Нет"); await state.clear(); return
    await db.add_balance(u["user_id"], amount)
    await m.answer(f"✅ +{fmt_full(amount)}$ → #{gid}")
    await state.clear()

@dp.callback_query(F.data == "adm_take_money")
async def cb_adm_take_money(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "money"): return
    await state.set_state(St.adm_take_money)
    await c.message.edit_text(f"💸 <code>ID сумма</code>")

@dp.message(St.adm_take_money)
async def cb_adm_take_money_do(m: Message, state: FSMContext):
    parts = m.text.split()
    if len(parts) != 2: await m.answer("❌ ID сумма"); return
    try: gid = int(parts[0])
    except: await m.answer("❌ ID"); return
    amount = parse_amount(parts[1])
    if not amount or amount <= 0: await m.answer("❌ Сумма"); return
    u = await db.get_user_by_game_id(gid)
    if not u: await m.answer("❌ Нет"); await state.clear(); return
    await db.add_balance(u["user_id"], -amount)
    await m.answer(f"✅ -{fmt_full(amount)}$ ← #{gid}")
    await state.clear()

# --- BTC ---
@dp.callback_query(F.data == "adm_give_btc")
async def cb_adm_give_btc(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "btc"): return
    await state.set_state(St.adm_give_btc); await c.message.edit_text("₿ <code>ID кол-во_BTC</code>")

@dp.message(St.adm_give_btc)
async def cb_adm_give_btc_do(m: Message, state: FSMContext):
    parts = m.text.split()
    if len(parts) != 2: await m.answer("❌"); return
    try: gid = int(parts[0]); amount = float(parts[1].replace(",", "."))
    except: await m.answer("❌ Данные"); return
    u = await db.get_user_by_game_id(gid)
    if not u: await m.answer("❌ Нет"); await state.clear(); return
    await db.update(u["user_id"], btc=u["btc"] + amount)
    await m.answer(f"✅ +{amount:.2f}₿")
    await state.clear()

@dp.callback_query(F.data == "adm_take_btc")
async def cb_adm_take_btc(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "btc"): return
    await state.set_state(St.adm_take_btc); await c.message.edit_text("₿ <code>ID кол-во</code>")

@dp.message(St.adm_take_btc)
async def cb_adm_take_btc_do(m: Message, state: FSMContext):
    parts = m.text.split()
    if len(parts) != 2: await m.answer("❌"); return
    try: gid = int(parts[0]); amount = float(parts[1].replace(",", "."))
    except: await m.answer("❌"); return
    u = await db.get_user_by_game_id(gid)
    if not u: await m.answer("❌"); await state.clear(); return
    await db.update(u["user_id"], btc=max(0, u["btc"] - amount))
    await m.answer(f"✅ -{amount:.2f}₿")
    await state.clear()

@dp.callback_query(F.data == "adm_set_btc_price")
async def cb_adm_set_btc_price(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "btc"): return
    await state.set_state(St.adm_btc_price)
    await c.message.edit_text(f"💱 Курс: {fmt_full(BTC_CURRENT)}$\n\nНовый:")

@dp.message(St.adm_btc_price)
async def cb_adm_btc_price_do(m: Message, state: FSMContext):
    global BTC_CURRENT
    amount = parse_amount(m.text)
    if not amount or amount <= 0: await m.answer("❌"); return
    BTC_CURRENT = amount
    await m.answer(f"✅ {fmt_full(amount)}$")
    await state.clear()

# --- Блокировка ---
@dp.callback_query(F.data == "adm_ban")
async def cb_adm_ban(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "ban"): return
    await state.set_state(St.adm_ban)
    await c.message.edit_text("🚫 <code>ID дней</code>\n999 = навсегда + сброс\nПример: <code>1001 7</code>")

@dp.message(St.adm_ban)
async def cb_adm_ban_do(m: Message, state: FSMContext):
    parts = m.text.split()
    if len(parts) != 2: await m.answer("❌ ID дней"); return
    try: gid = int(parts[0]); days = int(parts[1])
    except: await m.answer("❌"); return
    if days <= 0: await m.answer("❌"); return
    u = await db.get_user_by_game_id(gid)
    if not u: await m.answer("❌"); await state.clear(); return
    if u["user_id"] == ADMIN_ID: await m.answer("❌ Нельзя"); await state.clear(); return
    if not is_main_admin(m.from_user.id) and u.get("is_admin"):
        await m.answer("❌ Нельзя админов"); await state.clear(); return
    if days >= 999:
        await db.update(u["user_id"], is_banned=1, ban_until=0)
        await db.reset_full(u["user_id"])
        await m.answer(f"✅ #{gid} навсегда + обнулён")
    else:
        until = int(time.time()) + days * 86400
        await db.update(u["user_id"], is_banned=1, ban_until=until)
        await m.answer(f"✅ #{gid} до {datetime.fromtimestamp(until).strftime('%d.%m.%Y')}")
    await state.clear()

@dp.callback_query(F.data == "adm_unban")
async def cb_adm_unban(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "ban"): return
    await state.set_state(St.adm_unban); await c.message.edit_text("✅ ID:")

@dp.message(St.adm_unban)
async def cb_adm_unban_do(m: Message, state: FSMContext):
    try: gid = int(m.text.strip())
    except: await m.answer("❌"); return
    u = await db.get_user_by_game_id(gid)
    if not u: await m.answer("❌"); await state.clear(); return
    await db.update(u["user_id"], is_banned=0, ban_until=0)
    await m.answer(f"✅ #{gid} разбанен")
    await state.clear()

# --- Имущество ---
@dp.callback_query(F.data == "adm_prop_house")
async def cb_adm_prop_house(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "prop"): return
    await state.set_state(St.adm_prop_target); await state.update_data(prop="house")
    await c.message.edit_text("🏠 Введи ID:")

@dp.callback_query(F.data == "adm_prop_biz")
async def cb_adm_prop_biz(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "prop"): return
    await state.set_state(St.adm_prop_target); await state.update_data(prop="biz")
    await c.message.edit_text("🏢 Введи ID:")

@dp.callback_query(F.data == "adm_prop_farm")
async def cb_adm_prop_farm(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "prop"): return
    await state.set_state(St.adm_prop_target); await state.update_data(prop="farm")
    await c.message.edit_text("⛏ Введи ID:")

@dp.message(St.adm_prop_target)
async def cb_adm_prop_target_do(m: Message, state: FSMContext):
    try: gid = int(m.text.strip())
    except: await m.answer("❌"); return
    u = await db.get_user_by_game_id(gid)
    if not u: await m.answer("❌"); await state.clear(); return
    data = await state.get_data(); prop = data["prop"]
    await state.update_data(target_user_id=u["user_id"], target_gid=gid)
    if prop == "house":
        await m.answer(f"🏠 для #{gid}:", reply_markup=admin_house_select_kb("adm_set_house"))
    elif prop == "biz":
        await m.answer(f"🏢 для #{gid}:", reply_markup=admin_biz_select_kb("adm_set_biz"))
    else:
        await m.answer(f"⛏ для #{gid}:", reply_markup=admin_farm_select_kb("adm_set_farm"))

@dp.callback_query(F.data.startswith("adm_set_house_"))
async def cb_adm_set_house(c: CallbackQuery, state: FSMContext):
    key = c.data.split("_")[3]; data = await state.get_data(); uid = data.get("target_user_id")
    if not uid: return
    await db.update(uid, houses=key, garage_bought=0, garage="")
    await c.answer(f"✅ {HOUSES[key]['name']}!", show_alert=True); await state.clear()

@dp.callback_query(F.data.startswith("adm_set_biz_"))
async def cb_adm_set_biz(c: CallbackQuery, state: FSMContext):
    key = c.data.split("_")[3]; data = await state.get_data(); uid = data.get("target_user_id")
    if not uid: return
    await db.update(uid, businesses=serialize_businesses({key: 1}), business_last_collect=int(time.time()))
    await c.answer(f"✅ {BUSINESSES[key]['name']}!", show_alert=True); await state.clear()

@dp.callback_query(F.data.startswith("adm_set_farm_"))
async def cb_adm_set_farm(c: CallbackQuery, state: FSMContext):
    key = c.data.split("_")[3]; data = await state.get_data(); uid = data.get("target_user_id")
    if not uid: return
    u = await db.get_user_by_id(uid); lst = parse_list(u["farms"])
    if lst and lst[0] != key: lst = [key]
    else: lst.append(key)
    await db.update(uid, farms=serialize_list(lst))
    await c.answer(f"✅ {FARMS[key]['name']}!", show_alert=True); await state.clear()

# --- Глобальные ---
@dp.callback_query(F.data == "adm_give_all")
async def cb_adm_give_all(c: CallbackQuery):
    if not is_main_admin(c.from_user.id): await c.answer("Только главный", show_alert=True); return
    await c.message.edit_text("⚠️ <b>Выдать ВСЕМ</b>\n\nУверен?", reply_markup=admin_confirm_kb("give_all_ask"), parse_mode="HTML")

@dp.callback_query(F.data == "adm_confirm_give_all_ask")
async def cb_adm_give_all_ask(c: CallbackQuery, state: FSMContext):
    if not is_main_admin(c.from_user.id): return
    await state.set_state(St.adm_give_all)
    await c.message.edit_text(f"💰 Сумма для всех (макс {fmt_full(MAX_AMOUNT)}$):")

@dp.message(St.adm_give_all)
async def cb_adm_give_all_do(m: Message, state: FSMContext):
    if not is_main_admin(m.from_user.id): return
    amount = parse_amount(m.text)
    if not amount or amount <= 0: await m.answer("❌"); return
    if amount > MAX_AMOUNT: await m.answer("❌"); return
    users = await db.get_all_users()
    for u in users: await db.add_balance(u["user_id"], amount)
    await state.clear()
    await m.answer(f"✅ +{fmt_full(amount)}$ всем ({len(users)})")

@dp.callback_query(F.data == "adm_take_all")
async def cb_adm_take_all(c: CallbackQuery):
    if not is_main_admin(c.from_user.id): await c.answer("Только главный", show_alert=True); return
    await c.message.edit_text("⚠️ <b>Забрать у ВСЕХ</b>\n\nУверен?", reply_markup=admin_confirm_kb("take_all_ask"), parse_mode="HTML")

@dp.callback_query(F.data == "adm_confirm_take_all_ask")
async def cb_adm_take_all_ask(c: CallbackQuery, state: FSMContext):
    if not is_main_admin(c.from_user.id): return
    await state.set_state(St.adm_take_all)
    await c.message.edit_text(f"💸 Сумма для всех (макс {fmt_full(MAX_AMOUNT)}$):")

@dp.message(St.adm_take_all)
async def cb_adm_take_all_do(m: Message, state: FSMContext):
    if not is_main_admin(m.from_user.id): return
    amount = parse_amount(m.text)
    if not amount or amount <= 0: await m.answer("❌"); return
    if amount > MAX_AMOUNT: await m.answer("❌"); return
    users = await db.get_all_users()
    for u in users: await db.add_balance(u["user_id"], -amount)
    await state.clear()
    await m.answer(f"✅ -{fmt_full(amount)}$ у всех ({len(users)})")

@dp.callback_query(F.data == "adm_reset_all")
async def cb_adm_reset_all(c: CallbackQuery):
    if not is_main_admin(c.from_user.id): await c.answer("Только главный", show_alert=True); return
    await c.message.edit_text("⚠️ <b>ОБНУЛИТЬ ВСЕХ</b>\n\nУверен?", reply_markup=admin_confirm_kb("reset_all_ask"), parse_mode="HTML")

@dp.callback_query(F.data == "adm_confirm_reset_all_ask")
async def cb_adm_reset_all_do(c: CallbackQuery):
    if not is_main_admin(c.from_user.id): return
    await db.reset_all()
    await c.message.edit_text("✅ Все обнулены")

# --- Промокоды ---
@dp.callback_query(F.data == "adm_promo_create")
async def cb_adm_promo_create(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "promo"): return
    await state.set_state(St.adm_promo_create)
    await c.message.edit_text(
        "🎟 <code>КОД СУММА ЛИМИТ [VIP]</code>\n"
        "Пример: <code>START 1кк 100</code>\n"
        "Пример VIP: <code>VIPADMIN 0 1 ADMIN</code>")

@dp.message(St.adm_promo_create)
async def cb_adm_promo_create_do(m: Message, state: FSMContext):
    parts = m.text.split()
    if len(parts) < 3: await m.answer("❌ КОД СУММА ЛИМИТ [VIP]"); return
    code = parts[0].upper(); amount = parse_amount(parts[1])
    try: limit = int(parts[2])
    except: await m.answer("❌"); return
    vip = parts[3].upper() if len(parts) >= 4 else ""
    if amount is None or amount < 0 or limit <= 0: await m.answer("❌ Данные"); return
    await db.create_promo(code, amount, limit, vip)
    extra = f"\n⭐ VIP: {vip}" if vip else ""
    await m.answer(f"✅ <code>{code}</code> создан{extra}", parse_mode="HTML")
    await state.clear()

@dp.callback_query(F.data == "adm_promo_delete")
async def cb_adm_promo_delete(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "promo"): return
    await state.set_state(St.adm_promo_delete); await c.message.edit_text("🗑 Код:")

@dp.message(St.adm_promo_delete)
async def cb_adm_promo_delete_do(m: Message, state: FSMContext):
    code = m.text.strip().upper()
    ok = await db.deactivate_promo(code)
    if ok: await m.answer(f"✅ {code} деактивирован", parse_mode="HTML")
    else: await m.answer("❌ Не найден")
    await state.clear()

# --- Админка ---
@dp.callback_query(F.data == "adm_give_admin")
async def cb_adm_give_admin(c: CallbackQuery, state: FSMContext):
    if not await check_admin_perm(c, "admins"): return
    await state.set_state(St.adm_give_admin); await c.message.edit_text("👑 Введи игровой ID:")

@dp.message(St.adm_give_admin)
async def cb_adm_give_admin_do(m: Message, state: FSMContext):
    try: gid = int(m.text.strip())
    except: await m.answer("❌"); return
    u = await db.get_user_by_game_id(gid)
    if not u: await m.answer("❌"); await state.clear(); return
    if u["user_id"] == ADMIN_ID: await m.answer("❌ Это главный"); await state.clear(); return
    await state.update_data(adm_target_uid=u["user_id"], adm_target_gid=gid, adm_perms=[])
    await m.answer(f"👑 <b>Админка для #{gid} ({u['nick']})</b>\n\nВыбери функции:",
        reply_markup=admin_perms_kb(gid, []), parse_mode="HTML")
    await state.set_state(None)

@dp.callback_query(F.data.startswith("admperm_toggle_"))
async def cb_admperm_toggle(c: CallbackQuery, state: FSMContext):
    if not is_main_admin(c.from_user.id):
        u_admin = await db.get_user(c.from_user.id)
        if not has_perm(u_admin, "admins"): await c.answer("Нет прав", show_alert=True); return
    key = c.data.split("_")[2]
    data = await state.get_data()
    perms = data.get("adm_perms", [])
    if key in perms: perms.remove(key)
    else: perms.append(key)
    await state.update_data(adm_perms=perms)
    gid = data.get("adm_target_gid")
    await c.message.edit_reply_markup(reply_markup=admin_perms_kb(gid, perms))
    await c.answer()

@dp.callback_query(F.data == "admperm_save")
async def cb_admperm_save(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    uid = data.get("adm_target_uid"); gid = data.get("adm_target_gid")
    perms = data.get("adm_perms", [])
    if not uid: return
    if not perms: await c.answer("Выбери 1", show_alert=True); return
    await db.update(uid, is_admin=1, admin_perms=",".join(perms))
    await c.message.edit_text(
        f"✅ Админка #{gid}\n\n{', '.join(ADMIN_PERMS[p] for p in perms if p in ADMIN_PERMS)}")
    await state.clear()

@dp.callback_query(F.data == "admperm_take")
async def cb_admperm_take(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    uid = data.get("adm_target_uid"); gid = data.get("adm_target_gid")
    if not uid: return
    await db.update(uid, is_admin=0, admin_perms="")
    await c.message.edit_text(f"✅ Админка забрана у #{gid}")
    await state.clear()

# --- VIP ---
@dp.callback_query(F.data == "adm_vip_give")
async def cb_adm_vip_give(c: CallbackQuery, state: FSMContext):
    if not is_main_admin(c.from_user.id): return
    await state.set_state(St.adm_give_vip)
    await state.update_data(vip_action="give")
    await c.message.edit_text("⭐ <code>ID VIP_УРОВЕНЬ</code>\nПример: <code>1001 ADMIN</code>")

@dp.callback_query(F.data == "adm_vip_take")
async def cb_adm_vip_take(c: CallbackQuery, state: FSMContext):
    if not is_main_admin(c.from_user.id): return
    await state.set_state(St.adm_give_vip)
    await state.update_data(vip_action="take")
    await c.message.edit_text("❌ ID игрока для снятия VIP:")

@dp.message(St.adm_give_vip)
async def cb_adm_vip_do(m: Message, state: FSMContext):
    if not is_main_admin(m.from_user.id): return
    data = await state.get_data()
    action = data.get("vip_action", "give")
    if action == "take":
        try: gid = int(m.text.strip())
        except: await m.answer("❌"); return
        u = await db.get_user_by_game_id(gid)
        if not u: await m.answer("❌"); await state.clear(); return
        await db.update(u["user_id"], is_vip=0, vip_level="")
        await m.answer(f"✅ VIP снят у #{gid}")
        await state.clear()
        return
    parts = m.text.split()
    if len(parts) != 2: await m.answer("❌ ID VIP"); return
    try: gid = int(parts[0])
    except: await m.answer("❌"); return
    vip_level = parts[1].upper()
    u = await db.get_user_by_game_id(gid)
    if not u: await m.answer("❌"); await state.clear(); return
    await db.update(u["user_id"], is_vip=1, vip_level=vip_level)
    await m.answer(f"✅ VIP {vip_level} выдан #{gid}")
    await state.clear()

# ============ ЗАПУСК ============
register_group_handlers(dp)

async def health(request): return web.Response(text="OK")

async def start_web():
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, "0.0.0.0", port).start()

async def main():
    await db.init_db()
    await start_web()
    print("🎰 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
