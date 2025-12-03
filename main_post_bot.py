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

# Usa variable de entorno POST_BOT_TOKEN, o este token si no está definida
TOKEN = os.environ.get(
    "POST_BOT_TOKEN",
    "8491740253:AAG8GAnaCQYgHtabplU4Xf3pWahOlyzUXt8"
)

CHANNEL_USERNAME = "@JohaaleTrader_es"
ADMIN_ID = 5958164558

# Estados y datos en memoria
user_states = {}       # user_id -> estado actual
drafts = {}            # user_id -> borrador de publicación
button_templates = {}  # nombre -> lista de (texto, url)


# =====================================================
# TECLADOS (MENÚS)
# =====================================================

def get_main_menu_keyboard():
    keyboard = [
        ["📝 Crear publicación"],
        ["✏️ Editar publicación"],
        ["🔗 Botones guardados"],
        ["⏰ Programar publicación"],
        ["❌ Cancelar"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_buttons_menu_keyboard():
    keyboard = [
        ["➕ Añadir botón"],
        ["📋 Ver plantillas"],
        ["⬅ Volver al menú"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# =====================================================
# /START
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None or update.message is None:
        return

    if user.id != ADMIN_ID:
        await update.message.reply_text("Acceso restringido.")
        return

    user_states[user.id] = "IDLE"
    await update.message.reply_text(
        "Panel de publicaciones listo.\nElige una opción:",
        reply_markup=get_main_menu_keyboard(),
    )


# =====================================================
# MANEJO DE MENSAJES
# =====================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    user = message.from_user
    if user is None:
        return

    user_id = user.id
    text = message.text or ""

    # Restringir a admin
    if user_id != ADMIN_ID:
        await message.reply_text("Acceso restringido.")
        return

    state = user_states.get(user_id, "IDLE")

    # Permitir /start desde aquí también
    if text == "/start":
        user_states[user_id] = "IDLE"
        await message.reply_text(
            "Panel de publicaciones listo.\nElige una opción:",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # -------------------------
    # ESTADO: IDLE (MENÚ PRINCIPAL)
    # -------------------------
    if state == "IDLE":
        if text == "📝 Crear publicación":
            user_states[user_id] = "WAITING_CONTENT"
            drafts[user_id] = {}
            await message.reply_text(
                "Envía el contenido que quieres publicar.\n"
                "- Texto o\n"
                "- Foto / video / audio con caption."
            )
            return

        if text == "✏️ Editar publicación":
            user_states[user_id] = "WAITING_EDIT_MESSAGE"
            await message.reply_text(
                "Reenvía desde el canal la publicación que quieres editar."
            )
            return

        if text == "🔗 Botones guardados":
            user_states[user_id] = "BUTTONS_MENU"
            await message.reply_text(
                "Menú de botones guardados:",
                reply_markup=get_buttons_menu_keyboard(),
            )
            return

        if text == "⏰ Programar publicación":
            draft = drafts.get(user_id)
            if not draft:
                await message.reply_text(
                    "No hay borrador actual.\nPrimero usa '📝 Crear publicación'."
                )
                return
            user_states[user_id] = "WAITING_SCHEDULE"
            await message.reply_text(
                "Envía la fecha y hora.\n"
                "Formatos aceptados:\n"
                "2025-12-03 14:30\n"
                "03/12 14:30"
            )
            return

        if text == "❌ Cancelar":
            drafts.pop(user_id, None)
            user_states[user_id] = "IDLE"
            await message.reply_text(
                "Acción cancelada.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        await message.reply_text(
            "Usa el menú para elegir una opción.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # -------------------------
    # CREAR PUBLICACIÓN: CONTENIDO
    # -------------------------
    if state == "WAITING_CONTENT":
        drafts[user_id] = {
            "from_chat_id": message.chat_id,
            "message_id": message.message_id,
            "buttons": None,
        }
        user_states[user_id] = "WAITING_BUTTONS"

        await message.reply_text(
            "Ahora envía los botones en un solo mensaje, uno por línea:\n\n"
            "Texto - https://enlace.com\n\n"
            "Ejemplo:\n"
            "REGÍSTRATE - https://tu-enlace.com"
        )
        return

    # -------------------------
    # CREAR PUBLICACIÓN: BOTONES
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
            await message.reply_text(
                "No detecté botones válidos.\nUsa el formato:\n"
                "Texto - https://enlace.com"
            )
            return

        markup = InlineKeyboardMarkup(buttons)
        drafts[user_id]["buttons"] = markup

        # Vista previa en tu chat privado
        await context.bot.copy_message(
            chat_id=message.chat_id,
            from_chat_id=drafts[user_id]["from_chat_id"],
            message_id=drafts[user_id]["message_id"],
            reply_markup=markup,
        )

        keyboard = [
            ["📤 Publicar ahora"],
            ["⏰ Programar"],
            ["💾 Guardar botones como plantilla"],
            ["❌ Cancelar"],
        ]
        user_states[user_id] = "CONFIRM_ACTION"

        await message.reply_text(
            "Vista previa lista.\nElige una opción:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        )
        return

    # -------------------------
    # CONFIRMAR ACCIÓN (PUBLICAR / PROGRAMAR / GUARDAR)
    # -------------------------
    if state == "CONFIRM_ACTION":
        draft = drafts.get(user_id)

        if not draft:
            user_states[user_id] = "IDLE"
            await message.reply_text(
                "No hay borrador.\nVuelve a crear la publicación.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        if text == "📤 Publicar ahora":
            await context.bot.copy_message(
                chat_id=CHANNEL_USERNAME,
                from_chat_id=draft["from_chat_id"],
                message_id=draft["message_id"],
                reply_markup=draft.get("buttons"),
            )
            user_states[user_id] = "IDLE"
            await message.reply_text(
                "Publicación enviada al canal.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        if text == "⏰ Programar":
            user_states[user_id] = "WAITING_SCHEDULE"
            await message.reply_text(
                "Envía la fecha y hora para programar.\n"
                "Formatos aceptados:\n"
                "2025-12-03 14:30\n"
                "03/12 14:30"
            )
            return

        if text == "💾 Guardar botones como plantilla":
            if not draft.get("buttons"):
                await message.reply_text("No hay botones para guardar.")
                return
            user_states[user_id] = "WAITING_TEMPLATE_NAME"
            await message.reply_text(
                "Escribe un nombre para esta plantilla de botones."
            )
            return

        if text == "❌ Cancelar":
            drafts.pop(user_id, None)
            user_states[user_id] = "IDLE"
            await message.reply_text(
                "Acción cancelada.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        await message.reply_text(
            "Elige una opción con los botones.",
        )
        return

    # -------------------------
    # GUARDAR PLANTILLA DE BOTONES
    # -------------------------
    if state == "WAITING_TEMPLATE_NAME":
        draft = drafts.get(user_id)

        if not draft or not draft.get("buttons"):
            user_states[user_id] = "IDLE"
            await message.reply_text(
                "No hay botones para guardar.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        name = text.strip()
        if not name:
            await message.reply_text("El nombre no puede estar vacío.")
            return

        keyboard = draft["buttons"].inline_keyboard
        data = []
        for row in keyboard:
            for btn in row:
                data.append((btn.text, btn.url))

        button_templates[name] = data

        user_states[user_id] = "IDLE"
        await message.reply_text(
            'Plantilla guardada como "{}".'.format(name),
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # -------------------------
    # PROGRAMAR PUBLICACIÓN
    # -------------------------
    if state == "WAITING_SCHEDULE":
        draft = drafts.get(user_id)
        if not draft:
            user_states[user_id] = "IDLE"
            await message.reply_text(
                "No hay borrador actual.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        text_clean = text.strip()
        ahora = datetime.now()
        dt = None

        # Intento 1 — YYYY-MM-DD HH:MM
        try:
            dt = datetime.strptime(text_clean, "%Y-%m-%d %H:%M")
        except Exception:
            dt = None

        # Intento 2 — DD/MM HH:MM
        if dt is None:
            try:
                fecha_part, hora_part = text_clean.split(" ")
                d_str, m_str = fecha_part.split("/")
                h_str, mi_str = hora_part.split(":")
                d = int(d_str)
                m = int(m_str)
                h = int(h_str)
                mi = int(mi_str)
                dt = datetime(ahora.year, m, d, h, mi)
            except Exception:
                dt = None

        if dt is None:
            await message.reply_text(
                "Formato inválido.\nUsa alguno de estos formatos:\n"
                "2025-12-03 14:30\n"
                "03/12 14:30"
            )
            return

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
            data=job_data,
        )

        user_states[user_id] = "IDLE"
        await message.reply_text(
            "Publicación programada para {} a las {}.".format(
                dt.strftime("%d/%m"),
                dt.strftime("%H:%M"),
            ),
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # -------------------------
    # MENÚ DE BOTONES GUARDADOS
    # -------------------------
    if state == "BUTTONS_MENU":
        if text == "➕ Añadir botón":
            user_states[user_id] = "BUTTON_ADD"
            await message.reply_text(
                "Envía el botón en formato:\nTexto - https://enlace.com\n"
                "Se guardará en la plantilla DEFAULT."
            )
            return

        if text == "📋 Ver plantillas":
            if not button_templates:
                await message.reply_text("No hay plantillas guardadas.")
                return
            lines = []
            for name, data in button_templates.items():
                lines.append("- {} ({} botones)".format(name, len(data)))
            await message.reply_text(
                "Plantillas guardadas:\n" + "\n".join(lines)
            )
            return

        if text == "⬅ Volver al menú":
            user_states[user_id] = "IDLE"
            await message.reply_text(
                "Volviendo al menú principal.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        await message.reply_text(
            "Elige una opción del menú de botones.",
            reply_markup=get_buttons_menu_keyboard(),
        )
        return

    # -------------------------
    # AÑADIR BOTÓN A PLANTILLA DEFAULT
    # -------------------------
    if state == "BUTTON_ADD":
        if "-" not in text:
            await message.reply_text(
                "Formato inválido.\nUsa: Texto - https://enlace.com"
            )
            return

        label, url = text.split("-", 1)
        label = label.strip()
        url = url.strip()

        if not label or not url:
            await message.reply_text(
                "Texto o enlace vacío. Intenta de nuevo."
            )
            return

        data = button_templates.get("DEFAULT", [])
        data.append((label, url))
        button_templates["DEFAULT"] = data

        user_states[user_id] = "BUTTONS_MENU"
        await message.reply_text(
            "Botón añadido a la plantilla DEFAULT.",
            reply_markup=get_buttons_menu_keyboard(),
        )
        return

    # -------------------------
    # SI CAE EN UN ESTADO DESCONOCIDO
    # -------------------------
    user_states[user_id] = "IDLE"
    await message.reply_text(
        "Estado no reconocido. Volviendo al menú.",
        reply_markup=get_main_menu_keyboard(),
    )


# =====================================================
# ENVÍO PROGRAMADO (JOBQUEUE)
# =====================================================

async def send_scheduled_post(context: ContextTypes.DEFAULT_TYPE) -> None:
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

def main() -> None:
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
