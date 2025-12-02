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

# =========================
# CONFIGURACIÓN BÁSICA
# =========================

# En Railway crea una variable de entorno: POST_BOT_TOKEN
TOKEN = os.environ.get("POST_BOT_TOKEN")

# Canal donde se publicará
CHANNEL_USERNAME = "@JohaaleTrader_es"

# Solo tú puedes usar este panel (tu ID personal)
ADMIN_ID = 5924691120  # ya lo tenemos de antes

# Estados por usuario
user_states = {}  # user_id -> estado
drafts = {}       # user_id -> dict con borrador


def get_main_menu_keyboard():
    keyboard = [
        ["📝 Crear publicación"],
        ["✏️ Editar publicación"],
        ["⏰ Programar publicación"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# =========================
# HANDLERS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    if user.id != ADMIN_ID:
        await update.message.reply_text("Este bot es solo para el administrador.")
        return

    user_states[user.id] = "IDLE"
    text = "Panel de publicaciones listo. Elige una opción del menú."
    await update.message.reply_text(text, reply_markup=get_main_menu_keyboard())


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    user = message.from_user
    if user is None:
        return

    user_id = user.id

    if user_id != ADMIN_ID:
        await message.reply_text("Acceso solo para el administrador.")
        return

    text = message.text if message.text is not None else ""
    state = user_states.get(user_id, "IDLE")

    if text == "📝 Crear publicación":
        user_states[user_id] = "WAITING_CONTENT"
        drafts[user_id] = {}
        info = (
            "Envía ahora el contenido que quieres publicar.\n\n"
            "- Puede ser solo texto.\n"
            "- O foto / video / audio con el texto en el caption.\n\n"
            "Después te pediré los botones con enlaces."
        )
        await message.reply_text(info)
        return

    if text == "✏️ Editar publicación":
        user_states[user_id] = "WAITING_CONTENT"
        drafts[user_id] = {}
        info = (
            "Vamos a rehacer una publicación.\n"
            "Envía el contenido (texto o media con caption) que quieras usar."
        )
        await message.reply_text(info)
        return

    if text == "⏰ Programar publicación" and state == "IDLE":
        aviso = (
            "Para programar primero crea un borrador con 'Crear publicación'.\n"
            "Después de ver el preview podrás elegir la opción de programar."
        )
        await message.reply_text(aviso)
        return

    if state == "WAITING_CONTENT":
        drafts[user_id] = {
            "from_chat_id": message.chat_id,
            "message_id": message.message_id,
        }

        user_states[user_id] = "WAITING_BUTTONS"

        texto = (
            "Perfecto.\n\n"
            "Ahora envíame los botones en UN SOLO mensaje, uno por línea,\n"
            "con el formato:\n\n"
            "Texto botón - https://enlace.com\n"
            "Otro botón - https://otro-enlace.com\n\n"
            "Ejemplo:\n"
            "✨ REGÍSTRATE YA ✨ - https://tuenlace.com\n"
            "📊 CANAL DE RESULTADOS - https://t.me/tu_canal\n"
        )
        await message.reply_text(texto)
        return

    if state == "WAITING_BUTTONS":
        if not text:
            await message.reply_text(
                "Necesito que envíes los botones en texto, con el formato:\n"
                "Texto - URL"
            )
            return

        lines = text.splitlines()
        buttons = []

        for line in lines:
            if "-" not in line:
                continue
            parts = line.split("-", 1)
            label = parts[0].strip()
            url = parts[1].strip()
            if label and url:
                buttons.append([InlineKeyboardButton(label, url=url)])

        if not buttons:
            await message.reply_text(
                "No pude detectar botones válidos.\n"
                "Asegúrate de usar el formato:\n"
                "Texto botón - https://enlace.com"
            )
            return

        markup = InlineKeyboardMarkup(buttons)
        drafts[user_id]["buttons"] = markup

        await context.bot.copy_message(
            chat_id=message.chat_id,
            from_chat_id=drafts[user_id]["from_chat_id"],
            message_id=drafts[user_id]["message_id"],
            reply_markup=markup,
        )

        keyboard = [
            ["📤 Publicar ahora"],
            ["⏰ Programar publicación"],
            ["❌ Cancelar"],
        ]
        reply_kb = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        user_states[user_id] = "CONFIRM_ACTION"

        await message.reply_text(
            "Preview listo.\n\nElige una opción:",
            reply_markup=reply_kb,
        )
        return

    if state == "CONFIRM_ACTION":
        if "Publicar ahora" in text:
            draft = drafts.get(user_id)
            if not draft:
                user_states[user_id] = "IDLE"
                await message.reply_text(
                    "No encontré el borrador. Vuelve a crearlo desde el menú."
                )
                await message.reply_text(
                    "Menú principal:", reply_markup=get_main_menu_keyboard()
                )
                return

            await context.bot.copy_message(
                chat_id=CHANNEL_USERNAME,
                from_chat_id=draft["from_chat_id"],
                message_id=draft["message_id"],
                reply_markup=draft.get("buttons"),
            )

            user_states[user_id] = "IDLE"
            await message.reply_text(
                "✅ Publicación enviada al canal.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        if "Programar publicación" in text:
            user_states[user_id] = "WAITING_SCHEDULE"
            texto = (
                "Envía la fecha y hora en formato:\n"
                "DD/MM HH:MM (hora Colombia)\n\n"
                "Ejemplo: 02/12 14:30"
            )
            await message.reply_text(texto)
            return

        if "Cancelar" in text:
            user_states[user_id] = "IDLE"
            drafts.pop(user_id, None)
            await message.reply_text(
                "❌ Publicación cancelada.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        await message.reply_text("No entendí tu elección. Usa los botones del menú.")
        return

    if state == "WAITING_SCHEDULE":
        draft = drafts.get(user_id)
        if not draft:
            user_states[user_id] = "IDLE"
            await message.reply_text(
                "No encontré el borrador. Vuelve a crearlo desde el menú.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        try:
            text_clean = text.strip()
            fecha_part, hora_part = text_clean.split(" ")
            dia_str, mes_str = fecha_part.split("/")
            hora_str, minuto_str = hora_part.split(":")

            dia = int(dia_str)
            mes = int(mes_str)
            hora = int(hora_str)
            minuto = int(minuto_str)

            ahora = datetime.now()
            año = ahora.year

            dt = datetime(año, mes, dia, hora, minuto)

            if dt <= ahora:
                dt = dt + timedelta(days=1)

        except Exception:
            await message.reply_text(
                "Formato no válido.\nUsa: DD/MM HH:MM\nEjemplo: 02/12 14:30"
            )
            return

        job_data = {
            "from_chat_id": draft["from_chat_id"],
            "message_id": draft["message_id"],
            "buttons": draft.get("buttons"),
        }

        context.job_queue.run_once(send_scheduled_post, when=dt, data=job_data)

        user_states[user_id] = "IDLE"
        await message.reply_text(
            "⏰ Publicación programada.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    if state == "IDLE":
        await message.reply_text(
            "Usa el menú de abajo para crear o programar publicaciones.",
            reply_markup=get_main_menu_keyboard(),
        )
        return


async def send_scheduled_post(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    if not data:
        return

    from_chat_id = data.get("from_chat_id")
    message_id = data.get("message_id")
    buttons = data.get("buttons")

    await context.bot.copy_message(
        chat_id=CHANNEL_USERNAME,
        from_chat_id=from_chat_id,
        message_id=message_id,
        reply_markup=buttons,
    )


def main() -> None:
    if not TOKEN:
        raise RuntimeError("Falta la variable de entorno POST_BOT_TOKEN")

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.ALL & (~filters.COMMAND), handle_message)
    )

    application.run_polling()


if __name__ == "__main__":
    main()
