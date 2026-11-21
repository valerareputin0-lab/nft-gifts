BOT_TOKEN = "9031676987:AAHfnLPFQtIeXD5dfFhJZ3JkSYjNgvrl2dM"
ADMIN_ID = 222619025  # твой telegram id (узнать у @userinfobot)

START_BALANCE = 1000
BTC_PRICE = 60000
MIN_BET = 100
MAX_BET = 10_000_000_000_000
PASSIVE_CAP_HOURS = 48
WITHDRAW_FEE = 0.03

JOBS = {
    "courier":    {"name": "🍔 Курьер",       "income": 1500,  "cooldown": 300},
    "builder":    {"name": "🏗 Строитель",    "income": 6000,  "cooldown": 900},
    "programmer": {"name": "💻 Программист",  "income": 24000, "cooldown": 1800},
}

BUSINESSES = {
    "coffee":  {"name": "☕ Кофейня",  "price": 10_000,    "income": 500},
    "shop":    {"name": "🏪 Магазин",  "price": 50_000,    "income": 2500},
    "taxi":    {"name": "🚕 Таксопарк","price": 150_000,   "income": 8000},
    "factory": {"name": "🏭 Завод",    "price": 500_000,   "income": 25000},
    "bank":    {"name": "🏦 Банк",     "price": 2_000_000, "income": 100000},
}

FARMS = {
    "farm1": {"name": "⛏ Ферма-1", "price": 12_000_000, "btc_per_hour": 8.33},
    "farm2": {"name": "⛏ Ферма-2", "price": 36_000_000, "btc_per_hour": 25.0},
    "farm3": {"name": "⛏ Ферма-3", "price": 96_000_000, "btc_per_hour": 66.67},
}

HOUSES = {
    "shack":   {"name": "🏚 Лачуга",    "price": 5_000},
    "house":   {"name": "🏠 Дом",       "price": 50_000},
    "cottage": {"name": "🏡 Коттедж",   "price": 300_000},
    "mansion": {"name": "🏰 Особняк",   "price": 1_500_000},
    "villa":   {"name": "🏯 Вилла",     "price": 10_000_000},
}

DEPOSITS = {
    "day":   {"name": "📅 1 день",   "seconds": 86400,    "rate": 0.05},
    "week":  {"name": "📆 1 неделя", "seconds": 604800,   "rate": 0.15},
    "month": {"name": "🗓 1 месяц",  "seconds": 2592000,  "rate": 0.50},
}
