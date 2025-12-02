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
ADMIN_ID = 5958164558

user_states = {}
drafts = {}
last_post_message_id = None  # para edición REAL de publicaciones


# ======================================================
#               TECLADO PRINCIPAL
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
#                        /START
# ======================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != ADMIN_ID:
        await update.message.reply_text("Este bot es solo para el administrador.")
        return

    user_states[user_id] = "IDLE"
    drafts[user_id] = {}

    await update.message.reply_text(
        "Panel listo.\nSelecciona una opción:",
        reply_markup=get_main_menu_keyboard(),
    )


# ======================================================
#           MANEJO DEL BOTÓN EDITAR (MENÚ 3 OPCIONES)
# ======================================================

async def show_edit_menu(update, context):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Editar borrador", callback_data="edit_draft")],
        [InlineKeyboardButton("📝 Editar publicación enviada", callback_data="edit_last")],
        [InlineKeyboardButton("♻️ Rehacer desde cero", callback_data="edit_reset")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
    ])

    await update.message.reply_text(
        "¿Qué deseas editar?",
        reply_markup=keyboard
    )

    user_states[update.effective_user.id] = "EDIT_MENU"


# ======================================================
#                MANEJO DE MENSAJES PRINCIPALES
# ======================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message
    text = message.text if message.text else ""

    if user_id != ADMIN_ID:
        return

    state = user_states.get(user_id, "IDLE")

    # -------------------------------
    # CANCELAR
    # -------------------------------
    if text.strip().startswith("❌"):
        user_states[user_id] = "IDLE"
        drafts[user_id] = {}

        await message.reply_text(
            "❌ Proceso cancelado.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # -------------------------------
    # CREAR PUBLICACIÓN
    # -------------------------------
    if text == "📝 Crear publicación":
        drafts[user_id] = {}
        user_states[user_id] = "WAITING_CONTENT"

        await message.reply_text("Envíame el contenido (texto, imagen, video o audio).")
        return

    # -------------------------------
    # EDITAR PUBLICACIÓN (MENU)
    # -------------------------------
    if text == "✏️ Editar publicación":
        await show_edit_menu(update, context)
        return

    # -------------------------------
    # PROGRAMAR PUBLICACIÓN
    # -------------------------------
    if text == "⏰ Programar publicación":
        drafts[user_id] = {}
        user_states[user_id] = "WAITING_CONTENT_SCHEDULE"

        await message.reply_text("Envíame el contenido que quieres programar.")
        return

    # ======================================================
    #     RECEPCIÓN DE CONTENIDO NUEVO (CREAR / PROGRAMAR)
    # ======================================================

    if state in ["WAITING_CONTENT", "WAITING_CONTENT_SCHEDULE", "EDITING_DRAFT"]:
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
            await message.reply_text("Formato no soportado.")
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

    # -------------------------------
    # FECHA PARA PROGRAMAR
    # -------------------------------
    if state == "WAITING_DATETIME":
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
        except:
            await message.reply_text("Formato inválido. Usa: 2025-12-02 18:30")
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
#          CALLBACKS (inline buttons)
# ======================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_post_message_id

    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    await query.answer()

    if user_id != ADMIN_ID:
        return

    draft = drafts.get(user_id)
    state = user_states.get(user_id, "IDLE")

    # ------------------------------------------------
    # ❌ CANCELAR
    # ------------------------------------------------
    if data == "cancel":
        drafts[user_id] = {}
        user_states[user_id] = "IDLE"

        await query.message.reply_text(
            "❌ Proceso cancelado.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # ------------------------------------------------
    # 1️⃣ EDITAR BORRADOR
    # ------------------------------------------------
    if data == "edit_draft":
        if not draft:
            await query.message.reply_text("No tienes borrador activo.")
            return

        user_states[user_id] = "EDITING_DRAFT"
        await query.message.reply_text("Envía el contenido corregido.")
        return

    # ------------------------------------------------
    # 2️⃣ EDITAR ÚLTIMA PUBLICACIÓN ENVIADA
    # ------------------------------------------------
    if data == "edit_last":
        if last_post_message_id is None:
            await query.message.reply_text("Aún no hay publicaciones enviadas.")
            return

        user_states[user_id] = "EDITING_LAST"
        await query.message.reply_text(
            "Envía el contenido que reemplazará la última publicación."
        )
        return

    # ------------------------------------------------
    # 3️⃣ REHACER DESDE CERO
    # ------------------------------------------------
    if data == "edit_reset":
        drafts[user_id] = {}
        user_states[user_id] = "WAITING_CONTENT"

        await query.message.reply_text(
            "Perfecto, envía el nuevo contenido desde cero."
        )
        return

    # ------------------------------------------------
    # 📤 PUBLICAR AHORA
    # ------------------------------------------------
    if data == "publish_now" and draft:

        if draft["type"] == "text":
            msg = await context.bot.send_message(CHANNEL_USERNAME, draft["text"])
        elif draft["type"] == "photo":
            msg = await context.bot.send_photo(CHANNEL_USERNAME, draft["file_id"], caption=draft["caption"])
        elif draft["type"] == "video":
            msg = await context.bot.send_video(CHANNEL_USERNAME, draft["file_id"], caption=draft["caption"])
        elif draft["type"] == "audio":
            msg = await context.bot.send_audio(CHANNEL_USERNAME, draft["file_id"])

        last_post_message_id = msg.message_id   # <- guardar para edición REAL

        drafts[user_id] = {}
        user_states[user_id] = "IDLE"

        await query.message.reply_text(
            "✅ Publicación enviada.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # ------------------------------------------------
    # ⏳ BOTÓN PROGRAMAR
    # ------------------------------------------------
    if data == "schedule":
        user_states[user_id] = "WAITING_DATETIME"
        await query.message.reply_text("Envía fecha y hora así:\n2025-12-02 18:30")
        return


# ======================================================
#                        MAIN
# ======================================================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))

    app.add_handler(
        MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO | filters.AUDIO, handle_message)
    )

    app.run_polling()


if __name__ == "__main__":
    main()
