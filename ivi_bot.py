import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, MessageHandler, filters
)

# ─── КОНФИГ ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_СЮДА")
ADMIN_ID   = int(os.getenv("ADMIN_ID", "ТВОЙ_TELEGRAM_ID"))

IVI_LOGIN    = os.getenv("IVI_LOGIN", "почта@example.com")
IVI_PASSWORD = os.getenv("IVI_PASSWORD", "твой_пароль")
MAX_USERS    = 6

DB_FILE = "users.json"

# ─── БАЗА (простой JSON файл) ──────────────────────────────────────────────────
def load_db() -> dict:
    if not os.path.exists(DB_FILE):
        return {"users": {}}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def get_active_count(db: dict) -> int:
    return sum(1 for u in db["users"].values() if u.get("active"))

# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid  = str(user.id)
    db   = load_db()

    # Уже есть доступ
    if uid in db["users"] and db["users"][uid].get("active"):
        await update.message.reply_text(
            f"👋 Привет, {user.first_name}!\n\n"
            f"У тебя уже есть доступ к Иви ✅\n\n"
            f"📧 Логин: `{IVI_LOGIN}`\n"
            f"🔑 Пароль: `{IVI_PASSWORD}`\n\n"
            "Заходи на ivi.ru и смотри!",
            parse_mode="Markdown"
        )
        return

    active = get_active_count(db)

    # Мест нет
    if active >= MAX_USERS:
        await update.message.reply_text(
            "😔 К сожалению, все места заняты.\n"
            "Напиши владельцу — он освободит место."
        )
        return

    # Выдаём доступ
    db["users"][uid] = {
        "name": user.first_name,
        "username": user.username or "",
        "joined": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "active": True
    }
    save_db(db)

    await update.message.reply_text(
        f"🎉 Привет, {user.first_name}! Доступ выдан!\n\n"
        f"📧 Логин: `{IVI_LOGIN}`\n"
        f"🔑 Пароль: `{IVI_PASSWORD}`\n\n"
        "👉 Заходи на ivi.ru, нажми «Войти» и вводи эти данные.\n\n"
        "Приятного просмотра! 🍿",
        parse_mode="Markdown"
    )

    # Уведомление админу
    await ctx.bot.send_message(
        ADMIN_ID,
        f"🔔 Новый пользователь подключился!\n"
        f"👤 {user.first_name} (@{user.username or 'нет'})\n"
        f"📊 Мест занято: {active + 1}/{MAX_USERS}"
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
        f"📊 Мест занято: {active}/{MAX_USERS}\n\n"
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
            await query.message.reply_text(f"✅ {name} удалён. Место освободилось.")
            # Уведомить пользователя
            try:
                await ctx.bot.send_message(
                    int(uid),
                    "😔 Твой доступ к Иви был отключён владельцем.\n"
                    "Напиши ему если это ошибка."
                )
            except:
                pass
        await query.message.delete()
        await show_admin_panel(query.message, ctx)

# ─── /users (краткая статистика) ──────────────────────────────────────────────
async def users_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    db     = load_db()
    active = get_active_count(db)
    await update.message.reply_text(f"📊 Сейчас подключено: {active}/{MAX_USERS}")

# ─── ЗАПУСК ───────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Бот запущен ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
