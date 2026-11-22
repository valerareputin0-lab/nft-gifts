from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import (BUSINESSES, FARMS, HOUSES, CARS, SKINS, DEPOSITS,
                    BUSINESS_LEVEL_MULT, BUSINESS_UPGRADE_COST_MULT,
                    SELL_PERCENT, GARAGE_PERCENT, FARMS_LIMIT)
from utils import parse_businesses, business_income, fmt_short, fmt_full

def main_kb(is_admin: bool = False):
    rows = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🏆 Топ", callback_data="top")],
        [InlineKeyboardButton(text="💼 Бизнесы", callback_data="biz"),
         InlineKeyboardButton(text="⛏ Фермы", callback_data="farms")],
        [InlineKeyboardButton(text="🏠 Дома", callback_data="houses"),
         InlineKeyboardButton(text="🏦 Банк", callback_data="bank")],
        [InlineKeyboardButton(text="🎰 Казино", callback_data="casino"),
         InlineKeyboardButton(text="🎁 Награды", callback_data="rewards")],
        [InlineKeyboardButton(text="🛒 Магазин", callback_data="shop")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="👑 Админ", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def back_kb(target="menu"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=target)]])

def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Сменить ник", callback_data="change_nick")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")]])

# ============ БИЗНЕСЫ ============
def biz_shop_kb():
    buttons, row = [], []
    for i, key in enumerate(BUSINESSES.keys(), 1):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"biz_info_{key}"))
    buttons.append(row)
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def biz_confirm_kb(bid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Купить", callback_data=f"buybiz_{bid}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="biz")]])

def biz_manage_kb(bid, lvl, has_cash):
    rows = []
    if lvl < 3:
        cost = int(BUSINESSES[bid]["price"] * BUSINESS_UPGRADE_COST_MULT[lvl + 1])
        rows.append([InlineKeyboardButton(
            text=f"⬆️ Улучшить до Lvl {lvl+1} — {fmt_short(cost)}$",
            callback_data=f"upbiz_{bid}")])
    else:
        rows.append([InlineKeyboardButton(text="✅ Максимальный уровень",
                                          callback_data="noop")])
    rows.append([InlineKeyboardButton(text="💰 Собрать доход", callback_data="biz_collect")])
    sell = int(BUSINESSES[bid]["price"] * (1 - SELL_PERCENT))
    rows.append([InlineKeyboardButton(
        text=f"💸 Продать за {fmt_short(sell)}$", callback_data=f"sellbiz_{bid}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ============ ФЕРМЫ ============
def farms_kb(farm_type, count):
    rows = []
    if farm_type is None:
        for key, f in FARMS.items():
            rows.append([InlineKeyboardButton(
                text=f"{f['name']} — {fmt_short(f['price'])}$ (+{f['btc_per_hour']}฿/ч)",
                callback_data=f"buyfarm_{key}")])
    else:
        rows.append([InlineKeyboardButton(text="₿ Продать биткоины",
                                          callback_data="farms_sellbtc")])
        rows.append([
            InlineKeyboardButton(text="➕ Купить фермы", callback_data="farm_buy_menu"),
            InlineKeyboardButton(text="➖ Продать фермы", callback_data="farm_sell_menu"),
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ============ ДОМА ============
def houses_kb(has_house, house_id, has_garage):
    rows = []
    if not has_house:
        for key, h in HOUSES.items():
            rows.append([InlineKeyboardButton(
                text=f"{h['name']} — {fmt_short(h['price'])}$",
                callback_data=f"buyhouse_{key}")])
    else:
        h = HOUSES[house_id]
        sell = int(h["price"] * SELL_PERCENT)
        garage_price = int(h["price"] * GARAGE_PERCENT)
        if has_garage:
            rows.append([InlineKeyboardButton(text="🚗 Гараж", callback_data="garage"),
                         InlineKeyboardButton(text="👔 Шкаф", callback_data="wardrobe")])
        else:
            rows.append([InlineKeyboardButton(
                text=f"🚗 Купить гараж — {fmt_short(garage_price)}$",
                callback_data="buygarage")])
            rows.append([InlineKeyboardButton(text="👔 Шкаф", callback_data="wardrobe")])
        rows.append([InlineKeyboardButton(
            text=f"💸 Продать дом (+{fmt_short(sell)}$)",
            callback_data=f"sellhouse_{house_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def garage_kb(cars_owned):
    rows = []
    if cars_owned:
        key = cars_owned[0]
        c = CARS[key]
        sell = int(c["price"] * SELL_PERCENT)
        rows.append([InlineKeyboardButton(
            text=f"✅ {c['name']} | 💸 Продать +{fmt_short(sell)}$",
            callback_data=f"sellcar_{key}")])
    else:
        for key, c in CARS.items():
            rows.append([InlineKeyboardButton(
                text=f"{c['name']} — {fmt_short(c['price'])}$",
                callback_data=f"buycar_{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="houses")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def wardrobe_kb(owned, worn):
    rows = []
    for key, skin in SKINS.items():
        if key in owned:
            is_worn = key in worn
            label = f"{'✅' if is_worn else '👔'} {skin['name']} {'(снять)' if is_worn else '(надеть)'}"
            rows.append([InlineKeyboardButton(text=label, callback_data=f"wear_{key}")])
    if not owned:
        rows.append([InlineKeyboardButton(text="Пусто (купи в магазине)", callback_data="noop")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="houses")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def shop_kb(owned):
    rows = []
    for key, skin in SKINS.items():
        if key in owned:
            rows.append([InlineKeyboardButton(text=f"✅ {skin['name']}", callback_data="noop")])
        else:
            rows.append([InlineKeyboardButton(
                text=f"{skin['name']} — {fmt_short(skin['price'])}$",
                callback_data=f"buyskin_{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def rewards_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Бонус (12ч, +5000$)", callback_data="bonus")],
        [InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="enter_promo")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")]])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать по ID", callback_data="admin_give")],
        [InlineKeyboardButton(text="💸 Забрать по ID", callback_data="admin_take")],
        [InlineKeyboardButton(text="🎟 Создать промокод", callback_data="admin_promo")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")]])

def bank_kb(has_deposit, deposit_ready):
    rows = [
        [InlineKeyboardButton(text="💵 Внести на счёт", callback_data="bank_dep_in")],
        [InlineKeyboardButton(text="💸 Снять (3%)", callback_data="bank_dep_out")],
    ]
    if has_deposit:
        if deposit_ready:
            rows.append([InlineKeyboardButton(text="✅ Забрать вклад", callback_data="bank_view")])
        else:
            rows.append([InlineKeyboardButton(text="📊 Мой вклад", callback_data="bank_view")])
    else:
        rows.append([InlineKeyboardButton(text="📈 Открыть вклад", callback_data="bank_open")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def deposits_kb():
    rows = [[InlineKeyboardButton(
        text=f"{d['name']} — +{int(d['rate']*100)}%", callback_data=f"dep_{k}")]
        for k, d in DEPOSITS.items()]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="bank")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def casino_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🃏 Блэкджек", callback_data="bj_start"),
         InlineKeyboardButton(text="🎯 Рулетка", callback_data="rl_start")],
        [InlineKeyboardButton(text="🎲 Кости", callback_data="dice_start")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")]])

def bj_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Взять", callback_data="bj_hit"),
         InlineKeyboardButton(text="✋ Хватит", callback_data="bj_stand")],
        [InlineKeyboardButton(text="✖️ Удвоить", callback_data="bj_double")]])

def rl_choice_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Красное x2", callback_data="rl_red"),
         InlineKeyboardButton(text="⚫ Чёрное x2", callback_data="rl_black")],
        [InlineKeyboardButton(text="🟢 Зеро x14", callback_data="rl_green")],
        [InlineKeyboardButton(text="Чёт x2", callback_data="rl_even"),
         InlineKeyboardButton(text="Нечет x2", callback_data="rl_odd")]])

def dice_choice_kb():
    buttons, row = [], []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"dice_{i}"))
        if len(row) == 3: buttons.append(row); row = []
    if row: buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)
