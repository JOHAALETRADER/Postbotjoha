import logging
import os
import copy
from datetime import datetime
from typing import Dict, Any, Optional, List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Estructuras en memoria
DRAFTS: Dict[int, Dict[str, Any]] = {}
DEFAULTS: Dict[int, Dict[str, Any]] = {}

ADMIN_ID: int = 0
TARGET_CHAT_ID: Any = None


def init_user_structs(user_id: int) -> None:
    if user_id not in DRAFTS:
        DRAFTS[user_id] = {
            "type": None,
            "file_id": None,
            "text": "",
            "buttons": [],
            "scheduled_at": None,
            "job": None,
        }
    if user_id not in DEFAULTS:
        DEFAULTS[user_id] = {
            "buttons": [],
            "template_text": "",
        }


def draft_has_content(draft: Dict[str, Any]) -> bool:
    if draft is None:
        return False
    if draft.get("type"):
        return True
    text = draft.get("text") or ""
    return text.strip() != ""


def build_main_menu_text(user_id: int) -> str:
    draft = DRAFTS.get(user_id)
    defaults = DEFAULTS.get(user_id, {"buttons": [], "template_text": ""})

    if not draft:
        resumen = "(Sin publicación)"
        botones_count = 0
        prog = "Sin programación"
    else:
        text = draft.get("text") or ""
        text = text.strip()
        if not text and not draft.get("type"):
            resumen = "(Sin publicación)"
        else:
            if len(text) > 300:
                resumen = text[:300] + "..."
            else:
                resumen = text if text else "(Publicación sin texto)"
        botones_count = len(draft.get("buttons") or [])
        if draft.get("scheduled_at"):
            prog = draft["scheduled_at"].strftime("%Y-%m-%d %H:%M")
        else:
            prog = "Sin programación"

    has_default_buttons = bool(defaults.get("buttons"))
    has_template = bool((defaults.get("template_text") or "").strip())

    text_menu = (
        "Borrador actual:\n"
        "{resumen}\n\n"
        "Botones: {botones}\n"
        "Botones predeterminados: {pred}\n"
        "Plantilla recurrente: {plantilla}\n"
        "Programación: {prog}\n"
    ).format(
        resumen=resumen,
        botones=botones_count,
        pred="Sí" if has_default_buttons else "No",
        plantilla="Sí" if has_template else "No",
        prog=prog,
    )
    return text_menu


def build_main_menu_keyboard() -> List[List[InlineKeyboardButton]]:
    keyboard = [
        [
            InlineKeyboardButton("✏️ Crear / cambiar publicación", callback_data="MENU_CREATE"),
            InlineKeyboardButton("🔗 Botones", callback_data="MENU_BUTTONS"),
        ],
        [
            InlineKeyboardButton("⏰ Programar", callback_data="MENU_SCHEDULE"),
            InlineKeyboardButton("📤 Enviar ahora", callback_data="MENU_SEND_NOW"),
        ],
        [
            InlineKeyboardButton("✏️ Editar publicación", callback_data="MENU_EDIT"),
            InlineKeyboardButton("📄 Plantillas", callback_data="MENU_TEMPLATES"),
        ],
        [
            InlineKeyboardButton("❌ Cancelar borrador", callback_data="MENU_CANCEL_DRAFT"),
        ],
    ]
    return keyboard


async def send_main_menu_simple(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int
) -> None:
    text_menu = build_main_menu_text(user_id)
    keyboard = build_main_menu_keyboard()
    await context.bot.send_message(
        chat_id=chat_id,
        text=text_menu,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


def is_admin_private(update: Update) -> bool:
    if update.effective_user is None or update.effective_chat is None:
        return False

    user_id = update.effective_user.id
    chat = update.effective_chat

    if chat.type != "private" or user_id != ADMIN_ID:
        try:
            text = "Bot privado. No tienes permiso para usar este bot."
            if update.message:
                update.message.reply_text(text)  # type: ignore[union-attr]
            elif update.callback_query:
                update.callback_query.answer(text, show_alert=True)  # type: ignore[union-attr]
            else:
                chat.send_message(text=text)
        except Exception:
            pass
        return False
    return True


def get_draft(user_id: int) -> Dict[str, Any]:
    init_user_structs(user_id)
    return DRAFTS[user_id]


def get_defaults(user_id: int) -> Dict[str, Any]:
    init_user_structs(user_id)
    return DEFAULTS[user_id]


async def send_draft_preview(
    user_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE
) -> None:
    draft = get_draft(user_id)
    if not draft_has_content(draft):
        await context.bot.send_message(chat_id=chat_id, text="(Sin publicación para vista previa)")
        return

    buttons = draft.get("buttons") or []
    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
    text = draft.get("text") or ""
    content_type = draft.get("type")
    file_id = draft.get("file_id")

    if content_type == "photo" and file_id:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=file_id,
            caption=text,
            reply_markup=reply_markup,
        )
    elif content_type == "video" and file_id:
        await context.bot.send_video(
            chat_id=chat_id,
            video=file_id,
            caption=text,
            reply_markup=reply_markup,
        )
    elif content_type == "voice" and file_id:
        await context.bot.send_voice(
            chat_id=chat_id,
            voice=file_id,
            caption=text,
            reply_markup=reply_markup,
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text if text else "(Publicación sin texto)",
            reply_markup=reply_markup,
        )


async def send_publication_to_target(
    draft: Dict[str, Any],
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not draft_has_content(draft):
        return

    buttons = draft.get("buttons") or []
    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
    text = draft.get("text") or ""
    content_type = draft.get("type")
    file_id = draft.get("file_id")

    if content_type == "photo" and file_id:
        await context.bot.send_photo(
            chat_id=TARGET_CHAT_ID,
            photo=file_id,
            caption=text,
            reply_markup=reply_markup,
        )
    elif content_type == "video" and file_id:
        await context.bot.send_video(
            chat_id=TARGET_CHAT_ID,
            video=file_id,
            caption=text,
            reply_markup=reply_markup,
        )
    elif content_type == "voice" and file_id:
        await context.bot.send_voice(
            chat_id=TARGET_CHAT_ID,
            voice=file_id,
            caption=text,
            reply_markup=reply_markup,
        )
    else:
        await context.bot.send_message(
            chat_id=TARGET_CHAT_ID,
            text=text if text else "(Publicación sin texto)",
            reply_markup=reply_markup,
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin_private(update):
        return

    user_id = update.effective_user.id  # type: ignore[union-attr]
    chat_id = update.effective_chat.id  # type: ignore[union-attr]

    init_user_structs(user_id)
    context.user_data.clear()
    await send_main_menu_simple(context, chat_id, user_id)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    if not is_admin_private(update):
        return

    user_id = update.effective_user.id  # type: ignore[union-attr]
    chat_id = update.effective_chat.id  # type: ignore[union-attr]

    init_user_structs(user_id)
    data = query.data or ""

    if data == "MENU_CREATE":
        context.user_data["state"] = "AWAITING_NEW_PUBLICATION_MESSAGE"
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Envía ahora la publicación como si fueras a enviarla al canal "
                "(puede ser foto+texto, video+texto, nota de voz o solo texto)."
            ),
        )

    elif data == "MENU_BUTTONS" or data == "ADD_BUTTONS_AFTER_NEW":
        defaults = get_defaults(user_id)
        if defaults.get("buttons"):
            keyboard = [
                [
                    InlineKeyboardButton(
                        "🟢 Usar botones predeterminados",
                        callback_data="BUTTONS_USE_DEFAULT",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "✏️ Crear nuevos botones",
                        callback_data="BUTTONS_CREATE_NEW",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Volver al menú",
                        callback_data="BACK_TO_MENU",
                    )
                ],
            ]
            await context.bot.send_message(
                chat_id=chat_id,
                text="Elige una opción para los botones:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            context.user_data["state"] = "AWAITING_NEW_BUTTONS_TEXT"
            context.user_data["buttons_mode"] = "CREATE"
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Envía todos los botones en un solo mensaje, uno por línea, "
                    'con el formato "Texto del botón - URL".'
                ),
            )

    elif data == "BUTTONS_USE_DEFAULT":
        defaults = get_defaults(user_id)
        draft = get_draft(user_id)
        if not defaults.get("buttons"):
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay botones predeterminados guardados.",
            )
        else:
            draft["buttons"] = copy.deepcopy(defaults["buttons"])
            await context.bot.send_message(
                chat_id=chat_id,
                text="Botones predeterminados aplicados al borrador.",
            )
            await send_draft_preview(user_id, chat_id, context)
        await send_main_menu_simple(context, chat_id, user_id)

    elif data == "BUTTONS_CREATE_NEW":
        context.user_data["state"] = "AWAITING_NEW_BUTTONS_TEXT"
        context.user_data["buttons_mode"] = "CREATE"
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Envía todos los botones en un solo mensaje, uno por línea, "
                'con el formato "Texto del botón - URL".'
            ),
        )

    elif data == "SAVE_BUTTONS_YES":
        draft = get_draft(user_id)
        defaults = get_defaults(user_id)
        defaults["buttons"] = copy.deepcopy(draft.get("buttons") or [])
        context.user_data["state"] = None
        context.user_data.pop("buttons_mode", None)
        await context.bot.send_message(
            chat_id=chat_id,
            text="Botones guardados como predeterminados.",
        )
        await send_main_menu_simple(context, chat_id, user_id)

    elif data == "SAVE_BUTTONS_NO":
        context.user_data["state"] = None
        context.user_data.pop("buttons_mode", None)
        await context.bot.send_message(
            chat_id=chat_id,
            text="Botones usados solo en este borrador.",
        )
        await send_main_menu_simple(context, chat_id, user_id)

    elif data == "MENU_SCHEDULE":
        draft = get_draft(user_id)
        if not draft_has_content(draft):
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay borrador actual para programar.",
            )
        else:
            context.user_data["state"] = "AWAITING_SCHEDULE_DATETIME"
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Introduce la fecha y hora en formato AAAA-MM-DD HH:MM\n"
                    "Ejemplo: 2025-12-31 18:30"
                ),
            )

    elif data == "MENU_SEND_NOW":
        draft = get_draft(user_id)
        if not draft_has_content(draft):
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay borrador actual para enviar.",
            )
        else:
            if draft.get("job") is not None:
                try:
                    draft["job"].schedule_removal()
                except Exception:
                    pass
                draft["job"] = None
                draft["scheduled_at"] = None

            await send_publication_to_target(draft, context)
            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ Publicación enviada al canal.",
            )
        await send_main_menu_simple(context, chat_id, user_id)

    elif data == "MENU_EDIT":
        draft = get_draft(user_id)
        if not draft_has_content(draft):
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay borrador para editar.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
        else:
            keyboard = [
                [
                    InlineKeyboardButton(
                        "✏️ Editar texto",
                        callback_data="EDIT_TEXT",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔗 Editar botones",
                        callback_data="EDIT_BUTTONS",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🖼 Cambiar media",
                        callback_data="EDIT_MEDIA",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Volver al menú",
                        callback_data="BACK_TO_MENU",
                    )
                ],
            ]
            await context.bot.send_message(
                chat_id=chat_id,
                text="Elige qué parte de la publicación quieres editar:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    elif data == "EDIT_TEXT":
        draft = get_draft(user_id)
        if not draft_has_content(draft):
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay borrador para editar el texto.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
        else:
            context.user_data["state"] = "AWAITING_EDIT_TEXT"
            await context.bot.send_message(
                chat_id=chat_id,
                text="Envía ahora el nuevo texto de la publicación.",
            )

    elif data == "EDIT_BUTTONS":
        draft = get_draft(user_id)
        if not draft_has_content(draft):
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay borrador para editar los botones.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
        else:
            context.user_data["state"] = "AWAITING_EDIT_BUTTONS_TEXT"
            context.user_data["buttons_mode"] = "EDIT"
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Envía todos los botones en un solo mensaje, uno por línea, "
                    'con el formato "Texto del botón - URL".'
                ),
            )

    elif data == "EDIT_MEDIA":
        draft = get_draft(user_id)
        if not draft_has_content(draft):
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay borrador para cambiar la media.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
        else:
            context.user_data["state"] = "AWAITING_NEW_MEDIA"
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Envía ahora la nueva media (foto, video o nota de voz). "
                    "Si no envías texto, se conservará el texto actual."
                ),
            )

    elif data == "MENU_TEMPLATES":
        keyboard = [
            [
                InlineKeyboardButton(
                    "💾 Guardar borrador como plantilla",
                    callback_data="TEMPLATE_SAVE",
                )
            ],
            [
                InlineKeyboardButton(
                    "📥 Insertar plantilla en borrador",
                    callback_data="TEMPLATE_INSERT",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Volver al menú",
                    callback_data="BACK_TO_MENU",
                )
            ],
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text="Opciones de plantillas:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "TEMPLATE_SAVE":
        draft = get_draft(user_id)
        if not draft.get("text"):
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay texto en el borrador para guardar como plantilla.",
            )
        else:
            defaults = get_defaults(user_id)
            defaults["template_text"] = draft["text"]
            await context.bot.send_message(
                chat_id=chat_id,
                text="Plantilla guardada correctamente.",
            )
        await send_main_menu_simple(context, chat_id, user_id)

    elif data == "TEMPLATE_INSERT":
        defaults = get_defaults(user_id)
        template_text = defaults.get("template_text") or ""
        if not template_text.strip():
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay plantilla guardada para insertar.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
        else:
            draft = get_draft(user_id)
            existing_text = draft.get("text") or ""
            if not draft_has_content(draft):
                draft["type"] = "text"
                draft["file_id"] = None
                draft["text"] = template_text
            else:
                if existing_text.strip():
                    draft["text"] = existing_text + "\n\n" + template_text
                else:
                    draft["text"] = template_text
            await context.bot.send_message(
                chat_id=chat_id,
                text="Plantilla insertada en el borrador.",
            )
            await send_draft_preview(user_id, chat_id, context)
            await send_main_menu_simple(context, chat_id, user_id)

    elif data == "MENU_CANCEL_DRAFT":
        keyboard = [
            [
                InlineKeyboardButton(
                    "Sí, cancelar borrador",
                    callback_data="CONFIRM_CANCEL_DRAFT",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Volver al menú",
                    callback_data="BACK_TO_MENU",
                )
            ],
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text="¿Seguro que quieres cancelar y borrar el borrador actual?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "CONFIRM_CANCEL_DRAFT":
        draft = get_draft(user_id)
        if draft.get("job") is not None:
            try:
                draft["job"].schedule_removal()
            except Exception:
                pass
        DRAFTS[user_id] = {
            "type": None,
            "file_id": None,
            "text": "",
            "buttons": [],
            "scheduled_at": None,
            "job": None,
        }
        context.user_data.clear()
        await context.bot.send_message(
            chat_id=chat_id,
            text="Borrador cancelado.",
        )
        await send_main_menu_simple(context, chat_id, user_id)

    elif data == "BACK_TO_MENU":
        context.user_data["state"] = None
        context.user_data.pop("buttons_mode", None)
        await send_main_menu_simple(context, chat_id, user_id)

    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Opción no reconocida.",
        )
        await send_main_menu_simple(context, chat_id, user_id)


def parse_buttons_from_text(text: str) -> List[List[InlineKeyboardButton]]:
    lines = (text or "").splitlines()
    rows: List[List[InlineKeyboardButton]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "-" not in line:
            continue
        parts = line.split("-", 1)
        label = parts[0].strip()
        url = parts[1].strip()
        if not label or not url:
            continue
        button = InlineKeyboardButton(label, url=url)
        rows.append([button])
    return rows


async def handle_new_publication_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    if message is None:
        return

    user_id = update.effective_user.id  # type: ignore[union-attr]
    chat_id = update.effective_chat.id  # type: ignore[union-attr]
    draft = get_draft(user_id)

    content_type: Optional[str] = None
    file_id: Optional[str] = None
    text: str = ""

    if message.photo:
        content_type = "photo"
        file_id = message.photo[-1].file_id
        text = message.caption or ""
    elif message.video:
        content_type = "video"
        file_id = message.video.file_id
        text = message.caption or ""
    elif message.voice:
        content_type = "voice"
        file_id = message.voice.file_id
        text = message.caption or ""
    elif message.text:
        content_type = "text"
        file_id = None
        text = message.text
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Tipo de mensaje no soportado. Envía foto, video, nota de voz o texto.",
        )
        return

    draft["type"] = content_type
    draft["file_id"] = file_id
    draft["text"] = text

    context.user_data["state"] = None

    await context.bot.send_message(
        chat_id=chat_id,
        text="Publicación guardada en el borrador.",
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "➕ Añadir / editar botones",
                callback_data="ADD_BUTTONS_AFTER_NEW",
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Volver al menú",
                callback_data="BACK_TO_MENU",
            )
        ],
    ]
    await context.bot.send_message(
        chat_id=chat_id,
        text="¿Quieres añadir botones a esta publicación?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_new_buttons_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    if message is None:
        return

    user_id = update.effective_user.id  # type: ignore[union-attr]
    chat_id = update.effective_chat.id  # type: ignore[union-attr]
    draft = get_draft(user_id)

    text = message.text or ""
    rows = parse_buttons_from_text(text)
    if not rows:
        await context.bot.send_message(
            chat_id=chat_id,
            text="No se encontraron botones válidos. Revisa el formato.",
        )
        return

    draft["buttons"] = rows

    await context.bot.send_message(
        chat_id=chat_id,
        text="Botones actualizados en el borrador.",
    )
    # ÚNICA vista previa completa después de definir botones
    await send_draft_preview(user_id, chat_id, context)

    context.user_data["state"] = "AWAITING_SAVE_DEFAULT_BUTTONS_CHOICE"
    keyboard = [
        [
            InlineKeyboardButton(
                "Sí, guardar como predeterminados",
                callback_data="SAVE_BUTTONS_YES",
            )
        ],
        [
            InlineKeyboardButton(
                "No, solo usar en este borrador",
                callback_data="SAVE_BUTTONS_NO",
            )
        ],
    ]
    await context.bot.send_message(
        chat_id=chat_id,
        text="¿Quieres guardar estos botones como predeterminados?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_schedule_datetime(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    if message is None or not message.text:
        return

    user_id = update.effective_user.id  # type: ignore[union-attr]
    chat_id = update.effective_chat.id  # type: ignore[union-attr]
    draft = get_draft(user_id)
    text = message.text.strip()

    try:
        scheduled_dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Formato inválido. Usa AAAA-MM-DD HH:MM (ejemplo: 2025-12-31 18:30).",
        )
        return

    now = datetime.now()
    delta = (scheduled_dt - now).total_seconds()

    # Permitimos pequeños desfases de reloj; solo rechazamos si está claramente en el pasado
    if delta <= -60:
        await context.bot.send_message(
            chat_id=chat_id,
            text="La fecha y hora deben ser futuras.",
        )
        return

    delay = max(delta, 1.0)

    if draft.get("job") is not None:
        try:
            draft["job"].schedule_removal()
        except Exception:
            pass
        draft["job"] = None

    job = context.application.job_queue.run_once(
        send_scheduled_publication,
        delay,
        data={"user_id": user_id},
    )

    draft["scheduled_at"] = scheduled_dt
    draft["job"] = job
    context.user_data["state"] = None

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "✅ Publicación programada para "
            f"{scheduled_dt.strftime('%Y-%m-%d %H:%M')}."
        ),
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "⬅️ Volver al menú",
                callback_data="BACK_TO_MENU",
            )
        ]
    ]
    await context.bot.send_message(
        chat_id=chat_id,
        text="Puedes volver al menú cuando quieras.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_edit_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    if message is None or message.text is None:
        return

    user_id = update.effective_user.id  # type: ignore[union-attr]
    chat_id = update.effective_chat.id  # type: ignore[union-attr]
    draft = get_draft(user_id)

    draft["text"] = message.text
    context.user_data["state"] = None

    await context.bot.send_message(
        chat_id=chat_id,
        text="Texto del borrador actualizado.",
    )
    await send_draft_preview(user_id, chat_id, context)
    await send_main_menu_simple(context, chat_id, user_id)


async def handle_new_media(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    if message is None:
        return

    user_id = update.effective_user.id  # type: ignore[union-attr]
    chat_id = update.effective_chat.id  # type: ignore[union-attr]
    draft = get_draft(user_id)

    content_type: Optional[str] = None
    file_id: Optional[str] = None
    new_text: Optional[str] = None

    if message.photo:
        content_type = "photo"
        file_id = message.photo[-1].file_id
        new_text = message.caption
    elif message.video:
        content_type = "video"
        file_id = message.video.file_id
        new_text = message.caption
    elif message.voice:
        content_type = "voice"
        file_id = message.voice.file_id
        new_text = message.caption
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Debes enviar foto, video o nota de voz para cambiar la media.",
        )
        return

    draft["type"] = content_type
    draft["file_id"] = file_id

    if new_text is not None and new_text.strip() != "":
        draft["text"] = new_text

    context.user_data["state"] = None

    await context.bot.send_message(
        chat_id=chat_id,
        text="Media del borrador actualizada.",
    )
    await send_draft_preview(user_id, chat_id, context)
    await send_main_menu_simple(context, chat_id, user_id)


async def send_scheduled_publication(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if job is None:
        return
    data = job.data or {}
    user_id = data.get("user_id")
    if user_id is None:
        return

    draft = DRAFTS.get(user_id)
    if not draft_has_content(draft or {}):
        return

    try:
        await send_publication_to_target(draft, context)  # type: ignore[arg-type]
        draft["scheduled_at"] = None
        draft["job"] = None
        await context.bot.send_message(
            chat_id=user_id,
            text="✅ Publicación programada enviada correctamente al canal.",
        )
    except Exception as exc:
        logging.error("Error enviando publicación programada: %s", exc)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin_private(update):
        return

    if update.message is None:
        return

    user_id = update.effective_user.id  # type: ignore[union-attr]
    chat_id = update.effective_chat.id  # type: ignore[union-attr]

    init_user_structs(user_id)
    state = context.user_data.get("state")

    if state == "AWAITING_NEW_PUBLICATION_MESSAGE":
        await handle_new_publication_message(update, context)
    elif state in ("AWAITING_NEW_BUTTONS_TEXT", "AWAITING_EDIT_BUTTONS_TEXT"):
        await handle_new_buttons_text(update, context)
    elif state == "AWAITING_SCHEDULE_DATETIME":
        await handle_schedule_datetime(update, context)
    elif state == "AWAITING_EDIT_TEXT":
        await handle_edit_text(update, context)
    elif state == "AWAITING_NEW_MEDIA":
        await handle_new_media(update, context)
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Usa el menú para gestionar la publicación.",
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error("Excepción en el manejador", exc_info=context.error)


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    token = os.getenv("BOT_TOKEN")
    admin_id_str = os.getenv("ADMIN_ID")
    target_chat = os.getenv("TARGET_CHAT_ID")

    if not token or not admin_id_str or not target_chat:
        raise RuntimeError(
            "Faltan variables de entorno: BOT_TOKEN, ADMIN_ID o TARGET_CHAT_ID."
        )

    global ADMIN_ID, TARGET_CHAT_ID
    try:
        ADMIN_ID = int(admin_id_str)
    except ValueError:
        raise RuntimeError("ADMIN_ID debe ser un número entero válido.")

    TARGET_CHAT_ID = target_chat

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(on_button))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, on_message))
    application.add_error_handler(error_handler)

    application.run_polling()


if __name__ == "__main__":
    main()
