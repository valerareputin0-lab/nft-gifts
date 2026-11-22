import asyncio, time, random, os
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import config
import database as db
from utils import (fmt_full, fmt_short, fmt_btc, parse_amount, parse_list,
                   serialize_list, parse_businesses, serialize_businesses,
                   business_income, total_business_income, total_farm_income,
                   process_farms, calc_business_cash, collect_business,
                   new_deck, hand_value, dealer_play, fmt_hand, is_blackjack)
from keyboards import (main_kb, back_kb, profile_kb, biz_shop_kb, biz_confirm_kb,
                       biz_manage_kb, farms_kb, houses_kb, garage_kb, wardrobe_kb,
                       shop_kb, rewards_kb, admin_kb, bank_kb, deposits_kb,
                       casino_kb, bj_kb, rl_choice_kb, dice_choice_kb)
from config import (BUSINESSES, FARMS, HOUSES, CARS, SKINS, DEPOSITS,
                    MIN_BET, MAX_BET, WITHDRAW_FEE, BTC_PRICE, ADMIN_ID,
                    FARM_CAP_HOURS, CASH_CAP_HOURS, CASH_COLLECT_COOLDOWN,
                    SELL_PERCENT, BONUS_AMOUNT, BONUS_COOLDOWN,
                    GARAGE_PERCENT, BUSINESS_UPGRADE_COST_MULT,
                    NICK_MIN, NICK_MAX, FARMS_LIMIT)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

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
    admin_give = State(); admin_take = State(); admin_promo = State()
    nick_input = State()

def is_admin(uid): return uid == ADMIN_ID

def get_biz_dict(u):
    b = parse_businesses(u["businesses"])
    b = {k: v for k, v in b.items() if k in BUSINESSES}
    if len(b) > 1:
        b = {list(b.keys())[0]: list(b.values())[0]}
    return b

def get_farm_info(u):
    lst = parse_list(u["farms"])
    if not lst: return None, 0
    return lst[0], len(lst)

def fmt_date(ts):
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y")

# ============ НИК ============
async def ask_nick(m, state, source="start"):
    await state.set_state(St.nick_input)
    await state.update_data(nick_from=source)
    await m.answer(
        f"🎭 Придумай ник\n\n"
        f"Правила:\n• {NICK_MIN}–{NICK_MAX} символов\n"
        f"• Только буквы и цифры\n• Должен быть уникальным")

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
        await m.answer(f"✅ Ник: <b>{nick}</b>", parse_mode="HTML",
                       reply_markup=back_kb("profile"))
    else:
        await m.answer(f"✅ Ник: <b>{nick}</b>", parse_mode="HTML",
                       reply_markup=main_kb(is_admin(m.from_user.id)))

# ============ СТАРТ ============
@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    u = await db.get_user(m.from_user.id, m.from_user.username)
    if not u.get("nick"):
        await ask_nick(m, state, "start"); return
    await m.answer(
        f"🎰 <b>Добро пожаловать, {u['nick']}!</b>\n\n"
        f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n\n📋 Разделы ниже 👇",
        reply_markup=main_kb(is_admin(m.from_user.id)), parse_mode="HTML")

@dp.callback_query(F.data == "menu")
async def cb_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text("🏠 <b>Главное меню</b>",
        reply_markup=main_kb(is_admin(c.from_user.id)), parse_mode="HTML")

@dp.callback_query(F.data == "change_nick")
async def cb_change_nick(c: CallbackQuery, state: FSMContext):
    await ask_nick(c.message, state, "change"); await c.answer()

# ============ ПРОФИЛЬ ============
@dp.callback_query(F.data == "profile")
async def cb_profile(c: CallbackQuery):
    uid = c.from_user.id
    await process_farms(uid)
    u = await db.get_user(uid)
    rank = await db.get_user_rank(uid)
    biz = get_biz_dict(u)
    ftype, fcount = get_farm_info(u)
    houses = parse_list(u["houses"])
    cars = parse_list(u["garage"])

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

    if u['btc'] == 0: btc_str = "0"; btc_usd = 0
    else: btc_str = fmt_btc(u['btc']); btc_usd = int(u['btc'] * BTC_PRICE)

    imush = []
    if biz:
        bid = list(biz.keys())[0]
        name = BUSINESSES[bid]["name"].split(" ", 1)[-1]
        imush.append(f"⠀🚀 Бизнес: {name} ({biz[bid]} lvl)")
    if ftype:
        name = FARMS[ftype]["name"].split(" ", 1)[-1]
        imush.append(f"⠀🔋 Ферма: {name} ({fcount} шт)")
    if houses:
        name = HOUSES[houses[0]]["name"].split(" ", 1)[-1]
        imush.append(f"⠀🏠 Дом: {name}")
    if cars:
        name = CARS[cars[-1]]["name"].split(" ", 1)[-1]
        imush.append(f"⠀🚗 Машина: {name}")

    lines = [
        f"👻 {u.get('nick') or 'Игрок'}, профиль:", "",
        f"🔎 Игровой ID: {u.get('game_id') or '—'}",
        f"💰 Баланс: {fmt_full(u['balance'])}$",
        f"🏦 Счет: {fmt_full(u['bank_wallet'])}$",
        f"₿ Bitcoin: {btc_str} (~{fmt_full(btc_usd)}$)",
        f"👑 Рейтинг в топе: {rank}", ""]
    if imush:
        lines.append("🗄 Имущество:"); lines.extend(imush)
    else:
        lines.append("🗄 Имущество: пока нету")
    lines.append(""); lines.append(f"⌚ Регистрация: {reg_str}")

    await c.message.edit_text("\n".join(lines), reply_markup=profile_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "top")
async def cb_top(c: CallbackQuery):
    top = await db.get_top(10)
    medals = ["🥇","🥈","🥉"] + ["▫️"]*7
    lines = ["🏆 <b>Топ игроков</b>\n"]
    for i, u in enumerate(top):
        name = u.get("nick") or (f"@{u['username']}" if u.get("username") else "player")
        lines.append(f"{medals[i]} {i+1}. {name} — <b>{fmt_full(u['balance'])}$</b>")
    await c.message.edit_text("\n".join(lines), reply_markup=back_kb(), parse_mode="HTML")

# ============ БИЗНЕСЫ ============
@dp.callback_query(F.data == "biz")
async def cb_biz(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    biz = get_biz_dict(u)
    if biz:
        bid = list(biz.keys())[0]
        lvl = biz[bid]
        b = BUSINESSES[bid]
        cash, cap, income = calc_business_cash(u)
        text = (
            f"🚀 {u['nick']}, статистика «{b['name'].split(' ', 1)[-1]}»:\n\n"
            f"💸 Доход: {fmt_short(income // 60)}$в минуту\n"
            f"💰 В кассе: {fmt_short(cash)}$ из {fmt_short(cap)}$\n"
            f"📊 Уровень: {lvl}/3\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💼 Бизнес продаётся с комиссией 5%")
        await c.message.edit_text(text,
            reply_markup=biz_manage_kb(bid, lvl, cash > 0), parse_mode="HTML")
    else:
        lines = [f"💼 {u['nick']}, обеспечь себя ДЕНЬГАМИ! Список бизнесов:", ""]
        for i, (key, b) in enumerate(BUSINESSES.items(), 1):
            lines.append(f"{i}. {b['name']}")
            lines.append(f"⠀• Цена: {fmt_short(b['price'])}$")
            lines.append(f"⠀• Прибыль: {fmt_short(b['income'])}$ в час")
            lines.append("")
        lines.append(f"💰 Твой баланс: {fmt_full(u['balance'])}$")
        await c.message.edit_text("\n".join(lines),
            reply_markup=biz_shop_kb(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("biz_info_"))
async def cb_biz_info(c: CallbackQuery):
    bid = c.data.split("_")[2]
    if bid not in BUSINESSES: return
    b = BUSINESSES[bid]
    u = await db.get_user(c.from_user.id)
    can = u["balance"] >= b["price"]
    text = (
        f"{b['name']}\n\n"
        f"💵 Цена: {fmt_short(b['price'])}$\n"
        f"📈 Прибыль: {fmt_short(b['income'])}$ в час\n\n"
        f"💰 Твой баланс: {fmt_full(u['balance'])}$\n\n"
        f"{'✅ Можешь купить!' if can else '❌ Не хватает денег'}")
    await c.message.edit_text(text,
        reply_markup=biz_confirm_kb(bid), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buybiz_"))
async def cb_buy_biz(c: CallbackQuery):
    bid = c.data.split("_")[1]
    if bid not in BUSINESSES: return
    b = BUSINESSES[bid]
    u = await db.get_user(c.from_user.id)
    if get_biz_dict(u):
        await c.answer("Уже есть бизнес!", show_alert=True); return
    if u["balance"] < b["price"]:
        await c.answer("❌ Мало денег!", show_alert=True); return
    await db.add_balance(c.from_user.id, -b["price"])
    await db.update(c.from_user.id,
        businesses=serialize_businesses({bid: 1}),
        business_last_collect=int(time.time()))
    await c.answer(f"✅ Куплен {b['name']}!", show_alert=True)
    await cb_biz(c)

@dp.callback_query(F.data.startswith("upbiz_"))
async def cb_upgrade_biz(c: CallbackQuery):
    bid = c.data.split("_")[1]
    if bid not in BUSINESSES: return
    b = BUSINESSES[bid]
    u = await db.get_user(c.from_user.id)
    biz = get_biz_dict(u)
    if bid not in biz:
        await c.answer("Нет бизнеса", show_alert=True); return
    lvl = biz[bid]
    if lvl >= 3:
        await c.answer("Максимум!", show_alert=True); return
    cost = int(b["price"] * BUSINESS_UPGRADE_COST_MULT[lvl + 1])
    if u["balance"] < cost:
        await c.answer(f"❌ Нужно {fmt_short(cost)}$", show_alert=True); return
    cash, _, _ = calc_business_cash(u)
    await db.add_balance(c.from_user.id, -cost)
    await db.update(c.from_user.id,
        businesses=serialize_businesses({bid: lvl + 1}),
        business_last_collect=int(time.time()))
    await c.answer(f"✅ Lvl {lvl+1}! Касса: {fmt_short(cash)}$", show_alert=True)
    await cb_biz(c)

@dp.callback_query(F.data == "biz_collect")
async def cb_biz_collect(c: CallbackQuery):
    amount, cd = await collect_business(c.from_user.id)
    if cd > 0:
        await c.answer(f"⏳ Подожди {cd} сек", show_alert=True); return
    if amount == 0:
        await c.answer("Касса пуста", show_alert=True); return
    await c.answer(f"💰 +{fmt_full(amount)}$", show_alert=True)
    await cb_biz(c)

@dp.callback_query(F.data.startswith("sellbiz_"))
async def cb_sell_biz(c: CallbackQuery):
    bid = c.data.split("_")[1]
    if bid not in BUSINESSES: return
    u = await db.get_user(c.from_user.id)
    biz = get_biz_dict(u)
    if bid not in biz:
        await c.answer("Нет бизнеса", show_alert=True); return
    cash, _, _ = calc_business_cash(u)
    sell = int(BUSINESSES[bid]["price"] * (1 - SELL_PERCENT))
    await db.add_balance(c.from_user.id, cash + sell)
    await db.update(c.from_user.id, businesses="", business_last_collect=0)
    await c.answer(f"💸 +{fmt_full(cash + sell)}$ (касса + 95%)", show_alert=True)
    await cb_biz(c)

# ============ ФЕРМЫ ============
@dp.callback_query(F.data == "farms")
async def cb_farms(c: CallbackQuery):
    await process_farms(c.from_user.id)
    u = await db.get_user(c.from_user.id)
    ftype, fcount = get_farm_info(u)
    if ftype:
        f = FARMS[ftype]
        total = total_farm_income(parse_list(u["farms"]))
        text = (
            f"⛏️ Ферма {f['name'].split(' ', 1)[-1]} ({fcount}шт)\n\n"
            f"💰 Заработок в час: {total:.0f}฿\n"
            f"⛏️ Количество ферм: {fcount}\n"
            f"₿ Курс Bitcoin: {fmt_short(BTC_PRICE)}$\n"
            f"💵 В кошельке: {fmt_btc(u['btc'])}₿ (≈{fmt_full(int(u['btc']*BTC_PRICE))}$)"
        )
    else:
        lines = [f"🌐 {u['nick']}, список ферм:", ""]
        for i, (key, f) in enumerate(FARMS.items(), 1):
            lines.append(f"{i}. {f['name']}")
            lines.append(f"⠀• Цена: {fmt_short(f['price'])}$")
            lines.append(f"⠀• Прибыль: {f['btc_per_hour']}฿/час")
            lines.append(f"⠀• В наличии: 0 шт.")
            lines.append("")
        lines.append(f"💰 Твой баланс: {fmt_full(u['balance'])}$")
        lines.append(f"₿ Курс Bitcoin: {fmt_short(BTC_PRICE)}$")
        text = "\n".join(lines)
    await c.message.edit_text(text, reply_markup=farms_kb(ftype, fcount), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buyfarm_"))
async def cb_buy_farm_choose(c: CallbackQuery, state: FSMContext):
    key = c.data.split("_")[1]
    if key not in FARMS: return
    u = await db.get_user(c.from_user.id)
    ftype, fcount = get_farm_info(u)
    if ftype and ftype != key:
        await c.answer("❌ Можно покупать только твой тип!", show_alert=True); return
    f
