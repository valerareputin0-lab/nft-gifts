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
                    GARAGE_PRICE, BUSINESS_UPGRADE_COST_MULT,
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
    f = FARMS[key]
    await state.update_data(farm_key=key)
    await state.set_state(St.farm_buy_qty)
    await c.message.edit_text(
        f"➕ Покупка {f['name']}\n\n"
        f"💵 Цена за 1: {fmt_short(f['price'])}$\n"
        f"💰 Твой баланс: {fmt_full(u['balance'])}$\n\n"
        f"Сколько ферм купить?")

@dp.message(St.farm_buy_qty)
async def cb_buy_farm_qty(m: Message, state: FSMContext):
    try: qty = int(m.text.strip())
    except ValueError:
        await m.answer("❌ Введи число"); return
    if qty <= 0:
        await m.answer("❌ Кол-во > 0"); return
    data = await state.get_data()
    key = data["farm_key"]
    f = FARMS[key]
    u = await db.get_user(m.from_user.id)
    ftype, fcount = get_farm_info(u)
    if ftype and ftype != key:
        await m.answer("❌ Только твой тип!"); await state.clear(); return
    if fcount + qty > FARMS_LIMIT:
        await m.answer("❌ Слишком много"); await state.clear(); return
    total_cost = f["price"] * qty
    if u["balance"] < total_cost:
        await m.answer(f"❌ Нужно {fmt_full(total_cost)}$, у тебя {fmt_full(u['balance'])}$")
        await state.clear(); return
    await db.add_balance(m.from_user.id, -total_cost)
    lst = parse_list(u["farms"]) + [key] * qty
    await db.update(m.from_user.id, farms=serialize_list(lst))
    await state.clear()
    await m.answer(f"✅ Куплено {qty} × {f['name']} за {fmt_full(total_cost)}$",
                   reply_markup=back_kb("farms"))

@dp.callback_query(F.data == "farm_buy_menu")
async def cb_farm_buy_menu(c: CallbackQuery, state: FSMContext):
    u = await db.get_user(c.from_user.id)
    ftype, fcount = get_farm_info(u)
    if not ftype:
        await c.answer("Сначала купи тип фермы!", show_alert=True); return
    f = FARMS[ftype]
    await state.update_data(farm_key=ftype)
    await state.set_state(St.farm_buy_qty)
    await c.message.edit_text(
        f"➕ Покупка {f['name']}\n\n"
        f"💵 Цена за 1: {fmt_short(f['price'])}$\n"
        f"💰 Твой баланс: {fmt_full(u['balance'])}$\n\n"
        f"Сколько ферм купить?")

@dp.callback_query(F.data == "farm_sell_menu")
async def cb_farm_sell_menu(c: CallbackQuery, state: FSMContext):
    u = await db.get_user(c.from_user.id)
    ftype, fcount = get_farm_info(u)
    if not ftype or fcount == 0:
        await c.answer("Нет ферм", show_alert=True); return
    f = FARMS[ftype]
    sell_price = int(f["price"] * (1 - SELL_PERCENT))
    await state.set_state(St.farm_sell_qty)
    await c.message.edit_text(
        f"➖ Продажа {f['name']}\n\n"
        f"💵 Цена продажи за 1: {fmt_short(sell_price)}$ (комиссия 5%)\n"
        f"⛏️ У тебя: {fcount} шт\n\n"
        f"Сколько ферм продать?")

@dp.message(St.farm_sell_qty)
async def cb_sell_farm_qty(m: Message, state: FSMContext):
    try: qty = int(m.text.strip())
    except ValueError:
        await m.answer("❌ Число"); return
    if qty <= 0:
        await m.answer("❌ Кол-во > 0"); return
    u = await db.get_user(m.from_user.id)
    ftype, fcount = get_farm_info(u)
    if not ftype or fcount == 0:
        await m.answer("❌ Нет ферм"); await state.clear(); return
    if qty > fcount:
        await m.answer(f"❌ У тебя только {fcount} ферм"); await state.clear(); return
    await process_farms(m.from_user.id)
    u = await db.get_user(m.from_user.id)
    f = FARMS[ftype]
    sell_price = int(f["price"] * (1 - SELL_PERCENT))
    total = sell_price * qty
    await db.add_balance(m.from_user.id, total)
    lst = parse_list(u["farms"])
    for _ in range(qty):
        if lst: lst.pop()
    await db.update(m.from_user.id, farms=serialize_list(lst))
    await state.clear()
    await m.answer(f"✅ Продано {qty} × {f['name']} за {fmt_full(total)}$",
                   reply_markup=back_kb("farms"))

@dp.callback_query(F.data == "farms_sellbtc")
async def cb_farms_sellbtc(c: CallbackQuery, state: FSMContext):
    u = await db.get_user(c.from_user.id)
    if u["btc"] < 0.001:
        await c.answer("Мало BTC", show_alert=True); return
    await state.set_state(St.sell_btc)
    await c.message.edit_text(
        f"₿ У тебя {fmt_btc(u['btc'])}₿\n"
        f"Курс: 1₿ = {fmt_full(BTC_PRICE)}$\n"
        f"💰 Всего: ≈{fmt_full(int(u['btc']*BTC_PRICE))}$\n\n"
        f"Сколько BTC продать? (например 5.5)")

@dp.message(St.sell_btc)
async def cb_sell_btc_amount(m: Message, state: FSMContext):
    try: amount = float(m.text.strip().replace(",", "."))
    except: await m.answer("❌ Число"); return
    u = await db.get_user(m.from_user.id)
    if amount <= 0 or amount > u["btc"]:
        await m.answer("❌ Неверное"); return
    money = int(amount * BTC_PRICE)
    await db.update(m.from_user.id, btc=u["btc"] - amount)
    await db.add_balance(m.from_user.id, money)
    await state.clear()
    await m.answer(f"✅ Продано {amount:.4f}₿ за {fmt_full(money)}$",
                   reply_markup=back_kb("farms"))

# ============ ДОМА ============
@dp.callback_query(F.data == "houses")
async def cb_houses(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    houses = parse_list(u["houses"])
    if houses:
        hid = houses[0]
        h = HOUSES[hid]
        text = (f"🏠 <b>Твой дом</b>\n\n{h['name']}\n"
                f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n\n"
                f"Доступно: Гараж, Шкаф, продажа дома.")
        await c.message.edit_text(text, reply_markup=houses_kb(True, hid), parse_mode="HTML")
    else:
        text = (f"🏠 <b>Дома</b>\n\n💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n\n"
                f"Можно купить <b>1 дом</b>. Выбирай:")
        await c.message.edit_text(text, reply_markup=houses_kb(False, None), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buyhouse_"))
async def cb_buy_house(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in HOUSES: return
    h = HOUSES[key]
    u = await db.get_user(c.from_user.id)
    if parse_list(u["houses"]):
        await c.answer("Уже есть дом!", show_alert=True); return
    if u["balance"] < h["price"]:
        await c.answer("❌ Мало денег!", show_alert=True); return
    await db.add_balance(c.from_user.id, -h["price"])
    await db.update(c.from_user.id, houses=key)
    await c.answer(f"✅ Куплен {h['name']}!", show_alert=True)
    await cb_houses(c)

@dp.callback_query(F.data.startswith("sellhouse_"))
async def cb_sell_house(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in HOUSES: return
    u = await db.get_user(c.from_user.id)
    if key not in parse_list(u["houses"]):
        await c.answer("Нет дома", show_alert=True); return
    sell = int(HOUSES[key]["price"] * SELL_PERCENT)
    await db.add_balance(c.from_user.id, sell)
    await db.update(c.from_user.id, houses="")
    await c.answer(f"💸 +{fmt_full(sell)}$", show_alert=True)
    await cb_houses(c)

# ============ ГАРАЖ ============
@dp.callback_query(F.data == "garage")
async def cb_garage(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    if not parse_list(u["houses"]):
        await c.answer("Сначала купи дом!", show_alert=True); return
    await c.message.edit_text(
        f"🚗 <b>Гараж</b>\n\n💰 Баланс: <b>{fmt_full(u['balance'])}$</b>",
        reply_markup=garage_kb(bool(u["garage_bought"]), parse_list(u["garage"])),
        parse_mode="HTML")

@dp.callback_query(F.data == "buygarage")
async def cb_buy_garage(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    if u["garage_bought"]:
        await c.answer("Уже куплен!", show_alert=True); return
    if u["balance"] < GARAGE_PRICE:
        await c.answer("❌ Мало денег!", show_alert=True); return
    await db.add_balance(c.from_user.id, -GARAGE_PRICE)
    await db.update(c.from_user.id, garage_bought=1)
    await c.answer("✅ Гараж куплен!", show_alert=True)
    await cb_garage(c)

@dp.callback_query(F.data.startswith("buycar_"))
async def cb_buy_car(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in CARS: return
    car = CARS[key]
    u = await db.get_user(c.from_user.id)
    if not u["garage_bought"]:
        await c.answer("Сначала гараж!", show_alert=True); return
    cars = parse_list(u["garage"])
    if key in cars:
        await c.answer("Уже куплено!", show_alert=True); return
    if u["balance"] < car["price"]:
        await c.answer("❌ Мало денег!", show_alert=True); return
    await db.add_balance(c.from_user.id, -car["price"])
    cars.append(key)
    await db.update(c.from_user.id, garage=serialize_list(cars))
    await c.answer(f"✅ {car['name']}!", show_alert=True)
    await cb_garage(c)

@dp.callback_query(F.data.startswith("sellcar_"))
async def cb_sell_car(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in CARS: return
    u = await db.get_user(c.from_user.id)
    cars = parse_list(u["garage"])
    if key not in cars:
        await c.answer("Нет машины", show_alert=True); return
    sell = int(CARS[key]["price"] * SELL_PERCENT)
    cars.remove(key)
    await db.add_balance(c.from_user.id, sell)
    await db.update(c.from_user.id, garage=serialize_list(cars))
    await c.answer(f"💸 +{fmt_full(sell)}$", show_alert=True)
    await cb_garage(c)

# ============ ШКАФ ============
@dp.callback_query(F.data == "wardrobe")
async def cb_wardrobe(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    if not parse_list(u["houses"]):
        await c.answer("Сначала дом!", show_alert=True); return
    await c.message.edit_text(
        f"👔 <b>Шкаф скинов</b>\n\n💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n\n"
        f"Надень скин — он применится к тебе.",
        reply_markup=wardrobe_kb(parse_list(u["wardrobe"]), parse_list(u["clothes_worn"])),
        parse_mode="HTML")

@dp.callback_query(F.data.startswith("wear_"))
async def cb_wear(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in SKINS: return
    u = await db.get_user(c.from_user.id)
    worn = parse_list(u["clothes_worn"])
    if key in worn:
        worn.remove(key); await c.answer("Снято", show_alert=True)
    else:
        worn = [key]
        await c.answer("Надето!", show_alert=True)
    await db.update(c.from_user.id, clothes_worn=serialize_list(worn))
    await cb_wardrobe(c)

# ============ МАГАЗИН ============
@dp.callback_query(F.data == "shop")
async def cb_shop(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    owned = parse_list(u["wardrobe"])
    lines = [f"🛒 Магазин скинов", "", f"💰 Баланс: {fmt_full(u['balance'])}$", ""]
    for i, (key, skin) in enumerate(SKINS.items(), 1):
        lines.append(f"{i}. {skin['name']} — {fmt_short(skin['price'])}$")
    lines.append("")
    lines.append("Выбери скин:")
    await c.message.edit_text("\n".join(lines),
        reply_markup=shop_kb(owned), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buyskin_"))
async def cb_buy_skin(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in SKINS: return
    skin = SKINS[key]
    u = await db.get_user(c.from_user.id)
    owned = parse_list(u["wardrobe"])
    if key in owned:
        await c.answer("Уже куплено!", show_alert=True); return
    if u["balance"] < skin["price"]:
        await c.answer("❌ Мало денег!", show_alert=True); return
    await db.add_balance(c.from_user.id, -skin["price"])
    owned.append(key)
    await db.update(c.from_user.id, wardrobe=serialize_list(owned))
    await c.answer(f"✅ {skin['name']}!", show_alert=True)
    await cb_shop(c)

# ============ НАГРАДЫ ============
@dp.callback_query(F.data == "rewards")
async def cb_rewards(c: CallbackQuery):
    await c.message.edit_text(
        "🎁 <b>Награды</b>\n\n🎁 Бонус — 5.000$ каждые 12 часов\n"
        "🎟 Промокод — введи секретный код",
        reply_markup=rewards_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "bonus")
async def cb_bonus(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    now = int(time.time()); diff = now - u["last_bonus"]
    if diff < BONUS_COOLDOWN:
        left = BONUS_COOLDOWN - diff
        await c.answer(f"⏰ {left//3600}ч {(left%3600)//60}м", show_alert=True); return
    await db.add_balance(c.from_user.id, BONUS_AMOUNT)
    await db.update(c.from_user.id, last_bonus=now)
    await c.answer(f"🎁 +{fmt_full(BONUS_AMOUNT)}$!", show_alert=True)

@dp.callback_query(F.data == "enter_promo")
async def cb_enter_promo(c: CallbackQuery, state: FSMContext):
    await state.set_state(St.promo_enter)
    await c.message.edit_text("🎟 Введи промокод:")

@dp.message(St.promo_enter)
async def cb_promo_submit(m: Message, state: FSMContext):
    code = m.text.strip().upper()
    p = await db.get_promo(code)
    if not p:
        await m.answer("❌ Не найден", reply_markup=back_kb("rewards")); await state.clear(); return
    if p["used"] >= p["limit_total"]:
        await m.answer("❌ Исчерпан", reply_markup=back_kb("rewards")); await state.clear(); return
    if await db.user_used_promo(code, m.from_user.id):
        await m.answer("❌ Уже активирован", reply_markup=back_kb("rewards")); await state.clear(); return
    await db.add_balance(m.from_user.id, p["amount"])
    await db.use_promo(code, m.from_user.id)
    await state.clear()
    await m.answer(f"🎉 +{fmt_full(p['amount'])}$", reply_markup=back_kb("rewards"))

# ============ АДМИНКА ============
@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("Только админ", show_alert=True); return
    await c.message.edit_text("👑 <b>Админ-панель</b>",
        reply_markup=admin_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "admin_give")
async def cb_admin_give(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return
    await state.set_state(St.admin_give)
    await c.message.edit_text("💰 <code>ID сумма</code>", parse_mode="HTML")

@dp.message(St.admin_give)
async def cb_admin_give_do(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    parts = m.text.split()
    if len(parts) != 2: await m.answer("❌ ID сумма"); return
    try: target = int(parts[0])
    except ValueError: await m.answer("❌ ID числом"); return
    amount = parse_amount(parts[1])
    if not amount or amount <= 0: await m.answer("❌ Сумма"); return
    if not await db.get_user_by_id(target):
        await m.answer("❌ Нет игрока"); await state.clear(); return
    await db.add_balance(target, amount)
    await state.clear()
    await m.answer(f"✅ {fmt_full(amount)}$ → {target}", reply_markup=back_kb("admin_panel"))

@dp.callback_query(F.data == "admin_take")
async def cb_admin_take(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return
    await state.set_state(St.admin_take)
    await c.message.edit_text("💸 <code>ID сумма</code>", parse_mode="HTML")

@dp.message(St.admin_take)
async def cb_admin_take_do(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    parts = m.text.split()
    if len(parts) != 2: await m.answer("❌ ID сумма"); return
    try: target = int(parts[0])
    except ValueError: await m.answer("❌ ID числом"); return
    amount = parse_amount(parts[1])
    if not amount or amount <= 0: await m.answer("❌ Сумма"); return
    if not await db.get_user_by_id(target):
        await m.answer("❌ Нет игрока"); await state.clear(); return
    await db.add_balance(target, -amount)
    await state.clear()
    await m.answer(f"✅ {fmt_full(amount)}$ ← {target}", reply_markup=back_kb("admin_panel"))

@dp.callback_query(F.data == "admin_promo")
async def cb_admin_promo(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id): return
    await state.set_state(St.admin_promo)
    await c.message.edit_text("🎟 <code>КОД СУММА ЛИМИТ</code>\nПример: <code>START 1кк 100</code>", parse_mode="HTML")

@dp.message(St.admin_promo)
async def cb_admin_promo_do(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id): return
    parts = m.text.split()
    if len(parts) != 3: await m.answer("❌ КОД СУММА ЛИМИТ"); return
    code = parts[0].upper()
    amount = parse_amount(parts[1])
    try: limit = int(parts[2])
    except ValueError: await m.answer("❌ Лимит"); return
    if not amount or amount <= 0 or limit <= 0: await m.answer("❌ Данные"); return
    await db.create_promo(code, amount, limit)
    await state.clear()
    await m.answer(
        f"✅ Промокод:\n🎟 <code>{code}</code>\n💰 {fmt_full(amount)}$\n📊 {limit}",
        reply_markup=back_kb("admin_panel"), parse_mode="HTML")

# ============ БАНК ============
@dp.callback_query(F.data == "bank")
async def cb_bank(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    has_dep = u["deposit_amount"] > 0
    ready = has_dep and u["deposit_end"] <= time.time()

    lines = [f"🏦 <b>БАНК</b>", ""]
    lines.append(f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>")
    lines.append(f"🏦 Счёт: <b>{fmt_full(u['bank_wallet'])}$</b>")
    if has_dep:
        profit = int(u["deposit_amount"] * u["deposit_rate"])
        lines.append("")
        lines.append(f"📈 Вклад: <b>{fmt_full(u['deposit_amount'])}$</b>")
        lines.append(f"💵 Доход: <b>+{fmt_full(profit)}$</b>")
        if ready:
            lines.append(f"✅ <b>Вклад готов к снятию!</b>")
        else:
            lines.append(f"📅 Окончание: <b>{fmt_date(u['deposit_end'])}</b>")
    lines.append("")
    lines.append("💸 Комиссия снятия: 3%")

    await c.message.edit_text("\n".join(lines),
        reply_markup=bank_kb(has_dep, ready), parse_mode="HTML")

@dp.callback_query(F.data == "bank_dep_in")
async def cb_bank_in(c: CallbackQuery, state: FSMContext):
    await state.set_state(St.bank_in)
    await c.message.edit_text("💵 Введи сумму для внесения на счёт:")

@dp.message(St.bank_in)
async def cb_bank_in_amount(m: Message, state: FSMContext):
    amount = parse_amount(m.text)
    if not amount or amount <= 0: await m.answer("❌ Сумма"); return
    u = await db.get_user(m.from_user.id)
    if u["balance"] < amount:
        await m.answer("❌ Мало"); await state.clear(); return
    await db.add_balance(m.from_user.id, -amount)
    await db.update(m.from_user.id, bank_wallet=u["bank_wallet"] + amount)
    await state.clear()
    await m.answer(f"✅ +{fmt_full(amount)}$ на счёт", reply_markup=back_kb("bank"))

@dp.callback_query(F.data == "bank_dep_out")
async def cb_bank_out(c: CallbackQuery, state: FSMContext):
    await state.set_state(St.bank_out)
    await c.message.edit_text("💸 Введи сумму для снятия (3%):")

@dp.message(St.bank_out)
async def cb_bank_out_amount(m: Message, state: FSMContext):
    amount = parse_amount(m.text)
    if not amount or amount <= 0: await m.answer("❌ Сумма"); return
    u = await db.get_user(m.from_user.id)
    if u["bank_wallet"] < amount:
        await m.answer("❌ Мало"); await state.clear(); return
    fee = int(amount * WITHDRAW_FEE); net = amount - fee
    await db.update(m.from_user.id, bank_wallet=u["bank_wallet"] - amount)
    await db.add_balance(m.from_user.id, net)
    await state.clear()
    await m.answer(f"✅ Снято {fmt_full(amount)}$\n💸 Комиссия {fmt_full(fee)}$\n💰 Получено {fmt_full(net)}$",
                   reply_markup=back_kb("bank"))

@dp.callback_query(F.data == "bank_open")
async def cb_bank_open(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    if u["deposit_amount"] > 0:
        await c.answer("❌ Уже есть вклад. Дождись окончания!", show_alert=True); return
    await c.message.edit_text(
        "📈 <b>Вклады</b>\n\nВыбери срок:\n\n"
        "• 1 день — +1%\n• 7 дней — +10%\n• 30 дней — +35%\n\n"
        "⚠️ Максимум 1 вклад. Снять досрочно нельзя.",
        reply_markup=deposits_kb(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("dep_"))
async def cb_dep(c: CallbackQuery, state: FSMContext):
    key = c.data.split("_")[1]
    if key not in DEPOSITS: return
    u = await db.get_user(c.from_user.id)
    if u["deposit_amount"] > 0:
        await c.answer("❌ Уже есть вклад", show_alert=True); return
    d = DEPOSITS[key]
    await state.update_data(dep_key=key)
    await state.set_state(St.dep_amount)
    await c.message.edit_text(
        f"{d['name']} — +{int(d['rate']*100)}%\n\n"
        f"💰 Доступно: {fmt_full(u['bank_wallet'])}$ (с банковского счёта)\n\n"
        f"Введи сумму вклада:")

@dp.message(St.dep_amount)
async def cb_dep_amount(m: Message, state: FSMContext):
    amount = parse_amount(m.text)
    if not amount or amount < 100: await m.answer("❌ Мин 100$"); return
    data = await state.get_data()
    d = DEPOSITS[data["dep_key"]]
    u = await db.get_user(m.from_user.id)
    if u["bank_wallet"] < amount:
        await m.answer(f"❌ На счёте только {fmt_full(u['bank_wallet'])}$"); await state.clear(); return
    await db.update(m.from_user.id,
        bank_wallet=u["bank_wallet"] - amount,
        deposit_amount=amount,
        deposit_end=int(time.time()) + d["seconds"],
        deposit_rate=d["rate"])
    await state.clear()
    await m.answer(f"✅ Вклад открыт: {fmt_full(amount)}$\n📅 Срок: {d['name']}\n💵 Доход: +{fmt_full(int(amount*d['rate']))}$",
                   reply_markup=back_kb("bank"))

@dp.callback_query(F.data == "bank_view")
async def cb_bank_view(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    if u["deposit_amount"] == 0:
        await c.answer("Нет вклада", show_alert=True); return
    left = int(u["deposit_end"] - time.time())
    if left > 0:
        d = left // 86400
        h = (left % 86400) // 3600
        await c.answer(f"⏳ Осталось {d}д {h}ч", show_alert=True); return
    total = int(u["deposit_amount"] * (1 + u["deposit_rate"]))
    await db.add_balance(c.from_user.id, total)
    await db.update(c.from_user.id, deposit_amount=0, deposit_end=0, deposit_rate=0)
    await c.answer(f"✅ Вклад +{fmt_full(total)}$ → баланс", show_alert=True)
    await cb_bank(c)

# ============ КАЗИНО ============
@dp.callback_query(F.data == "casino")
async def cb_casino(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text("🎰 <b>Казино</b>", reply_markup=casino_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "bj_start")
async def cb_bj_start(c: CallbackQuery, state: FSMContext):
    await state.set_state(St.bj_bet)
    await c.message.edit_text("🃏 <b>Блэкджек</b>\n\nВведи ставку:")

@dp.message(St.bj_bet)
async def cb_bj_bet(m: Message, state: FSMContext):
    bet = parse_amount(m.text)
    if not bet or bet < MIN_BET or bet > MAX_BET:
        await m.answer("❌ Ставка"); return
    u = await db.get_user(m.from_user.id)
    if u["balance"] < bet:
        await m.answer("❌ Мало"); await state.clear(); return
    await db.add_balance(m.from_user.id, -bet)
    deck = new_deck(); random.shuffle(deck)
    player = [deck.pop(), deck.pop()]; dealer = [deck.pop(), deck.pop()]
    await state.set_state(St.bj_play)
    await state.update_data(bet=bet, player=player, dealer=dealer, deck=deck, doubled=False)
    pv = hand_value(player)
    if is_blackjack(player):
        if is_blackjack(dealer):
            await db.add_balance(m.from_user.id, bet); await state.clear()
            await m.answer("🃏 Блэкджек у обоих — ничья", reply_markup=casino_kb()); return
        win = int(bet * 2.5)
        await db.add_balance(m.from_user.id, win)
        await db.update(m.from_user.id, wins=u["wins"]+1); await state.clear()
        await m.answer(f"🎉 БЛЭКДЖЕК! +{fmt_full(win-bet)}$", reply_markup=casino_kb(), parse_mode="HTML"); return
    await m.answer(
        f"🃏 Ставка: {fmt_full(bet)}$\n\n👤 {fmt_hand(player)} = <b>{pv}</b>\n🤖 {dealer[0]} ?",
        reply_markup=bj_kb(), parse_mode="HTML")

@dp.callback_query(St.bj_play, F.data == "bj_hit")
async def cb_bj_hit(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    data["player"].append(data["deck"].pop())
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
    await finish_bj(c, state, await state.get_data())

@dp.callback_query(St.bj_play, F.data == "bj_double")
async def cb_bj_double(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if len(data["player"]) != 2 or data["doubled"]:
        await c.answer("Только в начале", show_alert=True); return
    u = await db.get_user(c.from_user.id)
    if u["balance"] < data["bet"]:
        await c.answer("Мало", show_alert=True); return
    await db.add_balance(c.from_user.id, -data["bet"])
    data["bet"] *= 2; data["doubled"] = True
    data["player"].append(data["deck"].pop())
    await state.update_data(**data)
    if hand_value(data["player"]) > 21:
        await db.update(c.from_user.id, losses=u["losses"]+1); await state.clear()
        await c.message.edit_text(f"💥 Перебор! -{fmt_full(data['bet'])}$",
            reply_markup=casino_kb(), parse_mode="HTML"); return
    await finish_bj(c, state, data)

async def finish_bj(c, state, data):
    data["dealer"] = dealer_play(data["dealer"], data["deck"])
    pv, dv, bet = hand_value(data["player"]), hand_value(data["dealer"]), data["bet"]
    u = await db.get_user(c.from_user.id)
    table = f"👤 {fmt_hand(data['player'])} = {pv}\n🤖 {fmt_hand(data['dealer'])} = {dv}\n\n"
    if dv > 21 or pv > dv:
        await db.add_balance(c.from_user.id, bet * 2)
        await db.update(c.from_user.id, wins=u["wins"]+1)
        text = table + f"🎉 +{fmt_full(bet)}$"
    elif pv == dv:
        await db.add_balance(c.from_user.id, bet)
        text = table + "🤝 Ничья"
    else:
        await db.update(c.from_user.id, losses=u["losses"]+1)
        text = table + f"❌ -{fmt_full(bet)}$"
    await state.clear()
    await c.message.edit_text(text, reply_markup=casino_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "rl_start")
async def cb_rl_start(c: CallbackQuery, state: FSMContext):
    await state.set_state(St.rl_bet)
    await c.message.edit_text("🎯 <b>Рулетка</b>\n\nВведи ставку:")

@dp.message(St.rl_bet)
async def cb_rl_bet(m: Message, state: FSMContext):
    bet = parse_amount(m.text)
    if not bet or bet < MIN_BET:
        await m.answer("❌ Ставка"); return
    u = await db.get_user(m.from_user.id)
    if u["balance"] < bet:
        await m.answer("❌ Мало"); await state.clear(); return
    await db.add_balance(m.from_user.id, -bet)
    await state.update_data(bet=bet)
    await m.answer(f"🎯 Ставка: {fmt_full(bet)}$", reply_markup=rl_choice_kb())

@dp.callback_query(St.rl_bet, F.data.startswith("rl_"))
async def cb_rl_result(c: CallbackQuery, state: FSMContext):
    if c.data == "rl_start": return
    choice = c.data.split("_")[1]
    data = await state.get_data(); bet = data["bet"]; await state.clear()
    num = random.randint(0, 36)
    color = "green" if num == 0 else ("red" if num in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36] else "black")
    win, mult = False, 0
    if choice == "red" and color == "red": win, mult = True, 2
    elif choice == "black" and color == "black": win, mult = True, 2
    elif choice == "green" and color == "green": win, mult = True, 14
    elif choice == "even" and num != 0 and num % 2 == 0: win, mult = True, 2
    elif choice == "odd" and num != 0 and num % 2 == 1: win, mult = True, 2
    u = await db.get_user(c.from_user.id)
    emoji = {"red": "🔴", "black": "⚫", "green": "🟢"}[color]
    if win:
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
    await state.set_state(St.dice_bet)
    await c.message.edit_text("🎲 <b>Кости</b>\n\nВведи ставку:")

@dp.message(St.dice_bet)
async def cb_dice_bet(m: Message, state: FSMContext):
    bet = parse_amount(m.text)
    if not bet or bet < MIN_BET:
        await m.answer("❌ Ставка"); return
    u = await db.get_user(m.from_user.id)
    if u["balance"] < bet:
        await m.answer("❌ Мало"); await state.clear(); return
    await db.add_balance(m.from_user.id, -bet)
    await state.update_data(bet=bet)
    await m.answer(f"🎲 Ставка: {fmt_full(bet)}$\nУгадай (x6):", reply_markup=dice_choice_kb())

@dp.callback_query(St.dice_bet, F.data.startswith("dice_"))
async def cb_dice_result(c: CallbackQuery, state: FSMContext):
    if c.data == "dice_start": return
    try: choice = int(c.data.split("_")[1])
    except ValueError: return
    data = await state.get_data(); bet = data["bet"]; await state.clear()
    roll = random.randint(1, 6)
    u = await db.get_user(c.from_user.id)
    if roll == choice:
        payout = bet * 6
        await db.add_balance(c.from_user.id, payout)
        await db.update(c.from_user.id, wins=u["wins"]+1)
        text = f"🎲 <b>{roll}</b>\n\n🎉 +{fmt_full(payout-bet)}$ (x6)"
    else:
        await db.update(c.from_user.id, losses=u["losses"]+1)
        text = f"🎲 <b>{roll}</b>\n\n❌ -{fmt_full(bet)}$"
    await c.message.edit_text(text, reply_markup=casino_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "noop")
async def cb_noop(c: CallbackQuery):
    await c.answer()

# ============ МИНИ-СЕРВЕР ============
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
