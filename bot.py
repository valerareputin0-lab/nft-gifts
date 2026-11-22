import asyncio, time, random, os
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import config
import database as db
from utils import (fmt_full, fmt_btc, parse_amount, parse_list, serialize_list,
                   parse_businesses, serialize_businesses, business_income,
                   total_business_income, total_farm_income, process_passive,
                   new_deck, hand_value, dealer_play, fmt_hand, is_blackjack)
from keyboards import (main_kb, back_kb, profile_kb, jobs_kb, biz_kb, farms_kb,
                       houses_kb, garage_kb, wardrobe_kb, shop_kb, rewards_kb,
                       admin_kb, bank_kb, deposits_kb, casino_kb, bj_kb,
                       rl_choice_kb, dice_choice_kb)
from config import (JOBS, BUSINESSES, FARMS, HOUSES, CARS, CLOTHES, DEPOSITS,
                    MIN_BET, MAX_BET, WITHDRAW_FEE, BTC_PRICE, ADMIN_ID,
                    PASSIVE_CAP_HOURS, SELL_PERCENT, BONUS_AMOUNT, BONUS_COOLDOWN,
                    GARAGE_PRICE, BUSINESS_UPGRADE_COST_MULT, NICK_MIN, NICK_MAX,
                    FARMS_LIMIT)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class St(StatesGroup):
    bj_bet = State(); bj_play = State()
    rl_bet = State()
    dice_bet = State()
    bank_in = State(); bank_out = State()
    dep_amount = State()
    sell_btc = State()
    promo_enter = State()
    admin_give = State(); admin_take = State(); admin_promo = State()
    nick_input = State()

def is_admin(uid): return uid == ADMIN_ID

def get_biz_dict(u):
    """Возвращает dict {id: lvl} или {} если нет бизнеса."""
    b = parse_businesses(u["businesses"])
    if len(b) > 1:
        # на случай старых данных — оставляем первый
        b = {list(b.keys())[0]: list(b.values())[0]}
    return b

def get_farm_info(u):
    """Возвращает (farm_type, count)."""
    lst = parse_list(u["farms"])
    if not lst: return None, 0
    ftype = lst[0]
    return ftype, len(lst)

# ============ НИК ============
async def ask_nick(m, state, source="start"):
    await state.set_state(St.nick_input)
    await state.update_data(nick_from=source)
    await m.answer(
        f"🎭 Придумай ник\n\n"
        f"Правила:\n"
        f"• {NICK_MIN}–{NICK_MAX} символов\n"
        f"• Только буквы и цифры\n"
        f"• Должен быть уникальным")

@dp.message(St.nick_input)
async def process_nick(m: Message, state: FSMContext):
    nick = m.text.strip()
    if not (NICK_MIN <= len(nick) <= NICK_MAX):
        await m.answer(f"❌ Длина: {NICK_MIN}–{NICK_MAX} символов"); return
    if not nick.isalnum():
        await m.answer("❌ Только буквы и цифры"); return
    if await db.is_nick_taken(nick, m.from_user.id):
        await m.answer("❌ Ник уже занят, придумай другой"); return
    await db.set_nick(m.from_user.id, nick)
    data = await state.get_data()
    await state.clear()
    if data.get("nick_from") == "change":
        await m.answer(f"✅ Ник изменён: <b>{nick}</b>", parse_mode="HTML",
                       reply_markup=back_kb("profile"))
    else:
        await m.answer(f"✅ Ник сохранён: <b>{nick}</b>", parse_mode="HTML",
                       reply_markup=main_kb(is_admin(m.from_user.id)))

# ============ СТАРТ ============
@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    u = await db.get_user(m.from_user.id, m.from_user.username)
    if not u.get("nick"):
        await ask_nick(m, state, "start")
        return
    await m.answer(
        f"🎰 <b>Добро пожаловать, {u['nick']}!</b>\n\n"
        f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n\n"
        f"📋 Разделы ниже 👇",
        reply_markup=main_kb(is_admin(m.from_user.id)), parse_mode="HTML")

@dp.callback_query(F.data == "menu")
async def cb_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text("🏠 <b>Главное меню</b>",
        reply_markup=main_kb(is_admin(c.from_user.id)), parse_mode="HTML")

@dp.callback_query(F.data == "change_nick")
async def cb_change_nick(c: CallbackQuery, state: FSMContext):
    await ask_nick(c.message, state, "change")
    await c.answer()

# ============ ПРОФИЛЬ ============
@dp.callback_query(F.data == "profile")
async def cb_profile(c: CallbackQuery):
    uid = c.from_user.id
    await process_passive(uid)
    u = await db.get_user(uid)
    biz = get_biz_dict(u)
    ftype, fcount = get_farm_info(u)
    houses = parse_list(u["houses"])
    cars = parse_list(u["garage"])
    worn = parse_list(u["clothes_worn"])

    house_bg = "🏙 Улица"
    if houses:
        house_bg = HOUSES.get(houses[0], {}).get("name", "🏙")
    car_bg = f"\n🚗 {CARS.get(cars[-1], {}).get('name', '—')}" if cars else ""
    worn_bg = ("\n👕 " + ", ".join(CLOTHES.get(w, {}).get("name", "?") for w in worn)) if worn else ""

    text = (
        f"👤 <b>Профиль</b>\n"
        f"🎭 Ник: <b>{u['nick']}</b>\n"
        f"🆔 ID: <code>{uid}</code>\n\n"
        f"🏠 Фон: {house_bg}{car_bg}{worn_bg}\n\n"
        f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n"
        f"₿ BTC: <b>{fmt_btc(u['btc'])}</b> (≈{fmt_full(int(u['btc']*BTC_PRICE))}$)\n"
        f"🏦 В банке: <b>{fmt_full(u['bank_wallet'])}$</b>\n\n"
        f"📊 <b>Имущество:</b>\n"
        f"💼 Бизнес: {list(biz.keys())[0] if biz else '—'}\n"
        f"⛏ Ферм: {fcount}\n"
        f"🏠 Дом: {'есть' if houses else '—'}\n\n"
        f"🎮 Побед: {u['wins']} | ❌ Поражений: {u['losses']}")
    if u["deposit_amount"] > 0:
        left = int(u["deposit_end"] - time.time())
        if left > 0:
            text += f"\n\n📈 Вклад: {fmt_full(u['deposit_amount'])}$ до {left//3600}ч"
    await c.message.edit_text(text, reply_markup=profile_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "top")
async def cb_top(c: CallbackQuery):
    top = await db.get_top(10)
    medals = ["🥇","🥈","🥉"] + ["▫️"]*7
    lines = ["🏆 <b>Топ игроков</b>\n"]
    for i, u in enumerate(top):
        name = u.get("nick") or f"@{u['username']}" if u.get("username") else (u.get("nick") or "player")
        lines.append(f"{medals[i]} {i+1}. {name} — <b>{fmt_full(u['balance'])}$</b>")
    await c.message.edit_text("\n".join(lines), reply_markup=back_kb(), parse_mode="HTML")

# ============ РАБОТЫ ============
@dp.callback_query(F.data == "jobs")
async def cb_jobs(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    times = {"courier": u["last_courier"], "builder": u["last_builder"], "programmer": u["last_programmer"]}
    await c.message.edit_text("💼 <b>Работы</b>\n\nВыбери работу:",
        reply_markup=jobs_kb(times), parse_mode="HTML")

@dp.callback_query(F.data.startswith("work_"))
async def cb_work(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in JOBS: return
    job = JOBS[key]
    u = await db.get_user(c.from_user.id)
    last_field = f"last_{key}"
    now = int(time.time())
    if now - u[last_field] < job["cooldown"]:
        left = int(job["cooldown"] - (now - u[last_field]))
        await c.answer(f"⏳ {left//60}м {left%60}с", show_alert=True); return
    await db.add_balance(c.from_user.id, job["income"])
    await db.update(c.from_user.id, **{last_field: now})
    await c.answer(f"✅ +{fmt_full(job['income'])}$", show_alert=True)
    await cb_jobs(c)

# ============ БИЗНЕСЫ (1 активный) ============
@dp.callback_query(F.data == "biz")
async def cb_biz(c: CallbackQuery):
    await process_passive(c.from_user.id)
    u = await db.get_user(c.from_user.id)
    biz = get_biz_dict(u)
    if biz:
        bid = list(biz.keys())[0]
        lvl = biz[bid]
        b = BUSINESSES[bid]
        inc = business_income(bid, lvl)
        text = (f"🏢 <b>Твой бизнес</b>\n\n"
                f"{b['name']} Lvl {lvl}\n"
                f"📈 Доход: <b>+{fmt_full(inc)}$/час</b>\n"
                f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n"
                f"⏱ Лимит: {PASSIVE_CAP_HOURS}ч\n\n"
                f"Продажа за {int(SELL_PERCENT*100)}% цены.")
    else:
        text = (f"🏢 <b>Бизнесы</b>\n\n"
                f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n\n"
                f"Можно купить <b>1 бизнес</b>. Выбирай:")
    await c.message.edit_text(text, reply_markup=biz_kb(biz), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buybiz_"))
async def cb_buy_biz(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in BUSINESSES: return
    b = BUSINESSES[key]
    u = await db.get_user(c.from_user.id)
    if get_biz_dict(u):
        await c.answer("У тебя уже есть бизнес!", show_alert=True); return
    if u["balance"] < b["price"]:
        await c.answer("❌ Мало денег!", show_alert=True); return
    await db.add_balance(c.from_user.id, -b["price"])
    await db.update(c.from_user.id, businesses=serialize_businesses({key: 1}))
    await c.answer(f"✅ Куплен {b['name']}!", show_alert=True)
    await cb_biz(c)

@dp.callback_query(F.data.startswith("upbiz_"))
async def cb_upgrade_biz(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in BUSINESSES: return
    b = BUSINESSES[key]
    u = await db.get_user(c.from_user.id)
    biz = get_biz_dict(u)
    if key not in biz:
        await c.answer("Нет бизнеса", show_alert=True); return
    lvl = biz[key]
    if lvl >= 3:
        await c.answer("Максимум!", show_alert=True); return
    cost = int(b["price"] * BUSINESS_UPGRADE_COST_MULT[lvl + 1])
    if u["balance"] < cost:
        await c.answer(f"❌ Нужно {fmt_full(cost)}$", show_alert=True); return
    await db.add_balance(c.from_user.id, -cost)
    await db.update(c.from_user.id, businesses=serialize_businesses({key: lvl + 1}))
    await c.answer(f"✅ Lvl {lvl+1}!", show_alert=True)
    await cb_biz(c)

@dp.callback_query(F.data == "biz_collect")
async def cb_biz_collect(c: CallbackQuery):
    inc, _ = await process_passive(c.from_user.id)
    if inc > 0:
        await c.answer(f"💰 Собрано +{fmt_full(inc)}$", show_alert=True)
    else:
        await c.answer("Пока нечего собирать (мин. 1 минута)", show_alert=True)
    await cb_biz(c)

@dp.callback_query(F.data.startswith("sellbiz_"))
async def cb_sell_biz(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in BUSINESSES: return
    u = await db.get_user(c.from_user.id)
    biz = get_biz_dict(u)
    if key not in biz:
        await c.answer("Нет бизнеса", show_alert=True); return
    await process_passive(c.from_user.id)
    sell = int(BUSINESSES[key]["price"] * SELL_PERCENT)
    await db.add_balance(c.from_user.id, sell)
    await db.update(c.from_user.id, businesses="")
    await c.answer(f"💸 Продан за {fmt_full(sell)}$", show_alert=True)
    await cb_biz(c)

# ============ ФЕРМЫ (тип фиксируется после первой покупки) ============
@dp.callback_query(F.data == "farms")
async def cb_farms(c: CallbackQuery):
    await process_passive(c.from_user.id)
    u = await db.get_user(c.from_user.id)
    ftype, fcount = get_farm_info(u)
    if ftype:
        f = FARMS[ftype]
        total = total_farm_income(parse_list(u["farms"]))
        text = (f"⛏ <b>Твои фермы</b>\n\n"
                f"{f['name']} × {fcount} / {FARMS_LIMIT}\n"
                f"📈 Доход: <b>{total:.2f}₿/час</b> (≈{fmt_full(int(total*BTC_PRICE))}$/ч)\n"
                f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n"
                f"₿ BTC: <b>{fmt_btc(u['btc'])}</b>\n"
                f"💱 Курс: 1₿ = {fmt_full(BTC_PRICE)}$\n\n"
                f"⚠️ Сменить тип нельзя. Продай все фермы — потом выберешь заново.")
    else:
        text = (f"⛏ <b>Фермы</b>\n\n"
                f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n\n"
                f"⚠️ Выбери <b>тип фермы один раз</b> — потом сможешь покупать только его (до {FARMS_LIMIT} шт).")
    await c.message.edit_text(text, reply_markup=farms_kb(ftype, fcount, u["btc"]), parse_mode="HTML")

@dp.callback_query(F.data.startswith("buyfarm_"))
async def cb_buy_farm(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in FARMS: return
    f = FARMS[key]
    u = await db.get_user(c.from_user.id)
    ftype, fcount = get_farm_info(u)
    if ftype and ftype != key:
        await c.answer("❌ Можно покупать только твой тип!", show_alert=True); return
    if fcount >= FARMS_LIMIT:
        await c.answer(f"❌ Лимит {FARMS_LIMIT}!", show_alert=True); return
    if u["balance"] < f["price"]:
        await c.answer("❌ Мало денег!", show_alert=True); return
    await db.add_balance(c.from_user.id, -f["price"])
    lst = parse_list(u["farms"])
    lst.append(key)
    await db.update(c.from_user.id, farms=serialize_list(lst))
    await c.answer(f"✅ Куплена! ({len(lst)}/{FARMS_LIMIT})", show_alert=True)
    await cb_farms(c)

@dp.callback_query(F.data == "sell_one_farm")
async def cb_sell_one_farm(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    ftype, fcount = get_farm_info(u)
    if not ftype or fcount == 0:
        await c.answer("Нет ферм", show_alert=True); return
    await process_passive(c.from_user.id)
    sell = int(FARMS[ftype]["price"] * SELL_PERCENT)
    await db.add_balance(c.from_user.id, sell)
    lst = parse_list(u["farms"])
    lst.pop()
    await db.update(c.from_user.id, farms=serialize_list(lst))
    await c.answer(f"💸 Продана 1 ферма (+{fmt_full(sell)}$). Осталось {len(lst)}", show_alert=True)
    await cb_farms(c)

@dp.callback_query(F.data == "farms_sellbtc")
async def cb_farms_sellbtc(c: CallbackQuery, state: FSMContext):
    u = await db.get_user(c.from_user.id)
    if u["btc"] < 0.001:
        await c.answer("Мало BTC", show_alert=True); return
    await state.set_state(St.sell_btc)
    await c.message.edit_text(
        f"₿ У тебя {fmt_btc(u['btc'])} BTC\n"
        f"Курс: 1₿ = {fmt_full(BTC_PRICE)}$\n\nСколько BTC продать?")

# ============ ДОМА (1 активный) ============
@dp.callback_query(F.data == "houses")
async def cb_houses(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    houses = parse_list(u["houses"])
    if houses:
        hid = houses[0]
        h = HOUSES[hid]
        text = (f"🏠 <b>Твой дом</b>\n\n"
                f"{h['name']}\n"
                f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n\n"
                f"Доступно: Гараж, Шкаф, продажа дома.")
        await c.message.edit_text(text, reply_markup=houses_kb(True, hid), parse_mode="HTML")
    else:
        text = (f"🏠 <b>Дома</b>\n\n"
                f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n\n"
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
    await c.answer(f"💸 Продан за {fmt_full(sell)}$", show_alert=True)
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
        await c.answer("Сначала купи гараж!", show_alert=True); return
    cars = parse_list(u["garage"])
    if key in cars:
        await c.answer("Уже куплено!", show_alert=True); return
    if u["balance"] < car["price"]:
        await c.answer("❌ Мало денег!", show_alert=True); return
    await db.add_balance(c.from_user.id, -car["price"])
    cars.append(key)
    await db.update(c.from_user.id, garage=serialize_list(cars))
    await c.answer(f"✅ Куплен {car['name']}!", show_alert=True)
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
    await c.answer(f"💸 Продана за {fmt_full(sell)}$", show_alert=True)
    await cb_garage(c)

# ============ ШКАФ ============
@dp.callback_query(F.data == "wardrobe")
async def cb_wardrobe(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    if not parse_list(u["houses"]):
        await c.answer("Сначала купи дом!", show_alert=True); return
    await c.message.edit_text(
        f"👕 <b>Шкаф</b> (бесплатно)\n\n💰 Баланс: <b>{fmt_full(u['balance'])}$</b>",
        reply_markup=wardrobe_kb(parse_list(u["wardrobe"]), parse_list(u["clothes_worn"])),
        parse_mode="HTML")

@dp.callback_query(F.data.startswith("buycloth_"))
async def cb_buy_cloth(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in CLOTHES: return
    cl = CLOTHES[key]
    u = await db.get_user(c.from_user.id)
    owned = parse_list(u["wardrobe"])
    if key in owned:
        await c.answer("Уже куплено!", show_alert=True); return
    if u["balance"] < cl["price"]:
        await c.answer("❌ Мало денег!", show_alert=True); return
    await db.add_balance(c.from_user.id, -cl["price"])
    owned.append(key)
    await db.update(c.from_user.id, wardrobe=serialize_list(owned))
    await c.answer(f"✅ {cl['name']} куплено", show_alert=True)
    # Возвращаемся откуда пришли
    if c.message.text and "Шкаф" in c.message.text:
        await cb_wardrobe(c)
    else:
        await cb_shop(c)

@dp.callback_query(F.data.startswith("wear_"))
async def cb_wear(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in CLOTHES: return
    u = await db.get_user(c.from_user.id)
    worn = parse_list(u["clothes_worn"])
    if key in worn:
        worn.remove(key); await c.answer("Снято", show_alert=True)
    else:
        worn.append(key); await c.answer("Надето", show_alert=True)
    await db.update(c.from_user.id, clothes_worn=serialize_list(worn))
    await cb_wardrobe(c)

# ============ МАГАЗИН ============
@dp.callback_query(F.data == "shop")
async def cb_shop(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    await c.message.edit_text(
        f"🛒 <b>Магазин одежды</b>\n\n"
        f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n\n"
        f"Купленная одежда → 🏠 Дома → 👕 Шкаф",
        reply_markup=shop_kb(parse_list(u["wardrobe"])), parse_mode="HTML")

# ============ НАГРАДЫ ============
@dp.callback_query(F.data == "rewards")
async def cb_rewards(c: CallbackQuery):
    await c.message.edit_text(
        "🎁 <b>Награды</b>\n\n"
        "🎁 Бонус — 5.000$ каждые 12 часов\n"
        "🎟 Промокод — введи секретный код",
        reply_markup=rewards_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "bonus")
async def cb_bonus(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    now = int(time.time())
    diff = now - u["last_bonus"]
    if diff < BONUS_COOLDOWN:
        left = BONUS_COOLDOWN - diff
        await c.answer(f"⏰ Через {left//3600}ч {(left%3600)//60}м", show_alert=True); return
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
        await m.answer("❌ Промокод не найден", reply_markup=back_kb("rewards")); await state.clear(); return
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
        await c.answer("Только для админа", show_alert=True); return
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
    except ValueError: await m.answer("❌ Лимит числом"); return
    if not amount or amount <= 0 or limit <= 0:
        await m.answer("❌ Данные"); return
    await db.create_promo(code, amount, limit)
    await state.clear()
    await m.answer(
        f"✅ Промокод:\n🎟 <code>{code}</code>\n💰 {fmt_full(amount)}$\n📊 {limit}",
        reply_markup=back_kb("admin_panel"), parse_mode="HTML")

# ============ БАНК ============
@dp.callback_query(F.data == "bank")
async def cb_bank(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    dep = ""
    if u["deposit_amount"] > 0:
        left = int(u["deposit_end"] - time.time())
        if left > 0: dep = f"\n📈 Вклад: {fmt_full(u['deposit_amount'])}$ ({left//3600}ч)"
        else: dep = f"\n📈 Вклад готов: {fmt_full(int(u['deposit_amount']*(1+u['deposit_rate'])))}"
    await c.message.edit_text(
        f"🏦 <b>Банк</b>\n\n💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n"
        f"🏦 Счёт: <b>{fmt_full(u['bank_wallet'])}$</b>\n"
        f"₿ BTC: <b>{fmt_btc(u['btc'])}</b>{dep}\n\n💸 Комиссия снятия: 3%",
        reply_markup=bank_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "bank_dep_in")
async def cb_bank_in(c: CallbackQuery, state: FSMContext):
    await state.set_state(St.bank_in)
    await c.message.edit_text("💵 Введи сумму для внесения:")

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
    await m.answer(f"✅ Внесено {fmt_full(amount)}$", reply_markup=back_kb("bank"))

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
    fee = int(amount * WITHDRAW_FEE)
    net = amount - fee
    await db.update(m.from_user.id, bank_wallet=u["bank_wallet"] - amount)
    await db.add_balance(m.from_user.id, net)
    await state.clear()
    await m.answer(f"✅ Снято {fmt_full(amount)}$\n💸 {fmt_full(fee)}$\n💰 {fmt_full(net)}$",
                   reply_markup=back_kb("bank"))

@dp.callback_query(F.data == "bank_open")
async def cb_bank_open(c: CallbackQuery):
    await c.message.edit_text("📈 <b>Вклады</b>", reply_markup=deposits_kb(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("dep_"))
async def cb_dep(c: CallbackQuery, state: FSMContext):
    key = c.data.split("_")[1]
    if key not in DEPOSITS: return
    u = await db.get_user(c.from_user.id)
    if u["deposit_amount"] > 0 and u["deposit_end"] > time.time():
        await c.answer("❌ Активный вклад", show_alert=True); return
    d = DEPOSITS[key]
    await state.update_data(dep_key=key)
    await state.set_state(St.dep_amount)
    await c.message.edit_text(f"{d['name']} — {int(d['rate']*100)}%\nВведи сумму:")

@dp.message(St.dep_amount)
async def cb_dep_amount(m: Message, state: FSMContext):
    amount = parse_amount(m.text)
    if not amount or amount < 100: await m.answer("❌ Мин 100$"); return
    data = await state.get_data()
    d = DEPOSITS[data["dep_key"]]
    u = await db.get_user(m.from_user.id)
    if u["balance"] < amount:
        await m.answer("❌ Мало"); await state.clear(); return
    await db.add_balance(m.from_user.id, -amount)
    await db.update(m.from_user.id, deposit_amount=amount,
        deposit_end=int(time.time()) + d["seconds"], deposit_rate=d["rate"])
    await state.clear()
    await m.answer(f"✅ Вклад: {fmt_full(amount)}$ на {d['name']}", reply_markup=back_kb("bank"))

@dp.callback_query(F.data == "bank_view")
async def cb_bank_view(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    if u["deposit_amount"] == 0:
        await c.answer("Нет вклада", show_alert=True); return
    left = int(u["deposit_end"] - time.time())
    if left > 0:
        await c.answer(f"⏳ {left//3600}ч {left%3600//60}м", show_alert=True); return
    total = int(u["deposit_amount"] * (1 + u["deposit_rate"]))
    await db.add_balance(c.from_user.id, total)
    await db.update(c.from_user.id, deposit_amount=0, deposit_end=0, deposit_rate=0)
    await c.answer(f"✅ +{fmt_full(total)}$", show_alert=True)
    await cb_bank(c)

@dp.message(St.sell_btc)
async def cb_sell_btc_amount(m: Message, state: FSMContext):
    try: amount = float(m.text.replace(",", "."))
    except: await m.answer("❌ Число"); return
    u = await db.get_user(m.from_user.id)
    if amount <= 0 or amount > u["btc"]:
        await m.answer("❌ Неверное количество"); return
    money = int(amount * BTC_PRICE)
    await db.update(m.from_user.id, btc=u["btc"] - amount)
    await db.add_balance(m.from_user.id, money)
    await state.clear()
    await m.answer(f"✅ {amount:.4f}₿ → {fmt_full(money)}$", reply_markup=back_kb("bank"))

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
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    await state.set_state(St.bj_play)
    await state.update_data(bet=bet, player=player, dealer=dealer, deck=deck, doubled=False)
    pv = hand_value(player)
    if is_blackjack(player):
        if is_blackjack(dealer):
            await db.add_balance(m.from_user.id, bet)
            await state.clear()
            await m.answer("🃏 Блэкджек у обоих — ничья", reply_markup=casino_kb()); return
        win = int(bet * 2.5)
        await db.add_balance(m.from_user.id, win)
        await db.update(m.from_user.id, wins=u["wins"]+1)
        await state.clear()
        await m.answer(f"🎉 БЛЭКДЖЕК! +{fmt_full(win-bet)}$", reply_markup=casino_kb(), parse_mode="HTML")
        return
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
        await db.update(c.from_user.id, losses=u["losses"]+1)
        await state.clear()
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
        await db.update(c.from_user.id, losses=u["losses"]+1)
        await state.clear()
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
