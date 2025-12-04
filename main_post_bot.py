import os
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
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
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", str(ADMIN_ID)))

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
LAST_SENT_KEY = "last_sent"
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

# ==================== UTILIDADES DE BORRADOR ==========================


def get_draft(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Obtiene el borrador actual y lo crea si no existe.
    """
    draft = user_data.get(DRAFT_KEY)
    if draft is None:
        draft = {
            "text": None,
            "photo": None,  # file_id de la foto
            "buttons": [],  # lista de dicts: {"text": str, "url": str}
            "scheduled_at": None,  # datetime o None
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
    Crea el teclado inline a partir de la lista de botones.
    """
    if not buttons:
        return None
    rows: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for btn in buttons:
        row.append(InlineKeyboardButton(btn["text"], url=btn["url"]))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def format_buttons_list(buttons: List[Dict[str, str]]) -> str:
    if not buttons:
        return "Sin botones."
    lines = []
    for i, btn in enumerate(buttons, start=1):
        lines.append("{i}. {t} → {u}".format(i=i, t=btn["text"], u=btn["url"]))
    return "\n".join(lines)


def format_schedule_info(dt: Optional[datetime]) -> str:
    if dt is None:
        return "Sin programación."
    return dt.strftime("%Y-%m-%d %H:%M")


# ============================= MENÚ ====================================


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Muestra el menú principal.
    """
    user_data = context.user_data
    draft = get_draft(user_data)
    default_buttons = get_default_buttons(user_data)
    user_data[STATE_KEY] = STATE_MAIN_MENU

    text_preview = draft["text"] if draft["text"] else "(Sin publicación en borrador)"
    num_btns = len(draft["buttons"])
    schedule_info = format_schedule_info(draft["scheduled_at"])
    has_template = "Sí" if user_data.get(TEMPLATE_TEXT_KEY) else "No"
    has_defaults = "Sí" if default_buttons else "No"

    menu_text = (
        "📌 *POSTBOT – MENÚ PRINCIPAL*\n\n"
        "*Publicación en borrador:*\n"
        "{text}\n\n"
        "*Botones en borrador:* {num_btns}\n"
        "*Botones predeterminados:* {has_defaults}\n"
        "*Plantilla recurrente:* {has_template}\n"
        "*Programación:* {schedule}"
    ).format(
        text=text_preview,
        num_btns=num_btns,
        has_defaults=has_defaults,
        has_template=has_template,
        schedule=schedule_info,
    )

    keyboard = [
        [InlineKeyboardButton("📝 Crear publicación", callback_data="CREATE_PUBLICATION")],
        [InlineKeyboardButton("✏️ Editar publicación", callback_data="EDIT_PUBLICATION")],
        [InlineKeyboardButton("🔗 Botones", callback_data="MENU_BUTTONS")],
        [InlineKeyboardButton("🌟 Plantilla recurrente", callback_data="MENU_TEMPLATE")],
        [InlineKeyboardButton("⏰ Programar", callback_data="MENU_SCHEDULE")],
        [InlineKeyboardButton("📤 Enviar ahora", callback_data="MENU_SEND_NOW")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=menu_text, reply_markup=reply_markup, parse_mode="Markdown"
        )
    else:
        await update.effective_chat.send_message(
            text=menu_text, reply_markup=reply_markup, parse_mode="Markdown"
        )


async def send_preview(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    notify_text: Optional[str] = None,
) -> None:
    """
    Envía la vista previa automática del borrador.
    """
    user_data = context.user_data
    draft = get_draft(user_data)
    buttons_keyboard = build_buttons_keyboard(draft["buttons"])

    # mensaje introductorio
    intro = notify_text if notify_text else "📎 Vista previa de la publicación:"

    chat = update.effective_chat

    await chat.send_message(intro)

    if draft["photo"]:
        await chat.send_photo(
            photo=draft["photo"],
            caption=draft["text"] or "",
            reply_markup=buttons_keyboard,
            parse_mode="HTML",
        )
    else:
        await chat.send_message(
            text=draft["text"] or "",
            reply_markup=buttons_keyboard,
            parse_mode="HTML",
        )

    # Después de la vista previa, mostrar opciones principales de esa publicación
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


# ============================== /START =================================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("Este bot es privado.")
        return
    get_draft(context.user_data)
    get_default_buttons(context.user_data)
    await send_main_menu(update, context)


# ======================= CALLBACKS DEL MENÚ ============================


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    user_data = context.user_data

    if user.id != ADMIN_ID:
        await query.edit_message_text("No estás autorizado para usar este bot.")
        return

    draft = get_draft(user_data)
    default_buttons = get_default_buttons(user_data)

    # -------- NAVEGACIÓN GENERAL --------

    if data == "BACK_MAIN":
        await send_main_menu(update, context)
        return

    if data == "CREATE_PUBLICATION":
        # Reiniciamos solo el borrador, no los botones predeterminados
        user_data[DRAFT_KEY] = {
            "text": None,
            "photo": None,
            "buttons": [],
            "scheduled_at": None,
        }
        user_data[STATE_KEY] = STATE_WAITING_PUBLICATION
        await query.edit_message_text(
            "Crea tu publicación: envía *en un solo mensaje* el contenido.\n\n"
            "- Puedes enviar solo texto.\n"
            "- O una imagen con su texto en el pie de foto.",
            parse_mode="Markdown",
        )
        return

    if data == "EDIT_PUBLICATION":
        if not draft["text"] and not draft["photo"]:
            await query.edit_message_text(
                "No hay ninguna publicación en borrador para editar."
            )
            await send_main_menu(update, context)
            return
        # Menú simple de edición
        keyboard = [
            [InlineKeyboardButton("✏️ Editar texto", callback_data="EDIT_TEXT")],
            [InlineKeyboardButton("🖼️ Cambiar imagen", callback_data="EDIT_IMAGE")],
            [InlineKeyboardButton("🔗 Editar botones", callback_data="MENU_BUTTONS")],
            [InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_MAIN")],
        ]
        await query.edit_message_text(
            "¿Qué parte de la publicación deseas editar?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data == "EDIT_TEXT":
        user_data[STATE_KEY] = STATE_WAITING_PUBLICATION
        await query.edit_message_text(
            "Envía de nuevo la publicación completa (texto con o sin imagen).\n"
            "El borrador actual será reemplazado."
        )
        return

    if data == "EDIT_IMAGE":
        # Solo avisamos, la lógica es igual que crear publicación desde cero
        user_data[STATE_KEY] = STATE_WAITING_PUBLICATION
        await query.edit_message_text(
            "Para cambiar la imagen debo crear una nueva publicación.\n\n"
            "Envía ahora el nuevo mensaje (imagen + texto o solo texto)."
        )
        return

    if data == "MENU_BUTTONS":
        user_data[STATE_KEY] = STATE_BUTTON_MENU
        buttons_info = format_buttons_list(draft["buttons"])
        keyboard = [
            [InlineKeyboardButton("➕ Añadir botón", callback_data="BTN_ADD")],
            [InlineKeyboardButton("✏️ Editar botón", callback_data="BTN_EDIT")],
            [InlineKeyboardButton("❌ Eliminar botón", callback_data="BTN_DELETE")],
            [InlineKeyboardButton("⭐ Guardar como predeterminados", callback_data="BTN_SAVE_DEFAULT")],
            [InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_MAIN")],
        ]
        await query.edit_message_text(
            "*Botones en este borrador:*\n{info}".format(info=buttons_info),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return

    if data == "MENU_TEMPLATE":
        # Menú de plantilla recurrente
        tpl = user_data.get(TEMPLATE_TEXT_KEY)
        info = tpl if tpl else "(Sin plantilla guardada)"
        keyboard = [
            [InlineKeyboardButton("💾 Guardar texto del borrador", callback_data="TPL_SAVE")],
            [InlineKeyboardButton("📥 Insertar en borrador", callback_data="TPL_INSERT")],
            [InlineKeyboardButton("🗑️ Borrar plantilla", callback_data="TPL_CLEAR")],
            [InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_MAIN")],
        ]
        msg = "*Plantilla recurrente actual:*\n{info}".format(info=info)
        await query.edit_message_text(
            msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
        return

    if data == "TPL_SAVE":
        draft = get_draft(user_data)
        if not draft["text"]:
            await query.edit_message_text(
                "No hay texto en el borrador para guardar como plantilla."
            )
        else:
            user_data[TEMPLATE_TEXT_KEY] = draft["text"]
            await query.edit_message_text("Plantilla recurrente guardada.")
        await send_main_menu(update, context)
        return

    if data == "TPL_INSERT":
        tpl_text = user_data.get(TEMPLATE_TEXT_KEY)
        if not tpl_text:
            await query.edit_message_text("No hay plantilla guardada.")
            await send_main_menu(update, context)
            return
        draft = get_draft(user_data)
        draft["text"] = tpl_text
        await query.edit_message_text("Texto de la plantilla insertado en el borrador.")
        await send_preview(update, context, "Vista previa con la plantilla aplicada:")
        return

    if data == "TPL_CLEAR":
        user_data[TEMPLATE_TEXT_KEY] = None
        await query.edit_message_text("Plantilla recurrente eliminada.")
        await send_main_menu(update, context)
        return

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

    # ---------- FLUJOS DESDE LA VISTA PREVIA -------------

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
        # volvemos al menú de edición
        keyboard = [
            [InlineKeyboardButton("✏️ Editar texto", callback_data="EDIT_TEXT")],
            [InlineKeyboardButton("🖼️ Cambiar imagen", callback_data="EDIT_IMAGE")],
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
            "text": None,
            "photo": None,
            "buttons": [],
            "scheduled_at": None,
        }
        await query.edit_message_text("Borrador cancelado.")
        await send_main_menu(update, context)
        return

    # ---------- BOTONES PREDETERMINADOS / NUEVOS ------------

    if data == "USE_DEFAULT_BTNS":
        draft["buttons"] = list(default_buttons)
        await query.edit_message_text("Botones predeterminados aplicados al borrador.")
        await send_preview(update, context)
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

    if data == "BTN_ADD":
        user_data[STATE_KEY] = STATE_WAITING_BUTTONS
        await query.edit_message_text(
            "Envía un botón por mensaje.\n"
            "Formato: Texto - enlace\n"
            "Escribe *listo* cuando termines.",
            parse_mode="Markdown",
        )
        return

    if data == "BTN_EDIT":
        if not draft["buttons"]:
            await query.edit_message_text("No hay botones para editar.")
            await send_main_menu(update, context)
            return
        user_data[STATE_KEY] = STATE_BUTTON_EDIT_SELECT
        await query.edit_message_text(
            "Escribe el número del botón que quieres editar:\n\n{info}".format(
                info=format_buttons_list(draft["buttons"])
            )
        )
        return

    if data == "BTN_DELETE":
        if not draft["buttons"]:
            await query.edit_message_text("No hay botones para eliminar.")
            await send_main_menu(update, context)
            return
        user_data[STATE_KEY] = STATE_BUTTON_DELETE_SELECT
        await query.edit_message_text(
            "Escribe el número del botón que quieres eliminar:\n\n{info}".format(
                info=format_buttons_list(draft["buttons"])
            )
        )
        return

    if data == "BTN_SAVE_DEFAULT":
        if not draft["buttons"]:
            await query.edit_message_text(
                "No hay botones en el borrador para guardar como predeterminados."
            )
            await send_main_menu(update, context)
            return
        user_data[DEFAULT_BUTTONS_KEY] = list(draft["buttons"])
        await query.edit_message_text("Botones del borrador guardados como predeterminados.")
        await send_main_menu(update, context)
        return

    if data == "SAVE_DEFAULT_YES":
        # guardamos los botones actuales como predeterminados
        user_data[DEFAULT_BUTTONS_KEY] = list(draft["buttons"])
        await query.edit_message_text("Botones guardados como predeterminados.")
        await send_preview(update, context)
        return

    if data == "SAVE_DEFAULT_NO":
        await query.edit_message_text("Botones NO se guardaron como predeterminados.")
        await send_preview(update, context)
        return


# ======================= MANEJO DE MENSAJES ============================


def parse_button_line(line: str) -> Optional[Dict[str, str]]:
    """
    Intenta separar 'Texto - enlace' en un dict.
    """
    # Admitimos varios separadores
    for sep in [" - ", " – ", " — ", " | "]:
        if sep in line:
            parts = line.split(sep, 1)
            text = parts[0].strip()
            url = parts[1].strip()
            if text and url:
                return {"text": text, "url": url}
    return None


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id != ADMIN_ID:
        return

    user_data = context.user_data
    state = user_data.get(STATE_KEY, STATE_MAIN_MENU)
    draft = get_draft(user_data)
    default_buttons = get_default_buttons(user_data)

    message = update.message
    if message is None:
        return

    text = message.text or ""
    text_lower = text.lower().strip() if text else ""

    # -------- ESTADO: ESPERANDO PUBLICACIÓN (IMAGEN+TEXTO EN UN SOLO MENSAJE) --------
    if state == STATE_WAITING_PUBLICATION:
        photo = None
        if message.photo:
            # nos quedamos con la foto de mayor resolución
            photo = message.photo[-1].file_id
        caption = message.caption or ""
        full_text = caption if photo else text

        if not full_text and not photo:
            await message.reply_text(
                "Envía un mensaje con texto o una imagen con texto en el pie."
            )
            return

        draft["text"] = full_text
        draft["photo"] = photo
        draft["buttons"] = []

        # Si ya hay botones predeterminados, preguntar si quiere usarlos
        if default_buttons:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Usar botones guardados", callback_data="USE_DEFAULT_BTNS")
                ],
                [
                    InlineKeyboardButton("➕ Crear nuevos botones", callback_data="CREATE_NEW_BTNS")
                ],
            ]
            await message.reply_text(
                "Publicación recibida.\n\n¿Deseas usar tus botones predeterminados "
                "o crear nuevos?",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            user_data[STATE_KEY] = STATE_MAIN_MENU  # se decidirá por callback
            return
        else:
            # No hay predeterminados: pasamos directo a creación de botones
            user_data[STATE_KEY] = STATE_WAITING_BUTTONS
            await message.reply_text(
                "Publicación recibida.\n\nAhora envía los botones uno por mensaje.\n"
                "Formato: Texto - enlace\n"
                "Escribe *listo* cuando termines.",
                parse_mode="Markdown",
            )
            return

    # -------- ESTADO: ESPERANDO BOTONES --------
    if state == STATE_WAITING_BUTTONS:
        if text_lower == "listo":
            if not draft["buttons"]:
                await message.reply_text(
                    "No agregaste ningún botón. Puedes seguir añadiendo o escribir 'listo' "
                    "cuando tengas al menos uno."
                )
                return

            # Si aún no hay botones predeterminados guardados, preguntar si desea guardarlos
            if not default_buttons:
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Sí, guardar", callback_data="SAVE_DEFAULT_YES")
                    ],
                    [
                        InlineKeyboardButton("❌ No guardar", callback_data="SAVE_DEFAULT_NO")
                    ],
                ]
                user_data[STATE_KEY] = STATE_WAITING_SAVE_DEFAULT
                await message.reply_text(
                    "¿Deseas guardar estos botones como predeterminados para futuras publicaciones?",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return

            # Si ya hay predeterminados, simplemente vista previa
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
        await message.reply_text(
            "Botón añadido: {t}".format(t=btn["text"])
        )
        return

    # -------- ESTADO: ESPERANDO DECISIÓN DE GUARDAR BOTONES --------
    if state == STATE_WAITING_SAVE_DEFAULT:
        # aquí en realidad la decisión llega por callback, no por texto
        await message.reply_text(
            "Responde usando los botones de la pregunta anterior."
        )
        return

    # -------- ESTADO: EDICIÓN DE BOTONES (SELECCIONAR) --------
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
        removed = draft["buttons"].pop(idx - 1)
        user_data[STATE_KEY] = STATE_MAIN_MENU
        await message.reply_text("Botón eliminado: {t}".format(t=removed["text"]))
        await send_preview(update, context, "Vista previa después de eliminar el botón:")
        return

    # -------- ESTADO: PROGRAMACIÓN --------
    if state == STATE_WAITING_SCHEDULE:
        try:
            scheduled_at = datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            await message.reply_text(
                "Formato inválido.\nUsa: AAAA-MM-DD HH:MM\nEjemplo: 2025-12-03 21:30"
            )
            return

        draft["scheduled_at"] = scheduled_at

        # Cancelar job anterior si existía
        old_job = user_data.get(SCHEDULE_JOB_KEY)
        if old_job is not None:
            old_job.schedule_removal()

        # Crear nuevo job
        job = context.job_queue.run_once(
            scheduled_job_send_post,
            when=scheduled_at,
            data={
                "chat_id": TARGET_CHAT_ID,
                "admin_id": ADMIN_ID,
                "text": draft["text"],
                "photo": draft["photo"],
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

    # Si no hay estado especial, simplemente mostramos el menú
    await message.reply_text("Usa el menú para gestionar tus publicaciones.")
    await send_main_menu(update, context)


# ====================== ENVÍO INMEDIATO ===============================


async def send_post_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = context.user_data
    draft = get_draft(user_data)

    if not draft["text"] and not draft["photo"]:
        chat = update.effective_chat
        await chat.send_message("No hay ninguna publicación en borrador.")
        return

    buttons_keyboard = build_buttons_keyboard(draft["buttons"])

    if draft["photo"]:
        msg = await context.bot.send_photo(
            chat_id=TARGET_CHAT_ID,
            photo=draft["photo"],
            caption=draft["text"] or "",
            reply_markup=buttons_keyboard,
            parse_mode="HTML",
        )
    else:
        msg = await context.bot.send_message(
            chat_id=TARGET_CHAT_ID,
            text=draft["text"] or "",
            reply_markup=buttons_keyboard,
            parse_mode="HTML",
        )

    # Guardamos referencia por si se quiere editar más adelante
    context.user_data[LAST_SENT_KEY] = {
        "chat_id": msg.chat_id,
        "message_id": msg.message_id,
        "has_photo": bool(draft["photo"]),
    }

    # Limpia programación si existía
    job = user_data.get(SCHEDULE_JOB_KEY)
    if job is not None:
        job.schedule_removal()
        user_data[SCHEDULE_JOB_KEY] = None
        draft["scheduled_at"] = None

    chat = update.effective_chat
    await chat.send_message("✅ Publicación enviada al canal/grupo.")
    await send_main_menu(update, context)


# ==================== JOB DE PUBLICACIÓN PROGRAMADA ====================


async def scheduled_job_send_post(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data
    chat_id = data["chat_id"]
    admin_id = data["admin_id"]
    text = data["text"]
    photo = data["photo"]
    buttons = data["buttons"]

    keyboard = build_buttons_keyboard(buttons)

    if photo:
        msg = await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=text or "",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text or "",
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    # Avisar al admin
    await context.bot.send_message(
        chat_id=admin_id,
        text="✅ Publicación programada enviada correctamente.",
    )

    # Guardar última publicación para posibles ediciones
    # (en user_data del admin; aquí no tenemos user_data, pero podemos usar bot_data)
    context.bot_data[LAST_SENT_KEY] = {
        "chat_id": msg.chat_id,
        "message_id": msg.message_id,
        "has_photo": bool(photo),
    }


# ============================= MAIN ===================================


def main() -> None:
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(menu_callback))
    application.add_handler(
        MessageHandler(~filters.COMMAND, message_handler)
    )

    application.run_polling()


if __name__ == "__main__":
    main()
