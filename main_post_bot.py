import os
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# =======================
# CONFIGURACIÓN BÁSICA
# =======================

TOKEN = os.environ.get("POST_BOT_TOKEN")

CHANNEL_USERNAME = "@JohaaleTrader_es"

ADMIN_ID = 5958164558  # tu ID actual y real

user_states = {}   # estados por usuario
drafts = {}        # borradores por usuario


def get_main_menu_keyboard():
    keyboard = [
        ["📝 Crear publicación"],
        ["✏️ Editar publicación"],
        ["⏰ Programar publicación"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# =========================================
#           INICIO / START
# =========================================
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


# =========================================
#      FUNCIONES DE MANEJO DE ESTADOS
# =========================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text if update.message.text else ""
    message = update.message

    if user_id != ADMIN_ID:
        return

    state = user_states.get(user_id, "IDLE")

    # ============================
    #     BOTÓN CANCELAR (FIX)
    # ============================
    if text.strip().startswith("❌"):
        drafts[user_id] = {}
        user_states[user_id] = "IDLE"

        await message.reply_text(
            "❌ Proceso cancelado.\n\nMenú principal:",
            reply_markup=get_main_menu_keyboard()
        )
        return

    # ============================
    #     CREAR PUBLICACIÓN
    # ============================
    if text == "📝 Crear publicación":
        drafts[user_id] = {}
        user_states[user_id] = "WAITING_CONTENT"

        await message.reply_text(
            "Envía el contenido (texto, foto, video o audio)."
        )
        return

    # ============================
    #     EDITAR PUBLICACIÓN (FIX)
    # ============================
    if text == "✏️ Editar publicación":
        drafts[user_id] = {}
        user_states[user_id] = "WAITING_CONTENT"

        await message.reply_text(
            "Vamos a rehacer una publicación.\n"
            "Envíame el nuevo contenido (texto o media con caption)."
        )
        return

    # ============================
    #     PROGRAMAR PUBLICACIÓN
    # ============================
    if text == "⏰ Programar publicación":
        drafts[user_id] = {}
        user_states[user_id] = "WAITING_CONTENT_SCHEDULE"

        await message.reply_text(
            "Envía el contenido que quieras programar."
        )
        return

    # ==========================================
    #      RECEPCIÓN DE CONTENIDO PRINCIPAL
    # ==========================================
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

        # Teclado de confirmación
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Publicar ahora", callback_data="publish_now")],
            [InlineKeyboardButton("⏳ Programar envío", callback_data="schedule")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ])

        await message.reply_text(
            "Preview listo.\n\nElige una opción:",
            reply_markup=keyboard
        )

        user_states[user_id] = "CONFIRM_ACTION"
        return


# =========================================
#      CALLBACKS PARA PUBLICAR / CANCELAR
# =========================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    await query.answer()

    if user_id != ADMIN_ID:
        return

    state = user_states.get(user_id, "IDLE")
    draft = drafts.get(user_id)

    # =============================
    # ❌ CANCELAR (BOTÓN INLINE)
    # =============================
    if data == "cancel":
        drafts[user_id] = {}
        user_states[user_id] = "IDLE"

        await query.message.reply_text(
            "❌ Proceso cancelado.\n\nMenú principal:",
            reply_markup=get_main_menu_keyboard()
        )
        return

    # =============================
    # 📤 PUBLICAR AHORA
    # =============================
    if data == "publish_now" and draft:

        if draft["type"] == "text":
            await context.bot.send_message(
                chat_id=CHANNEL_USERNAME,
                text=draft["text"]
            )
        elif draft["type"] == "photo":
            await context.bot.send_photo(
                chat_id=CHANNEL_USERNAME,
                photo=draft["file_id"],
                caption=draft["caption"]
            )
        elif draft["type"] == "video":
            await context.bot.send_video(
                chat_id=CHANNEL_USERNAME,
                video=draft["file_id"],
                caption=draft["caption"]
            )
        elif draft["type"] == "audio":
            await context.bot.send_audio(
                chat_id=CHANNEL_USERNAME,
                audio=draft["file_id"]
            )

        drafts[user_id] = {}
        user_states[user_id] = "IDLE"

        await query.message.reply_text(
            "✅ Publicación enviada al canal.",
            reply_markup=get_main_menu_keyboard()
        )
        return

    # =============================
    # ⏳ PROGRAMAR PUBLICACIÓN
    # =============================
    if data == "schedule":
        user_states[user_id] = "WAITING_DATETIME"
        await query.message.reply_text(
            "Envía fecha y hora en formato:\n\n`2025-12-02 18:30`",
            parse_mode="Markdown"
        )
        return


# =========================================
#      FECHA Y HORA DE PROGRAMACIÓN
# =========================================

async def schedule_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return

    state = user_states.get(user_id)

    if state != "WAITING_DATETIME":
        return

    try:
        dt = datetime.strptime(update.message.text, "%Y-%m-%d %H:%M")
    except:
        await update.message.reply_text("Formato inválido. Intenta de nuevo.")
        return

    draft = drafts[user_id]

    async def send_later(context):
        if draft["type"] == "text":
            await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=draft["text"])
        elif draft["type"] == "photo":
            await context.bot.send_photo(chat_id=CHANNEL_USERNAME, photo=draft["file_id"], caption=draft["caption"])
        elif draft["type"] == "video":
            await context.bot.send_video(chat_id=CHANNEL_USERNAME, video=draft["file_id"], caption=draft["caption"])
        elif draft["type"] == "audio":
            await context.bot.send_audio(chat_id=CHANNEL_USERNAME, audio=draft["file_id"])

    context.job_queue.run_once(send_later, when=(dt - datetime.now()))

    drafts[user_id] = {}
    user_states[user_id] = "IDLE"

    await update.message.reply_text(
        f"⏳ Publicación programada para {dt}.",
        reply_markup=get_main_menu_keyboard()
    )


# =========================================
#                 MAIN
# =========================================
def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO | filters.AUDIO, handle_message))
    application.add_handler(MessageHandler(filters.TEXT, schedule_handler))
    application.add_handler(MessageHandler(filters.COMMAND, handle_message))

    application.add_handler(MessageHandler(filters.ALL, handle_message))
    application.add_handler(MessageHandler(filters.ALL, schedule_handler))

    application.add_handler(MessageHandler(filters.ALL, handle_message))
    application.add_handler(MessageHandler(filters.ALL, schedule_handler))

    application.add_handler(MessageHandler(filters.COMMAND, handle_message))

    application.add_handler(MessageHandler(filters.COMMAND, schedule_handler))

    application.add_handler(MessageHandler(filters.ALL, handle_message))

    application.add_handler(MessageHandler(filters.ALL, schedule_handler))

    application.add_handler(MessageHandler(filters.COMMAND, handle_message))

    application.add_handler(MessageHandler(filters.COMMAND, schedule_handler))

    application.add_handler(MessageHandler(filters.ALL, handle_message))

    application.add_handler(MessageHandler(filters.ALL, schedule_handler))

    application.add_handler(MessageHandler(filters.COMMAND, handle_message))

    application.add_handler(MessageHandler(filters.COMMAND, schedule_handler))

    application.add_handler(MessageHandler(filters.ALL, handle_message))

    # Botones inline
    application.add_handler(
        telegram.ext.CallbackQueryHandler(button_callback)
    )

    application.run_polling()


if __name__ == "__main__":
    main()
