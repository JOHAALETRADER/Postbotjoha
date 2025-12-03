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

# =====================================================
# CONFIGURACIÓN GENERAL
# =====================================================

TOKEN = os.environ.get("POST_BOT_TOKEN")
CHANNEL_USERNAME = "@JohaaleTrader_es"
ADMIN_ID = 5958164558  # tu ID personal

# Estado del usuario
user_states = {}
drafts = {}


# =====================================================
# TECLADOS
# =====================================================

def get_main_menu_keyboard():
    keyboard = [
        ["Crear publicación"],
        ["Editar publicación"],
        ["Programar publicación"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# =====================================================
# COMANDO /START
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("Acceso restringido.")
        return

    user_states[user.id] = "IDLE"
    await update.message.reply_text(
        "Panel listo.\n\nSelecciona una opción:",
        reply_markup=get_main_menu_keyboard()
    )


# =====================================================
# MANEJO DE MENSAJES
# =====================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    user = message.from_user
    if user.id != ADMIN_ID:
        await message.reply_text("Acceso restringido.")
        return

    text = message.text or ""
    user_id = user.id
    state = user_states.get(user_id, "IDLE")

    # -------------------------
    # MENÚ PRINCIPAL
    # -------------------------

    if text == "Crear publicación":
        user_states[user_id] = "WAITING_CONTENT"
        drafts[user_id] = {}

        await message.reply_text(
            "Envía ahora el contenido (texto, foto, video o audio con caption)."
        )
        return

    if text == "Editar publicación":
        user_states[user_id] = "WAITING_CONTENT"
        drafts[user_id] = {}

        await message.reply_text(
            "Envía el contenido corregido para rehacer la publicación."
        )
        return

    if text == "Programar publicación" and state == "IDLE":
        await message.reply_text(
            "Primero debes crear una publicación.\nUsa 'Crear publicación'."
        )
        return

    # -------------------------
    # CONTENIDO RECIBIDO
    # -------------------------

    if state == "WAITING_CONTENT":
        drafts[user_id] = {
            "from_chat_id": message.chat_id,
            "message_id": message.message_id,
        }
        user_states[user_id] = "WAITING_BUTTONS"

        await message.reply_text(
            "Ahora envía los botones, uno por línea:\n\n"
            "Texto - https://enlace.com\n"
            "Texto2 - https://enlace2.com\n"
        )
        return

    # -------------------------
    # BOTONES RECIBIDOS
    # -------------------------

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

        if not buttons:
            await message.reply_text("No detecté botones válidos.")
            return

        markup = InlineKeyboardMarkup(buttons)
        drafts[user_id]["buttons"] = markup

        # PREVIEW
        await context.bot.copy_message(
            chat_id=message.chat_id,
            from_chat_id=drafts[user_id]["from_chat_id"],
            message_id=drafts[user_id]["message_id"],
            reply_markup=markup,
        )

        user_states[user_id] = "CONFIRM_ACTION"

        kb = ReplyKeyboardMarkup(
            [["Publicar ahora"], ["Programar"], ["Cancelar"]],
            resize_keyboard=True
        )

        await message.reply_text(
            "Preview listo.\n\nElige una opción:",
            reply_markup=kb
        )
        return

    # -------------------------
    # ACCIÓN FINAL
    # -------------------------

    if state == "CONFIRM_ACTION":
        draft = drafts.get(user_id)

        if text == "Publicar ahora":
            await context.bot.copy_message(
                chat_id=CHANNEL_USERNAME,
                from_chat_id=draft["from_chat_id"],
                message_id=draft["message_id"],
                reply_markup=draft.get("buttons"),
            )

            user_states[user_id] = "IDLE"
            await message.reply_text(
                "Publicación enviada.",
                reply_markup=get_main_menu_keyboard()
            )
            return

        if text == "Programar":
            user_states[user_id] = "WAITING_SCHEDULE"
            await message.reply_text(
                "Envía la fecha y hora.\nFormatos válidos:\n"
                "→ 2025-12-03 14:30\n"
                "→ 03/12 14:30"
            )
            return

        if text == "Cancelar":
            user_states[user_id] = "IDLE"
            drafts.pop(user_id, None)
            await message.reply_text(
                "Publicación cancelada.",
                reply_markup=get_main_menu_keyboard()
            )
            return

        return

    # -------------------------
    # FECHA / PROGRAMACIÓN
    # -------------------------

    if state == "WAITING_SCHEDULE":
        draft = drafts.get(user_id)
        if not draft:
            user_states[user_id] = "IDLE"
            await message.reply_text(
                "No encontré la publicación. Intenta de nuevo.",
                reply_markup=get_main_menu_keyboard()
            )
            return

        text_clean = text.strip()
        ahora = datetime.now()
        dt = None

        # Intento 1 — YYYY-MM-DD HH:MM
        try:
            dt = datetime.strptime(text_clean, "%Y-%m-%d %H:%M")
        except:
            dt = None

        # Intento 2 — DD/MM HH:MM
        if dt is None:
            try:
                fecha_part, hora_part = text_clean.split(" ")
                d, m = fecha_part.split("/")
                h, mi = hora_part.split(":")
                dt = datetime(ahora.year, int(m), int(d), int(h), int(mi))
            except:
                dt = None

        if dt is None:
            await message.reply_text(
                "Formato inválido.\nUsa:\n"
                "→ 2025-12-03 14:30\n"
                "→ 03/12 14:30"
            )
            return

        # Si la hora ya pasó hoy → siguiente día
        if dt <= ahora:
            dt = dt + timedelta(days=1)

        job_data = {
            "from_chat_id": draft["from_chat_id"],
            "message_id": draft["message_id"],
            "buttons": draft.get("buttons"),
        }

        context.job_queue.run_once(
            send_scheduled_post,
            when=dt,
            data=job_data
        )

        user_states[user_id] = "IDLE"

        await message.reply_text(
            "Publicación programada para {} a las {}.".format(
                dt.strftime("%d/%m"), dt.strftime("%H:%M")
            ),
            reply_markup=get_main_menu_keyboard()
        )
        return

    # -------------------------
    # ESTADO IDLE
    # -------------------------

    if state == "IDLE":
        await message.reply_text(
            "Selecciona una opción del menú.",
            reply_markup=get_main_menu_keyboard()
        )
        return


# =====================================================
# ENVÍO PROGRAMADO (JOBQUEUE)
# =====================================================

async def send_scheduled_post(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    if not data:
        return

    await context.bot.copy_message(
        chat_id=CHANNEL_USERNAME,
        from_chat_id=data["from_chat_id"],
        message_id=data["message_id"],
        reply_markup=data.get("buttons"),
    )


# =====================================================
# MAIN
# =====================================================

def main():
    if not TOKEN:
        raise RuntimeError("Falta POST_BOT_TOKEN")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()

