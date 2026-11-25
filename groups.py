import asyncio
import random
import time
from datetime import datetime

from aiogram import Bot, F
from aiogram.types import Message, CallbackQuery

import database as db
from keyboards import group_roulette_kb
from config import MIN_BET

ROULETTE_MULTS = [
    (2, 55),
    (3, 28),
    (5, 16),
    (50, 1),
]

ROUND_DURATION = 60
_active_timers = {}


def is_group(chat_type: str) -> bool:
    return chat_type in ("group", "supergroup")


def parse_bet(s: str):
    """Парсит сумму с сокращениями к/кк/ккк/кккк/ккккк."""
    if not s: return None
    s = s.lower().strip().replace("$", "").replace(",", "").replace(" ", "")
    mult = 1
    if s.endswith("ккккк"): mult, s = 10**15, s[:-5]
    elif s.endswith("кккк"): mult, s = 10**12, s[:-4]
    elif s.endswith("ккк"): mult, s = 10**9, s[:-3]
    elif s.endswith("кк"): mult, s = 10**6, s[:-2]
    elif s.endswith("к"): mult, s = 10**3, s[:-1]
    try: return int(float(s) * mult)
    except (ValueError, TypeError): return None


async def start_round(bot: Bot, chat_id: int):
    old = _active_timers.get(chat_id)
    if old and not old.done():
        old.cancel()
    end_time = int(time.time()) + ROUND_DURATION
    await db.set_group_round(chat_id, end_time, 1)
    task = asyncio.create_task(_round_finish(bot, chat_id, end_time))
    _active_timers[chat_id] = task


async def _round_finish(bot: Bot, chat_id: int, end_time: int):
    try:
        wait = end_time - int(time.time())
        if wait > 0:
            await asyncio.sleep(wait)

        bets = await db.get_group_bets(chat_id, end_time)
        if not bets:
            await db.clear_group_round(chat_id)
            _active_timers.pop(chat_id, None)
            return

        mults = [m for m, _ in ROULETTE_MULTS]
        weights = [w for _, w in ROULETTE_MULTS]
        winning = random.choices(mults, weights=weights, k=1)[0]

        winners = []
        losers = []
        for b in bets:
            if b["mult"] == winning:
                payout = b["amount"] * b["mult"]
                user = await db.get_user_by_id(b["user_id"])
                if user:
                    await db.add_balance(b["user_id"], payout)
                winners.append((b, payout))
            else:
                losers.append(b)

        lines = [
            "🎲 <b>РАУНД ЗАВЕРШЁН!</b>",
            "",
            f"🎯 Выигрышный множитель: <b>x{winning}</b>",
            "",
        ]
        if winners:
            lines.append("🏆 <b>Победители:</b>")
            for b, payout in winners:
                lines.append(f"  {b['nick']} — x{b['mult']} → +{payout:,}".replace(",", ".") + "$")
        else:
            lines.append("😢 Победителей нет.")
        if losers:
            total_lost = sum(b["amount"] for b in losers)
            lines.append("")
            lines.append(f"💸 Проиграли: {len(losers)} чел., всего -{total_lost:,}".replace(",", ".") + "$")
        lines.append("")
        lines.append("🎰 Новая рулетка — /kaz [множитель] [сумма]")

        await db.clear_group_bets(chat_id, end_time)
        await db.clear_group_round(chat_id)
        _active_timers.pop(chat_id, None)

        try:
            await bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML",
                                   reply_markup=group_roulette_kb())
        except Exception:
            pass
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


async def handle_kaz(bot: Bot, m: Message):
    chat_id = m.chat.id
    user_id = m.from_user.id

    user = await db.get_user(user_id, m.from_user.username)
    if user.get("is_banned"):
        await m.reply("🚫 Ты забанен.")
        return

    parts = m.text.split()
    if len(parts) != 3:
        await m.reply(
            "❌ Формат: <code>/kaz множитель сумма</code>\n"
            "Пример: <code>/kaz 5 100000</code>\n"
            "Сокращения: к (тыс), кк (млн), ккк (млрд), кккк (трлн), ккккк\n"
            "Множители: x2, x3, x5, x50",
            parse_mode="HTML",
            reply_markup=group_roulette_kb())
        return

    try:
        mult = int(parts[1].replace("x", "").replace("х", ""))
    except ValueError:
        await m.reply("❌ Множитель — число")
        return

    amount = parse_bet(parts[2])
    if amount is None:
        await m.reply("❌ Неверная сумма")
        return

    if mult not in [m for m, _ in ROULETTE_MULTS]:
        await m.reply(f"❌ Множитель: {', '.join('x'+str(m) for m, _ in ROULETTE_MULTS)}")
        return

    if amount < MIN_BET:
        await m.reply(f"❌ Минимум: {MIN_BET}$")
        return

    if user["balance"] < amount:
        await m.reply(f"❌ Недостаточно. Баланс: {user['balance']:,}$".replace(",", "."))
        return

    rnd = await db.get_group_round(chat_id)
    if not rnd or not rnd["active"] or rnd["end_time"] <= int(time.time()):
        await start_round(bot, chat_id)
        rnd = await db.get_group_round(chat_id)

    round_end = rnd["end_time"]
    await db.add_balance(user_id, -amount)

    nick = user.get("nick") or m.from_user.first_name or "Игрок"
    await db.add_group_bet(chat_id, user_id, nick, mult, amount, round_end)

    left = max(0, round_end - int(time.time()))
    all_bets = await db.get_group_bets(chat_id, round_end)
    user_bets = [b for b in all_bets if b["user_id"] == user_id]
    total_user = sum(b["amount"] for b in user_bets)

    text = (
        f"✅ Ставка принята!\n\n"
        f"🎯 Множитель: x{mult}\n"
        f"💰 Ставка: {amount:,}$\n".replace(",", ".") +
        f"💵 Всего твоих: {total_user:,}$\n".replace(",", ".") +
        f"\n⏳ До конца: {left} сек\n"
        f"📊 Баланс: {user['balance'] - amount:,}$".replace(",", ".")
    )
    await m.reply(text, parse_mode="HTML", reply_markup=group_roulette_kb())


async def handle_bank(c: CallbackQuery):
    chat_id = c.message.chat.id
    rnd = await db.get_group_round(chat_id)
    if not rnd or not rnd["active"]:
        await c.answer("Нет активного раунда.", show_alert=True)
        return
    left = max(0, rnd["end_time"] - int(time.time()))
    bets = await db.get_group_bets(chat_id, rnd["end_time"])
    if not bets:
        await c.answer("Пока никто не поставил.", show_alert=True)
        return
    lines = ["📊 <b>Банк раунда</b>", f"⏳ Осталось: <b>{left} сек</b>", ""]
    by_mult = {}
    for b in bets:
        by_mult.setdefault(b["mult"], []).append(b)
    total_pool = sum(b["amount"] for b in bets)
    lines.append(f"💰 Всего: <b>{total_pool:,}$</b>".replace(",", "."))
    lines.append("")
    for mult in sorted(by_mult.keys()):
        blist = by_mult[mult]
        total_m = sum(b["amount"] for b in blist)
        lines.append(f"<b>x{mult}</b> — {len(blist)} ставок, {total_m:,}$".replace(",", "."))
        for b in blist[:5]:
            lines.append(f"  • {b['nick']}: {b['amount']:,}$".replace(",", "."))
        if len(blist) > 5:
            lines.append(f"  ... и ещё {len(blist) - 5}")
        lines.append("")
    try:
        await c.message.edit_text("\n".join(lines), parse_mode="HTML",
                                   reply_markup=group_roulette_kb())
    except Exception:
        await c.message.reply("\n".join(lines), parse_mode="HTML",
                              reply_markup=group_roulette_kb())
    await c.answer()


async def handle_rules(c: CallbackQuery):
    lines = [
        "📖 <b>Правила рулетки</b>",
        "",
        "🎯 Ставка: <code>/kaz множитель сумма</code>",
        "Пример: <code>/kaz 5 100000</code>",
        "Сокращения: <code>к</code> (тыс), <code>кк</code> (млн), <code>ккк</code> (млрд), <code>кккк</code>, <code>ккккк</code>",
        "",
        "⏳ Раунд — <b>60 секунд</b> с первой ставки.",
        "Один раунд на чат.",
        "",
        "🎲 <b>Множители и шансы:</b>",
    ]
    for mult, chance in ROULETTE_MULTS:
        lines.append(f"  • x{mult} — {chance}%")
    lines.append("")
    lines.append("💰 Минимум: 1.000$")
    lines.append("♾ Максимум: по балансу")
    lines.append("")
    lines.append("✅ Выигрыш = ставка × множитель (включая тело)")
    lines.append("Можно делать несколько ставок на разные множители!")
    try:
        await c.message.edit_text("\n".join(lines), parse_mode="HTML",
                                   reply_markup=group_roulette_kb())
    except Exception:
        await c.message.reply("\n".join(lines), parse_mode="HTML",
                              reply_markup=group_roulette_kb())
    await c.answer()


def register_group_handlers(dp):
    @dp.message(F.text.startswith("/kaz"))
    async def kaz_handler(m: Message):
        if not is_group(m.chat.type):
            await m.reply("🎰 Рулетка работает только в группах!")
            return
        await handle_kaz(m.bot, m)

    @dp.callback_query(F.data == "gr_bank")
    async def bank_handler(c: CallbackQuery):
        if not is_group(c.message.chat.type):
            await c.answer("Только в группах")
            return
        await handle_bank(c)

    @dp.callback_query(F.data == "gr_rules")
    async def rules_handler(c: CallbackQuery):
        if not is_group(c.message.chat.type):
            await c.answer("Только в группах")
            return
        await handle_rules(c)
