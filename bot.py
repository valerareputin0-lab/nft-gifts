import asyncio, time, random
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import config
import database as db
from utils import (fmt_full, fmt_btc, parse_amount, parse_list, serialize_list,
                   process_passive, new_deck, hand_value, dealer_play, fmt_hand,
                   is_blackjack)
from keyboards import (main_kb, back_kb, jobs_kb, biz_kb, farms_kb, houses_kb,
                       bank_kb, deposits_kb, casino_kb, bj_kb, rl_choice_kb,
                       dice_choice_kb)
from config import (JOBS, BUSINESSES, FARMS, HOUSES, DEPOSITS, MIN_BET, MAX_BET,
                    WITHDRAW_FEE, BTC_PRICE, ADMIN_ID, PASSIVE_CAP_HOURS)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class St(StatesGroup):
    bj_bet = State(); bj_play = State()
    rl_bet = State()
    dice_bet = State()
    bank_in = State(); bank_out = State()
    dep_open = State(); dep_amount = State()
    sell_btc = State()


# ============ СТАРТ ============
@dp.message(Command("start"))
async def cmd_start(m: Message):
    await db.get_user(m.from_user.id, m.from_user.username)
    await m.answer(
        f"🎰 <b>Добро пожаловать!</b>\n\n"
        f"💰 Стартовый баланс: <b>{fmt_full(config.START_BALANCE)}$</b>\n\n"
        f"📋 Разделы:\n"
        f"💼 Работы • 🏢 Бизнесы • ⛏ Фермы\n"
        f"🏠 Дома • 🏦 Банк • 🎰 Казино",
        reply_markup=main_kb(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "menu")
async def cb_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text("🏠 <b>Главное меню</b>", reply_markup=main_kb(), parse_mode="HTML")


# ============ ПРОФИЛЬ ============
@dp.callback_query(F.data == "profile")
async def cb_profile(c: CallbackQuery):
    uid = c.from_user.id
    await process_passive(uid)
    u = await db.get_user(uid)
    biz = parse_list(u["businesses"])
    farms = parse_list(u["farms"])
    houses = parse_list(u["houses"])

    house_bg = "🏙 Улица"
    if houses:
        last_house = houses[-1]
        house_bg = HOUSES.get(last_house, {}).get("name", "🏙")

    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"🏠 Фон: {house_bg}\n"
        f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n"
        f"₿ BTC: <b>{fmt_btc(u['btc'])}</b> (≈{fmt_full(int(u['btc']*BTC_PRICE))}$)\n"
        f"🏦 В банке: <b>{fmt_full(u['bank_wallet'])}$</b>\n\n"
        f"📊 <b>Имущество:</b>\n"
        f"💼 Бизнесов: {len(biz)}\n"
        f"⛏ Ферм: {len(farms)}\n"
        f"🏠 Домов: {len(houses)}\n\n"
        f"🎮 Побед: {u['wins']} | ❌ Поражений: {u['losses']}"
    )

    if u["deposit_amount"] > 0:
        left = int(u["deposit_end"] - time.time())
        if left > 0:
            text += f"\n\n📈 Вклад: {fmt_full(u['deposit_amount'])}$ до конца: {left//3600}ч"

    await c.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")


# ============ ТОП ============
@dp.callback_query(F.data == "top")
async def cb_top(c: CallbackQuery):
    top = await db.get_top(10)
    medals = ["🥇","🥈","🥉"] + ["▫️"]*7
    lines = ["🏆 <b>Топ игроков</b>\n"]
    for i, u in enumerate(top):
        lines.append(f"{medals[i]} {i+1}. @{u['username'] or 'player'} — <b>{fmt_full(u['balance'])}$</b>")
    await c.message.edit_text("\n".join(lines), reply_markup=back_kb(), parse_mode="HTML")


# ============ РАБОТЫ ============
@dp.callback_query(F.data == "jobs")
async def cb_jobs(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    times = {
        "courier": u["last_courier"],
        "builder": u["last_builder"],
        "programmer": u["last_programmer"],
    }
    await c.message.edit_text(
        "💼 <b>Работы</b>\n\nВыбери работу (кнопка обновится через время):",
        reply_markup=jobs_kb(times), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("work_"))
async def cb_work(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in JOBS:
        return
    job = JOBS[key]
    u = await db.get_user(c.from_user.id)
    last_field = f"last_{key}"
    last = u[last_field]
    now = int(time.time())
    if now - last < job["cooldown"]:
        left = int(job["cooldown"] - (now - last))
        await c.answer(f"⏳ {left//60}м {left%60}с", show_alert=True)
        return
    await db.add_balance(c.from_user.id, job["income"])
    await db.update(c.from_user.id, **{last_field: now})
    await c.answer(f"✅ +{fmt_full(job['income'])}$", show_alert=True)
    await cb_jobs(c)


# ============ БИЗНЕСЫ ============
@dp.callback_query(F.data == "biz")
async def cb_biz(c: CallbackQuery):
    await process_passive(c.from_user.id)
    u = await db.get_user(c.from_user.id)
    owned = parse_list(u["businesses"])
    total = sum(BUSINESSES[b]["income"] for b in owned)
    await c.message.edit_text(
        f"🏢 <b>Бизнесы</b>\n\n"
        f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n"
        f"📈 Доход: <b>+{fmt_full(total)}$/час</b>\n"
        f"⏱ Лимит накопления: {PASSIVE_CAP_HOURS}ч\n\n"
        f"Выбери что купить:",
        reply_markup=biz_kb(owned, u["balance"]), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("buybiz_"))
async def cb_buy_biz(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in BUSINESSES: return
    b = BUSINESSES[key]
    u = await db.get_user(c.from_user.id)
    owned = parse_list(u["businesses"])
    if key in owned:
        await c.answer("Уже куплено!", show_alert=True); return
    if u["balance"] < b["price"]:
        await c.answer("❌ Мало денег!", show_alert=True); return
    await db.add_balance(c.from_user.id, -b["price"])
    owned.append(key)
    await db.update(c.from_user.id, businesses=serialize_list(owned))
    await c.answer(f"✅ Куплен {b['name']}!", show_alert=True)
    await cb_biz(c)


# ============ ФЕРМЫ ============
@dp.callback_query(F.data == "farms")
async def cb_farms(c: CallbackQuery):
    await process_passive(c.from_user.id)
    u = await db.get_user(c.from_user.id)
    owned = parse_list(u["farms"])
    total = sum(FARMS[f]["btc_per_hour"] for f in owned)
    await c.message.edit_text(
        f"⛏ <b>Фермы</b>\n\n"
        f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n"
        f"₿ BTC: <b>{fmt_btc(u['btc'])}</b>\n"
        f"📈 Фарм: <b>{total:.2f}₿/час</b> (≈{fmt_full(int(total*BTC_PRICE))}$/ч)\n"
        f"💱 Курс: 1₿ = {fmt_full(BTC_PRICE)}$",
        reply_markup=farms_kb(owned), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("buyfarm_"))
async def cb_buy_farm(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in FARMS: return
    f = FARMS[key]
    u = await db.get_user(c.from_user.id)
    owned = parse_list(u["farms"])
    if key in owned:
        await c.answer("Уже куплено!", show_alert=True); return
    if u["balance"] < f["price"]:
        await c.answer("❌ Мало денег!", show_alert=True); return
    await db.add_balance(c.from_user.id, -f["price"])
    owned.append(key)
    await db.update(c.from_user.id, farms=serialize_list(owned))
    await c.answer(f"✅ Куплена {f['name']}!", show_alert=True)
    await cb_farms(c)


# ============ ДОМА ============
@dp.callback_query(F.data == "houses")
async def cb_houses(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    owned = parse_list(u["houses"])
    await c.message.edit_text(
        f"🏠 <b>Дома</b>\n\n"
        f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n\n"
        f"Купи дом — он станет твоим фоном в профиле!",
        reply_markup=houses_kb(owned), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("buyhouse_"))
async def cb_buy_house(c: CallbackQuery):
    key = c.data.split("_")[1]
    if key not in HOUSES: return
    h = HOUSES[key]
    u = await db.get_user(c.from_user.id)
    owned = parse_list(u["houses"])
    if key in owned:
        await c.answer("Уже куплено!", show_alert=True); return
    if u["balance"] < h["price"]:
        await c.answer("❌ Мало денег!", show_alert=True); return
    await db.add_balance(c.from_user.id, -h["price"])
    owned.append(key)
    await db.update(c.from_user.id, houses=serialize_list(owned))
    await c.answer(f"✅ Куплен {h['name']}!", show_alert=True)
    await cb_houses(c)


# ============ БАНК ============
@dp.callback_query(F.data == "bank")
async def cb_bank(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    dep_info = ""
    if u["deposit_amount"] > 0:
        left = int(u["deposit_end"] - time.time())
        if left > 0:
            dep_info = f"\n📈 Вклад: {fmt_full(u['deposit_amount'])}$ (осталось {left//3600}ч)"
        else:
            dep_info = f"\n📈 Вклад готов к снятию! {fmt_full(int(u['deposit_amount']*(1+u['deposit_rate'])))}"

    await c.message.edit_text(
        f"🏦 <b>Банк</b>\n\n"
        f"💰 Баланс: <b>{fmt_full(u['balance'])}$</b>\n"
        f"🏦 Счёт: <b>{fmt_full(u['bank_wallet'])}$</b>\n"
        f"₿ BTC: <b>{fmt_btc(u['btc'])}</b>{dep_info}\n\n"
        f"💸 Комиссия снятия: 3%",
        reply_markup=bank_kb(), parse_mode="HTML"
    )

@dp.callback_query(F.data == "bank_dep_in")
async def cb_bank_in(c: CallbackQuery, state: FSMContext):
    await state.set_state(St.bank_in)
    await c.message.edit_text("💵 Введи сумму для внесения (например 1кк):")

@dp.message(St.bank_in)
async def cb_bank_in_amount(m: Message, state: FSMContext):
    amount = parse_amount(m.text)
    if not amount or amount <= 0:
        await m.answer("❌ Неверная сумма"); return
    u = await db.get_user(m.from_user.id)
    if u["balance"] < amount:
        await m.answer("❌ Недостаточно средств"); await state.clear(); return
    await db.add_balance(m.from_user.id, -amount)
    await db.update(m.from_user.id, bank_wallet=u["bank_wallet"] + amount)
    await state.clear()
    await m.answer(f"✅ Внесено {fmt_full(amount)}$", reply_markup=back_kb("bank"))

@dp.callback_query(F.data == "bank_dep_out")
async def cb_bank_out(c: CallbackQuery, state: FSMContext):
    await state.set_state(St.bank_out)
    await c.message.edit_text("💸 Введи сумму для снятия (3% комиссия):")

@dp.message(St.bank_out)
async def cb_bank_out_amount(m: Message, state: FSMContext):
    amount = parse_amount(m.text)
    if not amount or amount <= 0:
        await m.answer("❌ Неверная сумма"); return
    u = await db.get_user(m.from_user.id)
    if u["bank_wallet"] < amount:
        await m.answer("❌ На счёте мало денег"); await state.clear(); return
    fee = int(amount * WITHDRAW_FEE)
    net = amount - fee
    await db.update(m.from_user.id, bank_wallet=u["bank_wallet"] - amount)
    await db.add_balance(m.from_user.id, net)
    await state.clear()
    await m.answer(
        f"✅ Снято {fmt_full(amount)}$\n💸 Комиссия: {fmt_full(fee)}$\n💰 Получено: {fmt_full(net)}$",
        reply_markup=back_kb("bank")
    )

@dp.callback_query(F.data == "bank_open")
async def cb_bank_open(c: CallbackQuery):
    await c.message.edit_text(
        "📈 <b>Вклады</b>\n\nВыбери срок:",
        reply_markup=deposits_kb(), parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("dep_"))
async def cb_dep(c: CallbackQuery, state: FSMContext):
    key = c.data.split("_")[1]
    if key not in DEPOSITS: return
    u = await db.get_user(c.from_user.id)
    if u["deposit_amount"] > 0 and u["deposit_end"] > time.time():
        await c.answer("❌ Уже есть активный вклад", show_alert=True); return
    d = DEPOSITS[key]
    await state.update_data(dep_key=key)
    await state.set_state(St.dep_amount)
    await c.message.edit_text(f"{d['name']} — {int(d['rate']*100)}%\n\nВведи сумму вклада:")

@dp.message(St.dep_amount)
async def cb_dep_amount(m: Message, state: FSMContext):
    amount = parse_amount(m.text)
    if not amount or amount < 100:
        await m.answer("❌ Мин. 100$"); return
    data = await state.get_data()
    key = data["dep_key"]
    d = DEPOSITS[key]
    u = await db.get_user(m.from_user.id)
    if u["balance"] < amount:
        await m.answer("❌ Недостаточно средств"); await state.clear(); return
    await db.add_balance(m.from_user.id, -amount)
    await db.update(m.from_user.id,
        deposit_amount=amount,
        deposit_end=int(time.time()) + d["seconds"],
        deposit_rate=d["rate"])
    await state.clear()
    await m.answer(f"✅ Вклад открыт: {fmt_full(amount)}$ на {d['name']}",
                   reply_markup=back_kb("bank"))

@dp.callback_query(F.data == "bank_view")
async def cb_bank_view(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    if u["deposit_amount"] == 0:
        await c.answer("Нет активного вклада", show_alert=True); return
    left = int(u["deposit_end"] - time.time())
    if left > 0:
        await c.answer(f"⏳ Осталось {left//3600}ч {left%3600//60}м", show_alert=True); return
    total = int(u["deposit_amount"] * (1 + u["deposit_rate"]))
    await db.add_balance(c.from_user.id, total)
    await db.update(c.from_user.id, deposit_amount=0, deposit_end=0, deposit_rate=0)
    await c.answer(f"✅ Вклад закрыт: +{fmt_full(total)}$", show_alert=True)
    await cb_bank(c)

@dp.callback_query(F.data == "bank_sell_btc")
async def cb_sell_btc(c: CallbackQuery, state: FSMContext):
    u = await db.get_user(c.from_user.id)
    if u["btc"] < 0.001:
        await c.answer("Мало BTC", show_alert=True); return
    await state.set_state(St.sell_btc)
    await c.message.edit_text(
        f"₿ У тебя {fmt_btc(u['btc'])} BTC\n"
        f"Курс: 1₿ = {fmt_full(BTC_PRICE)}$\n\n"
        f"Сколько BTC продать? (например 10.5)"
    )

@dp.message(St.sell_btc)
async def cb_sell_btc_amount(m: Message, state: FSMContext):
    try:
        amount = float(m.text.replace(",", "."))
    except:
        await m.answer("❌ Неверное число"); return
    u = await db.get_user(m.from_user.id)
    if amount <= 0 or amount > u["btc"]:
        await m.answer("❌ Неверное количество"); return
    money = int(amount * BTC_PRICE)
    await db.update(m.from_user.id, btc=u["btc"] - amount)
    await db.add_balance(m.from_user.id, money)
    await state.clear()
    await m.answer(f"✅ Продано {amount:.4f}₿ за {fmt_full(money)}$",
                   reply_markup=back_kb("bank"))


# ============ КАЗИНО ============
@dp.callback_query(F.data == "casino")
async def cb_casino(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text(
        "🎰 <b>Казино</b>\n\nВыбери игру:",
        reply_markup=casino_kb(), parse_mode="HTML"
    )


# --- БЛЭКДЖЕК ---
@dp.callback_query(F.data == "bj_start")
async def cb_bj_start(c: CallbackQuery, state: FSMContext):
    await state.set_state(St.bj_bet)
    await c.message.edit_text(
        f"🃏 <b>Блэкджек</b>\n\n"
        f"Введи ставку (например 1000 или 1кк):\n"
        f"Мин: {fmt_full(MIN_BET)}$ | Макс: 10кккк"
    )

@dp.message(St.bj_bet)
async def cb_bj_bet(m: Message, state: FSMContext):
    bet = parse_amount(m.text)
    if not bet or bet < MIN_BET or bet > MAX_BET:
        await m.answer("❌ Неверная ставка"); return
    u = await db.get_user(m.from_user.id)
    if u["balance"] < bet:
        await m.answer("❌ Недостаточно средств"); await state.clear(); return

    await db.add_balance(m.from_user.id, -bet)
    deck = new_deck(); random.shuffle(deck)
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]

    await state.set_state(St.bj_play)
    await state.update_data(bet=bet, player=player, dealer=dealer, deck=deck, doubled=False)

    pv = hand_value(player)

    # Проверка блэкджека
    if is_blackjack(player):
        if is_blackjack(dealer):
            await db.add_balance(m.from_user.id, bet)
            await state.clear()
            await m.answer(
                f"🃏 <b>Блэкджек!</b>\n\n"
                f"Твои: {fmt_hand(player)} = 21\n"
                f"Дилер: {fmt_hand(dealer)} = 21\n\n"
                f"🤝 Ничья — ставка возвращена",
                reply_markup=casino_kb(), parse_mode="HTML"
            )
            return
        win = int(bet * 2.5)
        await db.add_balance(m.from_user.id, win)
        await db.update(m.from_user.id, wins=u["wins"]+1)
        await state.clear()
        await m.answer(
            f"🎉 <b>БЛЭКДЖЕК!</b>\n\n"
            f"Твои: {fmt_hand(player)} = 21\n"
            f"Дилер: {fmt_hand(dealer)}\n\n"
            f"💰 Выигрыш: <b>+{fmt_full(win - bet)}$</b> (x1.5)",
            reply_markup=casino_kb(), parse_mode="HTML"
        )
        return

    await m.answer(
        f"🃏 <b>Блэкджек</b> | Ставка: {fmt_full(bet)}$\n\n"
        f"👤 Твои: {fmt_hand(player)} = <b>{pv}</b>\n"
        f"🤖 Дилер: {dealer[0]} ?\n\n"
        f"Твоё действие:",
        reply_markup=bj_kb(), parse_mode="HTML"
    )

async def send_bj_table(target, data, text_prefix=""):
    pv = hand_value(data["player"])
    dv = hand_value(data["dealer"])
    return (
        f"{text_prefix}"
        f"👤 Твои: {fmt_hand(data['player'])} = <b>{pv}</b>\n"
        f"🤖 Дилер: {fmt_hand(data['dealer'])} = <b>{dv}</b>\n"
        f"💰 Ставка: {fmt_full(data['bet'])}$"
    )

@dp.callback_query(St.bj_play, F.data == "bj_hit")
async def cb_bj_hit(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    data["player"].append(data["deck"].pop())
    pv = hand_value(data["player"])

    if pv > 21:
        u = await db.get_user(c.from_user.id)
        await db.update(c.from_user.id, losses=u["losses"]+1)
        await state.clear()
        await c.message.edit_text(
            f"💥 <b>Перебор!</b>\n\n"
            f"👤 Твои: {fmt_hand(data['player'])} = {pv}\n"
            f"❌ Проигрыш: -{fmt_full(data['bet'])}$",
            reply_markup=casino_kb(), parse_mode="HTML"
        )
        return

    await state.update_data(**data)
    await c.message.edit_text(
        await send_bj_table(c, data),
        reply_markup=bj_kb(), parse_mode="HTML"
    )

@dp.callback_query(St.bj_play, F.data == "bj_stand")
async def cb_bj_stand(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await finish_blackjack(c, state, data)

@dp.callback_query(St.bj_play, F.data == "bj_double")
async def cb_bj_double(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if len(data["player"]) != 2 or data["doubled"]:
        await c.answer("Удвоить можно только в начале", show_alert=True); return
    u = await db.get_user(c.from_user.id)
    if u["balance"] < data["bet"]:
        await c.answer("Недостаточно средств для удвоения", show_alert=True); return
    await db.add_balance(c.from_user.id, -data["bet"])
    data["bet"] *= 2
    data["doubled"] = True
    data["player"].append(data["deck"].pop())
    await state.update_data(**data)
    if hand_value(data["player"]) > 21:
        await db.update(c.from_user.id, losses=u["losses"]+1)
        await state.clear()
        await c.message.edit_text(
            f"💥 <b>Перебор!</b>\n\n"
            f"👤 Твои: {fmt_hand(data['player'])} = {hand_value(data['player'])}\n"
            f"❌ Проигрыш: -{fmt_full(data['bet'])}$",
            reply_markup=casino_kb(), parse_mode="HTML"
        )
        return
    await finish_blackjack(c, state, data)

async def finish_blackjack(c, state, data):
    data["dealer"] = dealer_play(data["dealer"], data["deck"])
    pv = hand_value(data["player"])
    dv = hand_value(data["dealer"])
    bet = data["bet"]
    u = await db.get_user(c.from_user.id)

    table = f"👤 Твои: {fmt_hand(data['player'])} = {pv}\n🤖 Дилер: {fmt_hand(data['dealer'])} = {dv}\n\n"

    if dv > 21 or pv > dv:
        win = bet * 2
        await db.add_balance(c.from_user.id, win)
        await db.update(c.from_user.id, wins=u["wins"]+1)
        text = table + f"🎉 <b>Победа!</b> +{fmt_full(bet)}$"
    elif pv == dv:
        await db.add_balance(c.from_user.id, bet)
        text = table + f"🤝 <b>Ничья</b> — ставка возвращена"
    else:
        await db.update(c.from_user.id, losses=u["losses"]+1)
        text = table + f"❌ <b>Проигрыш</b> -{fmt_full(bet)}$"

    await state.clear()
    await c.message.edit_text(text, reply_markup=casino_kb(), parse_mode="HTML")


# --- РУЛЕТКА ---
@dp.callback_query(F.data == "rl_start")
async def cb_rl_start(c: CallbackQuery, state: FSMContext):
    await state.set_state(St.rl_bet)
    await c.message.edit_text(
        f"🎯 <b>Рулетка</b>\n\nВведи ставку (мин {fmt_full(MIN_BET)}$):"
    )

@dp.message(St.rl_bet)
async def cb_rl_bet(m: Message, state: FSMContext):
    bet = parse_amount(m.text)
    if not bet or bet < MIN_BET:
        await m.answer("❌ Неверная ставка"); return
    u = await db.get_user(m.from_user.id)
    if u["balance"] < bet:
        await m.answer("❌ Недостаточно средств"); await state.clear(); return
    await db.add_balance(m.from_user.id, -bet)
    await state.update_data(bet=bet)
    await m.answer(
        f"🎯 Ставка: {fmt_full(bet)}$\nВыбери вариант:",
        reply_markup=rl_choice_kb()
    )

@dp.callback_query(F.data.startswith("rl_"), St.rl_bet)
async def cb_rl_result(c: CallbackQuery, state: FSMContext):
    if c.data == "rl_start": return
    choice = c.data.split("_")[1]
    data = await state.get_data()
    bet = data["bet"]
    await state.clear()

    num = random.randint(0, 36)
    if num == 0: color = "green"
    elif num in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]: color = "red"
    else: color = "black"

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
        text = f"🎯 Выпало: {emoji} <b>{num}</b>\n\n✅ Победа! +{fmt_full(payout - bet)}$ (x{mult})"
    else:
        await db.update(c.from_user.id, losses=u["losses"]+1)
        text = f"🎯 Выпало: {emoji} <b>{num}</b>\n\n❌ Проигрыш: -{fmt_full(bet)}$"

    await c.message.edit_text(text, reply_markup=casino_kb(), parse_mode="HTML")


# --- КОСТИ ---
@dp.callback_query(F.data == "dice_start")
async def cb_dice_start(c: CallbackQuery, state: FSMContext):
    await state.set_state(St.dice_bet)
    await c.message.edit_text(f"🎲 <b>Кости</b>\n\nВведи ставку:")

@dp.message(St.dice_bet)
async def cb_dice_bet(m: Message, state: FSMContext):
    bet = parse_amount(m.text)
    if not bet or bet < MIN_BET:
        await m.answer("❌ Неверная ставка"); return
    u = await db.get_user(m.from_user.id)
    if u["balance"] < bet:
        await m.answer("❌ Недостаточно средств"); await state.clear(); return
    await db.add_balance(m.from_user.id, -bet)
    await state.update_data(bet=bet)
    await m.answer(
        f"🎲 Ставка: {fmt_full(bet)}$\nУгадай число (x6):",
        reply_markup=dice_choice_kb()
    )

@dp.callback_query(F.data.startswith("dice_"), St.dice_bet)
async def cb_dice_result(c: CallbackQuery, state: FSMContext):
    if c.data == "dice_start": return
    choice = int(c.data.split("_")[1])
    data = await state.get_data()
    bet = data["bet"]
    await state.clear()

    roll = random.randint(1, 6)
    u = await db.get_user(c.from_user.id)

    if roll == choice:
        payout = bet * 6
        await db.add_balance(c.from_user.id, payout)
        await db.update(c.from_user.id, wins=u["wins"]+1)
        text = f"🎲 Выпало: <b>{roll}</b>\n\n🎉 Победа! +{fmt_full(payout - bet)}$ (x6)"
    else:
        await db.update(c.from_user.id, losses=u["losses"]+1)
        text = f"🎲 Выпало: <b>{roll}</b>\n\n❌ Проигрыш: -{fmt_full(bet)}$"

    await c.message.edit_text(text, reply_markup=casino_kb(), parse_mode="HTML")


# ============ АДМИН ============
@dp.message(Command("admin"))
async def cmd_admin(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    await m.answer(
        f"👑 <b>Админ-панель</b>\n\n"
        f"Команды:\n"
        f"/give СУММА — выдать себе\n"
        f"/reset — сбросить себя\n"
        f"/stats — общая статистика",
        parse_mode="HTML"
    )

@dp.message(Command("give"))
async def cmd_give(m: Message):
    if m.from_user.id != ADMIN_ID: return
    parts = m.text.split()
    if len(parts) < 2: return
    amount = parse_amount(parts[1])
    if not amount: return
    await db.add_balance(m.from_user.id, amount)
    await m.answer(f"✅ +{fmt_full(amount)}$")

@dp.message(Command("reset"))
async def cmd_reset(m: Message):
    if m.from_user.id != ADMIN_ID: return
    await db.update(m.from_user.id, balance=config.START_BALANCE, btc=0,
                    bank_wallet=0, businesses="", farms="", houses="",
                    deposit_amount=0, deposit_end=0, deposit_rate=0)
    await m.answer(f"✅ Сброшено до {fmt_full(config.START_BALANCE)}$")

@dp.message(Command("stats"))
async def cmd_stats(m: Message):
    if m.from_user.id != ADMIN_ID: return
    top = await db.get_top(1)
    await m.answer(f"👥 Всего игроков (топ-10): {len(await db.get_top(1000))}")


@dp.callback_query(F.data == "noop")
async def cb_noop(c: CallbackQuery):
    await c.answer("✅ Уже куплено")


async def main():
    await db.init_db()
    print("🎰 Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
