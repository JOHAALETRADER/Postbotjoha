import os
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ======================================================
#                   CONFIGURACIÓN
# ======================================================

TOKEN = os.environ.get("POST_BOT_TOKEN")
CHANNEL_USERNAME = "@JohaaleTrader_es"
ADMIN_ID = 5958164558   # Tu ID real

user_states = {}
drafts = {}


# ======================================================
#               MENÚ PRINCIPAL
# ======================================================

def get_main_menu_keyboard():
    keyboard = [
        ["📝 Crear publicación"],
        ["✏️ Editar publicación"],
        ["⏰ Programar publicación"],
        ["❌ Cancelar"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ======================================================
#                   /START
# ======================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("Este bot es solo para el administrador.")
        return

    user_states[user_id] = "IDLE"
    drafts[user_id] = {}

    await update.message.reply_text(
        "Panel listo.\n\nElige una opción:",
        reply_markup=get_main_menu_keyboard(),
    )


# ======================================================
#              MANEJO DE MENSAJES
# ======================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message
    text = message.text if message.text else ""

    if user_id != ADMIN_ID:
        return

    state = user_states.get(user_id, "IDLE")

    # ============================
    #     BOTÓN CANCELAR
    # ============================
    if text.strip().startswith("❌"):
        drafts[user_id] = {}
        user_states[user_id] = "IDLE"

        await message.reply_text(
            "❌ Proceso cancelado.\nMenú principal:",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # ============================
    #     CREAR PUBLICACIÓN
    # ============================
    if text == "📝 Crear publicación":
        drafts[user_id] = {}
        user_states[user_id] = "WAITING_CONTENT"

        await message.reply_text("Envía el contenido (texto, foto, video o audio).")
        return

    # ============================
    #     EDITAR PUBLICACIÓN
    # ============================
    if text == "✏️ Editar publicación":
        drafts[user_id] = {}
        user_states[user_id] = "WAITING_CONTENT"

        await message.reply_text(
            "Vamos a rehacer una publicación.\n"
            "Envíame el nuevo contenido."
        )
        return

    # ============================
    #     PROGRAMAR PUBLICACIÓN
    # ============================
    if text == "⏰ Programar publicación":
        drafts[user_id] = {}
        user_states[user_id] = "WAITING_CONTENT_SCHEDULE"

        await message.reply_text("Envía el contenido que quieres programar.")
        return

    # ======================================================
    #        RECIBIENDO CONTENIDO PRINCIPAL
    # ======================================================

    if state in ["WAITING_CONTENT", "WAITING_CONTENT_SCHEDULE"]:
        content = {}

        if message.photo:
            content["type"] = "photo"
            content["file_id"] = message.photo[-1].file_id
            content["caption"] = message.caption or ""

        elif message.video:
            content["type"] = "video"
            content["file_id"] = message.video.file_id
            content["caption"] = message.caption or ""

        elif message.audio:
            content["type"] = "audio"
            content["file_id"] = message.audio.file_id
            content["caption"] = ""

        elif message.text:
            content["type"] = "text"
            content["text"] = message.text

        else:
            await message.reply_text("Formato no compatible.")
            return

        drafts[user_id] = content

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Publicar ahora", callback_data="publish_now")],
            [InlineKeyboardButton("⏳ Programar", callback_data="schedule")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")],
        ])

        await message.reply_text("Preview listo.\nElige una opción:", reply_markup=keyboard)
        user_states[user_id] = "CONFIRM"
        return

    # ======================================================
    #  FECHA Y HORA PARA PROGRAMAR
    # ======================================================

    if state == "WAITING_DATETIME":
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
        except:
            await message.reply_text("Formato inválido. Usa:\n2025-12-02 18:30")
            return

        draft = drafts.get(user_id)

        async def send_later(context):
            if draft["type"] == "text":
                await context.bot.send_message(CHANNEL_USERNAME, draft["text"])
            elif draft["type"] == "photo":
                await context.bot.send_photo(CHANNEL_USERNAME, draft["file_id"], caption=draft["caption"])
            elif draft["type"] == "video":
                await context.bot.send_video(CHANNEL_USERNAME, draft["file_id"], caption=draft["caption"])
            elif draft["type"] == "audio":
                await context.bot.send_audio(CHANNEL_USERNAME, draft["file_id"])

        context.job_queue.run_once(send_later, when=(dt - datetime.now()))

        drafts[user_id] = {}
        user_states[user_id] = "IDLE"

        await message.reply_text(
            f"⏳ Publicación programada para {dt}.",
            reply_markup=get_main_menu_keyboard(),
        )
        return


# ======================================================
#              CALLBACKS DE BOTONES
# ======================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    await query.answer()

    if user_id != ADMIN_ID:
        return

    draft = drafts.get(user_id)

    # ❌ CANCELAR
    if data == "cancel":
        drafts[user_id] = {}
        user_states[user_id] = "IDLE"

        await query.message.reply_text(
            "❌ Proceso cancelado.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # 📤 PUBLICAR AHORA
    if data == "publish_now" and draft:
        if draft["type"] == "text":
            await context.bot.send_message(CHANNEL_USERNAME, draft["text"])
        elif draft["type"] == "photo":
            await context.bot.send_photo(CHANNEL_USERNAME, draft["file_id"], caption=draft["caption"])
        elif draft["type"] == "video":
            await context.bot.send_video(CHANNEL_USERNAME, draft["file_id"], caption=draft["caption"])
        elif draft["type"] == "audio":
            await context.bot.send_audio(CHANNEL_USERNAME, draft["file_id"])

        drafts[user_id] = {}
        user_states[user_id] = "IDLE"

        await query.message.reply_text(
            "✅ Publicación enviada al canal.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # ⏳ PROGRAMAR
    if data == "schedule":
        user_states[user_id] = "WAITING_DATETIME"
        await query.message.reply_text(
            "Envía la fecha y hora en formato:\n2025-12-02 18:30"
        )
        return


# ======================================================
#                     MAIN
# ======================================================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO | filters.AUDIO, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()
