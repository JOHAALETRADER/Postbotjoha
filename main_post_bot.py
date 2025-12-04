import os
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ========================= CONFIGURACIÓN BÁSICA =========================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = os.getenv("ADMIN_ID", "")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID", "")

if not BOT_TOKEN:
    raise RuntimeError("Falta la variable de entorno BOT_TOKEN")

if not ADMIN_ID:
    raise RuntimeError("Falta la variable de entorno ADMIN_ID")

# ============================== LOGGING ================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ======================== CLAVES USER_DATA =============================

DRAFT_KEY = "draft"
STATE_KEY = "state"
DEFAULT_BUTTONS_KEY = "default_buttons"
SCHEDULE_JOB_KEY = "schedule_job"
TEMPLATE_TEXT_KEY = "template_text"

# ============================= ESTADOS ================================

STATE_MAIN_MENU = "MAIN_MENU"
STATE_WAITING_PUBLICATION = "WAITING_PUBLICATION"
STATE_WAITING_BUTTONS = "WAITING_BUTTONS"
STATE_WAITING_SAVE_DEFAULT = "WAITING_SAVE_DEFAULT"
STATE_BUTTON_MENU = "BUTTON_MENU"
STATE_BUTTON_EDIT_SELECT = "BUTTON_EDIT_SELECT"
STATE_BUTTON_EDIT_TEXT = "BUTTON_EDIT_TEXT"
STATE_BUTTON_EDIT_URL = "BUTTON_EDIT_URL"
STATE_BUTTON_DELETE_SELECT = "BUTTON_DELETE_SELECT"
STATE_WAITING_SCHEDULE = "WAITING_SCHEDULE"

# ==================== BORRADOR ==========================

def get_draft(user_data: Dict[str, Any]) -> Dict[str, Any]:
    draft = user_data.get(DRAFT_KEY)
    if draft is None:
        draft = {
            "type": None,      # photo, video, audio, voice, text
            "file_id": None,   # file_id correspondiente
            "text": None,
            "buttons": [],
            "scheduled_at": None,
        }
        user_data[DRAFT_KEY] = draft
    return draft


def get_default_buttons(user_data: Dict[str, Any]) -> List[Dict[str, str]]:
    buttons = user_data.get(DEFAULT_BUTTONS_KEY)
    if buttons is None:
        buttons = []
        user_data[DEFAULT_BUTTONS_KEY] = buttons
    return buttons


def build_buttons_keyboard(buttons: List[Dict[str, str]]) -> Optional[InlineKeyboardMarkup]:
    if not buttons:
        return None
    rows, temp = [], []
    for b in buttons:
        temp.append(InlineKeyboardButton(b["text"], url=b["url"]))
        if len(temp) == 2:
            rows.append(temp)
            temp = []
    if temp:
        rows.append(temp)
    return InlineKeyboardMarkup(rows)
# ============================= MENÚ PRINCIPAL =============================

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    draft = get_draft(user_data)
    default_buttons = get_default_buttons(user_data)
    user_data[STATE_KEY] = STATE_MAIN_MENU

    resumen = draft["text"] if draft["text"] else "(Sin publicación en borrador)"
    botones = len(draft["buttons"])
    tiene_defaults = "Sí" if default_buttons else "No"
    tiene_template = "Sí" if user_data.get(TEMPLATE_TEXT_KEY) else "No"
    schedule = draft["scheduled_at"].strftime("%Y-%m-%d %H:%M") if draft["scheduled_at"] else "Sin programación"

    menu_text = (
        "📌 *POSTBOT – MENÚ PRINCIPAL*\n\n"
        "*Borrador actual:*\n{text}\n\n"
        "*Botones:* {b}\n"
        "*Botones predeterminados:* {d}\n"
        "*Plantilla recurrente:* {t}\n"
        "*Programación:* {p}"
    ).format(text=resumen, b=botones, d=tiene_defaults, t=tiene_template, p=schedule)

    keyboard = [
        [InlineKeyboardButton("📝 Crear publicación", callback_data="CREATE_PUBLICATION")],
        [InlineKeyboardButton("✏️ Editar publicación", callback_data="EDIT_PUBLICATION")],
        [InlineKeyboardButton("🔗 Botones", callback_data="MENU_BUTTONS")],
        [InlineKeyboardButton("🌟 Plantilla recurrente", callback_data="MENU_TEMPLATE")],
        [InlineKeyboardButton("⏰ Programar", callback_data="MENU_SCHEDULE")],
        [InlineKeyboardButton("📤 Enviar ahora", callback_data="MENU_SEND_NOW")],
    ]

    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(menu_text, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.effective_chat.send_message(menu_text, parse_mode="Markdown", reply_markup=markup)


# ================================ /START ==================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_user.id) != str(ADMIN_ID):
        await update.message.reply_text("Este bot es privado.")
        return
    
    get_draft(context.user_data)
    get_default_buttons(context.user_data)
    await send_main_menu(update, context)


# ========================= CALLBACKS DEL MENÚ ============================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if str(query.from_user.id) != str(ADMIN_ID):
        await query.edit_message_text("No tienes permiso para usar este bot.")
        return

    user_data = context.user_data
    draft = get_draft(user_data)
    default_buttons = get_default_buttons(user_data)

    # ------------------------ VOLVER AL MENÚ ------------------------

    if data == "BACK_MAIN":
        await send_main_menu(update, context)
        return

    # ------------------------ CREAR PUBLICACIÓN ---------------------

    if data == "CREATE_PUBLICATION":
        user_data[DRAFT_KEY] = {
            "type": None,
            "file_id": None,
            "text": None,
            "buttons": [],
            "scheduled_at": None,
        }
        user_data[STATE_KEY] = STATE_WAITING_PUBLICATION

        await query.edit_message_text(
            "Crea tu publicación:\n\n"
            "📌 Envía *en un solo mensaje* tu imagen, video, audio, nota de voz o texto.",
            parse_mode="Markdown",
        )
        return

    # ------------------------ EDITAR PUBLICACIÓN --------------------

    if data == "EDIT_PUBLICATION":
        if not draft["text"] and not draft["file_id"]:
            await query.edit_message_text("No hay ninguna publicación para editar.")
            await send_main_menu(update, context)
            return

        keyboard = [
            [InlineKeyboardButton("✏️ Editar texto", callback_data="EDIT_TEXT")],
            [InlineKeyboardButton("🖼️ Cambiar imagen/video/audio", callback_data="EDIT_MEDIA")],
            [InlineKeyboardButton("🔗 Editar botones", callback_data="MENU_BUTTONS")],
            [InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_MAIN")],
        ]

        await query.edit_message_text(
            "¿Qué deseas editar?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "EDIT_TEXT":
        user_data[STATE_KEY] = STATE_WAITING_PUBLICATION
        await query.edit_message_text(
            "Envía nuevamente tu publicación (imagen/video/audio + texto o solo texto).\n"
            "La actualizaré con lo que envíes."
        )
        return

    if data == "EDIT_MEDIA":
        user_data[STATE_KEY] = STATE_WAITING_PUBLICATION
        await query.edit_message_text(
            "Envía la nueva imagen, video o audio.\n"
            "El contenido multimedia anterior será reemplazado."
        )
        return

    # --------------------------- BOTONES -----------------------------

    if data == "MENU_BUTTONS":
        user_data[STATE_KEY] = STATE_BUTTON_MENU

        botones_txt = "Sin botones." if not draft["buttons"] else "\n".join(
            [f"{i+1}. {b['text']} → {b['url']}" for i, b in enumerate(draft["buttons"])]
        )

        keyboard = [
            [InlineKeyboardButton("➕ Añadir botón", callback_data="BTN_ADD")],
            [InlineKeyboardButton("✏️ Editar botón", callback_data="BTN_EDIT")],
            [InlineKeyboardButton("❌ Eliminar botón", callback_data="BTN_DELETE")],
            [InlineKeyboardButton("⭐ Guardar como predeterminados", callback_data="BTN_SAVE_DEFAULT")],
            [InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_MAIN")],
        ]

        await query.edit_message_text(
            "*Botones actuales:*\n{b}".format(b=botones_txt),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data == "BTN_ADD":
        user_data[STATE_KEY] = STATE_WAITING_BUTTONS
        await query.edit_message_text(
            "Envía el botón en formato:\n\nTexto - enlace\n\nEscribe *listo* cuando termines.",
            parse_mode="Markdown",
        )
        return

    if data == "BTN_EDIT":
        if not draft["buttons"]:
            await query.edit_message_text("No hay botones para editar.")
            await send_main_menu(update, context)
            return

        user_data[STATE_KEY] = STATE_BUTTON_EDIT_SELECT
        lista = "\n".join([f"{i+1}. {b['text']} → {b['url']}" for i, b in enumerate(draft["buttons"])])

        await query.edit_message_text(
            "¿Qué botón deseas editar?\n\n{l}".format(l=lista)
        )
        return

    if data == "BTN_DELETE":
        if not draft["buttons"]:
            await query.edit_message_text("No hay botones para eliminar.")
            await send_main_menu(update, context)
            return

        user_data[STATE_KEY] = STATE_BUTTON_DELETE_SELECT
        lista = "\n".join([f"{i+1}. {b['text']} → {b['url']}" for i, b in enumerate(draft["buttons"])])

        await query.edit_message_text(
            "¿Qué botón deseas eliminar?\n\n{l}".format(l=lista)
        )
        return

    if data == "BTN_SAVE_DEFAULT":
        if not draft["buttons"]:
            await query.edit_message_text("No hay botones para guardar.")
            await send_main_menu(update, context)
            return

        user_data[DEFAULT_BUTTONS_KEY] = list(draft["buttons"])
        await query.edit_message_text("Botones guardados como predeterminados.")
        await send_main_menu(update, context)
        return

    # --------------------- PLANTILLA RECURRENTE -----------------------

    if data == "MENU_TEMPLATE":
        tpl = user_data.get(TEMPLATE_TEXT_KEY)
        txt_tpl = tpl if tpl else "(Sin plantilla guardada)"

        keyboard = [
            [InlineKeyboardButton("💾 Guardar borrador como plantilla", callback_data="TPL_SAVE")],
            [InlineKeyboardButton("📥 Insertar plantilla en borrador", callback_data="TPL_INSERT")],
            [InlineKeyboardButton("🗑️ Borrar plantilla", callback_data="TPL_CLEAR")],
            [InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_MAIN")],
        ]

        await query.edit_message_text(
            "*Plantilla actual:*\n{t}".format(t=txt_tpl),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data == "TPL_SAVE":
        if not draft["text"]:
            await query.edit_message_text("No hay texto para guardar como plantilla.")
        else:
            user_data[TEMPLATE_TEXT_KEY] = draft["text"]
            await query.edit_message_text("Plantilla guardada correctamente.")
        await send_main_menu(update, context)
        return

    if data == "TPL_INSERT":
        tpl = user_data.get(TEMPLATE_TEXT_KEY)
        if not tpl:
            await query.edit_message_text("No hay plantilla guardada.")
        else:
            draft["text"] = tpl
            await query.edit_message_text("Plantilla insertada en el borrador.")
        await send_main_menu(update, context)
        return

    if data == "TPL_CLEAR":
        user_data[TEMPLATE_TEXT_KEY] = None
        await query.edit_message_text("Plantilla eliminada.")
        await send_main_menu(update, context)
        return
    # --------------------- PROGRAMAR / ENVIAR -----------------------

    if data == "MENU_SCHEDULE":
        user_data[STATE_KEY] = STATE_WAITING_SCHEDULE
        await query.edit_message_text(
            "Indica fecha y hora para programar la publicación.\n"
            "Formato: AAAA-MM-DD HH:MM\n"
            "Ejemplo: 2025-12-03 21:30"
        )
        return

    if data == "MENU_SEND_NOW":
        await send_post_now(update, context)
        return

    # ---- Acciones desde la vista previa ----

    if data == "PREVIEW_SEND_NOW":
        await send_post_now(update, context)
        return

    if data == "PREVIEW_SCHEDULE":
        user_data[STATE_KEY] = STATE_WAITING_SCHEDULE
        await query.edit_message_text(
            "Indica fecha y hora para programar la publicación.\n"
            "Formato: AAAA-MM-DD HH:MM"
        )
        return

    if data == "PREVIEW_EDIT":
        keyboard = [
            [InlineKeyboardButton("✏️ Editar texto", callback_data="EDIT_TEXT")],
            [InlineKeyboardButton("🖼️ Cambiar imagen/video/audio", callback_data="EDIT_MEDIA")],
            [InlineKeyboardButton("🔗 Editar botones", callback_data="MENU_BUTTONS")],
            [InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_MAIN")],
        ]
        await query.edit_message_text(
            "¿Qué deseas editar?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data == "PREVIEW_CANCEL":
        user_data[DRAFT_KEY] = {
            "type": None,
            "file_id": None,
            "text": None,
            "buttons": [],
            "scheduled_at": None,
        }
        await query.edit_message_text("Borrador cancelado.")
        await send_main_menu(update, context)
        return

    # ---- Uso de botones predeterminados / nuevos ----

    if data == "USE_DEFAULT_BTNS":
        draft["buttons"] = list(default_buttons)
        await query.edit_message_text("Botones predeterminados aplicados al borrador.")
        await send_preview(update, context, "Vista previa con los botones predeterminados:")
        return

    if data == "CREATE_NEW_BTNS":
        user_data[STATE_KEY] = STATE_WAITING_BUTTONS
        await query.edit_message_text(
            "Ahora envía los botones uno por mensaje.\n"
            "Formato: Texto - enlace\n"
            "Escribe *listo* cuando termines.",
            parse_mode="Markdown",
        )
        return

    if data == "SAVE_DEFAULT_YES":
        user_data[DEFAULT_BUTTONS_KEY] = list(draft["buttons"])
        user_data[STATE_KEY] = STATE_MAIN_MENU
        await query.edit_message_text("Botones guardados como predeterminados.")
        await send_preview(update, context)
        return

    if data == "SAVE_DEFAULT_NO":
        user_data[STATE_KEY] = STATE_MAIN_MENU
        await query.edit_message_text("Botones no guardados como predeterminados.")
        await send_preview(update, context)
        return


# ============================ VISTA PREVIA ==============================

async def send_preview(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    intro_text: Optional[str] = None,
) -> None:
    user_data = context.user_data
    draft = get_draft(user_data)
    chat = update.effective_chat

    intro = intro_text if intro_text else "📎 Vista previa de la publicación:"
    await chat.send_message(intro)

    kb = build_buttons_keyboard(draft["buttons"])

    t = draft["type"]
    file_id = draft["file_id"]
    text = draft["text"] or ""

    if t == "photo" and file_id:
        await chat.send_photo(photo=file_id, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "video" and file_id:
        await chat.send_video(video=file_id, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "audio" and file_id:
        await chat.send_audio(audio=file_id, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "voice" and file_id:
        await chat.send_voice(voice=file_id, caption=text, reply_markup=kb, parse_mode="HTML")
    else:
        await chat.send_message(text=text, reply_markup=kb, parse_mode="HTML")

    keyboard = [
        [InlineKeyboardButton("📤 Enviar ahora", callback_data="PREVIEW_SEND_NOW")],
        [InlineKeyboardButton("⏰ Programar", callback_data="PREVIEW_SCHEDULE")],
        [InlineKeyboardButton("✏️ Editar publicación", callback_data="PREVIEW_EDIT")],
        [InlineKeyboardButton("❌ Cancelar borrador", callback_data="PREVIEW_CANCEL")],
        [InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_MAIN")],
    ]
    await chat.send_message(
        "¿Qué deseas hacer con esta publicación?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ====================== PARSEO DE BOTONES ==============================

def parse_button_line(line: str) -> Optional[Dict[str, str]]:
    line = line.strip()
    if not line:
        return None

    separators = [" - ", " – ", " — ", " | "]
    for sep in separators:
        if sep in line:
            text, url = line.split(sep, 1)
            text = text.strip()
            url = url.strip()
            if text and url:
                return {"text": text, "url": url}
    return None


# ========================= MANEJO DE MENSAJES ==========================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if str(user.id) != str(ADMIN_ID):
        return

    user_data = context.user_data
    state = user_data.get(STATE_KEY, STATE_MAIN_MENU)
    draft = get_draft(user_data)
    default_buttons = get_default_buttons(user_data)

    message = update.message
    if not message:
        return

    text = message.text or ""
    text_lower = text.lower().strip() if text else ""

    # -------- ESPERANDO PUBLICACIÓN (IMAGEN / VIDEO / AUDIO / VOICE / TEXTO) --------

    if state == STATE_WAITING_PUBLICATION:
        mtype = "text"
        file_id = None
        contenido_texto = ""

        if message.photo:
            mtype = "photo"
            file_id = message.photo[-1].file_id
            contenido_texto = message.caption or ""
        elif message.video:
            mtype = "video"
            file_id = message.video.file_id
            contenido_texto = message.caption or ""
        elif message.audio:
            mtype = "audio"
            file_id = message.audio.file_id
            contenido_texto = message.caption or ""
        elif message.voice:
            mtype = "voice"
            file_id = message.voice.file_id
            contenido_texto = message.caption or ""
        else:
            mtype = "text"
            file_id = None
            contenido_texto = message.text or ""

        if not contenido_texto and not file_id:
            await message.reply_text(
                "Envía un mensaje con texto o un mensaje con imagen/video/audio/nota de voz."
            )
            return

        draft["type"] = mtype
        draft["file_id"] = file_id
        draft["text"] = contenido_texto
        draft["buttons"] = []

        if default_buttons:
            keyboard = [
                [InlineKeyboardButton("✅ Usar botones predeterminados", callback_data="USE_DEFAULT_BTNS")],
                [InlineKeyboardButton("➕ Crear nuevos botones", callback_data="CREATE_NEW_BTNS")],
            ]
            user_data[STATE_KEY] = STATE_MAIN_MENU
            await message.reply_text(
                "Publicación recibida.\n\n¿Deseas usar tus botones predeterminados o crear nuevos?",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return

        # Sin botones predeterminados: pasar directamente a creación
        user_data[STATE_KEY] = STATE_WAITING_BUTTONS
        await message.reply_text(
            "Publicación recibida.\n\nAhora envía los botones uno por mensaje.\n"
            "Formato: Texto - enlace\n"
            "Escribe *listo* cuando termines.",
            parse_mode="Markdown",
        )
        return

    # ---------------- ESPERANDO BOTONES ----------------

    if state == STATE_WAITING_BUTTONS:
        if text_lower == "listo":
            if not draft["buttons"]:
                await message.reply_text(
                    "No has añadido ningún botón. Añade al menos uno o escribe 'listo' cuando termines."
                )
                return

            if not default_buttons:
                keyboard = [
                    [InlineKeyboardButton("✅ Sí, guardar", callback_data="SAVE_DEFAULT_YES")],
                    [InlineKeyboardButton("❌ No guardar", callback_data="SAVE_DEFAULT_NO")],
                ]
                user_data[STATE_KEY] = STATE_WAITING_SAVE_DEFAULT
                await message.reply_text(
                    "¿Deseas guardar estos botones como predeterminados?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return

            user_data[STATE_KEY] = STATE_MAIN_MENU
            await send_preview(update, context)
            return

        btn = parse_button_line(text)
        if not btn:
            await message.reply_text(
                "Formato inválido.\nEjemplo: Registrarme - https://tuenlace.com"
            )
            return

        draft["buttons"].append(btn)
        await message.reply_text("Botón añadido: {t}".format(t=btn["text"]))
        return

    # ------------- ESPERANDO DECISIÓN GUARDAR BOTONES ---------------

    if state == STATE_WAITING_SAVE_DEFAULT:
        await message.reply_text(
            "Responde usando los botones de la pregunta anterior."
        )
        return

    # ----------------- EDICIÓN DE BOTONES ---------------------------

    if state == STATE_BUTTON_EDIT_SELECT:
        try:
            idx = int(text.strip())
        except ValueError:
            await message.reply_text("Escribe un número válido.")
            return

        if idx < 1 or idx > len(draft["buttons"]):
            await message.reply_text("Número fuera de rango.")
            return

        user_data["edit_index"] = idx - 1
        user_data[STATE_KEY] = STATE_BUTTON_EDIT_TEXT
        await message.reply_text("Escribe el nuevo texto del botón.")
        return

    if state == STATE_BUTTON_EDIT_TEXT:
        index = user_data.get("edit_index")
        if index is None or index < 0 or index >= len(draft["buttons"]):
            await message.reply_text("Ocurrió un problema con el índice del botón.")
            user_data[STATE_KEY] = STATE_MAIN_MENU
            return

        draft["buttons"][index]["text"] = text.strip()
        user_data[STATE_KEY] = STATE_BUTTON_EDIT_URL
        await message.reply_text("Ahora escribe el nuevo enlace para ese botón.")
        return

    if state == STATE_BUTTON_EDIT_URL:
        index = user_data.get("edit_index")
        if index is None or index < 0 or index >= len(draft["buttons"]):
            await message.reply_text("Ocurrió un problema con el índice del botón.")
            user_data[STATE_KEY] = STATE_MAIN_MENU
            return

        draft["buttons"][index]["url"] = text.strip()
        user_data["edit_index"] = None
        user_data[STATE_KEY] = STATE_MAIN_MENU
        await message.reply_text("Botón actualizado.")
        await send_preview(update, context, "Vista previa después de editar el botón:")
        return

    if state == STATE_BUTTON_DELETE_SELECT:
        try:
            idx = int(text.strip())
        except ValueError:
            await message.reply_text("Escribe un número válido.")
            return

        if idx < 1 or idx > len(draft["buttons"]):
            await message.reply_text("Número fuera de rango.")
            return

        eliminado = draft["buttons"].pop(idx - 1)
        user_data[STATE_KEY] = STATE_MAIN_MENU
        await message.reply_text("Botón eliminado: {t}".format(t=eliminado["text"]))
        await send_preview(update, context, "Vista previa después de eliminar el botón:")
        return

    # ---------------------- PROGRAMACIÓN ----------------------------

    if state == STATE_WAITING_SCHEDULE:
        try:
            scheduled_at = datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            await message.reply_text(
                "Formato inválido.\nUsa: AAAA-MM-DD HH:MM\nEjemplo: 2025-12-03 21:30"
            )
            return

        draft["scheduled_at"] = scheduled_at

        old_job = user_data.get(SCHEDULE_JOB_KEY)
        if old_job is not None:
            old_job.schedule_removal()

        job = context.job_queue.run_once(
            scheduled_job_send_post,
            when=scheduled_at,
            data={
                "chat_id": TARGET_CHAT_ID,
                "admin_id": ADMIN_ID,
                "type": draft["type"],
                "file_id": draft["file_id"],
                "text": draft["text"],
                "buttons": draft["buttons"],
            },
            name="scheduled_post",
        )
        user_data[SCHEDULE_JOB_KEY] = job
        user_data[STATE_KEY] = STATE_MAIN_MENU

        await message.reply_text(
            "Publicación programada para {dt}".format(
                dt=scheduled_at.strftime("%Y-%m-%d %H:%M")
            )
        )
        await send_preview(update, context, "Vista previa de la publicación programada:")
        return

    # ----------------------- DEFAULT ----------------------------

    await message.reply_text("Usa el menú para gestionar tus publicaciones.")
    await send_main_menu(update, context)


# =========================== ENVÍO INMEDIATO ===========================

async def send_post_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    draft = get_draft(user_data)

    if not draft["text"] and not draft["file_id"]:
        await update.effective_chat.send_message("No hay ninguna publicación en borrador.")
        return

    kb = build_buttons_keyboard(draft["buttons"])
    t = draft["type"]
    file_id = draft["file_id"]
    text = draft["text"] or ""

    if t == "photo" and file_id:
        await context.bot.send_photo(chat_id=TARGET_CHAT_ID, photo=file_id, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "video" and file_id:
        await context.bot.send_video(chat_id=TARGET_CHAT_ID, video=file_id, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "audio" and file_id:
        await context.bot.send_audio(chat_id=TARGET_CHAT_ID, audio=file_id, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "voice" and file_id:
        await context.bot.send_voice(chat_id=TARGET_CHAT_ID, voice=file_id, caption=text, reply_markup=kb, parse_mode="HTML")
    else:
        await context.bot.send_message(chat_id=TARGET_CHAT_ID, text=text, reply_markup=kb, parse_mode="HTML")

    job = user_data.get(SCHEDULE_JOB_KEY)
    if job is not None:
        job.schedule_removal()
        user_data[SCHEDULE_JOB_KEY] = None
        draft["scheduled_at"] = None

    await update.effective_chat.send_message("✅ Publicación enviada.")
    await send_main_menu(update, context)


# ====================== JOB DE PUBLICACIÓN PROGRAMADA ===================

async def scheduled_job_send_post(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    chat_id = data["chat_id"]
    admin_id = data["admin_id"]
    t = data["type"]
    file_id = data["file_id"]
    text = data["text"] or ""
    buttons = data["buttons"]

    kb = build_buttons_keyboard(buttons)

    if t == "photo" and file_id:
        await context.bot.send_photo(chat_id=chat_id, photo=file_id, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "video" and file_id:
        await context.bot.send_video(chat_id=chat_id, video=file_id, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "audio" and file_id:
        await context.bot.send_audio(chat_id=chat_id, audio=file_id, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "voice" and file_id:
        await context.bot.send_voice(chat_id=chat_id, voice=file_id, caption=text, reply_markup=kb, parse_mode="HTML")
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb, parse_mode="HTML")

    await context.bot.send_message(
        chat_id=admin_id,
        text="✅ Publicación programada enviada correctamente.",
    )


# ================================ MAIN =================================

def main() -> None:
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(menu_callback))
    application.add_handler(MessageHandler(~filters.COMMAND, message_handler))

    application.run_polling()


if __name__ == "__main__":
    main()
