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

# ================== CONFIG ==================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = os.getenv("ADMIN_ID", "")
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID", "")

if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN")
if not ADMIN_ID:
    raise RuntimeError("Falta ADMIN_ID")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# keys user_data
DRAFT_KEY = "draft"
STATE_KEY = "state"
DEFAULT_BUTTONS_KEY = "default_buttons"
SCHEDULE_JOB_KEY = "schedule_job"
TEMPLATE_TEXT_KEY = "template_text"

# states
STATE_MAIN_MENU = "MAIN_MENU"
STATE_WAITING_PUBLICATION = "WAITING_PUBLICATION"
STATE_WAITING_BUTTONS = "WAITING_BUTTONS"
STATE_WAITING_SAVE_DEFAULT = "WAITING_SAVE_DEFAULT"
STATE_BUTTON_EDIT_SELECT = "BUTTON_EDIT_SELECT"
STATE_BUTTON_EDIT_TEXT = "BUTTON_EDIT_TEXT"
STATE_BUTTON_EDIT_URL = "BUTTON_EDIT_URL"
STATE_BUTTON_DELETE_SELECT = "BUTTON_DELETE_SELECT"
STATE_WAITING_SCHEDULE = "WAITING_SCHEDULE"


# ================ HELPERS ==================

def get_draft(ud: Dict[str, Any]) -> Dict[str, Any]:
    if DRAFT_KEY not in ud:
        ud[DRAFT_KEY] = {
            "type": None,        # "photo", "video", "audio", "voice", "text"
            "file_id": None,
            "text": None,
            "buttons": [],       # list[{"text","url"}]
            "scheduled_at": None,
        }
    return ud[DRAFT_KEY]


def get_default_buttons(ud: Dict[str, Any]) -> List[Dict[str, str]]:
    if DEFAULT_BUTTONS_KEY not in ud:
        ud[DEFAULT_BUTTONS_KEY] = []
    return ud[DEFAULT_BUTTONS_KEY]


def build_buttons_keyboard(buttons: List[Dict[str, str]]) -> Optional[InlineKeyboardMarkup]:
    # siempre 1 botón por fila
    if not buttons:
        return None
    rows = [[InlineKeyboardButton(b["text"], url=b["url"])] for b in buttons]
    return InlineKeyboardMarkup(rows)


# ================ MENÚ PRINCIPAL ==================

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    draft = get_draft(ud)
    defaults = get_default_buttons(ud)
    ud[STATE_KEY] = STATE_MAIN_MENU

    texto = draft["text"] or "(Sin publicación en borrador)"
    if len(texto) > 250:
        texto = texto[:247] + "..."
    botones = len(draft["buttons"])
    pred = "Sí" if defaults else "No"
    plantilla = "Sí" if ud.get(TEMPLATE_TEXT_KEY) else "No"
    prog = draft["scheduled_at"].strftime("%Y-%m-%d %H:%M") if draft["scheduled_at"] else "Sin programación"

    msg = (
        "📌 *BOT AVANZADO – OPCIÓN A*\n\n"
        f"*Borrador actual:*\n{texto}\n\n"
        f"*Botones:* {botones}\n"
        f"*Botones predeterminados:* {pred}\n"
        f"*Plantilla recurrente:* {plantilla}\n"
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
        await update.callback_query.edit_message_text(msg, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.effective_chat.send_message(msg, parse_mode="Markdown", reply_markup=markup)


# ================ /START ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_user.id) != str(ADMIN_ID):
        return await update.message.reply_text("Este bot es privado.")
    get_draft(context.user_data)
    get_default_buttons(context.user_data)
    await send_main_menu(update, context)


# ================ CALLBACK MENÚ ==================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = q.data

    if str(q.from_user.id) != str(ADMIN_ID):
        return await q.edit_message_text("Sin permisos.")

    ud = context.user_data
    draft = get_draft(ud)
    defaults = get_default_buttons(ud)

    # volver
    if data == "BACK_MAIN":
        return await send_main_menu(update, context)

    # crear
    if data == "CREATE_PUBLICATION":
        ud[DRAFT_KEY] = {"type": None, "file_id": None, "text": None, "buttons": [], "scheduled_at": None}
        ud[STATE_KEY] = STATE_WAITING_PUBLICATION
        return await q.edit_message_text(
            "Crea tu publicación:\n\n"
            "Envía *en un solo mensaje* tu imagen / video / audio / nota de voz con texto,\n"
            "o solo texto.",
            parse_mode="Markdown",
        )

    # editar publicación
    if data == "EDIT_PUBLICATION":
        if not draft["text"] and not draft["file_id"]:
            await q.edit_message_text("No hay publicación para editar.")
            return await send_main_menu(update, context)
        kb = [
            [InlineKeyboardButton("✏️ Editar texto / contenido", callback_data="EDIT_TEXT")],
            [InlineKeyboardButton("🔗 Editar botones", callback_data="MENU_BUTTONS")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="BACK_MAIN")],
        ]
        return await q.edit_message_text("¿Qué deseas editar?", reply_markup=InlineKeyboardMarkup(kb))

    if data == "EDIT_TEXT":
        ud[STATE_KEY] = STATE_WAITING_PUBLICATION
        return await q.edit_message_text(
            "Envía nuevamente la publicación (texto + multimedia opcional).\n"
            "Reemplazará al borrador actual."
        )

    # menú de botones
    if data == "MENU_BUTTONS":
        ud[STATE_KEY] = "BTN_MENU"
        lista = "Sin botones." if not draft["buttons"] else "\n".join(
            f"{i+1}. {b['text']} → {b['url']}" for i, b in enumerate(draft["buttons"])
        )
        kb = [
            [InlineKeyboardButton("➕ Añadir botón", callback_data="BTN_ADD")],
            [InlineKeyboardButton("✏️ Editar botón", callback_data="BTN_EDIT")],
            [InlineKeyboardButton("❌ Eliminar botón", callback_data="BTN_DELETE")],
            [InlineKeyboardButton("⭐ Guardar como predeterminados", callback_data="BTN_SAVE_DEFAULT")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="BACK_MAIN")],
        ]
        return await q.edit_message_text(
            f"*Botones actuales:*\n{lista}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb),
        )

    if data == "BTN_ADD":
        ud[STATE_KEY] = STATE_WAITING_BUTTONS
        return await q.edit_message_text(
            "Ahora envía los botones.\n\n"
            "- Un botón por mensaje, o\n"
            "- Varios botones en un solo mensaje (uno por línea)\n\n"
            "Formato: Texto - enlace\n"
            "Escribe *listo* cuando termines.",
            parse_mode="Markdown",
        )

    if data == "BTN_EDIT":
        if not draft["buttons"]:
            await q.edit_message_text("No hay botones para editar.")
            return await send_main_menu(update, context)
        ud[STATE_KEY] = STATE_BUTTON_EDIT_SELECT
        lista = "\n".join(f"{i+1}. {b['text']} → {b['url']}" for i, b in enumerate(draft["buttons"]))
        return await q.edit_message_text(f"¿Qué botón deseas editar?\n\n{lista}")

    if data == "BTN_DELETE":
        if not draft["buttons"]:
            await q.edit_message_text("No hay botones para eliminar.")
            return await send_main_menu(update, context)
        ud[STATE_KEY] = STATE_BUTTON_DELETE_SELECT
        lista = "\n".join(f"{i+1}. {b['text']} → {b['url']}" for i, b in enumerate(draft["buttons"]))
        return await q.edit_message_text(f"¿Qué botón deseas eliminar?\n\n{lista}")

    if data == "BTN_SAVE_DEFAULT":
        if not draft["buttons"]:
            await q.edit_message_text("No hay botones que guardar.")
            return await send_main_menu(update, context)
        ud[DEFAULT_BUTTONS_KEY] = list(draft["buttons"])
        await q.edit_message_text("Botones guardados como predeterminados.")
        return await send_main_menu(update, context)

    # plantilla
    if data == "MENU_TEMPLATE":
        tpl = ud.get(TEMPLATE_TEXT_KEY) or "(Sin plantilla guardada)"
        kb = [
            [InlineKeyboardButton("💾 Guardar borrador como plantilla", callback_data="TPL_SAVE")],
            [InlineKeyboardButton("📥 Insertar plantilla", callback_data="TPL_INSERT")],
            [InlineKeyboardButton("🗑️ Borrar plantilla", callback_data="TPL_CLEAR")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="BACK_MAIN")],
        ]
        return await q.edit_message_text(
            f"*Plantilla actual:*\n{tpl}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb),
        )

    if data == "TPL_SAVE":
        if not draft["text"]:
            await q.edit_message_text("No hay texto para guardar.")
        else:
            ud[TEMPLATE_TEXT_KEY] = draft["text"]
            await q.edit_message_text("Plantilla guardada.")
        return await send_main_menu(update, context)

    if data == "TPL_INSERT":
        tpl = ud.get(TEMPLATE_TEXT_KEY)
        if not tpl:
            await q.edit_message_text("No hay plantilla guardada.")
        else:
            draft["text"] = tpl
            await q.edit_message_text("Plantilla insertada en el borrador.")
        return await send_main_menu(update, context)

    if data == "TPL_CLEAR":
        ud[TEMPLATE_TEXT_KEY] = None
        await q.edit_message_text("Plantilla borrada.")
        return await send_main_menu(update, context)

    # programar / enviar
    if data == "MENU_SCHEDULE":
        ud[STATE_KEY] = STATE_WAITING_SCHEDULE
        return await q.edit_message_text(
            "Indica fecha y hora para programar.\nFormato: AAAA-MM-DD HH:MM"
        )

    if data == "MENU_SEND_NOW":
        return await send_post_now(update, context)

    if data == "PREVIEW_SEND_NOW":
        return await send_post_now(update, context)

    if data == "PREVIEW_SCHEDULE":
        ud[STATE_KEY] = STATE_WAITING_SCHEDULE
        return await q.edit_message_text(
            "Indica fecha y hora para programar.\nFormato: AAAA-MM-DD HH:MM"
        )

    if data == "PREVIEW_EDIT":
        # reutilizamos EDIT_PUBLICATION
        if not draft["text"] and not draft["file_id"]:
            await q.edit_message_text("No hay publicación para editar.")
            return await send_main_menu(update, context)
        kb = [
            [InlineKeyboardButton("✏️ Editar texto / contenido", callback_data="EDIT_TEXT")],
            [InlineKeyboardButton("🔗 Editar botones", callback_data="MENU_BUTTONS")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="BACK_MAIN")],
        ]
        return await q.edit_message_text("¿Qué deseas editar?", reply_markup=InlineKeyboardMarkup(kb))

    if data == "PREVIEW_CANCEL":
        ud[DRAFT_KEY] = {"type": None, "file_id": None, "text": None, "buttons": [], "scheduled_at": None}
        await q.edit_message_text("Borrador cancelado.")
        return await send_main_menu(update, context)

    # guardar botones como predeterminados desde el flujo de creación
    if data == "SAVE_DEFAULT_YES":
        ud[DEFAULT_BUTTONS_KEY] = list(draft["buttons"])
        ud[STATE_KEY] = STATE_MAIN_MENU
        await q.edit_message_text("Botones guardados como predeterminados.")
        return await send_preview(update, context)

    if data == "SAVE_DEFAULT_NO":
        ud[STATE_KEY] = STATE_MAIN_MENU
        await q.edit_message_text("Botones no guardados como predeterminados.")
        return await send_preview(update, context)

    # usar default después de crear publicación
    if data == "USE_DEFAULT_BTNS":
        draft["buttons"] = list(defaults)
        ud[STATE_KEY] = STATE_MAIN_MENU
        await q.edit_message_text("Botones predeterminados aplicados.")
        return await send_preview(update, context)

    if data == "CREATE_NEW_BTNS":
        ud[STATE_KEY] = STATE_WAITING_BUTTONS
        return await q.edit_message_text(
            "Envía los botones (uno por mensaje o varios por línea).\n"
            "Formato: Texto - enlace\nEscribe *listo* cuando termines.",
            parse_mode="Markdown",
        )


# ================ PREVIEW ==================

async def send_preview(update: Update, context: ContextTypes.DEFAULT_TYPE, intro: str = "📎 Vista previa:") -> None:
    chat = update.effective_chat
    ud = context.user_data
    draft = get_draft(ud)

    await chat.send_message(intro)

    kb = build_buttons_keyboard(draft["buttons"])
    t = draft["type"]
    fid = draft["file_id"]
    text = draft["text"] or ""

    if t == "photo" and fid:
        await chat.send_photo(photo=fid, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "video" and fid:
        await chat.send_video(video=fid, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "audio" and fid:
        await chat.send_audio(audio=fid, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "voice" and fid:
        await chat.send_voice(voice=fid, caption=text, reply_markup=kb, parse_mode="HTML")
    else:
        await chat.send_message(text, reply_markup=kb, parse_mode="HTML")

    kb2 = [
        [InlineKeyboardButton("📤 Enviar ahora", callback_data="PREVIEW_SEND_NOW")],
        [InlineKeyboardButton("⏰ Programar", callback_data="PREVIEW_SCHEDULE")],
        [InlineKeyboardButton("✏️ Editar publicación", callback_data="PREVIEW_EDIT")],
        [InlineKeyboardButton("❌ Cancelar borrador", callback_data="PREVIEW_CANCEL")],
        [InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_MAIN")],
    ]
    await chat.send_message("¿Qué deseas hacer?", reply_markup=InlineKeyboardMarkup(kb2))


# ================ PARSE BOTONES ==================

def parse_button_line(line: str) -> Optional[Dict[str, str]]:
    line = line.strip()
    if not line:
        return None
    seps = [" - ", " – ", " — ", " | "]
    for sep in seps:
        if sep in line:
            t, u = line.split(sep, 1)
            t = t.strip()
            u = u.strip()
            if t and u:
                return {"text": t, "url": u}
    return None


# ================ MESSAGE HANDLER ==================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_user.id) != str(ADMIN_ID):
        return

    msg = update.message
    text = msg.text or ""
    text_low = text.lower().strip()
    ud = context.user_data
    state = ud.get(STATE_KEY, STATE_MAIN_MENU)
    draft = get_draft(ud)
    defaults = get_default_buttons(ud)

    # -------- PUBLICACIÓN --------
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
                "Publicación recibida.\n\n¿Deseas usar tus botones predeterminados o crear nuevos?",
                reply_markup=InlineKeyboardMarkup(kb),
            )

        ud[STATE_KEY] = STATE_WAITING_BUTTONS
        return await msg.reply_text(
            "Publicación recibida.\n\n"
            "Ahora envía los botones.\n"
            "- Un botón por mensaje, o\n"
            "- Varios botones en un solo mensaje (uno por línea)\n\n"
            "Formato: Texto - enlace\n"
            "Escribe *listo* cuando termines.",
            parse_mode="Markdown",
        )

    # -------- BOTONES --------
    if state == STATE_WAITING_BUTTONS:
        if text_low == "listo":
            if not draft["buttons"]:
                return await msg.reply_text("Todavía no añadiste botones.")
            if not defaults:
                kb = [
                    [InlineKeyboardButton("✅ Sí, guardar", callback_data="SAVE_DEFAULT_YES")],
                    [InlineKeyboardButton("❌ No guardar", callback_data="SAVE_DEFAULT_NO")],
                ]
                ud[STATE_KEY] = STATE_WAITING_SAVE_DEFAULT
                return await msg.reply_text(
                    "¿Deseas guardar estos botones como predeterminados?",
                    reply_markup=InlineKeyboardMarkup(kb),
                )
            ud[STATE_KEY] = STATE_MAIN_MENU
            return await send_preview(update, context)

        lineas = [l for l in text.splitlines() if l.strip()]
        if not lineas:
            return await msg.reply_text(
                "Envía botones en formato: Texto - enlace\nUno por línea."
            )

        nuevos: List[Dict[str, str]] = []
        for i, linea in enumerate(lineas, start=1):
            b = parse_button_line(linea)
            if not b:
                return await msg.reply_text(
                    f"Línea {i} inválida:\n{linea}\n\nFormato correcto:\nTexto - enlace"
                )
            nuevos.append(b)

        draft["buttons"].extend(nuevos)

        if len(nuevos) == 1:
            return await msg.reply_text(
                "Botón añadido. Puedes enviar más o escribir *listo*.",
                parse_mode="Markdown",
            )

        # varios de golpe
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
        return await msg.reply_text("Responde con los botones de la pregunta (Sí, guardar / No guardar).")

    # -------- EDITAR BOTONES --------
    if state == STATE_BUTTON_EDIT_SELECT:
        try:
            idx = int(text.strip())
        except ValueError:
            return await msg.reply_text("Escribe un número válido.")
        if idx < 1 or idx > len(draft["buttons"]):
            return await msg.reply_text("Número fuera de rango.")
        ud["edit_index"] = idx - 1
        ud[STATE_KEY] = STATE_BUTTON_EDIT_TEXT
        return await msg.reply_text("Escribe el nuevo texto del botón.")

    if state == STATE_BUTTON_EDIT_TEXT:
        idx = ud.get("edit_index")
        if idx is None or idx < 0 or idx >= len(draft["buttons"]):
            ud[STATE_KEY] = STATE_MAIN_MENU
            return await msg.reply_text("Error de índice.")
        draft["buttons"][idx]["text"] = text.strip()
        ud[STATE_KEY] = STATE_BUTTON_EDIT_URL
        return await msg.reply_text("Ahora escribe el nuevo enlace.")

    if state == STATE_BUTTON_EDIT_URL:
        idx = ud.get("edit_index")
        if idx is None or idx < 0 or idx >= len(draft["buttons"]):
            ud[STATE_KEY] = STATE_MAIN_MENU
            return await msg.reply_text("Error de índice.")
        draft["buttons"][idx]["url"] = text.strip()
        ud["edit_index"] = None
        ud[STATE_KEY] = STATE_MAIN_MENU
        await msg.reply_text("Botón actualizado.")
        return await send_preview(update, context, "Vista previa después de editar el botón:")

    if state == STATE_BUTTON_DELETE_SELECT:
        try:
            idx = int(text.strip())
        except ValueError:
            return await msg.reply_text("Escribe un número válido.")
        if idx < 1 or idx > len(draft["buttons"]):
            return await msg.reply_text("Número fuera de rango.")
        eliminado = draft["buttons"].pop(idx - 1)
        ud[STATE_KEY] = STATE_MAIN_MENU
        await msg.reply_text(f"Botón eliminado: {eliminado['text']}")
        return await send_preview(update, context, "Vista previa después de eliminar el botón:")

    # -------- PROGRAMAR --------
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
                "⚠ No hay JobQueue disponible en este servidor.\n"
                "La publicación queda guardada. Puedes usar 'Enviar ahora'."
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
        ud[STATE_KEY] = STATE_MAIN_MENU

        await msg.reply_text(f"📅 Publicación programada para {dt.strftime('%Y-%m-%d %H:%M')}")
        return await send_preview(update, context, "Vista previa de la publicación programada:")

    # default
    await msg.reply_text("Usa el menú para gestionar tus publicaciones.")
    await send_main_menu(update, context)


# ================ ENVIAR AHORA ==================

async def send_post_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    draft = get_draft(ud)

    if not draft["text"] and not draft["file_id"]:
        return await update.effective_chat.send_message("No hay publicación en borrador.")

    kb = build_buttons_keyboard(draft["buttons"])
    t = draft["type"]
    fid = draft["file_id"]
    text = draft["text"] or ""

    if t == "photo" and fid:
        await context.bot.send_photo(chat_id=TARGET_CHAT_ID, photo=fid, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "video" and fid:
        await context.bot.send_video(chat_id=TARGET_CHAT_ID, video=fid, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "audio" and fid:
        await context.bot.send_audio(chat_id=TARGET_CHAT_ID, audio=fid, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "voice" and fid:
        await context.bot.send_voice(chat_id=TARGET_CHAT_ID, voice=fid, caption=text, reply_markup=kb, parse_mode="HTML")
    else:
        await context.bot.send_message(chat_id=TARGET_CHAT_ID, text=text, reply_markup=kb, parse_mode="HTML")

    job = ud.get(SCHEDULE_JOB_KEY)
    if job is not None:
        job.schedule_removal()
        ud[SCHEDULE_JOB_KEY] = None
        draft["scheduled_at"] = None

    await update.effective_chat.send_message("✅ Publicación enviada.")
    await send_main_menu(update, context)


# ================ JOB PROGRAMADO ==================

async def scheduled_job_send_post(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    chat_id = data["chat_id"]
    admin_id = data["admin_id"]
    t = data["type"]
    fid = data["file_id"]
    text = data["text"] or ""
    buttons = data["buttons"]

    kb = build_buttons_keyboard(buttons)

    if t == "photo" and fid:
        await context.bot.send_photo(chat_id=chat_id, photo=fid, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "video" and fid:
        await context.bot.send_video(chat_id=chat_id, video=fid, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "audio" and fid:
        await context.bot.send_audio(chat_id=chat_id, audio=fid, caption=text, reply_markup=kb, parse_mode="HTML")
    elif t == "voice" and fid:
        await context.bot.send_voice(chat_id=chat_id, voice=fid, caption=text, reply_markup=kb, parse_mode="HTML")
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb, parse_mode="HTML")

    await context.bot.send_message(chat_id=admin_id, text="✅ Publicación programada enviada correctamente.")


# ================ MAIN ==================

def main() -> None:
    app: Application = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(~filters.COMMAND, message_handler))

    app.run_polling()


if __name__ == "__main__":
    main()
