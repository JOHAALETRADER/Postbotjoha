import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# ===================== CONFIGURACIÓN BÁSICA =====================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "5958164558"))
# Donde se mandan las publicaciones (puede ser canal, grupo o tu propio chat)
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", str(ADMIN_ID)))

if not BOT_TOKEN:
    raise RuntimeError("Falta la variable de entorno BOT_TOKEN")

# ===================== LOGGING =====================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ===================== CLAVES USER_DATA =====================

DRAFT_KEY = "draft"          # dict con texto, botones, fecha
STATE_KEY = "state"          # estado actual
TEMP_BUTTON_KEY = "temp_btn" # datos temporales para añadir / editar botón
SCHEDULE_JOB_KEY = "schedule_job"  # referencia a job programado

# ===================== ESTADOS POSIBLES =====================

STATE_MAIN_MENU = "MAIN_MENU"
STATE_WAITING_TEXT = "WAITING_TEXT"
STATE_BUTTON_MENU = "BUTTON_MENU"
STATE_BUTTON_ADD_TEXT = "BUTTON_ADD_TEXT"
STATE_BUTTON_ADD_URL = "BUTTON_ADD_URL"
STATE_BUTTON_EDIT_SELECT = "BUTTON_EDIT_SELECT"
STATE_BUTTON_EDIT_NEW_TEXT = "BUTTON_EDIT_NEW_TEXT"
STATE_BUTTON_EDIT_NEW_URL = "BUTTON_EDIT_NEW_URL"
STATE_BUTTON_DELETE_SELECT = "STATE_BUTTON_DELETE_SELECT"
STATE_WAITING_SCHEDULE = "WAITING_SCHEDULE"


# ===================== UTILIDADES DE BORRADOR =====================

def get_draft(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Asegura que exista un borrador en user_data.
    """
    draft = user_data.get(DRAFT_KEY)
    if draft is None:
        draft = {
            "text": None,
            "buttons": [],      # lista de dicts: {"text": "...", "url": "..."}
            "scheduled_at": None,  # datetime o None
        }
        user_data[DRAFT_KEY] = draft
    return draft


def build_buttons_keyboard(buttons: List[Dict[str, str]]) -> InlineKeyboardMarkup:
    """
    Construye un InlineKeyboardMarkup a partir de la lista de botones del borrador.
    Se colocan 2 botones por fila.
    """
    rows = []
    temp_row = []
    for idx, btn in enumerate(buttons):
        temp_row.append(
            InlineKeyboardButton(btn["text"], url=btn["url"])
        )
        if len(temp_row) == 2:
            rows.append(temp_row)
            temp_row = []
    if temp_row:
        rows.append(temp_row)
    return InlineKeyboardMarkup(rows) if rows else None


def format_buttons_list(buttons: List[Dict[str, str]]) -> str:
    """
    Devuelve un texto con el listado de botones actuales numerados.
    """
    if not buttons:
        return "No hay botones añadidos todavía."
    lines = []
    for idx, btn in enumerate(buttons, start=1):
        line = "{idx}. {text} → {url}".format(
            idx=idx,
            text=btn["text"],
            url=btn["url"],
        )
        lines.append(line)
    return "\n".join(lines)


def format_schedule_info(scheduled_at: Optional[datetime]) -> str:
    if scheduled_at is None:
        return "Sin programación."
    return "Programado para: {dt}".format(
        dt=scheduled_at.strftime("%Y-%m-%d %H:%M")
    )


# ===================== MENÚ PRINCIPAL Y PREVISUALIZACIÓN =====================

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Envía el menú principal al admin.
    """
    user_data = context.user_data
    user_data[STATE_KEY] = STATE_MAIN_MENU
    draft = get_draft(user_data)

    keyboard = [
        [
            InlineKeyboardButton("📝 Crear / cambiar texto", callback_data="MENU_CREATE_TEXT"),
        ],
        [
            InlineKeyboardButton("🔗 Botones", callback_data="MENU_BUTTONS"),
        ],
        [
            InlineKeyboardButton("⏰ Programar envío", callback_data="MENU_SCHEDULE"),
        ],
        [
            InlineKeyboardButton("📤 Enviar ahora", callback_data="MENU_SEND_NOW"),
        ],
        [
            InlineKeyboardButton("🧹 Limpiar borrador", callback_data="MENU_CLEAR"),
        ],
        [
            InlineKeyboardButton("👀 Ver previsualización", callback_data="MENU_PREVIEW"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text_info = draft["text"] if draft["text"] else "(Sin texto aún)"
    buttons_info = format_buttons_list(draft["buttons"])
    schedule_info = format_schedule_info(draft["scheduled_at"])

    menu_text = (
        "📌 *BOT AVANZADO – OPCIÓN A*\n\n"
        "*Texto actual:*\n"
        "{text}\n\n"
        "*Botones:*\n"
        "{buttons}\n\n"
        "*Programación:*\n"
        "{schedule}"
    ).format(
        text=text_info,
        buttons=buttons_info,
        schedule=schedule_info,
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=menu_text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
    else:
        await update.effective_chat.send_message(
            text=menu_text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )


async def send_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Envía previsualización del borrador al admin.
    """
    user_data = context.user_data
    draft = get_draft(user_data)

    text = draft["text"] or "Sin texto aún."
    buttons_keyboard = build_buttons_keyboard(draft["buttons"])

    if update.callback_query:
        await update.callback_query.answer()
        await update.effective_chat.send_message(
            text="📎 Previsualización de la publicación:",
        )
        await update.effective_chat.send_message(
            text=text,
            reply_markup=buttons_keyboard,
            parse_mode="HTML",
        )
    else:
        await update.effective_chat.send_message(
            text="📎 Previsualización de la publicación:",
        )
        await update.effective_chat.send_message(
            text=text,
            reply_markup=buttons_keyboard,
            parse_mode="HTML",
        )


# ===================== /START =====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("Este bot es de uso privado.")
        return
    get_draft(context.user_data)  # inicializa borrador
    await send_main_menu(update, context)


# ===================== HANDLER DE MENÚ (BOTONES INLINE) =====================

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_data = context.user_data
    draft = get_draft(user_data)

    if update.effective_user.id != ADMIN_ID:
        await query.edit_message_text("No estás autorizado para usar este bot.")
        return

    if data == "MENU_CREATE_TEXT":
        user_data[STATE_KEY] = STATE_WAITING_TEXT
        await query.edit_message_text(
            "Envía el texto de la publicación.\n\n"
            "Puedes usar formato HTML simple (por ejemplo <b>negrita</b>, <i>cursiva</i>)."
        )
        return

    if data == "MENU_BUTTONS":
        user_data[STATE_KEY] = STATE_BUTTON_MENU
        buttons_info = format_buttons_list(draft["buttons"])
        keyboard = [
            [
                InlineKeyboardButton("➕ Añadir botón", callback_data="BTN_ADD"),
            ],
            [
                InlineKeyboardButton("✏️ Editar botón", callback_data="BTN_EDIT"),
            ],
            [
                InlineKeyboardButton("🗑️ Eliminar botón", callback_data="BTN_DELETE"),
            ],
            [
                InlineKeyboardButton("⬅️ Volver al menú", callback_data="BTN_BACK_MENU"),
            ],
        ]
        await query.edit_message_text(
            text="*Botones actuales:*\n{info}".format(info=buttons_info),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return

    if data == "MENU_SCHEDULE":
        user_data[STATE_KEY] = STATE_WAITING_SCHEDULE
        await query.edit_message_text(
            "Escribe la fecha y hora para enviar la publicación.\n\n"
            "Formato: AAAA-MM-DD HH:MM\n"
            "Ejemplo: 2025-12-03 21:30"
        )
        return

    if data == "MENU_SEND_NOW":
        await send_post_now(update, context)
        return

    if data == "MENU_CLEAR":
        # cancelar programación si existe
        job = user_data.get(SCHEDULE_JOB_KEY)
        if job is not None:
            job.schedule_removal()
            user_data[SCHEDULE_JOB_KEY] = None

        user_data[DRAFT_KEY] = {
            "text": None,
            "buttons": [],
            "scheduled_at": None,
        }
        await query.edit_message_text("Borrador limpiado.")
        await send_main_menu(update, context)
        return

    if data == "MENU_PREVIEW":
        await send_preview(update, context)
        return

    # ---- SUBMENÚ BOTONES ----

    if data == "BTN_BACK_MENU":
        await send_main_menu(update, context)
        return

    if data == "BTN_ADD":
        user_data[STATE_KEY] = STATE_BUTTON_ADD_TEXT
        user_data[TEMP_BUTTON_KEY] = {}
        await query.edit_message_text("Escribe el texto del nuevo botón.")
        return

    if data == "BTN_EDIT":
        if not draft["buttons"]:
            await query.edit_message_text(
                "No hay botones para editar.\n\n"
                "Primero añade alguno."
            )
            await send_main_menu(update, context)
            return
        user_data[STATE_KEY] = STATE_BUTTON_EDIT_SELECT
        buttons_info = format_buttons_list(draft["buttons"])
        await query.edit_message_text(
            "Escribe el número del botón que quieres editar:\n\n{info}".format(
                info=buttons_info
            )
        )
        return

    if data == "BTN_DELETE":
        if not draft["buttons"]:
            await query.edit_message_text(
                "No hay botones para eliminar.\n\n"
                "Primero añade alguno."
            )
            await send_main_menu(update, context)
            return
        user_data[STATE_KEY] = STATE_BUTTON_DELETE_SELECT
        buttons_info = format_buttons_list(draft["buttons"])
        await query.edit_message_text(
            "Escribe el número del botón que quieres eliminar:\n\n{info}".format(
                info=buttons_info
            )
        )
        return


# ===================== MANEJO DE MENSAJES (SEGÚN ESTADO) =====================

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id != ADMIN_ID:
        # Ignorar mensajes de otros usuarios
        return

    user_data = context.user_data
    state = user_data.get(STATE_KEY, STATE_MAIN_MENU)
    draft = get_draft(user_data)
    text = update.message.text.strip()

    # ---- ESTADO: ESPERANDO TEXTO DEL POST ----
    if state == STATE_WAITING_TEXT:
        draft["text"] = text
        # No tocamos programación ni botones
        await update.message.reply_text("Texto actualizado.")
        await send_preview(update, context)
        await send_main_menu(update, context)
        return

    # ---- ESTADO: AÑADIR BOTÓN (TEXTO) ----
    if state == STATE_BUTTON_ADD_TEXT:
        temp_btn = user_data.get(TEMP_BUTTON_KEY, {})
        temp_btn["text"] = text
        user_data[TEMP_BUTTON_KEY] = temp_btn
        user_data[STATE_KEY] = STATE_BUTTON_ADD_URL
        await update.message.reply_text(
            "Ahora escribe el enlace del botón."
        )
        return

    # ---- ESTADO: AÑADIR BOTÓN (URL) ----
    if state == STATE_BUTTON_ADD_URL:
        temp_btn = user_data.get(TEMP_BUTTON_KEY, {})
        btn_text = temp_btn.get("text")
        btn_url = text

        if not btn_text:
            await update.message.reply_text(
                "Ocurrió un problema con el texto del botón. Vuelve a intentarlo."
            )
            user_data[STATE_KEY] = STATE_BUTTON_ADD_TEXT
            return

        draft["buttons"].append(
            {
                "text": btn_text,
                "url": btn_url,
            }
        )
        user_data[TEMP_BUTTON_KEY] = {}
        user_data[STATE_KEY] = STATE_BUTTON_MENU

        await update.message.reply_text("Botón añadido.")
        await send_preview(update, context)
        await send_main_menu(update, context)
        return

    # ---- ESTADO: EDITAR BOTÓN (SELECCIÓN) ----
    if state == STATE_BUTTON_EDIT_SELECT:
        try:
            idx = int(text)
        except ValueError:
            await update.message.reply_text("Escribe un número válido.")
            return

        if idx < 1 or idx > len(draft["buttons"]):
            await update.message.reply_text("Número fuera de rango.")
            return

        user_data[TEMP_BUTTON_KEY] = {"index": idx - 1}
        user_data[STATE_KEY] = STATE_BUTTON_EDIT_NEW_TEXT
        await update.message.reply_text("Escribe el nuevo texto para ese botón.")
        return

    # ---- ESTADO: EDITAR BOTÓN (NUEVO TEXTO) ----
    if state == STATE_BUTTON_EDIT_NEW_TEXT:
        temp_btn = user_data.get(TEMP_BUTTON_KEY, {})
        index = temp_btn.get("index")
        if index is None or index < 0 or index >= len(draft["buttons"]):
            await update.message.reply_text(
                "Ocurrió un problema con el índice del botón. Vuelve a intentarlo."
            )
            user_data[STATE_KEY] = STATE_BUTTON_MENU
            return
        temp_btn["text"] = text
        user_data[TEMP_BUTTON_KEY] = temp_btn
        user_data[STATE_KEY] = STATE_BUTTON_EDIT_NEW_URL
        await update.message.reply_text("Ahora escribe el nuevo enlace para ese botón.")
        return

    # ---- ESTADO: EDITAR BOTÓN (NUEVA URL) ----
    if state == STATE_BUTTON_EDIT_NEW_URL:
        temp_btn = user_data.get(TEMP_BUTTON_KEY, {})
        index = temp_btn.get("index")
        new_text = temp_btn.get("text")

        if index is None or index < 0 or index >= len(draft["buttons"]):
            await update.message.reply_text(
                "Ocurrió un problema con el índice del botón. Vuelve a intentarlo."
            )
            user_data[STATE_KEY] = STATE_BUTTON_MENU
            return

        draft["buttons"][index] = {
            "text": new_text,
            "url": text,
        }
        user_data[TEMP_BUTTON_KEY] = {}
        user_data[STATE_KEY] = STATE_BUTTON_MENU

        await update.message.reply_text("Botón actualizado.")
        await send_preview(update, context)
        await send_main_menu(update, context)
        return

    # ---- ESTADO: ELIMINAR BOTÓN ----
    if state == STATE_BUTTON_DELETE_SELECT:
        try:
            idx = int(text)
        except ValueError:
            await update.message.reply_text("Escribe un número válido.")
            return

        if idx < 1 or idx > len(draft["buttons"]):
            await update.message.reply_text("Número fuera de rango.")
            return

        removed = draft["buttons"].pop(idx - 1)
        user_data[STATE_KEY] = STATE_BUTTON_MENU

        msg_removed = "Se eliminó el botón: {t}".format(t=removed["text"])
        await update.message.reply_text(msg_removed)
        await send_preview(update, context)
        await send_main_menu(update, context)
        return

    # ---- ESTADO: ESPERANDO FECHA/HORA DE PROGRAMACIÓN ----
    if state == STATE_WAITING_SCHEDULE:
        try:
            # Se interpreta en hora local del servidor
            scheduled_at = datetime.strptime(text, "%Y-%m-%d %H:%M")
        except ValueError:
            await update.message.reply_text(
                "Formato inválido.\nUsa: AAAA-MM-DD HH:MM\nEjemplo: 2025-12-03 21:30"
            )
            return

        draft["scheduled_at"] = scheduled_at

        # Cancelar programación previa si existía
        old_job = user_data.get(SCHEDULE_JOB_KEY)
        if old_job is not None:
            old_job.schedule_removal()

        # Programar nuevo job
        job_queue = context.job_queue
        job = job_queue.run_once(
            callback=scheduled_job_send_post,
            when=scheduled_at,
            data={
                "chat_id": TARGET_CHAT_ID,
                "text": draft["text"],
                "buttons": draft["buttons"],
            },
            name="scheduled_post",
        )
        user_data[SCHEDULE_JOB_KEY] = job
        user_data[STATE_KEY] = STATE_MAIN_MENU

        msg = "Publicación programada para: {dt}".format(
            dt=scheduled_at.strftime("%Y-%m-%d %H:%M")
        )
        await update.message.reply_text(msg)
        await send_main_menu(update, context)
        return

    # Si no hay estado especial, volvemos al menú principal
    await update.message.reply_text("Usa el menú para gestionar la publicación.")
    await send_main_menu(update, context)


# ===================== ENVÍO INMEDIATO =====================

async def send_post_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    draft = get_draft(user_data)

    if not draft["text"]:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "No hay texto en el borrador. Primero crea la publicación."
            )
        else:
            await update.effective_chat.send_message(
                "No hay texto en el borrador. Primero crea la publicación."
            )
        return

    buttons_keyboard = build_buttons_keyboard(draft["buttons"])

    await context.bot.send_message(
        chat_id=TARGET_CHAT_ID,
        text=draft["text"],
        reply_markup=buttons_keyboard,
        parse_mode="HTML",
    )

    # Si había programación, la quitamos porque ya se envió
    job = user_data.get(SCHEDULE_JOB_KEY)
    if job is not None:
        job.schedule_removal()
        user_data[SCHEDULE_JOB_KEY] = None
        draft["scheduled_at"] = None

    if update.callback_query:
        await update.callback_query.edit_message_text(
            "Publicación enviada."
        )
        await send_main_menu(update, context)
    else:
        await update.effective_chat.send_message("Publicación enviada.")
        await send_main_menu(update, context)


# ===================== JOB PROGRAMADO =====================

async def scheduled_job_send_post(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    chat_id = data["chat_id"]
    text = data["text"]
    buttons = data["buttons"]

    keyboard = build_buttons_keyboard(buttons)

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# ===================== MAIN =====================

def main() -> None:
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(menu_callback))
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_message_handler,
        )
    )

    application.run_polling()


if __name__ == "__main__":
    main()
