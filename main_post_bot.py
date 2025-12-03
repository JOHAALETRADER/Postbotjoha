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

TOKEN = os.environ.get("POST_BOT_TOKEN")
CHANNEL_USERNAME = "@JohaaleTrader_es"  # canal público
ADMIN_ID = 5958164558  # tu ID

DEFAULT_BUTTONS_FILE = "default_buttons.json"

user_states: dict[int, str] = {}
drafts: dict[int, dict] = {}
last_post_message_id: int | None = None
edit_button_index: dict[int, int] = {}

default_buttons: list[dict] = []


# ======================================================
#            CARGA / GUARDADO DE BOTONES
# ======================================================

def load_default_buttons():
    global default_buttons
    try:
        with open(DEFAULT_BUTTONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                default_buttons = [b for b in data if "label" in b and "url" in b]
    except:
        default_buttons = []


def save_default_buttons():
    try:
        with open(DEFAULT_BUTTONS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_buttons, f, ensure_ascii=False, indent=2)
    except:
        pass


def parse_buttons_from_text(text: str):
    buttons = []
    for line in text.splitlines():
        if "-" not in line:
            continue
        label, url = line.split("-", 1)
        label = label.strip()
        url = url.strip()
        if label and url:
            buttons.append({"label": label, "url": url})
    return buttons


def buttons_list_to_markup(button_list):
    rows = []
    for b in button_list:
        rows.append([InlineKeyboardButton(b["label"], url=b["url"])])
    if not rows:
        rows = [[InlineKeyboardButton("Sin enlaces", callback_data="noop")]]
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
        await update.message.reply_text("Este bot es solo para el administrador.")
        return

    user_states[user_id] = "IDLE"
    drafts[user_id] = {}

    await update.message.reply_text(
        "Panel listo. Selecciona una opción:",
        reply_markup=get_main_menu_keyboard(),
    )


# ======================================================
#       MENÚ EDICIÓN DE PUBLICACIONES (OPCION B)
# ======================================================

async def show_edit_menu(update, context):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Editar borrador", callback_data="edit_draft")],
        [InlineKeyboardButton("📝 Editar publicación enviada", callback_data="edit_last")],
        [InlineKeyboardButton("♻️ Rehacer desde cero", callback_data="edit_reset")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
    ])
    await update.message.reply_text("¿Qué deseas hacer?", reply_markup=keyboard)
    user_states[update.effective_user.id] = "EDIT_MENU"


# ======================================================
#        MENÚ BOTONES GUARDADOS (AVANZADO)
# ======================================================

async def show_buttons_menu(update, context):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Ver botones actuales", callback_data="btn_view")],
        [InlineKeyboardButton("✏️ Reemplazar todos", callback_data="btn_replace")],
        [InlineKeyboardButton("➕ Agregar nuevos", callback_data="btn_add")],
        [InlineKeyboardButton("✏️ / 🗑️ Editar o eliminar uno", callback_data="btn_editone_menu")],
        [InlineKeyboardButton("🗑️ Eliminar todos", callback_data="btn_clear")],
        [InlineKeyboardButton("🔙 Volver", callback_data="btn_back")],
    ])
    await update.message.reply_text("Menú de botones guardados:", reply_markup=keyboard)
    user_states[update.effective_user.id] = "EDIT_BUTTONS_MENU"


# ======================================================
#               MANEJO DE MENSAJES
# ======================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = update.message
    text = message.text or ""
    state = user_states.get(user_id, "IDLE")

    if user_id != ADMIN_ID:
        return

    # CANCELAR GRANDE
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
    #   CONTENIDO NUEVO
    # ==================================================

    if state in ["WAITING_CONTENT", "WAITING_CONTENT_SCHEDULE", "EDITING_DRAFT"]:
        draft = {}

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

        if drafts.get(user_id, {}).get("schedule"):
            draft["schedule"] = True

        drafts[user_id] = draft

        if default_buttons:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Usar botones guardados", callback_data="use_saved_buttons")],
                [InlineKeyboardButton("🆕 Usar nuevos enlaces", callback_data="use_new_buttons")],
                [InlineKeyboardButton("🚫 Sin botones", callback_data="use_no_buttons")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
            ])
            await message.reply_text("¿Cómo quieres manejar los botones?", reply_markup=keyboard)
            user_states[user_id] = "CHOOSE_BUTTON_SOURCE"
        else:
            user_states[user_id] = "WAITING_BUTTONS"
            await message.reply_text("Agrega los enlaces (uno por línea).")
        return

    # ==================================================
    #   EDITAR BOTÓN INDIVIDUAL
    # ==================================================

    if state == "EDIT_BUTTONS_EDIT_ONE":
        idx = edit_button_index.get(user_id)
        if idx is None or idx < 0 or idx >= len(default_buttons):
            await message.reply_text("No tengo un botón seleccionado.")
            user_states[user_id] = "IDLE"
            return

        new_button = parse_buttons_from_text(text)
        if not new_button:
            await message.reply_text("Formato inválido.\nUsa: Texto - https://enlace")
            return

        default_buttons[idx] = new_button[0]
        save_default_buttons()
        user_states[user_id] = "IDLE"

        await message.reply_text("✅ Botón actualizado.", reply_markup=get_main_menu_keyboard())
        return

    # ==================================================
    #   ESPERANDO BOTONES PARA BORRADOR
    # ==================================================

    if state == "WAITING_BUTTONS":
        btns = parse_buttons_from_text(text)
        if not btns:
            await message.reply_text("No encontré enlaces válidos.")
            return

        drafts[user_id]["buttons_data"] = btns
        drafts[user_id]["buttons"] = buttons_list_to_markup(btns)

        await message.reply_text("Preview:", reply_markup=drafts[user_id]["buttons"])

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💾 Guardar como predeterminados", callback_data="save_buttons_yes")],
            [InlineKeyboardButton("No guardar", callback_data="save_buttons_no")]
        ])
        await message.reply_text("¿Guardar estos botones como predeterminados?", reply_markup=keyboard)
        user_states[user_id] = "ASK_SAVE_BUTTONS"
        return

    # ==================================================
    #  FECHA/HORA PARA PROGRAMACIÓN
    # ==================================================

    if state == "WAITING_DATETIME":
        try:
            dt = datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
        except:
            await message.reply_text("Formato inválido. Usa: 2025-12-02 18:30")
            return

        draft = drafts.get(user_id)
        if not draft:
            await message.reply_text("No tengo borrador.")
            user_states[user_id] = "IDLE"
            return

        async def send_later(context):
            global last_post_message_id
            if draft["type"] == "text":
                msg = await context.bot.send_message(
                    CHANNEL_USERNAME, draft["text"], reply_markup=draft.get("buttons")
                )
            elif draft["type"] == "photo":
                msg = await context.bot.send_photo(
                    CHANNEL_USERNAME, draft["file_id"], caption=draft["caption"],
                    reply_markup=draft.get("buttons")
                )
            elif draft["type"] == "video":
                msg = await context.bot.send_video(
                    CHANNEL_USERNAME, draft["file_id"], caption=draft["caption"],
                    reply_markup=draft.get("buttons")
                )
            elif draft["type"] == "audio":
                msg = await context.bot.send_audio(
                    CHANNEL_USERNAME, draft["file_id"], reply_markup=draft.get("buttons")
                )
            last_post_message_id = msg.message_id

        delay = (dt - datetime.now()).total_seconds()
        if delay < 0:
            await message.reply_text("La fecha/hora ya pasó.")
            return

        context.job_queue.run_once(send_later, delay)

        user_states[user_id] = "IDLE"
        drafts[user_id] = {}

        await message.reply_text(
            f"⏳ Publicación programada para {dt}.",
            reply_markup=get_main_menu_keyboard()
        )
        return


# ======================================================
#              CALLBACKS INLINE
# ======================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_post_message_id

    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    await query.answer()

    if user_id != ADMIN_ID:
        return

    draft = drafts.get(user_id, {})
    state = user_states.get(user_id, "IDLE")

    # CANCELAR
    if data == "cancel":
        drafts[user_id] = {}
        user_states[user_id] = "IDLE"
        await query.message.reply_text(
            "❌ Proceso cancelado.",
            reply_markup=get_main_menu_keyboard()
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
                await query.message.reply_text("Agrega los enlaces.")
                return

            drafts[user_id]["buttons_data"] = list(default_buttons)
            drafts[user_id]["buttons"] = buttons_list_to_markup(default_buttons)

            await query.message.reply_text(
                "Preview de botones:",
                reply_markup=drafts[user_id]["buttons"]
            )

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Publicar ahora", callback_data="publish_now")],
                [InlineKeyboardButton("⏳ Programar", callback_data="schedule")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
            ])
            await query.message.reply_text("Elige una opción:", reply_markup=keyboard)
            user_states[user_id] = "CONFIRM"
            return

        if data == "use_new_buttons":
            user_states[user_id] = "WAITING_BUTTONS"
            await query.message.reply_text("Agrega los enlaces (uno por línea).")
            return

        if data == "use_no_buttons":
            drafts[user_id]["buttons"] = None
            drafts[user_id]["buttons_data"] = []
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 Publicar ahora", callback_data="publish_now")],
                [InlineKeyboardButton("⏳ Programar", callback_data="schedule")],
                [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
            ])
            await query.message.reply_text("Elige una opción:", reply_markup=keyboard)
            user_states[user_id] = "CONFIRM"
            return

    # ===================================
    #  GUARDAR BOTONES NUEVOS
    # ===================================

    if state == "ASK_SAVE_BUTTONS":
        if data == "save_buttons_yes":
            default_buttons.clear()
            default_buttons.extend(drafts[user_id]["buttons_data"])
            save_default_buttons()
            await query.message.reply_text("✔ Botones guardados.")
        elif data == "save_buttons_no":
            await query.message.reply_text("No se guardaron los botones.")

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Publicar ahora", callback_data="publish_now")],
            [InlineKeyboardButton("⏳ Programar", callback_data="schedule")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ])
        await query.message.reply_text("Elige una opción:", reply_markup=keyboard)
        user_states[user_id] = "CONFIRM"
        return

    # ===================================
    #         PUBLICAR AHORA
    # ===================================

    if data == "publish_now":
        if not draft:
            await query.message.reply_text("No tengo borrador.")
            return

        if draft["type"] == "text":
            msg = await context.bot.send_message(
                CHANNEL_USERNAME, draft["text"], reply_markup=draft.get("buttons")
            )
        elif draft["type"] == "photo":
            msg = await context.bot.send_photo(
                CHANNEL_USERNAME, draft["file_id"], caption=draft.get("caption"),
                reply_markup=draft.get("buttons")
            )
        elif draft["type"] == "video":
            msg = await context.bot.send_video(
                CHANNEL_USERNAME, draft["file_id"], caption=draft.get("caption"),
                reply_markup=draft.get("buttons")
            )
        elif draft["type"] == "audio":
            msg = await context.bot.send_audio(
                CHANNEL_USERNAME, draft["file_id"],
                reply_markup=draft.get("buttons")
            )
        else:
            await query.message.reply_text("Tipo no soportado.")
            return

        last_post_message_id = msg.message_id
