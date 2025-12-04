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
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    JobQueue,
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
            "type": None,
            "file_id": None,
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
    """
    ❗ Botones siempre en LISTA VERTICAL, uno por fila.
    """
    if not buttons:
        return None
    rows = [[InlineKeyboardButton(b["text"], url=b["url"])] for b in buttons]
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
            "📌 Envía ahora, en un solo mensaje:\n"
            "- Imagen + texto\n"
            "- Video + texto\n"
            "- Audio + texto\n"
            "- Nota de voz + texto\n"
            "- O solo texto.",
            parse_mode="Markdown",
        )
        return

    # ------------------------ EDITAR PUBLICACIÓN --------------------

    if data == "EDIT_PUBLICATION":
        if not draft["text"] and not draft["file_id"]:
            await query.edit_message_text("No hay publicación para editar.")
            await send_main_menu(update, context)
            return

        keyboard = [
            [InlineKeyboardButton("✏️ Editar texto", callback_data="EDIT_TEXT")],
            [InlineKeyboardButton("🖼️ Cambiar multimedia", callback_data="EDIT_MEDIA")],
            [InlineKeyboardButton("🔗 Editar botones", callback_data="MENU_BUTTONS")],
            [InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_MAIN")],
        ]

        await query.edit_message_text(
            "¿Qué deseas editar?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data == "EDIT_TEXT":
        user_data[STATE_KEY] = STATE_WAITING_PUBLICATION
        await query.edit_message_text("Envía la publicación nueva (texto + opcional multimedia).")
        return

    if data == "EDIT_MEDIA":
        user_data[STATE_KEY] = STATE_WAITING_PUBLICATION
        await query.edit_message_text("Envía la nueva imagen / video / audio / nota de voz.")
        return

    # --------------------------- BOTONES -----------------------------

    if data == "MENU_BUTTONS":
        user_data[STATE_KEY] = STATE_BUTTON_MENU

        lista = "Sin botones." if not draft["buttons"] else "\n".join(
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
            f"*Botones actuales:*\n{lista}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data == "BTN_ADD":
        user_data[STATE_KEY] = STATE_WAITING_BUTTONS
        await query.edit_message_text(
            "Envía tus botones:\n\n"
            "- Un botón por mensaje, o\n"
            "- Varios botones en un solo mensaje (uno por línea)\n\n"
            "Formato: Texto - enlace\n"
            "Escribe *listo* cuando termines.",
            parse_mode="Markdown",
        )
        return

    if data == "BTN_EDIT":
        if not draft["buttons"]:
            await query.edit_message_text("No hay botones.")
            await send_main_menu(update, context)
            return

        user_data[STATE_KEY] = STATE_BUTTON_EDIT_SELECT
        lista = "\n".join([f"{i+1}. {b['text']} → {b['url']}" for i, b in enumerate(draft["buttons"])])
        await query.edit_message_text(f"¿Qué botón deseas editar?\n\n{lista}")
        return

    if data == "BTN_DELETE":
        if not draft["buttons"]:
            await query.edit_message_text("No hay botones para eliminar.")
            await send_main_menu(update, context)
            return

        user_data[STATE_KEY] = STATE_BUTTON_DELETE_SELECT
        lista = "\n".join([f"{i+1}. {b['text']} → {b['url']}" for i, b in enumerate(draft["buttons"])])
        await query.edit_message_text(f"¿Qué botón deseas eliminar?\n\n{lista}")
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
        texto = tpl if tpl else "(Sin plantilla guardada)"

        keyboard = [
            [InlineKeyboardButton("💾 Guardar borrador como plantilla", callback_data="TPL_SAVE")],
            [InlineKeyboardButton("📥 Insertar plantilla", callback_data="TPL_INSERT")],
            [InlineKeyboardButton("🗑️ Borrar plantilla", callback_data="TPL_CLEAR")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="BACK_MAIN")],
        ]

        await query.edit_message_text(
            f"*Plantilla actual:*\n{texto}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "TPL_SAVE":
        if not draft["text"]:
            await query.edit_message_text("No hay texto para guardar.")
        else:
            user_data[TEMPLATE_TEXT_KEY] = draft["text"]
            await query.edit_message_text("Plantilla guardada.")
        await send_main_menu(update, context)
        return

    if data == "TPL_INSERT":
        tpl = user_data.get(TEMPLATE_TEXT_KEY)
        if not tpl:
            await query.edit_message_text("No hay plantilla guardada.")
        else:
            draft["text"] = tpl
            await query.edit_message_text("Plantilla insertada.")
        await send_main_menu(update, context)
        return

    if data == "TPL_CLEAR":
        user_data[TEMPLATE_TEXT_KEY] = None
        await query.edit_message_text("Plantilla borrada.")
        await send_main_menu(update, context)
        return

    # --------------------- PROGRAMAR / ENVIAR -----------------------

    if data == "MENU_SCHEDULE":
        user_data[STATE_KEY] = STATE_WAITING_SCHEDULE
        await query.edit_message_text(
            "Indica fecha y hora:\nFormato: AAAA-MM-DD HH:MM\nEj: 2025-12-03 19:50"
        )
        return

    if data == "MENU_SEND_NOW":
        await send_post_now(update, context)
        return

    if data == "PREVIEW_SEND_NOW":
        await send_post_now(update, context)
        return

    if data == "PREVIEW_SCHEDULE":
        user_data[STATE_KEY] = STATE_WAITING_SCHEDULE
        await query.edit_message_text(
            "Indica fecha y hora (AAAA-MM-DD HH:MM)"
        )
        return

    if data == "PREVIEW_EDIT":
        keyboard = [
            [InlineKeyboardButton("✏️ Editar texto", callback_data="EDIT_TEXT")],
            [InlineKeyboardButton("🖼️ Cambiar multimedia", callback_data="EDIT_MEDIA")],
            [InlineKeyboardButton("🔗 Editar botones", callback_data="MENU_BUTTONS")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="BACK_MAIN")],
        ]
        await query.edit_message_text("¿Qué deseas editar?", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data == "PREVIEW_CANCEL":
        user_data[DRAFT_KEY] = {
            "type": None, "file_id": None, "text": None, "buttons": [], "scheduled_at": None
        }
        await query.edit_message_text("Borrador cancelado.")
        await send_main_menu(update, context)
        return

# ============================ VISTA PREVIA ==============================

async def send_preview(update: Update, context: ContextTypes.DEFAULT_TYPE, titulo=None):
    user_data = context.user_data
    draft = get_draft(user_data)
    chat = update.effective_chat

    titulo = titulo or "📎 Vista previa:"
    await chat.send_message(titulo)

    kb = build_buttons_keyboard(draft["buttons"])

    t = draft["type"]
    fid = draft["file_id"]
    txt = draft["text"] or ""

    if t == "photo" and fid:
        await chat.send_photo(photo=fid, caption=txt, reply_markup=kb, parse_mode="HTML")
    elif t == "video" and fid:
        await chat.send_video(video=fid, caption=txt, reply_markup=kb, parse_mode="HTML")
    elif t == "audio" and fid:
        await chat.send_audio(audio=fid, caption=txt, reply_markup=kb, parse_mode="HTML")
    elif t == "voice" and fid:
        await chat.send_voice(voice=fid, caption=txt, reply_markup=kb, parse_mode="HTML")
    else:
        await chat.send_message(txt, reply_markup=kb, parse_mode="HTML")

    keyboard = [
        [InlineKeyboardButton("📤 Enviar ahora", callback_data="PREVIEW_SEND_NOW")],
        [InlineKeyboardButton("⏰ Programar", callback_data="PREVIEW_SCHEDULE")],
        [InlineKeyboardButton("✏️ Editar publicación", callback_data="PREVIEW_EDIT")],
        [InlineKeyboardButton("❌ Cancelar borrador", callback_data="PREVIEW_CANCEL")],
        [InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_MAIN")],
    ]

    await chat.send_message("¿Qué deseas hacer?", reply_markup=InlineKeyboardMarkup(keyboard))

# ========================= BOTONES EN GRUPO =============================

def parse_button_line(line: str) -> Optional[Dict[str, str]]:
    line = line.strip()
    if not line:
        return None

    separadores = [" - ", " – ", " — ", " | "]
    for sep in separadores:
        if sep in line:
            text, url = line.split(sep, 1)
            text = text.strip()
            url = url.strip()
            if text and url:
                return {"text": text, "url": url}
    return None

# ========================= MANEJO DE MENSAJES ==========================

# ========================= MANEJO DE MENSAJES ==========================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Solo el admin puede usarlo
    if str(update.effective_user.id) != str(ADMIN_ID):
        return

    user_data = context.user_data
    state = user_data.get(STATE_KEY, STATE_MAIN_MENU)
    draft = get_draft(user_data)
    default_buttons = get_default_buttons(user_data)

    msg = update.message
    if not msg:
        return

    text = msg.text or ""
    text_lower = text.lower().strip() if text else ""

    # -------- ESPERANDO PUBLICACIÓN (IMAGEN / VIDEO / AUDIO / VOICE / TEXTO) --------

    if state == STATE_WAITING_PUBLICATION:
        mtype = "text"
        file_id = None
        contenido_texto = ""

        if msg.photo:
            mtype = "photo"
            file_id = msg.photo[-1].file_id
            contenido_texto = msg.caption or ""
        elif msg.video:
            mtype = "video"
            file_id = msg.video.file_id
            contenido_texto = msg.caption or ""
        elif msg.audio:
            mtype = "audio"
            file_id = msg.audio.file_id
            contenido_texto = msg.caption or ""
        elif msg.voice:
            mtype = "voice"
            file_id = msg.voice.file_id
            contenido_texto = msg.caption or ""
        else:
            mtype = "text"
            file_id = None
            contenido_texto = msg.text or ""

        if not contenido_texto and not file_id:
            await msg.reply_text(
                "Envía un mensaje con texto o un mensaje con imagen/video/audio/nota de voz."
            )
            return

        draft["type"] = mtype
        draft["file_id"] = file_id
        draft["text"] = contenido_texto
        draft["buttons"] = []

        # ¿Tienes botones predeterminados?
        if default_buttons:
            keyboard = [
                [InlineKeyboardButton("✅ Usar botones predeterminados", callback_data="USE_DEFAULT_BTNS")],
                [InlineKeyboardButton("➕ Crear nuevos botones", callback_data="CREATE_NEW_BTNS")],
            ]
            user_data[STATE_KEY] = STATE_MAIN_MENU
            await msg.reply_text(
                "Publicación recibida.\n\n¿Deseas usar tus botones predeterminados o crear nuevos?",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return

        # Sin predeterminados → vamos directo a creación de botones
        user_data[STATE_KEY] = STATE_WAITING_BUTTONS
        await msg.reply_text(
            "Publicación recibida.\n\n"
            "Ahora envía los botones:\n"
            "- Un botón por mensaje, o\n"
            "- Varios botones en un solo mensaje (uno por línea)\n\n"
            "Formato: Texto - enlace\n"
            "Escribe *listo* cuando termines.",
            parse_mode="Markdown",
        )
        return

    # ---------------- ESPERANDO BOTONES ----------------

    if state == STATE_WAITING_BUTTONS:
        if text_lower == "listo":
            if not draft["buttons"]:
                await msg.reply_text(
                    "No has añadido ningún botón. Añade al menos uno o envía de nuevo."
                )
                return

            if not default_buttons:
                keyboard = [
                    [InlineKeyboardButton("✅ Sí, guardar", callback_data="SAVE_DEFAULT_YES")],
                    [InlineKeyboardButton("❌ No guardar", callback_data="SAVE_DEFAULT_NO")],
                ]
                user_data[STATE_KEY] = STATE_WAITING_SAVE_DEFAULT
                await msg.reply_text(
                    "¿Deseas guardar estos botones como predeterminados?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return

            user_data[STATE_KEY] = STATE_MAIN_MENU
            await send_preview(update, context)
            return

        # Permitimos 1 o varios botones en un mensaje
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            await msg.reply_text(
                "Envía el botón en formato: Texto - enlace.\n"
                "O varios botones, uno por línea."
            )
            return

        # VALIDACIÓN ESTRICTA (opción B): si alguna línea está mal, error y no se guarda nada
        nuevos_botones: List[Dict[str, str]] = []
        for i, line in enumerate(lines, start=1):
            btn = parse_button_line(line)
            if not btn:
                await msg.reply_text(
                    f"Línea {i} inválida.\n"
                    "Cada botón debe ir así: Texto - enlace\n\n"
                    f"Línea recibida:\n{line}"
                )
                return
            nuevos_botones.append(btn)

        # Todas las líneas son válidas → agregamos
        draft["buttons"].extend(nuevos_botones)

        if len(lines) == 1:
            # Solo un botón: seguimos en modo añadir
            await msg.reply_text(
                f"Botón añadido: {nuevos_botones[0]['text']}\n\n"
                "Puedes enviar más botones o escribir *listo* cuando termines.",
                parse_mode="Markdown",
            )
            return
        else:
            # Varios botones: añadimos y pasamos a guardar predet / vista previa
            await msg.reply_text(
                f"{len(nuevos_botones)} botones añadidos correctamente."
            )
            if not default_buttons:
                keyboard = [
                    [InlineKeyboardButton("✅ Sí, guardar", callback_data="SAVE_DEFAULT_YES")],
                    [InlineKeyboardButton("❌ No guardar", callback_data="SAVE_DEFAULT_NO")],
                ]
                user_data[STATE_KEY] = STATE_WAITING_SAVE_DEFAULT
                await msg.reply_text(
                    "¿Deseas guardar estos botones como predeterminados?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return

            user_data[STATE_KEY] = STATE_MAIN_MENU
            await send_preview(update, context)
            return

    # ------------- ESPERANDO DECISIÓN GUARDAR BOTONES ---------------

    if state == STATE_WAITING_SAVE_DEFAULT:
        await msg.reply_text(
            "Responde usando los botones de la pregunta anterior."
        )
        return

    # ----------------- EDICIÓN DE BOTONES ---------------------------

    if state == STATE_BUTTON_EDIT_SELECT:
        try:
            idx = int(text.strip())
        except ValueError:
            await msg.reply_text("Escribe un número válido.")
            return

        if idx < 1 or idx > len(draft["buttons"]):
            await msg.reply_text("Número fuera de rango.")
            return

        user_data["edit_index"] = idx - 1
        user_data[STATE_KEY] = STATE_BUTTON_EDIT_TEXT
        await msg.reply_text("Escribe el nuevo texto del botón.")
        return

    if state == STATE_BUTTON_EDIT_TEXT:
        index = user_data.get("edit_index")
        if index is None or index < 0 or index >= len(draft["buttons"]):
            await msg.reply_text("Ocurrió un problema con el índice del botón.")
            user_data[STATE_KEY] = STATE_MAIN_MENU
            return

        draft["buttons"][index]["text"] = text.strip()
        user_data[STATE_KEY] = STATE_BUTTON_EDIT_URL
        await msg.reply_text("Ahora escribe el nuevo enlace para ese botón.")
        return

    if state == STATE_BUTTON_EDIT_URL:
        index = user_data.get("edit_index")
        if index is None or index < 0 or index >= len(draft["buttons"]):
            await msg.reply_text("Ocurrió un problema con el índice del botón.")
            user_data[STATE_KEY] = STATE_MAIN_MENU
            return

        draft["buttons"][index]["url"] = text.strip()
        user_data["edit_index"] = None
        user_data[STATE_KEY] = STATE_MAIN_MENU
        await msg.reply_text("Botón actualizado.")
        await send_preview(update, context, "Vista previa después de editar el botón:")
        return

    if state == STATE_BUTTON_DELETE_SELECT:
        try:
            idx = int(text.strip())
        except ValueError:
            await msg.reply_text("Escribe un número válido.")
            return

        if idx < 1 or idx > len(draft["buttons"]):
            await msg.reply_text("Número fuera de rango.")
            return

        eliminado = draft["buttons"].pop(idx - 1)
        user_data[STATE_KEY] = STATE_MAIN_MENU
        await msg.reply_text(f"Botón eliminado: {eliminado['text']}")
        await send_preview(update, context, "Vista previa después de eliminar el botón:")
        return

    # ---------------------- PROGRAMACIÓN ----------------------------

    if state == STATE_WAITING_SCHEDULE:
        try:
            scheduled_at = datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            await msg.reply_text(
                "Formato inválido.\nUsa: AAAA-MM-DD HH:MM\nEjemplo: 2025-12-03 21:30"
            )
            return

        draft["scheduled_at"] = scheduled_at

        job_queue: Optional[JobQueue] = context.application.job_queue
        if job_queue is None:
            # Evitamos que el bot se caiga si no está instalado APScheduler
            await msg.reply_text(
                "⚠ No se pudo programar automáticamente porque JobQueue no está disponible "
                "en este servidor.\n\n"
                "La publicación quedó guardada en borrador. Podrás enviarla con 'Enviar ahora'."
            )
            user_data[STATE_KEY] = STATE_MAIN_MENU
            await send_preview(update, context, "Vista previa (no se programó, envío manual):")
            return

        # Cancelar job anterior si existía
        old_job = user_data.get(SCHEDULE_JOB_KEY)
        if old_job is not None:
            old_job.schedule_removal()

        job = job_queue.run_once(
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

        await msg.reply_text(
            "📅 Publicación programada para {dt}".format(
                dt=scheduled_at.strftime("%Y-%m-%d %H:%M")
            )
        )
        await send_preview(update, context, "Vista previa de la publicación programada:")
        return

    # ----------------------- DEFAULT ----------------------------

    await msg.reply_text("Usa el menú para gestionar tus publicaciones.")
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

    # Limpiar programación si había
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
    application: Application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(menu_callback))
    application.add_handler(MessageHandler(~filters.COMMAND, message_handler))

    application.run_polling()

if __name__ == "__main__":
    main()
