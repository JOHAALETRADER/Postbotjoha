import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# Configuración general
TOKEN = os.environ.get("POST_BOT_TOKEN")
CHANNEL_USERNAME = "@JohaaleTrader_es"
ADMIN_ID = 5958164558

# Estados y borradores
user_states = {}
drafts = {}
button_templates = {}

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("Acceso restringido.")
        return

    user_states[user.id] = "IDLE"
    await update.message.reply_text(
        "¡Bot listo! Elige una opción del menú.",
        reply_markup=get_main_menu_keyboard(),
    )
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user
    user_id = user.id

    if user_id != ADMIN_ID:
        await message.reply_text("Acceso restringido.")
        return

    text = message.text or ""
    state = user_states.get(user_id, "IDLE")

    if text == "/start":
        user_states[user_id] = "IDLE"
        await message.reply_text(
            "¡Bot listo! Elige una opción del menú.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    if state == "IDLE":
        if text == "📝 Crear publicación":
            user_states[user_id] = "WAITING_CONTENT"
            drafts[user_id] = {}
            await message.reply_text("Añade el contenido de la publicación (texto o multimedia).")
            return

        if text == "✏️ Editar publicación":
            user_states[user_id] = "WAITING_EDIT_MESSAGE"
            await message.reply_text("Reenvía desde el canal la publicación que deseas editar.")
            return

        if text == "🔗 Botones guardados":
            user_states[user_id] = "BUTTONS_MENU"
            await message.reply_text(
                "Menú de botones guardados.",
                reply_markup=get_buttons_menu_keyboard(),
            )
            return

        if text == "⏰ Programar publicación":
            draft = drafts.get(user_id)
            if not draft:
                await message.reply_text("Primero crea una publicación.")
                return
            user_states[user_id] = "WAITING_SCHEDULE"
            await message.reply_text("Envía la fecha y hora (formato: 2025-12-03 14:30 o 03/12 14:30).")
            return

        if text == "❌ Cancelar":
            drafts.pop(user_id, None)
            user_states[user_id] = "IDLE"
            await message.reply_text("Acción cancelada.", reply_markup=get_main_menu_keyboard())
            return
        if state == "WAITING_CONTENT":
            drafts[user_id] = {
                "from_chat_id": message.chat_id,
                "message_id": message.message_id,
                "buttons": None,
            }
            user_states[user_id] = "WAITING_BUTTONS"
            await message.reply_text("Añade enlaces y botones (formato: Texto - https://enlace.com).")
            return

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

            await context.bot.copy_message(
                chat_id=message.chat_id,
                from_chat_id=drafts[user_id]["from_chat_id"],
                message_id=drafts[user_id]["message_id"],
                reply_markup=markup
            )

            keyboard = [
                ["📤 Publicar ahora"],
                ["⏰ Programar"],
                ["💾 Guardar botones como plantilla"],
                ["❌ Cancelar"],
            ]

            user_states[user_id] = "CONFIRM_ACTION"
            await message.reply_text(
                "Vista previa lista. Elige una opción:",
                reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            )
            return

# Aquí puedes continuar con las lógicas para la confirmación, programación y demás acciones finales.

# Finalmente, la inicialización de la aplicación
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.ALL, handle_message))

if __name__ == "__main__":
    app.run_polling()
