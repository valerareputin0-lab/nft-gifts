from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import JOBS, BUSINESSES, FARMS, HOUSES, DEPOSITS

def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🏆 Топ", callback_data="top")],
        [InlineKeyboardButton(text="💼 Работы", callback_data="jobs"),
         InlineKeyboardButton(text="🏢 Бизнесы", callback_data="biz")],
        [InlineKeyboardButton(text="⛏ Фермы", callback_data="farms"),
         InlineKeyboardButton(text="🏠 Дома", callback_data="houses")],
        [InlineKeyboardButton(text="🏦 Банк", callback_data="bank"),
         InlineKeyboardButton(text="🎰 Казино", callback_data="casino")],
    ])

def back_kb(target="menu"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=target)]
    ])

def jobs_kb(owned_times: dict):
    import time
    buttons = []
    now = int(time.time())
    for key, j in JOBS.items():
        last = owned_times.get(key, 0)
        left = int(last + j["cooldown"] - now)
        if left > 0:
            label = f"{j['name']} ⏳ {left//60}м {left%60}с"
        else:
            label = f"{j['name']} +{j['income']}$"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"work_{key}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def biz_kb(owned: list, balance: int):
    buttons = []
    for key, b in BUSINESSES.items():
        if key in owned:
            label = f"✅ {b['name']} (+{b['income']}$/ч)"
            cb = "noop"
        else:
            label = f"{b['name']} — {b['price']}$"
            cb = f"buybiz_{key}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=cb)])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def farms_kb(owned: list):
    buttons = []
    for key, f in FARMS.items():
        if key in owned:
            label = f"✅ {f['name']} (+{f['btc_per_hour']}₿/ч)"
            cb = "noop"
        else:
            label = f"{f['name']} — {f['price']}$"
            cb = f"buyfarm_{key}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=cb)])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def houses_kb(owned: list):
    buttons = []
    for key, h in HOUSES.items():
        if key in owned:
            label = f"✅ {h['name']}"
            cb = "noop"
        else:
            label = f"{h['name']} — {h['price']}$"
            cb = f"buyhouse_{key}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=cb)])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def bank_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Внести в банк", callback_data="bank_dep_in")],
        [InlineKeyboardButton(text="💸 Снять (3%)", callback_data="bank_dep_out")],
        [InlineKeyboardButton(text="📈 Открыть вклад", callback_data="bank_open")],
        [InlineKeyboardButton(text="📊 Мой вклад", callback_data="bank_view")],
        [InlineKeyboardButton(text="₿ Продать BTC", callback_data="bank_sell_btc")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")],
    ])

def deposits_kb():
    buttons = []
    for key, d in DEPOSITS.items():
        buttons.append([InlineKeyboardButton(
            text=f"{d['name']} — {int(d['rate']*100)}%",
            callback_data=f"dep_{key}"
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="bank")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

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
    buttons = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"dice_{i}"))
        if len(row) == 3:
            buttons.append(row); row = []
    if row: buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)
