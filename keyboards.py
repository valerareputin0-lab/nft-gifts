from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import (JOBS, BUSINESSES, FARMS, HOUSES, CARS, CLOTHES, DEPOSITS,
                    BUSINESS_LEVEL_MULT, BUSINESS_UPGRADE_COST_MULT,
                    SELL_PERCENT, GARAGE_PRICE)
from utils import parse_businesses, business_income
import time

def main_kb(is_admin: bool = False):
    rows = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🏆 Топ", callback_data="top")],
        [InlineKeyboardButton(text="💼 Работы", callback_data="jobs"),
         InlineKeyboardButton(text="🏢 Бизнесы", callback_data="biz")],
        [InlineKeyboardButton(text="⛏ Фермы", callback_data="farms"),
         InlineKeyboardButton(text="🏠 Дома", callback_data="houses")],
        [InlineKeyboardButton(text="🏦 Банк", callback_data="bank"),
         InlineKeyboardButton(text="🎰 Казино", callback_data="casino")],
        [InlineKeyboardButton(text="🎁 Награды", callback_data="rewards"),
         InlineKeyboardButton(text="🛒 Магазин", callback_data="shop")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="👑 Админ", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def back_kb(target="menu"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=target)]
    ])

def jobs_kb(times):
    buttons = []
    now = int(time.time())
    for key, j in JOBS.items():
        left = int(times.get(key, 0) + j["cooldown"] - now)
        label = f"{j['name']} ⏳ {left//60}м {left%60}с" if left > 0 else f"{j['name']} +{j['income']}$"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"work_{key}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def biz_kb(biz_dict):
    rows = []
    for key, b in BUSINESSES.items():
        if key in biz_dict:
            lvl = biz_dict[key]
            inc = business_income(key, lvl)
            if lvl < 3:
                cost = int(b["price"] * BUSINESS_UPGRADE_COST_MULT[lvl + 1])
                rows.append([InlineKeyboardButton(
                    text=f"{b['name']} Lvl {lvl} (+{inc}$/ч) — ⬆️ {cost}$",
                    callback_data=f"upbiz_{key}"
                )])
            else:
                rows.append([InlineKeyboardButton(
                    text=f"{b['name']} MAX Lvl 3 (+{inc}$/ч)", callback_data="noop"
                )])
            sell = int(b["price"] * SELL_PERCENT)
            rows.append([InlineKeyboardButton(
                text=f"💸 Продать {b['name']} +{sell}$",
                callback_data=f"sellbiz_{key}"
            )])
        else:
            rows.append([InlineKeyboardButton(
                text=f"{b['name']} — {b['price']}$",
                callback_data=f"buybiz_{key}"
            )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def farms_kb(owned):
    rows = []
    for key, f in FARMS.items():
        if key in owned:
            sell = int(f["price"] * SELL_PERCENT)
            rows.append([InlineKeyboardButton(
                text=f"✅ {f['name']} +{f['btc_per_hour']}₿/ч", callback_data="noop")])
            rows.append([InlineKeyboardButton(
                text=f"💸 Продать {f['name']} +{sell}$",
                callback_data=f"sellfarm_{key}")])
        else:
            rows.append([InlineKeyboardButton(
                text=f"{f['name']} — {f['price']}$", callback_data=f"buyfarm_{key}")])
    rows.append([InlineKeyboardButton(text="₿ Продать BTC", callback_data="farms_sellbtc")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def houses_kb(owned):
    rows = []
    for key, h in HOUSES.items():
        if key in owned:
            sell = int(h["price"] * SELL_PERCENT)
            rows.append([InlineKeyboardButton(
                text=f"🏠 {h['name']} ✅ | 💸 +{sell}$",
                callback_data=f"sellhouse_{key}")])
        else:
            rows.append([InlineKeyboardButton(
                text=f"{h['name']} — {h['price']}$", callback_data=f"buyhouse_{key}")])
    rows.append([InlineKeyboardButton(text="🚗 Гараж", callback_data="garage"),
                 InlineKeyboardButton(text="👕 Шкаф", callback_data="wardrobe")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def garage_kb(has_garage, cars_owned):
    if not has_garage:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🚗 Купить гараж — {GARAGE_PRICE}$",
                                  callback_data="buygarage")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="houses")],
        ])
    rows = []
    for key, c in CARS.items():
        if key in cars_owned:
            sell = int(c["price"] * SELL_PERCENT)
            rows.append([InlineKeyboardButton(
                text=f"✅ {c['name']} | 💸 +{sell}$",
                callback_data=f"sellcar_{key}")])
        else:
            rows.append([InlineKeyboardButton(
                text=f"{c['name']} — {c['price']}$", callback_data=f"buycar_{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="houses")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def wardrobe_kb(owned, worn):
    rows = []
    for key, cl in CLOTHES.items():
        if key in owned:
            is_worn = key in worn
            label = f"{'✅' if is_worn else '👕'} {cl['name']} {'(снять)' if is_worn else '(надеть)'}"
            rows.append([InlineKeyboardButton(text=label, callback_data=f"wear_{key}")])
        else:
            rows.append([InlineKeyboardButton(
                text=f"{cl['name']} — {cl['price']}$", callback_data=f"buycloth_{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="houses")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def shop_kb(owned):
    rows = []
    for key, cl in CLOTHES.items():
        if key in owned:
            rows.append([InlineKeyboardButton(text=f"✅ {cl['name']}", callback_data="noop")])
        else:
            rows.append([InlineKeyboardButton(
                text=f"{cl['name']} — {cl['price']}$", callback_data=f"buycloth_{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def rewards_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Бонус (12ч, +5000$)", callback_data="bonus")],
        [InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="enter_promo")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")],
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать по ID", callback_data="admin_give")],
        [InlineKeyboardButton(text="💸 Забрать по ID", callback_data="admin_take")],
        [InlineKeyboardButton(text="🎟 Создать промокод", callback_data="admin_promo")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")],
    ])

def bank_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Внести в банк", callback_data="bank_dep_in")],
        [InlineKeyboardButton(text="💸 Снять (3%)", callback_data="bank_dep_out")],
        [InlineKeyboardButton(text="📈 Открыть вклад", callback_data="bank_open")],
        [InlineKeyboardButton(text="📊 Мой вклад", callback_data="bank_view")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")],
    ])

def deposits_kb():
    rows = [[InlineKeyboardButton(
        text=f"{d['name']} — {int(d['rate']*100)}%", callback_data=f"dep_{k}")]
        for k, d in DEPOSITS.items()]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="bank")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def casino_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🃏 Блэкджек", callback_data="bj_start"),
         InlineKeyboardButton(text="🎯 Рулетка", callback_data="rl_start")],
        [InlineKeyboardButton(text="🎲 Кости", callback_data="dice_start")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")],
    ])

def bj_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Взять", callback_data="bj_hit"),
         InlineKeyboardButton(text="✋ Хватит", callback_data="bj_stand")],
        [InlineKeyboardButton(text="✖️ Удвоить", callback_data="bj_double")],
    ])

def rl_choice_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔴 Красное x2", callback_data="rl_red"),
         InlineKeyboardButton(text="⚫ Чёрное x2", callback_data="rl_black")],
        [InlineKeyboardButton(text="🟢 Зеро x14", callback_data="rl_green")],
        [InlineKeyboardButton(text="Чёт x2", callback_data="rl_even"),
         InlineKeyboardButton(text="Нечет x2", callback_data="rl_odd")],
    ])

def dice_choice_kb():
    buttons, row = [], []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"dice_{i}"))
        if len(row) == 3: buttons.append(row); row = []
    if row: buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)
