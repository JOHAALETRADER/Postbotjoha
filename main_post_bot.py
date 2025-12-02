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
ADMIN_ID = 5958164558   # tu ID real

user_states = {}
drafts = {}
last_post_message_id = None


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
#                 MENÚ DE EDICIÓN 3 OPCIONES
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
#              MANEJO DE MENSAJES
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

        await message.reply_text("Envíame el contenido (texto, media).")
        return

    # -------------------------------
    # EDITAR PUBLICACIÓN (MENÚ)
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

        await message.reply_text("Envíame el contenido que deseas programar.")
        return

    # ======================================================
    #    RECIBIENDO CONTENIDO PRINCIPAL
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
        user_states[user_id] = "WAITING_BUTTONS"

        await message.reply_text("Agrega los enlaces (uno por línea).")
        return

    # ======================================================
    #     RECIBIENDO BOTONES
    # ======================================================

    if state == "WAITING_BUTTONS":
        lines = text.splitlines()
        buttons = []

        for line in lines:
            if "-" not in line:
                continue

            label, url = line.split("-", 1)
            label = label.strip()
            url = url.strip()

            if label and url:
                buttons.append([InlineKeyboardButton(label, url=url)])

        drafts[user_id]["buttons"] = InlineKeyboardMarkup(buttons)

        preview_markup = InlineKeyboardMarkup(buttons)

        await message.reply_text(
            "Preview listo.\nElige una opción:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Publicar ahora", callback_data="publish_now")],
                [InlineKeyboardButton("⏳ Programar", callback_data="schedule")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")],
            ])
        )

        user_states[user_id] = "CONFIRM"
        return

    # ======================================================
    #       FECHA PARA PROGRAMAR
    # ======================================================

    if state == "WAITING_DATETIME":
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
        except:
            await message.reply_text("Formato inválido. Usa: 2025-12-02 18:30")
            return

        draft = drafts.get(user_id)

        async def send_later(context):
            if draft["type"] == "text":
                await context.bot.send_message(
                    CHANNEL_USERNAME,
                    draft["text"],
                    reply_markup=draft.get("buttons")
                )
            elif draft["type"] == "photo":
                await context.bot.send_photo(
                    CHANNEL_USERNAME,
                    draft["file_id"],
                    caption=draft["caption"],
                    reply_markup=draft.get("buttons")
                )
            elif draft["type"] == "video":
                await context.bot.send_video(
                    CHANNEL_USERNAME,
                    draft["file_id"],
                    caption=draft["caption"],
                    reply_markup=draft.get("buttons")
                )
            elif draft["type"] == "audio":
                await context.bot.send_audio(
                    CHANNEL_USERNAME,
                    draft["file_id"],
                    reply_markup=draft.get("buttons")
                )

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

    draft = drafts.get(user_id)

    if user_id != ADMIN_ID:
        return

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
    # EDITAR BORRADOR
    # ------------------------------------------------
    if data == "edit_draft":
        if not draft:
            await query.message.reply_text("No tienes borrador activo.")
            return

        user_states[user_id] = "EDITING_DRAFT"
        await query.message.reply_text("Envía el contenido corregido.")
        return

    # ------------------------------------------------
    # EDITAR ÚLTIMA PUBLICACIÓN (REAL)
    # ------------------------------------------------
    if data == "edit_last":
        if last_post_message_id is None:
            await query.message.reply_text("No hay publicaciones previas.")
            return

        user_states[user_id] = "EDITING_LAST"
        await query.message.reply_text(
            "Envía el contenido nuevo para reemplazar la última publicación."
        )
        return

    # ------------------------------------------------
    # REHACER
    # ------------------------------------------------
    if data == "edit_reset":
        drafts[user_id] = {}
        user_states[user_id] = "WAITING_CONTENT"

        await query.message.reply_text(
            "Perfecto, envía el nuevo contenido."
        )
        return

    # ------------------------------------------------
    # PUBLICAR AHORA
    # ------------------------------------------------
    if data == "publish_now" and draft:
        if draft["type"] == "text":
            msg = await context.bot.send_message(
                CHANNEL_USERNAME,
                draft["text"],
                reply_markup=draft.get("buttons")
            )
        elif draft["type"] == "photo":
            msg = await context.bot.send_photo(
                CHANNEL_USERNAME,
                draft["file_id"],
                caption=draft["caption"],
                reply_markup=draft.get("buttons")
            )
        elif draft["type"] == "video":
            msg = await context.bot.send_video(
                CHANNEL_USERNAME,
                draft["file_id"],
                caption=draft["caption"],
                reply_markup=draft.get("buttons")
            )
        elif draft["type"] == "audio":
            msg = await context.bot.send_audio(
                CHANNEL_USERNAME,
                draft["file_id"],
                reply_markup=draft.get("buttons")
            )

        last_post_message_id = msg.message_id
        drafts[user_id] = {}
        user_states[user_id] = "IDLE"

        await query.message.reply_text(
            "✔ Publicación enviada.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # ------------------------------------------------
    # PROGRAMAR DESDE BOTÓN
    # ------------------------------------------------
    if data == "schedule":
        user_states[user_id] = "WAITING_DATETIME"
        await query.message.reply_text("Envía la fecha y hora:\n2025-12-02 18:30")
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
