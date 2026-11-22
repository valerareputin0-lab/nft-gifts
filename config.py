# ============ SUPABASE ============
DATABASE_URL = "postgresql://postgres.miizjvnllvcgdkeaverx:Bombastik228@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

# ============ BOT ============
BOT_TOKEN = "9031676987:AAEAMl_VXjvh6GGNFTUgIHKmNa8DuSxX3fM"
ADMIN_ID = 222619025

START_BALANCE = 1000
BTC_PRICE = 60000
MIN_BET = 100
MAX_BET = 10_000_000_000_000
FARM_CAP_HOURS = 48
CASH_CAP_HOURS = 24
CASH_COLLECT_COOLDOWN = 60
WITHDRAW_FEE = 0.03
SELL_PERCENT = 0.05

NICK_MIN = 3
NICK_MAX = 20

BONUS_AMOUNT = 5000
BONUS_COOLDOWN = 12 * 3600

GARAGE_PRICE = 200_000
FARMS_LIMIT = 9999

BUSINESSES = {
    "hype":   {"name": "🐬 Хайповый паблик",    "price": 20_000_000,      "income": 70_000},
    "sauna":  {"name": "🔥 Сауна",               "price": 100_000_000,     "income": 165_000},
    "garage": {"name": "🔨 Завод в гараже",      "price": 500_000_000,     "income": 560_000},
    "studio": {"name": "💡 Анимационная студия", "price": 5_000_000_000,   "income": 4_000_000},
    "tesla":  {"name": "🚀 Tesla",               "price": 100_000_000_000, "income": 50_000_000},
}

BUSINESS_LEVEL_MULT = {1: 1.0, 2: 1.10, 3: 1.30}
BUSINESS_UPGRADE_COST_MULT = {2: 1.5, 3: 2.5}

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

CARS = {
    "lada":     {"name": "🚗 Лада",        "price": 50_000},
    "bmw":      {"name": "🚙 BMW",         "price": 500_000},
    "mercedes": {"name": "🚘 Mercedes",    "price": 2_000_000},
    "ferrari":  {"name": "🏎 Ferrari",     "price": 10_000_000},
    "lambo":    {"name": "🏎 Lamborghini", "price": 50_000_000},
}

SKINS = {
    "suit1": {"name": "👔 Хороший костюм",  "price": 50_000},
    "suit2": {"name": "🤵 Деловой костюм",  "price": 50_000_000},
    "suit3": {"name": "🕴 Gucci костюм",    "price": 5_000_000_000},
}

DEPOSITS = {
    "day":   {"name": "📅 1 день",   "seconds": 86400,    "rate": 0.01},
    "week":  {"name": "📆 7 дней",   "seconds": 604800,   "rate": 0.10},
    "month": {"name": "🗓 30 дней",  "seconds": 2592000,  "rate": 0.35},
}
