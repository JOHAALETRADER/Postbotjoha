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
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    JobQueue,
    MessageHandler,
    filters,
)

# ================= CONFIGURACIÓN BÁSICA =================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = os.getenv("ADMIN_ID", "")
# Puede ser id numérico del canal o @username
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID", "") or ADMIN_ID

if not BOT_TOKEN:
    raise RuntimeError("Falta la variable de entorno BOT_TOKEN")
if not ADMIN_ID:
    raise RuntimeError("Falta la variable de entorno ADMIN_ID")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ================= CLAVES PARA user_data =================

DRAFT_KEY = "draft"
STATE_KEY = "state"
DEFAULT_BUTTONS_KEY = "default_buttons"
SCHEDULE_JOB_KEY = "schedule_job"
TEMPLATE_TEXT_KEY = "template_text"

# Estados
STATE_MAIN_MENU = "MAIN_MENU"
STATE_WAITING_PUBLICATION = "WAITING_PUBLICATION"
STATE_WAITING_BUTTONS = "WAITING_BUTTONS"
STATE_WAITING_SAVE_DEFAULT = "WAITING_SAVE_DEFAULT"
STATE_BUTTON_EDIT_SELECT = "BUTTON_EDIT_SELECT"
STATE_BUTTON_EDIT_TEXT = "BUTTON_EDIT_TEXT"
STATE_BUTTON_EDIT_URL = "BUTTON_EDIT_URL"
STATE_BUTTON_DELETE_SELECT = "BUTTON_DELETE_SELECT"
STATE_WAITING_SCHEDULE = "WAITING_SCHEDULE"


# ================= FUNCIONES AUXILIARES =================

def get_draft(ud: Dict[str, Any]) -> Dict[str, Any]:
    """Obtiene / inicializa el borrador actual."""
    if DRAFT_KEY not in ud:
        ud[DRAFT_KEY] = {
            "type": None,          # photo, video, audio, voice, text
            "file_id": None,
            "text": None,
            "buttons": [],         # lista de dicts {"text","url"}
            "scheduled_at": None,  # datetime
        }
    return ud[DRAFT_KEY]


def get_default_buttons(ud: Dict[str, Any]) -> List[Dict[str, str]]:
    if DEFAULT_BUTTONS_KEY not in ud:
        ud[DEFAULT_BUTTONS_KEY] = []
    return ud[DEFAULT_BUTTONS_KEY]


def build_buttons_keyboard(buttons: List[Dict[str, str]]) -> Optional[InlineKeyboardMarkup]:
    """Crea teclado en lista vertical (un botón por fila)."""
    if not buttons:
        return None
    rows = [[InlineKeyboardButton(b["text"], url=b["url"])] for b in buttons]
    return InlineKeyboardMarkup(rows)


def invisible_text() -> str:
    """Caracter invisible aceptado por Telegram como texto no vacío."""
    return "\u2063"


# ================= MENÚ PRINCIPAL =================

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    draft = get_draft(ud)
    defaults = get_default_buttons(ud)

    ud[STATE_KEY] = STATE_MAIN_MENU

    resumen_texto = draft["text"] or "(Sin publicación)"
    if len(resumen_texto) > 250:
        resumen_texto = resumen_texto[:247] + "..."

    num_botones = len(draft["buttons"])
    hay_predeterminados = "Sí" if defaults else "No"
    hay_plantilla = "Sí" if ud.get(TEMPLATE_TEXT_KEY) else "No"
    prog = draft["scheduled_at"].strftime("%Y-%m-%d %H:%M") if draft["scheduled_at"] else "Sin programación"

    msg = (
        "📌 *BOT AVANZADO – OPCIÓN A*\n\n"
        f"*Borrador actual:*\n{resumen_texto}\n\n"
        f"*Botones:* {num_botones}\n"
        f"*Botones predeterminados:* {hay_predeterminados}\n"
        f"*Plantilla recurrente:* {hay_plantilla}\n"
        f"*Programación:* {prog}"
    )

    kb = [
        [InlineKeyboardButton("📝 Crear publicación", callback_data="CREATE_PUBLICATION")],
        [InlineKeyboardButton("✏️ Editar publicación", callback_data="EDIT_PUBLICATION")],
        [InlineKeyboardButton("🔗 Botones", callback_data="MENU_BUTTONS")],
        [InlineKeyboardButton("🌟 Plantilla recurrente", callback_data="MENU_TEMPLATE")],
        [InlineKeyboardButton("⏰ Programar envío", callback_data="MENU_SCHEDULE")],
        [InlineKeyboardButton("📤 Enviar ahora", callback_data="MENU_SEND_NOW")],
    ]
    markup = InlineKeyboardMarkup(kb)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            msg, parse_mode="Markdown", reply_markup=markup
        )
    else:
        await update.effective_chat.send_message(
            msg, parse_mode="Markdown", reply_markup=markup
        )


# ================= /START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_user.id) != str(ADMIN_ID):
        return await update.message.reply_text("Este bot es privado.")

    get_draft(context.user_data)
    get_default_buttons(context.user_data)
    await send_main_menu(update, context)


# ================= CALLBACK QUERY (MENÚ) =================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if str(query.from_user.id) != str(ADMIN_ID):
        return await query.edit_message_text("No tienes permisos para usar este bot.")

    ud = context.user_data
    draft = get_draft(ud)
    defaults = get_default_buttons(ud)

    # Volver al menú
    if data == "BACK_MAIN":
        return await send_main_menu(update, context)

    # Crear publicación nueva
    if data == "CREATE_PUBLICATION":
        ud[DRAFT_KEY] = {
            "type": None,
            "file_id": None,
            "text": None,
            "buttons": [],
            "scheduled_at": None,
        }
        ud[STATE_KEY] = STATE_WAITING_PUBLICATION
        return await query.edit_message_text(
            "Envía tu publicación como mensaje normal:\n\n"
            "- Puede ser: foto, video, audio o nota de voz con texto, o solo texto.\n"
            "- Lo que envíes será el borrador actual."
        )

    # Editar publicación existente
    if data == "EDIT_PUBLICATION":
        if not draft["text"] and not draft["file_id"]:
            await query.edit_message_text("No hay publicación en borrador para editar.")
            return await send_main_menu(update, context)
        kb = [
            [InlineKeyboardButton("✏️ Editar texto / multimedia", callback_data="EDIT_TEXT")],
            [InlineKeyboardButton("🔗 Editar botones", callback_data="MENU_BUTTONS")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="BACK_MAIN")],
        ]
        return await query.edit_message_text(
            "¿Qué parte de la publicación deseas editar?",
            reply_markup=InlineKeyboardMarkup(kb),
        )

    if data == "EDIT_TEXT":
        ud[STATE_KEY] = STATE_WAITING_PUBLICATION
        return await query.edit_message_text(
            "Envía la nueva publicación (texto + multimedia). "
            "Reemplazará completamente al borrador actual."
        )

    # Submenú de botones
    if data == "MENU_BUTTONS":
        ud[STATE_KEY] = "BTN_MENU"
        if draft["buttons"]:
            lista = "\n".join(
                f"{i+1}. {b['text']} → {b['url']}" for i, b in enumerate(draft["buttons"])
            )
        else:
            lista = "Sin botones."

        kb = [
            [InlineKeyboardButton("➕ Añadir botón", callback_data="BTN_ADD")],
            [InlineKeyboardButton("✏️ Editar botón", callback_data="BTN_EDIT")],
            [InlineKeyboardButton("❌ Eliminar botón", callback_data="BTN_DELETE")],
            [InlineKeyboardButton("⭐ Guardar como predeterminados", callback_data="BTN_SAVE_DEFAULT")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="BACK_MAIN")],
        ]
        return await query.edit_message_text(
            f"*Botones actuales:*\n{lista}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb),
        )

    if data == "BTN_ADD":
        ud[STATE_KEY] = STATE_WAITING_BUTTONS
        return await query.edit_message_text(
            "Envía los botones así:\n\n"
            "- Puedes enviar varios en UN solo mensaje (uno por línea),\n"
            "- o un botón por mensaje.\n\n"
            "Formato: Texto - enlace\n\n"
            "Cuando termines, escribe *listo*.",
            parse_mode="Markdown",
        )

    if data == "BTN_EDIT":
        if not draft["buttons"]:
            await query.edit_message_text("No hay botones para editar.")
            return await send_main_menu(update, context)
        ud[STATE_KEY] = STATE_BUTTON_EDIT_SELECT
        lista = "\n".join(
            f"{i+1}. {b['text']} → {b['url']}" for i, b in enumerate(draft["buttons"])
        )
        return await query.edit_message_text(
            f"¿Qué botón quieres editar? (envía el número)\n\n{lista}"
        )

    if data == "BTN_DELETE":
        if not draft["buttons"]:
            await query.edit_message_text("No hay botones para eliminar.")
            return await send_main_menu(update, context)
        ud[STATE_KEY] = STATE_BUTTON_DELETE_SELECT
        lista = "\n".join(
            f"{i+1}. {b['text']} → {b['url']}" for i, b in enumerate(draft["buttons"])
        )
        return await query.edit_message_text(
            f"¿Qué botón quieres eliminar? (envía el número)\n\n{lista}"
        )

    if data == "BTN_SAVE_DEFAULT":
        if not draft["buttons"]:
            await query.edit_message_text("No hay botones en el borrador para guardar.")
            return await send_main_menu(update, context)
        ud[DEFAULT_BUTTONS_KEY] = list(draft["buttons"])
        await query.edit_message_text("✅ Botones guardados como predeterminados.")
        return await send_main_menu(update, context)

    # Plantilla recurrente
    if data == "MENU_TEMPLATE":
        tpl = ud.get(TEMPLATE_TEXT_KEY) or "(Sin plantilla guardada)"
        kb = [
            [InlineKeyboardButton("💾 Guardar plantilla", callback_data="TPL_SAVE")],
            [InlineKeyboardButton("📥 Insertar plantilla", callback_data="TPL_INSERT")],
            [InlineKeyboardButton("🗑️ Borrar plantilla", callback_data="TPL_CLEAR")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="BACK_MAIN")],
        ]
        return await query.edit_message_text(
            f"*Plantilla actual:*\n{tpl}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb),
        )

    if data == "TPL_SAVE":
        if not draft["text"]:
            await query.edit_message_text("No hay texto en el borrador para guardar.")
        else:
            ud[TEMPLATE_TEXT_KEY] = draft["text"]
            await query.edit_message_text("✅ Plantilla guardada.")
        return await send_main_menu(update, context)

    if data == "TPL_INSERT":
        tpl = ud.get(TEMPLATE_TEXT_KEY)
        if not tpl:
            await query.edit_message_text("No hay plantilla guardada.")
            return await send_main_menu(update, context)
        draft["text"] = tpl
        await query.edit_message_text("📌 Plantilla insertada en el borrador.")
        return await send_preview(update, context)

    if data == "TPL_CLEAR":
        ud[TEMPLATE_TEXT_KEY] = None
        await query.edit_message_text("🗑️ Plantilla borrada.")
        return await send_main_menu(update, context)

    # Programación
    if data == "MENU_SCHEDULE":
        ud[STATE_KEY] = STATE_WAITING_SCHEDULE
        return await query.edit_message_text(
            "Indica fecha y hora para programar.\nFormato: AAAA-MM-DD HH:MM"
        )

    if data == "MENU_SEND_NOW":
        return await send_post_now(update, context)

    if data == "PREVIEW_SEND_NOW":
        return await send_post_now(update, context)

    if data == "PREVIEW_SCHEDULE":
        ud[STATE_KEY] = STATE_WAITING_SCHEDULE
        return await query.edit_message_text(
            "Indica fecha y hora para programar.\nFormato: AAAA-MM-DD HH:MM"
        )

    if data == "PREVIEW_EDIT":
        kb = [
            [InlineKeyboardButton("✏️ Editar texto / multimedia", callback_data="EDIT_TEXT")],
            [InlineKeyboardButton("🔗 Editar botones", callback_data="MENU_BUTTONS")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="BACK_MAIN")],
        ]
        return await query.edit_message_text(
            "¿Qué deseas editar?",
            reply_markup=InlineKeyboardMarkup(kb),
        )

    if data == "PREVIEW_CANCEL":
        ud[DRAFT_KEY] = {
            "type": None,
            "file_id": None,
            "text": None,
            "buttons": [],
            "scheduled_at": None,
        }
        await query.edit_message_text("❌ Borrador cancelado.")
        return await send_main_menu(update, context)

    if data == "SAVE_DEFAULT_YES":
        ud[DEFAULT_BUTTONS_KEY] = list(draft["buttons"])
        await query.edit_message_text("✅ Botones guardados como predeterminados.")
        return await send_preview(update, context)

    if data == "SAVE_DEFAULT_NO":
        await query.edit_message_text("Botones NO guardados como predeterminados.")
        return await send_preview(update, context)

    if data == "USE_DEFAULT_BTNS":
        draft["buttons"] = list(defaults)
        await query.edit_message_text("Botones predeterminados aplicados al borrador.")
        return await send_preview(update, context)

    if data == "CREATE_NEW_BTNS":
        ud[STATE_KEY] = STATE_WAITING_BUTTONS
        return await query.edit_message_text(
            "Envía los nuevos botones.\nFormato: Texto - enlace\n"
            "Puedes enviar varios en un solo mensaje (uno por línea).",
            parse_mode="Markdown",
        )


# ================= VISTA PREVIA =================

async def send_preview(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    intro: str = "📎 Vista previa de la publicación:"
) -> None:
    chat = update.effective_chat
    ud = context.user_data
    draft = get_draft(ud)

    await chat.send_message(intro)

    kb = build_buttons_keyboard(draft["buttons"])
    t = draft["type"]
    fid = draft["file_id"]
    text = draft["text"] or ""

    caption = text.strip() if text.strip() else None
    safe_text = text.strip() if text.strip() else invisible_text()

    if t == "photo" and fid:
        await chat.send_photo(photo=fid, caption=caption, reply_markup=kb)
    elif t == "video" and fid:
        await chat.send_video(video=fid, caption=caption, reply_markup=kb)
    elif t == "audio" and fid:
        await chat.send_audio(audio=fid, caption=caption, reply_markup=kb)
    elif t == "voice" and fid:
        await chat.send_voice(voice=fid, caption=caption, reply_markup=kb)
    else:
        await chat.send_message(safe_text, reply_markup=kb)

    kb2 = [
        [InlineKeyboardButton("📤 Enviar ahora", callback_data="PREVIEW_SEND_NOW")],
        [InlineKeyboardButton("⏰ Programar", callback_data="PREVIEW_SCHEDULE")],
        [InlineKeyboardButton("✏️ Editar publicación", callback_data="PREVIEW_EDIT")],
        [InlineKeyboardButton("❌ Cancelar borrador", callback_data="PREVIEW_CANCEL")],
        [InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_MAIN")],
    ]
    await chat.send_message(
        "¿Qué deseas hacer con esta publicación?",
        reply_markup=InlineKeyboardMarkup(kb2),
    )


# ================= PARSEO DE BOTONES =================

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


# ================= MANEJADOR DE MENSAJES =================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_user.id) != str(ADMIN_ID):
        return

    msg = update.message
    text = msg.text or ""
    text_lower = text.lower().strip()

    ud = context.user_data
    state = ud.get(STATE_KEY, STATE_MAIN_MENU)
    draft = get_draft(ud)
    defaults = get_default_buttons(ud)

    # ----- PUBLICACIÓN -----
    if state == STATE_WAITING_PUBLICATION:
        if msg.photo:
            draft["type"] = "photo"
            draft["file_id"] = msg.photo[-1].file_id
            draft["text"] = msg.caption or ""
        elif msg.video:
            draft["type"] = "video"
            draft["file_id"] = msg.video.file_id
            draft["text"] = msg.caption or ""
        elif msg.audio:
            draft["type"] = "audio"
            draft["file_id"] = msg.audio.file_id
            draft["text"] = msg.caption or ""
        elif msg.voice:
            draft["type"] = "voice"
            draft["file_id"] = msg.voice.file_id
            draft["text"] = msg.caption or ""
        else:
            draft["type"] = "text"
            draft["file_id"] = None
            draft["text"] = text

        if not draft["text"] and not draft["file_id"]:
            return await msg.reply_text("Envía texto o multimedia con texto.")

        draft["buttons"] = []
        draft["scheduled_at"] = None

        if defaults:
            kb = [
                [InlineKeyboardButton("✅ Usar botones predeterminados", callback_data="USE_DEFAULT_BTNS")],
                [InlineKeyboardButton("➕ Crear nuevos botones", callback_data="CREATE_NEW_BTNS")],
            ]
            ud[STATE_KEY] = STATE_MAIN_MENU
            return await msg.reply_text(
                "Publicación recibida.\n¿Quieres usar los botones predeterminados o crear nuevos?",
                reply_markup=InlineKeyboardMarkup(kb),
            )

        ud[STATE_KEY] = STATE_WAITING_BUTTONS
        return await msg.reply_text(
            "Publicación recibida.\n\n"
            "Ahora envía los botones:\n"
            "- Un botón por mensaje, o\n"
            "- Varios botones en un mensaje (uno por línea).\n\n"
            "Formato: Texto - enlace\n\n"
            "Escribe *listo* cuando termines.",
            parse_mode="Markdown",
        )

    # ----- BOTONES -----
    if state == STATE_WAITING_BUTTONS:
        if text_lower == "listo":
            if not draft["buttons"]:
                return await msg.reply_text("Todavía no has añadido botones.")
            if not defaults:
                kb = [
                    [InlineKeyboardButton("✅ Sí, guardar", callback_data="SAVE_DEFAULT_YES")],
                    [InlineKeyboardButton("❌ No guardar", callback_data="SAVE_DEFAULT_NO")],
                ]
                ud[STATE_KEY] = STATE_WAITING_SAVE_DEFAULT
                return await msg.reply_text(
                    "¿Quieres guardar estos botones como predeterminados?",
                    reply_markup=InlineKeyboardMarkup(kb),
                )
            ud[STATE_KEY] = STATE_MAIN_MENU
            return await send_preview(update, context)

        lines = [l for l in text.splitlines() if l.strip()]
        if not lines:
            return await msg.reply_text(
                "Envía los botones en formato: Texto - enlace (uno por línea)."
            )

        nuevos: List[Dict[str, str]] = []
        for i, line in enumerate(lines, start=1):
            b = parse_button_line(line)
            if not b:
                return await msg.reply_text(
                    f"Línea {i} inválida:\n{line}\n\n"
                    "Formato correcto: Texto - enlace"
                )
            nuevos.append(b)

        draft["buttons"].extend(nuevos)

        if len(nuevos) == 1:
            return await msg.reply_text(
                "Botón añadido. Puedes enviar más o escribir *listo*.",
                parse_mode="Markdown",
            )

        if not defaults:
            kb = [
                [InlineKeyboardButton("✅ Sí, guardar", callback_data="SAVE_DEFAULT_YES")],
                [InlineKeyboardButton("❌ No guardar", callback_data="SAVE_DEFAULT_NO")],
            ]
            ud[STATE_KEY] = STATE_WAITING_SAVE_DEFAULT
            return await msg.reply_text(
                f"{len(nuevos)} botones añadidos.\n¿Guardarlos como predeterminados?",
                reply_markup=InlineKeyboardMarkup(kb),
            )

        ud[STATE_KEY] = STATE_MAIN_MENU
        return await send_preview(update, context, f"{len(nuevos)} botones añadidos correctamente:")

    if state == STATE_WAITING_SAVE_DEFAULT:
        return await msg.reply_text(
            "Responde usando los botones (Sí, guardar / No guardar)."
        )

    # ----- EDITAR BOTONES -----
    if state == STATE_BUTTON_EDIT_SELECT:
        try:
            idx = int(text.strip())
        except ValueError:
            return await msg.reply_text("Envía un número válido.")
        if idx < 1 or idx > len(draft["buttons"]):
            return await msg.reply_text("Número fuera de rango.")
        ud["edit_index"] = idx - 1
        ud[STATE_KEY] = STATE_BUTTON_EDIT_TEXT
        return await msg.reply_text("Escribe el nuevo texto del botón.")

    if state == STATE_BUTTON_EDIT_TEXT:
        idx = ud.get("edit_index")
        if idx is None or idx < 0 or idx >= len(draft["buttons"]):
            ud[STATE_KEY] = STATE_MAIN_MENU
            return await msg.reply_text("Error interno con el índice del botón.")
        draft["buttons"][idx]["text"] = text.strip()
        ud[STATE_KEY] = STATE_BUTTON_EDIT_URL
        return await msg.reply_text("Ahora escribe el nuevo enlace del botón.")

    if state == STATE_BUTTON_EDIT_URL:
        idx = ud.get("edit_index")
        if idx is None or idx < 0 or idx >= len(draft["buttons"]):
            ud[STATE_KEY] = STATE_MAIN_MENU
            return await msg.reply_text("Error interno con el índice del botón.")
        draft["buttons"][idx]["url"] = text.strip()
        ud["edit_index"] = None
        ud[STATE_KEY] = STATE_MAIN_MENU
        await msg.reply_text("✅ Botón actualizado.")
        return await send_preview(update, context, "Vista previa después de editar el botón:")

    if state == STATE_BUTTON_DELETE_SELECT:
        try:
            idx = int(text.strip())
        except ValueError:
            return await msg.reply_text("Envía un número válido.")
        if idx < 1 or idx > len(draft["buttons"]):
            return await msg.reply_text("Número fuera de rango.")
        eliminado = draft["buttons"].pop(idx - 1)
        ud[STATE_KEY] = STATE_MAIN_MENU
        await msg.reply_text(f"Botón eliminado: {eliminado['text']}")
        return await send_preview(update, context, "Vista previa después de eliminar el botón:")

    # ----- PROGRAMAR -----
    if state == STATE_WAITING_SCHEDULE:
        try:
            dt = datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            return await msg.reply_text(
                "Formato inválido.\nUsa: AAAA-MM-DD HH:MM"
            )

        draft["scheduled_at"] = dt
        job_queue: Optional[JobQueue] = context.application.job_queue

        if job_queue is None:
            ud[STATE_KEY] = STATE_MAIN_MENU
            await msg.reply_text(
                "⚠ Este servidor no tiene JobQueue activo.\n"
                "La publicación queda guardada; puedes usar 'Enviar ahora' desde la vista previa."
            )
            return await send_preview(update, context, "Vista previa (no se programó, envío manual):")

        old_job = ud.get(SCHEDULE_JOB_KEY)
        if old_job is not None:
            old_job.schedule_removal()

        job = job_queue.run_once(
            scheduled_job_send_post,
            when=dt,
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
        ud[SCHEDULE_JOB_KEY] = job
        await msg.reply_text(f"📅 Publicación programada para {dt.strftime('%Y-%m-%d %H:%M')}")

# MOSTRAR SOLO LA VISTA PREVIA, NO REGRESAR AL MENÚ
return await send_preview(update, context, "Vista previa de la publicación programada:")


    # Estado por defecto
    await msg.reply_text("Usa el menú para gestionar tus publicaciones.")
    await send_main_menu(update, context)


# ================= ENVÍO AHORA =================

async def send_post_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    draft = get_draft(ud)

    if not draft["text"] and not draft["file_id"]:
        return await update.effective_chat.send_message("No hay publicación en borrador.")

    kb = build_buttons_keyboard(draft["buttons"])
    t = draft["type"]
    fid = draft["file_id"]
    text = draft["text"] or ""

    caption = text.strip() if text.strip() else None
    safe_text = text.strip() if text.strip() else invisible_text()

    try:
        if t == "photo" and fid:
            await context.bot.send_photo(
                chat_id=TARGET_CHAT_ID,
                photo=fid,
                caption=caption,
                reply_markup=kb,
            )
        elif t == "video" and fid:
            await context.bot.send_video(
                chat_id=TARGET_CHAT_ID,
                video=fid,
                caption=caption,
                reply_markup=kb,
            )
        elif t == "audio" and fid:
            await context.bot.send_audio(
                chat_id=TARGET_CHAT_ID,
                audio=fid,
                caption=caption,
                reply_markup=kb,
            )
        elif t == "voice" and fid:
            await context.bot.send_voice(
                chat_id=TARGET_CHAT_ID,
                voice=fid,
                caption=caption,
                reply_markup=kb,
            )
        else:
            await context.bot.send_message(
                chat_id=TARGET_CHAT_ID,
                text=safe_text,
                reply_markup=kb,
            )
    except Exception as e:
        logger.exception("Error al enviar publicación inmediata")
        await update.effective_chat.send_message(
            f"⚠ Error al enviar la publicación:\n{e}"
        )
        return

    # Si había job programado, lo cancelamos
    job = ud.get(SCHEDULE_JOB_KEY)
    if job is not None:
        job.schedule_removal()
        ud[SCHEDULE_JOB_KEY] = None
        draft["scheduled_at"] = None

    await update.effective_chat.send_message("✅ Publicación enviada al canal.")
    await send_main_menu(update, context)


# ================= JOB PROGRAMADO =================

async def scheduled_job_send_post(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    chat_id = data["chat_id"]
    admin_id = data["admin_id"]
    t = data["type"]
    fid = data["file_id"]
    text = data["text"] or ""
    buttons = data["buttons"]

    kb = build_buttons_keyboard(buttons)
    caption = text.strip() if text.strip() else None
    safe_text = text.strip() if text.strip() else invisible_text()

    try:
        if t == "photo" and fid:
            await context.bot.send_photo(chat_id=chat_id, photo=fid, caption=caption, reply_markup=kb)
        elif t == "video" and fid:
            await context.bot.send_video(chat_id=chat_id, video=fid, caption=caption, reply_markup=kb)
        elif t == "audio" and fid:
            await context.bot.send_audio(chat_id=chat_id, audio=fid, caption=caption, reply_markup=kb)
        elif t == "voice" and fid:
            await context.bot.send_voice(chat_id=chat_id, voice=fid, caption=caption, reply_markup=kb)
        else:
            await context.bot.send_message(chat_id=chat_id, text=safe_text, reply_markup=kb)
    except Exception as e:
        logger.exception("Error al enviar publicación programada")
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"⚠ Error al enviar la publicación programada:\n{e}",
            )
        except Exception:
            pass
        return

    # Confirmación al admin
    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text="✅ Publicación programada enviada correctamente al canal.",
        )
    except Exception:
        # Segundo intento de seguridad
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text="✔ Se envió la publicación programada (confirmación de respaldo).",
            )
        except Exception:
            pass


# ================= MAIN =================

def main() -> None:
    app: Application = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(~filters.COMMAND, message_handler))

    logger.info("Bot de publicaciones avanzado iniciado.")
    app.run_polling()


if __name__ == "__main__":
    main()
