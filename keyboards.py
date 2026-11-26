from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from config import (BUSINESSES, FARMS, HOUSES, CARS, SKINS, DEPOSITS,
                    BUSINESS_LEVEL_MULT, BUSINESS_UPGRADE_COST_MULT,
                    SELL_PERCENT, GARAGE_PERCENT, FARMS_LIMIT)
from utils import parse_businesses, business_income, fmt_short, fmt_full

def main_reply_kb(is_admin: bool = False):
    rows = [
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🎰 Казино"), KeyboardButton(text="🏠 Дом")],
        [KeyboardButton(text="💼 Бизнес"), KeyboardButton(text="⛏ Фермы"), KeyboardButton(text="🛒 Магазин")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def group_reply_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📊 Банк"), KeyboardButton(text="📖 Правила")]],
        resize_keyboard=True)

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
    return InlineKeyboardMarkup(inline_keyboard=rows)

def back_kb(target="menu"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=target)]])

def profile_kb(is_admin: bool = False):
    rows = [
        [InlineKeyboardButton(text="🏦 Банк", callback_data="bank"),
         InlineKeyboardButton(text="🏆 Топ", callback_data="top")],
        [InlineKeyboardButton(text="✏️ Сменить ник", callback_data="change_nick"),
         InlineKeyboardButton(text="🎁 Награды", callback_data="rewards")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="👑 Админка", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

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
            text=f"⬆️ Улучшить до Lvl {lvl+1} — {fmt_short(cost)}$", callback_data=f"upbiz_{bid}")])
    else:
        rows.append([InlineKeyboardButton(text="✅ Максимальный уровень", callback_data="noop")])
    rows.append([InlineKeyboardButton(text="💰 Собрать доход", callback_data="biz_collect")])
    sell = int(BUSINESSES[bid]["price"] * (1 - SELL_PERCENT))
    rows.append([InlineKeyboardButton(text=f"💸 Продать за {fmt_short(sell)}$", callback_data=f"sellbiz_{bid}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def farms_kb(farm_type, count):
    rows = []
    if farm_type is None:
        for key, f in FARMS.items():
            rows.append([InlineKeyboardButton(
                text=f"{f['name']} — {fmt_short(f['price'])}$ (+{f['btc_per_hour']}฿/ч)",
                callback_data=f"buyfarm_{key}")])
    else:
        rows.append([
            InlineKeyboardButton(text="💰 Снять биткоины", callback_data="farms_withdraw"),
            InlineKeyboardButton(text="₿ Продать биткоины", callback_data="farms_sellbtc"),
        ])
        rows.append([
            InlineKeyboardButton(text="➕ Купить фермы", callback_data="farm_buy_menu"),
            InlineKeyboardButton(text="➖ Продать фермы", callback_data="farm_sell_menu"),
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def houses_kb(has_house, house_id, has_garage):
    rows = []
    if not has_house:
        for key, h in HOUSES.items():
            rows.append([InlineKeyboardButton(
                text=f"{h['name']} — {fmt_short(h['price'])}$", callback_data=f"buyhouse_{key}")])
    else:
        h = HOUSES[house_id]
        sell = int(h["price"] * SELL_PERCENT)
        garage_price = int(h["price"] * GARAGE_PERCENT)
        if has_garage:
            rows.append([InlineKeyboardButton(text="🚗 Гараж", callback_data="garage"),
                         InlineKeyboardButton(text="👔 Шкаф", callback_data="wardrobe")])
        else:
            rows.append([InlineKeyboardButton(
                text=f"🚗 Купить гараж — {fmt_short(garage_price)}$", callback_data="buygarage")])
            rows.append([InlineKeyboardButton(text="👔 Шкаф", callback_data="wardrobe")])
        rows.append([InlineKeyboardButton(
            text=f"💸 Продать дом (+{fmt_short(sell)}$)", callback_data=f"sellhouse_{house_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def garage_kb(cars_owned):
    rows = []
    if cars_owned:
        key = cars_owned[0]
        c = CARS[key]
        sell = int(c["price"] * SELL_PERCENT)
        rows.append([InlineKeyboardButton(
            text=f"✅ {c['name']} | 💸 Продать +{fmt_short(sell)}$", callback_data=f"sellcar_{key}")])
    else:
        for key, c in CARS.items():
            rows.append([InlineKeyboardButton(
                text=f"{c['name']} — {fmt_short(c['price'])}$", callback_data=f"buycar_{key}")])
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
                text=f"{skin['name']} — {fmt_short(skin['price'])}$", callback_data=f"buyskin_{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def rewards_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Бонус (12ч, 5%)", callback_data="bonus")],
        [InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="enter_promo")],
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
        [InlineKeyboardButton(text="🎯 Рулетка — угадай цвет/число (x2–x30)", callback_data="rl_info")],
        [InlineKeyboardButton(text="🃏 Блэкджек — набери 21 (x2)", callback_data="bj_info")],
        [InlineKeyboardButton(text="🎲 Кости — угадай число (x2–x5)", callback_data="dice_info")],
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
        [InlineKeyboardButton(text="🟢 Зеро x30", callback_data="rl_green")],
        [InlineKeyboardButton(text="Чёт x2", callback_data="rl_even"),
         InlineKeyboardButton(text="Нечет x2", callback_data="rl_odd")],
        [InlineKeyboardButton(text="1-12 x3", callback_data="rl_low"),
         InlineKeyboardButton(text="13-24 x3", callback_data="rl_mid"),
         InlineKeyboardButton(text="25-36 x3", callback_data="rl_high")]])

def dice_choice_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1", callback_data="dice_1"),
         InlineKeyboardButton(text="2", callback_data="dice_2"),
         InlineKeyboardButton(text="3", callback_data="dice_3")],
        [InlineKeyboardButton(text="4", callback_data="dice_4"),
         InlineKeyboardButton(text="5", callback_data="dice_5"),
         InlineKeyboardButton(text="6", callback_data="dice_6")],
        [InlineKeyboardButton(text="Меньше (1-3) x2", callback_data="dice_low"),
         InlineKeyboardButton(text="Больше (4-6) x2", callback_data="dice_high")]])

# ============ АДМИНКА ============
def admin_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Деньги", callback_data="adm_money_menu"),
         InlineKeyboardButton(text="₿ Биткоины", callback_data="adm_btc_menu")],
        [InlineKeyboardButton(text="🏢 Имущество", callback_data="adm_prop_menu"),
         InlineKeyboardButton(text="🚫 Блокировка", callback_data="adm_ban_menu")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats"),
         InlineKeyboardButton(text="🎟 Промокоды", callback_data="adm_promo_menu")],
        [InlineKeyboardButton(text="🍀 Удача", callback_data="adm_luck_menu")],
        [InlineKeyboardButton(text="👤 Профиль игрока", callback_data="adm_view_profile")],
        [InlineKeyboardButton(text="👑 Выдать админку", callback_data="adm_give_admin")],
        [InlineKeyboardButton(text="⭐ Выдать VIP", callback_data="adm_give_vip")],
        [InlineKeyboardButton(text="⚙️ Глобальные", callback_data="adm_global_menu")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="profile")]])

def admin_money_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Выдать по ID", callback_data="adm_give_money")],
        [InlineKeyboardButton(text="➖ Забрать по ID", callback_data="adm_take_money")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]])

def admin_btc_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Выдать BTC", callback_data="adm_give_btc")],
        [InlineKeyboardButton(text="➖ Забрать BTC", callback_data="adm_take_btc")],
        [InlineKeyboardButton(text="💱 Изменить курс BTC", callback_data="adm_set_btc_price")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]])

def admin_prop_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Дом", callback_data="adm_prop_house")],
        [InlineKeyboardButton(text="🏢 Бизнес", callback_data="adm_prop_biz")],
        [InlineKeyboardButton(text="⛏ Ферма", callback_data="adm_prop_farm")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]])

def admin_ban_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Забанить", callback_data="adm_ban")],
        [InlineKeyboardButton(text="✅ Разбанить", callback_data="adm_unban")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]])

def admin_global_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать всем", callback_data="adm_give_all")],
        [InlineKeyboardButton(text="💸 Забрать у всех", callback_data="adm_take_all")],
        [InlineKeyboardButton(text="🔄 Обнулить всех", callback_data="adm_reset_all")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]])

def admin_promo_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="adm_promo_create")],
        [InlineKeyboardButton(text="🗑 Удалить промокод", callback_data="adm_promo_delete")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]])

def admin_luck_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Установить удачу", callback_data="adm_luck_set")],
        [InlineKeyboardButton(text="📊 Посмотреть удачу", callback_data="adm_luck_view")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]])

def admin_confirm_kb(action):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"adm_confirm_{action}"),
         InlineKeyboardButton(text="❌ Нет", callback_data="admin_panel")]])

def admin_house_select_kb(prefix):
    rows = []
    for key, h in HOUSES.items():
        rows.append([InlineKeyboardButton(text=h["name"], callback_data=f"{prefix}_{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_prop_house")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_biz_select_kb(prefix):
    rows = []
    for key, b in BUSINESSES.items():
        rows.append([InlineKeyboardButton(text=b["name"], callback_data=f"{prefix}_{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_prop_biz")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_farm_select_kb(prefix):
    rows = []
    for key, f in FARMS.items():
        rows.append([InlineKeyboardButton(text=f["name"], callback_data=f"{prefix}_{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_prop_farm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

ADMIN_PERMS = {
    "money":  "💰 Деньги",
    "btc":    "₿ BTC",
    "prop":   "🏢 Имущество",
    "ban":    "🚫 Блокировка",
    "stats":  "📊 Статистика",
    "promo":  "🎟 Промокоды",
    "view":   "👤 Профиль",
    "admins": "👑 Выдать админку",
    "luck":   "🍀 Удача",
}

def admin_perms_kb(target_game_id: int, perms: list):
    rows = []
    for key, label in ADMIN_PERMS.items():
        mark = "✅" if key in perms else "☐"
        rows.append([InlineKeyboardButton(
            text=f"{mark} {label}", callback_data=f"admperm_toggle_{key}")])
    rows.append([InlineKeyboardButton(text="💾 Сохранить", callback_data="admperm_save")])
    rows.append([InlineKeyboardButton(text="🗑 Забрать админку", callback_data="admperm_take")])
    rows.append([InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_vip_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Выдать ADMIN VIP", callback_data="adm_vip_give")],
        [InlineKeyboardButton(text="❌ Забрать VIP", callback_data="adm_vip_take")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]])

# ============ ГРУППОВАЯ РУЛЕТКА ============
def group_roulette_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Банк", callback_data="gr_bank"),
         InlineKeyboardButton(text="📖 Правила", callback_data="gr_rules")]])
