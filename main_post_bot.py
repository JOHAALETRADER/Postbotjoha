import os
import json
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

# En Railway debes tener:
# POST_BOT_TOKEN = <token_de_este_bot>
TOKEN = os.environ.get("POST_BOT_TOKEN")

# Canal donde se publicará
CHANNEL_USERNAME = "@JohaaleTrader_es"  # canal público

# Solo tú puedes usar este panel
ADMIN_ID = 5958164558  # tu ID

# Archivo donde se guardan los botones por defecto
DEFAULT_BUTTONS_FILE = "default_buttons.json"

# Estados de usuario y borradores en memoria
user_states: dict[int, str] = {}
drafts: dict[int, dict] = {}
last_post_message_id: int | None = None
edit_button_index: dict[int, int] = {}

# Lista de botones guardados
default_buttons: list[dict] = []


# ======================================================
#            CARGA / GUARDADO DE BOTONES
# ======================================================

def load_default_buttons():
    """Carga los botones por defecto desde disco."""
    global default_buttons
    try:
        with open(DEFAULT_BUTTONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                default_buttons = [b for b in data if "label" in b and "url" in b]
            else:
                default_buttons = []
    except FileNotFoundError:
        default_buttons = []
    except Exception:
        default_buttons = []


def save_default_buttons():
    """Guarda los botones por defecto en disco."""
    try:
        with open(DEFAULT_BUTTONS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_buttons, f, ensure_ascii=False, indent=2)
    except Exception:
        # Si falla no queremos tumbar el bot
        pass


def parse_buttons_from_text(text: str):
    """
    Convierte texto a botones.
    Formato esperado por línea:
    Texto del botón - https://enlace
    """
    buttons = []
    for line in text.splitlines():
        line = line.strip()
        if not line or "-" not in line:
            continue
        label, url = line.split("-", 1)
        label = label.strip()
        url = url.strip()
        if label and url:
            buttons.append({"label": label, "url": url})
    return buttons


def buttons_list_to_markup(button_list):
    """Convierte lista [{'label','url'}] a InlineKeyboardMarkup."""
    rows = []
    for b in button_list:
        rows.append([InlineKeyboardButton(b["label"], url=b["url"])])
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


# ======================================================
#               MENÚ PRINCIPAL
# ======================================================

def get_main_menu_keyboard():
    keyboard = [
        ["📝 Crear publicación"],
        ["✏️ Editar publicación"],
        ["🧷 Editar botones guardados"],
        ["⏰ Programar publicación"],
        ["❌ Cancelar"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ======================================================
#                        START
# ======================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        if update.message:
            await update.message.reply_text("Este bot es solo para el administrador.")
        return

    load_default_buttons()
    user_states[user_id] = "IDLE"
    drafts[user_id] = {}

    if update.message:
        await update.message.reply_text(
            "Panel listo. Selecciona una opción:",
            reply_markup=get_main_menu_keyboard(),
        )


# ======================================================
#       MENÚ EDICIÓN DE PUBLICACIONES (OPCIÓN B)
# ======================================================

async def show_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Editar borrador", callback_data="edit_draft")],
        [InlineKeyboardButton("📝 Editar publicación enviada", callback_data="edit_last")],
        [InlineKeyboardButton("♻️ Rehacer desde cero", callback_data="edit_reset")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")],
    ])
    if update.message:
        await update.message.reply_text("¿Qué deseas hacer?", reply_markup=keyboard)
    user_states[update.effective_user.id] = "EDIT_MENU"


# ======================================================
#        MENÚ BOTONES GUARDADOS (AVANZADO)
# ======================================================

async def show_buttons_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Ver botones actuales", callback_data="btn_view")],
        [InlineKeyboardButton("✏️ Reemplazar todos", callback_data="btn_replace")],
        [InlineKeyboardButton("➕ Agregar nuevos", callback_data="btn_add")],
        [InlineKeyboardButton("✏️ / 🗑️ Editar o eliminar uno", callback_data="btn_editone_menu")],
        [InlineKeyboardButton("🗑️ Eliminar todos", callback_data="btn_clear")],
        [InlineKeyboardButton("🔙 Volver", callback_data="btn_back")],
    ])
    if update.message:
        await update.message.reply_text("Menú de botones guardados:", reply_markup=keyboard)
    user_states[update.effective_user.id] = "EDIT_BUTTONS_MENU"


# ======================================================
#               MANEJO DE MENSAJES
# ======================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = update.effective_user.id
    message = update.message
    text = message.text or ""
    state = user_states.get(user_id, "IDLE")

    # Solo tú usas el panel
    if user_id != ADMIN_ID:
        return

    # CANCELAR GLOBAL (botón de menú)
    if text.strip().startswith("❌"):
        user_states[user_id] = "IDLE"
        drafts[user_id] = {}
        await message.reply_text("❌ Proceso cancelado.", reply_markup=get_main_menu_keyboard())
        return

    # ========================
    # MENÚ PRINCIPAL
    # ========================

    if state == "IDLE":

        if text == "📝 Crear publicación":
            drafts[user_id] = {}
            user_states[user_id] = "WAITING_CONTENT"
            await message.reply_text("Envíame el contenido (texto, foto, video o audio).")
            return

        if text == "✏️ Editar publicación":
            await show_edit_menu(update, context)
            return

        if text == "🧷 Editar botones guardados":
            await show_buttons_menu(update, context)
            return

        if text == "⏰ Programar publicación":
            drafts[user_id] = {"schedule": True}
            user_states[user_id] = "WAITING_CONTENT_SCHEDULE"
            await message.reply_text("Envíame el contenido que quieres programar.")
            return

    # ==================================================
    #   CONTENIDO NUEVO (BORRADOR)
    # ==================================================

    if state in ["WAITING_CONTENT", "WAITING_CONTENT_SCHEDULE", "EDITING_DRAFT"]:
        draft: dict = {}

        if message.photo:
            draft["type"] = "photo"
            draft["file_id"] = message.photo[-1].file_id
            draft["caption"] = message.caption or ""
        elif message.video:
            draft["type"] = "video"
            draft["file_id"] = message.video.file_id
            draft["caption"] = message.caption or ""
        elif message.audio:
            draft["type"] = "audio"
            draft["file_id"] = message.audio.file_id
        elif message.text:
            draft["type"] = "text"
            draft["text"] = message.text
        else:
            await message.reply_text("Formato no soportado.")
            return

        # Si venía de opción programar, mantenemos la marca
        if drafts.get(user_id, {}).get("schedule"):
            draft["schedule"] = True

        drafts[user_id] = draft

        # Ya hay botones guardados → te preguntamos qué quieres hacer
        if default_buttons:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Usar botones guardados", callback_data="use_saved_buttons")],
                [InlineKeyboardButton("🆕 Usar nuevos enlaces", callback_data="use_new_buttons")],
                [InlineKeyboardButton("🚫 Sin botones", callback_data="use_no_buttons")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")],
            ])
            await message.reply_text("¿Cómo quieres manejar los botones?", reply_markup=keyboard)
            user_states[user_id] = "CHOOSE_BUTTON_SOURCE"
        else:
            # No hay botones guardados → te pido enlaces
            user_states[user_id] = "WAITING_BUTTONS"
            await message.reply_text(
                "Agrega los enlaces (uno por línea).\n"
                "Formato: Texto - https://enlace"
            )
        return

    # ==================================================
    #   EDITAR BOTÓN INDIVIDUAL
    # ==================================================

    if state == "EDIT_BUTTONS_CHOOSE_ONE":
        try:
            idx = int(text.strip()) - 1
        except ValueError:
            await message.reply_text("Envía solo el número del botón que quieres editar o eliminar.")
            return

        if idx < 0 or idx >= len(default_buttons):
            await message.reply_text("Número fuera de rango.")
            return

        edit_button_index[user_id] = idx
        user_states[user_id] = "EDIT_BUTTONS_CHOOSE_ACTION"
        btn = default_buttons[idx]
        await message.reply_text(
            f"Botón {idx+1}:\n{btn['label']} - {btn['url']}\n\n"
            "Escribe 'editar' para cambiarlo o 'eliminar' para borrarlo."
        )
        return

    if state == "EDIT_BUTTONS_CHOOSE_ACTION":
        idx = edit_button_index.get(user_id)
        if idx is None or idx < 0 or idx >= len(default_buttons):
            await message.reply_text("No tengo un botón seleccionado.")
            user_states[user_id] = "IDLE"
            return

        lower = text.strip().lower()
        if lower.startswith("editar"):
            user_states[user_id] = "EDIT_BUTTONS_EDIT_ONE"
            await message.reply_text("Envíame el nuevo botón en formato:\nTexto - https://enlace")
            return
        elif lower.startswith("eliminar"):
            removed = default_buttons.pop(idx)
            save_default_buttons()
            user_states[user_id] = "IDLE"
            await message.reply_text(
                f"🗑️ Botón eliminado:\n{removed['label']} - {removed['url']}",
                reply_markup=get_main_menu_keyboard(),
            )
            return
        else:
            await message.reply_text("Responde solo 'editar' o 'eliminar'.")
            return

    if state == "EDIT_BUTTONS_EDIT_ONE":
        idx = edit_button_index.get(user_id)
        if idx is None or idx < 0 or idx >= len(default_buttons):
            await message.reply_text("No tengo un botón seleccionado.")
            user_states[user_id] = "IDLE"
            return

        new_button = parse_buttons_from_text(text)
        if not new_button:
            await message.reply_text("Formato inválido. Usa: Texto - https://enlace")
            return

        default_buttons[idx] = new_button[0]
        save_default_buttons()
        user_states[user_id] = "IDLE"
        await message.reply_text("✅ Botón actualizado.", reply_markup=get_main_menu_keyboard())
        return

    # ==================================================
    #   ESPERANDO BOTONES PARA BORRADOR
    # ==================================================

    if state in ["WAITING_BUTTONS", "EDIT_BUTTONS_REPLACE_ALL", "EDIT_BUTTONS_ADD"]:
        btns = parse_buttons_from_text(text)
        if not btns:
            await message.reply_text(
                "No encontré enlaces válidos.\n"
                "Formato: Texto - https://enlace"
            )
            return

        # Botones para el borrador actual
        if state == "WAITING_BUTTONS":
            drafts[user_id]["buttons_data"] = btns
            drafts[user_id]["buttons"] = buttons_list_to_markup(btns)

            if drafts[user_id]["buttons"]:
                await message.reply_text("Preview de botones:", reply_markup=drafts[user_id]["buttons"])
            else:
                await message.reply_text("Sin botones válidos.")

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("💾 Guardar como predeterminados", callback_data="save_buttons_yes")],
                [InlineKeyboardButton("No guardar", callback_data="save_buttons_no")],
            ])
            await message.reply_text("¿Guardar estos botones como predeterminados?", reply_markup=keyboard)
            user_states[user_id] = "ASK_SAVE_BUTTONS"
            return

        # Edición global de botones guardados
        if state == "EDIT_BUTTONS_REPLACE_ALL":
            default_buttons.clear()
            default_buttons.extend(btns)
            save_default_buttons()
            user_states[user_id] = "IDLE"
            await message.reply_text("✅ Botones reemplazados.", reply_markup=get_main_menu_keyboard())
            return

        if state == "EDIT_BUTTONS_ADD":
            default_buttons.extend(btns)
            save_default_buttons()
            user_states[user_id] = "IDLE"
            await message.reply_text("✅ Botones añadidos.", reply_markup=get_main_menu_keyboard())
            return

    # ==================================================
    #  FECHA/HORA PARA PROGRAMACIÓN
    # ==================================================

    if state == "WAITING_DATETIME":
        text_clean = text.strip()
        try:
            dt = datetime.strptime(text_clean, "%Y-%m-%d %H:%M")
        except ValueError:
            await message.reply_text("Formato inválido. Usa: 2025-12-02 18:30")
            return

        draft = drafts.get(user_id)
        if not draft:
            await message.reply_text("No tengo borrador.")
            user_states[user_id] = "IDLE"
            return

        async def send_later(job_context: ContextTypes.DEFAULT_TYPE):
            """Callback del JobQueue para enviar la publicación programada."""
            global last_post_message_id
            bot = job_context.bot
            ch_name = CHANNEL_USERNAME
            buttons = draft.get("buttons")

            if draft["type"] == "text":
                msg = await bot.send_message(ch_name, draft["text"], reply_markup=buttons)
            elif draft["type"] == "photo":
                msg = await bot.send_photo(
                    ch_name,
                    draft["file_id"],
                    caption=draft["caption"],
                    reply_markup=buttons,
                )
            elif draft["type"] == "video":
                msg = await bot.send_video(
                    ch_name,
                    draft["file_id"],
                    caption=draft["caption"],
                    reply_markup=buttons,
                )
            elif draft["type"] == "audio":
                msg = await bot.send_audio(ch_name, draft["file_id"], reply_markup=buttons)
            else:
                return

            last_post_message_id = msg.message_id

            # Enlace corto con botón "Ver publicación"
            chan_link = CHANNEL_USERNAME.lstrip("@")
            url = f"https://t.me/{chan_link}/{msg.message_id}"
            button = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Ver publicación", url=url)]])
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text="✅ Publicación programada enviada al canal.",
                    reply_markup=button,
                )
            except Exception:
                pass

        delay = (dt - datetime.now()).total_seconds()
        if delay <= 0:
            await message.reply_text("La fecha/hora ya pasó.")
            return

        context.application.job_queue.run_once(send_later, delay)

        user_states[user_id] = "IDLE"
        drafts[user_id] = {}

        await message.reply_text(
            f"⏳ Publicación programada para {dt}.",
            reply_markup=get_main_menu_keyboard(),
        )
        return


# ======================================================
#              CALLBACKS INLINE
# ======================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_post_message_id

    query = update.callback_query
    if not query:
        return

    user_id = query.from_user.id
    data = query.data

    await query.answer()

    if user_id != ADMIN_ID:
        return

    draft = drafts.get(user_id, {})
    state = user_states.get(user_id, "IDLE")

    # CANCELAR DESDE INLINE
    if data == "cancel":
        drafts[user_id] = {}
        user_states[user_id] = "IDLE"
        await query.message.reply_text("❌ Proceso cancelado.", reply_markup=get_main_menu_keyboard())
        return

    # ===================================
    #  MENÚ EDICIÓN PUBLICACIÓN (OPCIÓN B)
    # ===================================

    if state == "EDIT_MENU":
        if data == "edit_draft":
            if not drafts.get(user_id):
                await query.message.reply_text("No hay borrador para editar. Usa 'Crear publicación'.")
                user_states[user_id] = "IDLE"
                return
            user_states[user_id] = "EDITING_DRAFT"
            await query.message.reply_text("Envía el nuevo contenido para el borrador.")
            return

        if data == "edit_last":
            await query.message.reply_text(
                "Por ahora no se edita la publicación ya enviada.\n"
                "Si quieres cambiar algo, crea una nueva publicación desde cero.",
            )
            user_states[user_id] = "IDLE"
            return

        if data == "edit_reset":
            drafts[user_id] = {}
            user_states[user_id] = "WAITING_CONTENT"
            await query.message.reply_text("Vamos a rehacer la publicación. Envíame el contenido.")
            return

    # ===================================
    #  MENÚ BOTONES GUARDADOS
    # ===================================

    if state == "EDIT_BUTTONS_MENU":
        if data == "btn_view":
            if not default_buttons:
                await query.message.reply_text("No hay botones guardados.")
            else:
                lines = []
                for i, b in enumerate(default_buttons, start=1):
                    lines.append(f"{i}. {b['label']} - {b['url']}")
                await query.message.reply_text("Botones guardados:\n" + "\n".join(lines))
            return

        if data == "btn_replace":
            user_states[user_id] = "EDIT_BUTTONS_REPLACE_ALL"
            await query.message.reply_text(
                "Envía todos los botones NUEVOS (uno por línea):\nTexto - https://enlace"
            )
            return

        if data == "btn_add":
            user_states[user_id] = "EDIT_BUTTONS_ADD"
            await query.message.reply_text(
                "Envía los botones a AÑADIR (uno por línea):\nTexto - https://enlace"
            )
            return

        if data == "btn_editone_menu":
            if not default_buttons:
                await query.message.reply_text("No hay botones guardados.")
                return
            lines = []
            for i, b in enumerate(default_buttons, start=1):
                lines.append(f"{i}. {b['label']} - {b['url']}")
            await query.message.reply_text(
                "Botones actuales:\n" + "\n".join(lines) +
                "\n\nEnvía el NÚMERO del botón que quieres editar o eliminar."
            )
            user_states[user_id] = "EDIT_BUTTONS_CHOOSE_ONE"
            return

        if data == "btn_clear":
            default_buttons.clear()
            save_default_buttons()
            await query.message.reply_text("🗑️ Se eliminaron todos los botones guardados.")
            user_states[user_id] = "IDLE"
            return

        if data == "btn_back":
            user_states[user_id] = "IDLE"
            await query.message.reply_text(
                "Volviendo al menú principal.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

    # ===================================
    #  ELECCIÓN FUENTE DE BOTONES
    # ===================================

    if state == "CHOOSE_BUTTON_SOURCE":
        if data == "use_saved_buttons":
            if not default_buttons:
                await query.message.reply_text("No hay botones guardados.")
                user_states[user_id] = "WAITING_BUTTONS"
                await query.message.reply_text("Agrega los enlaces (uno por línea).")
                return

            drafts[user_id]["buttons_data"] = list(default_buttons)
            drafts[user_id]["buttons"] = buttons_list_to_markup(default_buttons)

            if drafts[user_id]["buttons"]:
                await query.message.reply_text("Preview de botones:", reply_markup=drafts[user_id]["buttons"])

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Publicar ahora", callback_data="publish_now")],
                [InlineKeyboardButton("⏳ Programar", callback_data="schedule")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")],
            ])
            await query.message.reply_text("Elige una opción:", reply_markup=keyboard)
            user_states[user_id] = "CONFIRM"
            return

        if data == "use_new_buttons":
            user_states[user_id] = "WAITING_BUTTONS"
            await query.message.reply_text(
                "Agrega los enlaces (uno por línea).\n"
                "Formato: Texto - https://enlace"
            )
            return

        if data == "use_no_buttons":
            drafts[user_id]["buttons"] = None
            drafts[user_id]["buttons_data"] = []
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Publicar ahora", callback_data="publish_now")],
                [InlineKeyboardButton("⏳ Programar", callback_data="schedule")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")],
            ])
            await query.message.reply_text("Elige una opción:", reply_markup=keyboard)
            user_states[user_id] = "CONFIRM"
            return

    # ===================================
    #  GUARDAR BOTONES NUEVOS COMO PREDETERMINADOS
    # ===================================

    if state == "ASK_SAVE_BUTTONS":
        if data == "save_buttons_yes":
            default_buttons.clear()
            default_buttons.extend(drafts[user_id].get("buttons_data", []))
            save_default_buttons()
            await query.message.reply_text("✔ Botones guardados.")
        elif data == "save_buttons_no":
            await query.message.reply_text("No se guardaron los botones.")

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Publicar ahora", callback_data="publish_now")],
            [InlineKeyboardButton("⏳ Programar", callback_data="schedule")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")],
        ])
        await query.message.reply_text("Elige una opción:", reply_markup=keyboard)
        user_states[user_id] = "CONFIRM"
        return

    # ===================================
    #         PUBLICAR AHORA
    # ===================================

    if data == "publish_now" and state == "CONFIRM":
        if not draft:
            await query.message.reply_text("No tengo borrador.")
            return

        buttons = draft.get("buttons")
        ch_name = CHANNEL_USERNAME

        if draft["type"] == "text":
            msg = await context.bot.send_message(ch_name, draft["text"], reply_markup=buttons)
        elif draft["type"] == "photo":
            msg = await context.bot.send_photo(
                ch_name,
                draft["file_id"],
                caption=draft["caption"],
                reply_markup=buttons,
            )
        elif draft["type"] == "video":
            msg = await context.bot.send_video(
                ch_name,
                draft["file_id"],
                caption=draft["caption"],
                reply_markup=buttons,
            )
        elif draft["type"] == "audio":
            msg = await context.bot.send_audio(ch_name, draft["file_id"], reply_markup=buttons)
        else:
            await query.message.reply_text("Tipo de contenido no soportado.")
            return

        last_post_message_id = msg.message_id

        # Botón "Ver publicación" sin mostrar la URL larga en el mensaje
        chan_link = CHANNEL_USERNAME.lstrip("@")
        url = f"https://t.me/{chan_link}/{msg.message_id}"
        view_button = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Ver publicación", url=url)]])

        drafts[user_id] = {}
        user_states[user_id] = "IDLE"

        await query.message.reply_text(
            "✅ Publicación enviada al canal.",
            reply_markup=view_button,
        )
        await query.message.reply_text(
            "Volviendo al menú principal.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # ===================================
    #         PROGRAMAR DESDE CONFIRM
    # ===================================

    if data == "schedule" and state == "CONFIRM":
        user_states[user_id] = "WAITING_DATETIME"
        await query.message.reply_text("Envía la fecha y hora (formato 2025-12-02 18:30).")
        return


# ======================================================
#                       MAIN
# ======================================================

def main():
    if not TOKEN:
        raise RuntimeError("POST_BOT_TOKEN no está definido en las variables de entorno.")

    application = ApplicationBuilder().token(TOKEN).build()

    load_default_buttons()

    text_or_media = (
        (filters.TEXT & ~filters.COMMAND)
        | filters.PHOTO
        | filters.VIDEO
        | filters.AUDIO
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(text_or_media, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))

    application.run_polling()


if __name__ == "__main__":
    main()
