import os
import json
import imaplib
import email
import re
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes
)

# ─── КОНФИГ ───────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.getenv("BOT_TOKEN", "ТОКЕН_БОТА")
ADMIN_ID       = int(os.getenv("ADMIN_ID", "0"))
GMAIL_USER     = os.getenv("GMAIL_USER", "почта@gmail.com")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "пароль_приложения")
MAX_USERS      = 6
DB_FILE        = "users.json"

# ─── БАЗА ─────────────────────────────────────────────────────────────────────
def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "pending": {}}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def get_active_count(db):
    return sum(1 for u in db["users"].values() if u.get("active"))

# ─── ПОЛУЧИТЬ КОД С GMAIL ─────────────────────────────────────────────────────
def get_ivi_code():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASSWORD)
        mail.select("inbox")

        # Ищем письма от Иви за последние письма
        _, data = mail.search(None, 'FROM "ivi.ru"')
        ids = data[0].split()

        if not ids:
            return None

        # Берём последнее письмо
        _, msg_data = mail.fetch(ids[-1], "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])

        # Извлекаем текст
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    break
        else:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

        # Ищем код (4-6 цифр)
        codes = re.findall(r'\b\d{4,6}\b', body)
        mail.logout()

        return codes[0] if codes else None
    except Exception as e:
        print(f"Gmail ошибка: {e}")
        return None

# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid  = str(user.id)
    db   = load_db()

    if uid in db["users"] and db["users"][uid].get("active"):
        await update.message.reply_text(
            f"👋 {user.first_name}, у тебя уже есть доступ!\n\n"
            f"📧 Почта Иви: `{GMAIL_USER}`\n\n"
            "Зайди на ivi.ru → введи почту → получишь код на эту почту.\n"
            "Напиши /код чтобы получить код прямо здесь 👇",
            parse_mode="Markdown"
        )
        return

    active = get_active_count(db)
    if active >= MAX_USERS:
        await update.message.reply_text(
            "😔 Все места заняты. Напиши владельцу."
        )
        return

    db["users"][uid] = {
        "name": user.first_name,
        "username": user.username or "",
        "joined": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "active": True
    }
    save_db(db)

    await update.message.reply_text(
        f"🎉 {user.first_name}, доступ выдан!\n\n"
        f"📧 Почта для входа на Иви: `{GMAIL_USER}`\n\n"
        "👉 Как войти:\n"
        "1. Зайди на ivi.ru\n"
        "2. Нажми «Войти»\n"
        "3. Введи эту почту\n"
        "4. Напиши /код — я пришлю тебе код из письма\n\n"
        "Приятного просмотра! 🍿",
        parse_mode="Markdown"
    )

    await ctx.bot.send_message(
        ADMIN_ID,
        f"🔔 Новый пользователь!\n"
        f"👤 {user.first_name} (@{user.username or 'нет'})\n"
        f"📊 Занято: {active + 1}/{MAX_USERS}"
    )

# ─── /код — получить код из Gmail ─────────────────────────────────────────────
async def get_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    db  = load_db()

    if uid not in db["users"] or not db["users"][uid].get("active"):
        await update.message.reply_text("❌ У тебя нет доступа. Напиши /start")
        return

    await update.message.reply_text("🔍 Ищу код в почте...")

    code = get_ivi_code()
    if code:
        await update.message.reply_text(
            f"✅ Вот твой код для входа:\n\n`{code}`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "😔 Код не найден. Попробуй:\n"
            "1. Сначала введи почту на ivi.ru\n"
            "2. Подожди 30 секунд\n"
            "3. Напиши /код снова"
        )

# ─── АДМИН ПАНЕЛЬ ─────────────────────────────────────────────────────────────
async def admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await show_admin_panel(update.message, ctx)

async def show_admin_panel(message, ctx):
    db     = load_db()
    active = get_active_count(db)

    text = (
        f"🛠 *Админ панель*\n\n"
        f"📊 Занято мест: {active}/{MAX_USERS}\n\n"
        f"👥 *Пользователи:*\n"
    )

    buttons = []
    if db["users"]:
        for uid, u in db["users"].items():
            status = "✅" if u.get("active") else "❌"
            text  += f"{status} {u['name']} (@{u['username'] or '—'}) — {u['joined']}\n"
            if u.get("active"):
                buttons.append([InlineKeyboardButton(
                    f"❌ Убрать {u['name']}", callback_data=f"remove_{uid}"
                )])
    else:
        text += "Пока никого нет.\n"

    buttons.append([InlineKeyboardButton("🔄 Обновить", callback_data="refresh")])

    await message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    data = query.data

    if data == "refresh":
        await query.message.delete()
        await show_admin_panel(query.message, ctx)
        return

    if data.startswith("remove_"):
        uid = data.replace("remove_", "")
        db  = load_db()
        if uid in db["users"]:
            name = db["users"][uid]["name"]
            db["users"][uid]["active"] = False
            save_db(db)
            try:
                await ctx.bot.send_message(
                    int(uid),
                    "😔 Твой доступ к Иви был отключён."
                )
            except:
                pass
            await query.message.reply_text(f"✅ {name} удалён.")
        await query.message.delete()
        await show_admin_panel(query.message, ctx)

# ─── ЗАПУСК ───────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("код", get_code))
    app.add_handler(CommandHandler("kod", get_code))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Бот запущен ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
