import logging
import os
import copy
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List

from telegram import (
    Update,
    InputMediaPhoto,
    InputMediaVideo,
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
PENDING_ALBUMS: Dict[int, Dict[str, Any]] = {}

ADMIN_ID: int = 0
TARGET_CHAT_ID: Any = None


# --------- Utilidades de estado y estructuras ---------
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
            "templates": [],  # cada item: {"id": int, "title": str, "text": str}
        }
    else:
        if "templates" not in DEFAULTS[user_id]:
            DEFAULTS[user_id]["templates"] = []


def draft_has_content(draft: Optional[Dict[str, Any]]) -> bool:
    if not draft:
        return False
    if draft.get("type"):
        return True
    text = draft.get("text") or ""
    return text.strip() != ""


def get_draft(user_id: int) -> Dict[str, Any]:
    init_user_structs(user_id)
    return DRAFTS[user_id]


def get_defaults(user_id: int) -> Dict[str, Any]:
    init_user_structs(user_id)
    return DEFAULTS[user_id]


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


# --------- Plantillas ---------
def _make_template_title(text: str, index: int) -> str:
    """
    Genera un título corto a partir del texto de la plantilla.
    Regla: mantener emoji inicial (si lo hay) + primeras 5 palabras,
    sin pasar de ~40 caracteres, sin cortar palabras.
    """
    clean = " ".join(text.strip().split())
    if not clean:
        return f"Plantilla {index}"

    words = clean.split()
    # Tomar hasta 5 palabras
    selected_words = words[:5]
    title = " ".join(selected_words)
    if len(title) > 40:
        # Recortar respetando palabras
        shortened = []
        total = 0
        for w in selected_words:
            extra = len(w) + (1 if shortened else 0)
            if total + extra > 40:
                break
            shortened.append(w)
            total += extra
        if shortened:
            title = " ".join(shortened)
    if len(words) > 5 or len(clean) > len(title):
        title += "..."
    return title


def save_template_from_text(user_id: int, text: str) -> str:
    defaults = get_defaults(user_id)
    templates: List[Dict[str, str]] = defaults.get("templates", [])
    idx = len(templates) + 1
    title = _make_template_title(text, idx)
    templates.append({"id": idx, "title": title, "text": text})
    defaults["templates"] = templates
    return title


def get_templates(user_id: int) -> List[Dict[str, str]]:
    defaults = get_defaults(user_id)
    return defaults.get("templates", [])


# --------- Construcción de menús ---------
def build_main_menu_text(user_id: int) -> str:
    return "Menú principal:"



def build_main_menu_keyboard() -> List[List[InlineKeyboardButton]]:
    keyboard = [
        [
            InlineKeyboardButton("📝 Ver borrador actual", callback_data="SHOW_DRAFT"),
        ],
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



def build_buttons_menu_keyboard() -> List[List[InlineKeyboardButton]]:
    keyboard = [
        [
            InlineKeyboardButton("✏️ Crear nuevos botones", callback_data="BUTTONS_MENU_CREATE_NEW"),
        ],
        [
            InlineKeyboardButton("🟢 Usar botones predeterminados", callback_data="BUTTONS_MENU_USE_DEFAULT"),
        ],
        [
            InlineKeyboardButton("✏️ Editar botones existentes", callback_data="BUTTONS_MENU_EDIT_EXISTING"),
        ],
        [
            InlineKeyboardButton("🗑 Eliminar TODOS los botones", callback_data="BUTTONS_MENU_DELETE_ALL"),
        ],
        [
            InlineKeyboardButton("➖ Eliminar UN botón", callback_data="BUTTONS_MENU_DELETE_ONE"),
        ],
        [
            InlineKeyboardButton("💾 Guardar actuales como predeterminados", callback_data="BUTTONS_MENU_SAVE_DEFAULTS"),
        ],
        [
            InlineKeyboardButton("📝 Ver botones guardados", callback_data="BUTTONS_MENU_VIEW_SAVED"),
        ],
        [
            InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_TO_MENU"),
        ],
    ]
    return keyboard


def build_final_action_keyboard() -> List[List[InlineKeyboardButton]]:
    keyboard = [
        [
            InlineKeyboardButton("📤 Enviar ahora", callback_data="MENU_SEND_NOW"),
            InlineKeyboardButton("⏰ Programar", callback_data="MENU_SCHEDULE"),
        ],
        [
            InlineKeyboardButton("✏️ Editar publicación", callback_data="MENU_EDIT"),
        ],
        [
            InlineKeyboardButton("💾 Guardar como plantilla", callback_data="FINAL_SAVE_TEMPLATE"),
            InlineKeyboardButton("❌ Cancelar borrador", callback_data="MENU_CANCEL_DRAFT"),
        ],
        [
            InlineKeyboardButton("🔙 Volver al menú", callback_data="BACK_TO_MENU"),
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


# --------- Vista previa y envío ---------
def get_media_items(draft: Dict[str, Any]) -> List[Dict[str, str]]:
    if draft.get("media"):
        return draft["media"]
    if draft.get("type") in ("photo", "video", "voice") and draft.get("file_id"):
        return [{"type": draft["type"], "file_id": draft["file_id"]}]
    return []


async def send_draft_content(draft, chat_id, context):
    buttons = draft.get("buttons") or []
    markup = InlineKeyboardMarkup(buttons) if buttons else None
    text = draft.get("text") or ""
    media = get_media_items(draft)
    if len(media) > 1:
        # Telegram albums do not accept an inline keyboard. Keep the complete
        # text and buttons together immediately below the album.
        inputs = [
            (InputMediaPhoto if item["type"] == "photo" else InputMediaVideo)(
                media=item["file_id"]
            ) for item in media
        ]
        messages = await context.bot.send_media_group(chat_id=chat_id, media=inputs)
        if text or markup:
            await send_publication_text(text or "🔗 Enlaces", chat_id, context, markup)
        return messages[0]
    if media:
        item = media[0]
        separate_text = len(text.encode("utf-16-le")) // 2 > 1024
        sender = getattr(context.bot, "send_" + item["type"])
        message = await sender(
            chat_id=chat_id, **{item["type"]: item["file_id"]},
            caption="" if separate_text else text,
            reply_markup=None if separate_text else markup,
        )
        if separate_text:
            await send_publication_text(text, chat_id, context, markup)
        return message
    return await send_publication_text(text or "(Publicación sin texto)", chat_id, context, markup)


async def send_publication_text(text, chat_id, context, markup):
    # Split at Telegram's UTF-16 message limit; keep buttons on the final part.
    chunks, current, units = [], [], 0
    for char in text:
        size = 2 if ord(char) > 0xFFFF else 1
        if units + size > 4096:
            chunks.append("".join(current))
            current, units = [], 0
        current.append(char)
        units += size
    if current:
        chunks.append("".join(current))
    first = None
    for index, chunk in enumerate(chunks):
        message = await context.bot.send_message(
            chat_id=chat_id, text=chunk,
            reply_markup=markup if index == len(chunks) - 1 else None,
        )
        if first is None:
            first = message
    return first


async def send_draft_preview(user_id, chat_id, context) -> None:
    draft = get_draft(user_id)
    if not draft_has_content(draft):
        await context.bot.send_message(chat_id=chat_id, text="(Sin publicación para vista previa)")
        return
    await send_draft_content(draft, chat_id, context)


async def send_publication_to_target(draft, context):
    if not draft_has_content(draft):
        return None
    return await send_draft_content(draft, TARGET_CHAT_ID, context)


async def finish_album(context):
    user_id = context.job.data["user_id"]
    pending = PENDING_ALBUMS.pop(user_id, None)
    if pending is None:
        return
    updates = sorted(pending["updates"], key=lambda u: u.message.message_id)
    first = updates[0]
    messages = [u.message for u in updates]
    context.user_data["received_album_media"] = [
        {"type": "photo" if m.photo else "video",
         "file_id": m.photo[-1].file_id if m.photo else m.video.file_id}
        for m in messages
    ]
    context.user_data["received_album_caption"] = "\n\n".join(
        m.caption for m in messages if m.caption
    )
    handler = handle_new_media if pending["state"] == "AWAITING_NEW_MEDIA" else handle_new_publication_message
    await handler(first, context)


# --------- Comandos ---------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin_private(update):
        return

    user_id = update.effective_user.id  # type: ignore[union-attr]
    chat_id = update.effective_chat.id  # type: ignore[union-attr]

    init_user_structs(user_id)
    context.user_data.clear()
    await send_main_menu_simple(context, chat_id, user_id)


# --------- Callbacks de botones ---------
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    if not is_admin_private(update):
        return

    user_id = update.effective_user.id  # type: ignore[union-attr]
    chat_id = update.effective_chat.id  # type: ignore[union-attr]
    data = query.data or ""
    if user_id in PENDING_ALBUMS:
        await context.bot.send_message(chat_id=chat_id, text="Estoy recibiendo el álbum; espera un momento y vuelve a pulsar la opción.")
        return


    init_user_structs(user_id)

    # --- Menú principal ---
    if data == "MENU_CREATE":
        templates = get_templates(user_id)
        if templates:
            keyboard = [
                [
                    InlineKeyboardButton(
                        "✔ Sí, usar plantilla", callback_data="NEWPUB_USE_TEMPLATE"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "✏️ No, escribir texto nuevo", callback_data="NEWPUB_NO_TEMPLATE"
                    )
                ],
                [InlineKeyboardButton("❌ Cancelar", callback_data="BACK_TO_MENU")],
            ]
            await context.bot.send_message(
                chat_id=chat_id,
                text="¿Quieres usar una plantilla de texto guardada?",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            context.user_data["state"] = "AWAITING_NEW_PUBLICATION_MESSAGE"
            context.user_data["after_buttons_action"] = "FINAL_MENU"
            context.user_data.pop("selected_template_text", None)
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Envía ahora la publicación como si fueras a enviarla al canal "
                    "(puede ser un álbum de hasta 10 fotos/videos con texto, una foto, un video, nota de voz o solo texto)."
                ),
            )

    elif data == "NEWPUB_USE_TEMPLATE":
        templates = get_templates(user_id)
        if not templates:
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay plantillas guardadas.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
        else:
            keyboard_rows: List[List[InlineKeyboardButton]] = []
            for idx, tpl in enumerate(templates):
                keyboard_rows.append(
                    [
                        InlineKeyboardButton(
                            tpl["title"],
                            callback_data=f"NEWPUB_TEMPLATE_{idx}",
                        )
                    ]
                )
            keyboard_rows.append(
                [InlineKeyboardButton("⬅️ Volver", callback_data="MENU_CREATE")]
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text="Elige la plantilla que quieres usar:",
                reply_markup=InlineKeyboardMarkup(keyboard_rows),
            )

    elif data.startswith("NEWPUB_TEMPLATE_"):
        try:
            idx = int(data.split("_")[-1])
        except ValueError:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Plantilla no válida.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
            return
        templates = get_templates(user_id)
        if idx < 0 or idx >= len(templates):
            await context.bot.send_message(
                chat_id=chat_id,
                text="Plantilla no válida.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
            return

        selected = templates[idx]
        context.user_data["selected_template_text"] = selected["text"]
        context.user_data["state"] = "AWAITING_NEW_PUBLICATION_MESSAGE"
        context.user_data["after_buttons_action"] = "FINAL_MENU"
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Envía ahora la publicación (álbum de fotos/videos, foto, video, nota de voz o texto).\n"
                "Se usará la plantilla seleccionada como texto de la publicación."
            ),
        )

    elif data == "NEWPUB_NO_TEMPLATE":
        context.user_data["state"] = "AWAITING_NEW_PUBLICATION_MESSAGE"
        context.user_data["after_buttons_action"] = "FINAL_MENU"
        context.user_data.pop("selected_template_text", None)
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Envía ahora la publicación como si fueras a enviarla al canal "
                "(puede ser un álbum de hasta 10 fotos/videos con texto, una foto, un video, nota de voz o solo texto)."
            ),
        )

    elif data == "MENU_BUTTONS":
        context.user_data["after_buttons_action"] = "MAIN_MENU"
        await context.bot.send_message(
            chat_id=chat_id,
            text="Gestión de botones para el borrador actual:",
            reply_markup=InlineKeyboardMarkup(build_buttons_menu_keyboard()),
        )

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

            message = await send_publication_to_target(draft, context)
            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ Publicación enviada al canal.",
            )

            post_id = None
            try:
                if message is not None:
                    post_id = message.message_id
            except Exception:
                post_id = None

            base_url = "https://t.me/JohaaleTrader_es"
            url = base_url
            if post_id is not None:
                url = f"{base_url}/{post_id}"

            buttons_after_send = [
                [InlineKeyboardButton("🔗 Así se publicó en el canal", url=url)],
                [InlineKeyboardButton("Volver al menú", callback_data="BACK_TO_MENU")],
            ]
            await context.bot.send_message(
                chat_id=chat_id,
                text="Selecciona una opción:",
                reply_markup=InlineKeyboardMarkup(buttons_after_send),
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
                [InlineKeyboardButton("✏️ Editar texto", callback_data="EDIT_TEXT")],
                [InlineKeyboardButton("🔗 Editar botones", callback_data="EDIT_BUTTONS")],
                [InlineKeyboardButton("🖼 Cambiar media", callback_data="EDIT_MEDIA")],
                [InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_TO_MENU")],
            ]
            await context.bot.send_message(
                chat_id=chat_id,
                text="Elige qué parte de la publicación quieres editar:",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    elif data == "MENU_TEMPLATES":
        keyboard = [
            [
                InlineKeyboardButton(
                    "💾 Guardar texto actual como plantilla", callback_data="TEMPLATE_SAVE"
                )
            ],
            [
                InlineKeyboardButton(
                    "📥 Insertar plantilla en borrador", callback_data="TEMPLATE_INSERT"
                )
            ],
            [
                InlineKeyboardButton(
                    "📚 Ver plantillas guardadas", callback_data="TEMPLATE_VIEW"
                )
            ],
            [
                InlineKeyboardButton(
                    "🗑 Eliminar plantilla guardada", callback_data="TEMPLATE_DELETE"
                )
            ],
            [InlineKeyboardButton("❌ Cancelar y volver", callback_data="BACK_TO_MENU")],
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text="Opciones de plantillas:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "MENU_CANCEL_DRAFT":
        keyboard = [
            [
                InlineKeyboardButton(
                    "Sí, cancelar borrador", callback_data="CONFIRM_CANCEL_DRAFT"
                )
            ],
            [InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_TO_MENU")],
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text="¿Seguro que quieres cancelar y borrar el borrador actual?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # --- Confirmaciones ---
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
        context.user_data.pop("buttons_context", None)
        context.user_data.pop("after_buttons_action", None)
        context.user_data.pop("selected_template_text", None)
        await send_main_menu_simple(context, chat_id, user_id)

    elif data == "FINAL_SAVE_TEMPLATE":
        draft = get_draft(user_id)
        text = (draft.get("text") or "").strip()
        if not text:
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay texto en el borrador para guardar como plantilla.",
            )
        else:
            title = save_template_from_text(user_id, text)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Plantilla guardada: {title}",
            )
        await send_main_menu_simple(context, chat_id, user_id)

    # --- Flujo de botones después de nueva publicación ---
    elif data == "NEW_USE_DEFAULT_BUTTONS":
        defaults = get_defaults(user_id)
        draft = get_draft(user_id)
        if not defaults.get("buttons"):
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay botones predeterminados guardados.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
        else:
            draft["buttons"] = copy.deepcopy(defaults["buttons"])
            await context.bot.send_message(
                chat_id=chat_id,
                text="Botones predeterminados aplicados al borrador.",
            )
            await send_draft_preview(user_id, chat_id, context)
            await context.bot.send_message(
                chat_id=chat_id,
                text="¿Qué quieres hacer ahora?",
                reply_markup=InlineKeyboardMarkup(build_final_action_keyboard()),
            )

    elif data == "NEW_CREATE_BUTTONS":
        context.user_data["state"] = "AWAITING_NEW_BUTTONS_TEXT"
        context.user_data["buttons_context"] = "from_new"
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Envía todos los botones en un solo mensaje, uno por línea,\n"
                'con el formato "Texto del botón - URL".'
            ),
        )

    # --- Menú general de botones ---
    elif data == "BUTTONS_MENU_CREATE_NEW":
        context.user_data["state"] = "AWAITING_NEW_BUTTONS_TEXT"
        context.user_data["buttons_context"] = "from_buttons_menu"
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Envía todos los botones en un solo mensaje, uno por línea,\n"
                'con el formato "Texto del botón - URL".'
            ),
        )

    elif data == "BUTTONS_MENU_USE_DEFAULT":
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
        await send_main_menu_simple(context, chat_id, user_id)

    elif data == "BUTTONS_MENU_EDIT_EXISTING":
        draft = get_draft(user_id)
        if not draft.get("buttons"):
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay botones en el borrador para editar.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
        else:
            context.user_data["state"] = "AWAITING_NEW_BUTTONS_TEXT"
            context.user_data["buttons_context"] = "from_buttons_menu"
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Vas a reemplazar los botones actuales.\n"
                    "Envía todos los botones en un solo mensaje, uno por línea,\n"
                    'con el formato "Texto del botón - URL".'
                ),
            )

    elif data == "BUTTONS_MENU_DELETE_ALL":
        draft = get_draft(user_id)
        draft["buttons"] = []
        await context.bot.send_message(
            chat_id=chat_id,
            text="Todos los botones del borrador han sido eliminados.",
        )
        await send_main_menu_simple(context, chat_id, user_id)

    elif data == "BUTTONS_MENU_DELETE_ONE":
        draft = get_draft(user_id)
        buttons = draft.get("buttons") or []
        if not buttons:
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay botones en el borrador para eliminar.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
        else:
            lines = []
            for idx, row in enumerate(buttons, start=1):
                btn = row[0]
                lines.append(f"{idx}. {btn.text} - {btn.url}")
            listing = "\n".join(lines)
            context.user_data["state"] = "AWAITING_DELETE_BUTTON_INDEX"
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Botones actuales:\n"
                    f"{listing}\n\n"
                    "Envía el número del botón que quieres eliminar."
                ),
            )

    elif data == "BUTTONS_MENU_SAVE_DEFAULTS":
        draft = get_draft(user_id)
        if not draft.get("buttons"):
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay botones en el borrador para guardar como predeterminados.",
            )
        else:
            defaults = get_defaults(user_id)
            defaults["buttons"] = copy.deepcopy(draft["buttons"])
            await context.bot.send_message(
                chat_id=chat_id,
                text="Botones actuales guardados como predeterminados.",
            )
        await send_main_menu_simple(context, chat_id, user_id)

    elif data == "BUTTONS_MENU_VIEW_SAVED":
        defaults = get_defaults(user_id)
        saved_buttons = defaults.get("buttons") or []
        if not saved_buttons:
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay botones predeterminados guardados.",
            )
        else:
            lines = []
            for idx, row in enumerate(saved_buttons, start=1):
                # Cada fila es una lista de InlineKeyboardButton; mostramos solo el primero
                btn = row[0]
                lines.append(f"{idx}. {btn.text} - {btn.url}")
            listing = "\n".join(lines)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Botones predeterminados guardados:\n{listing}",
            )
        await context.bot.send_message(
            chat_id=chat_id,
            text="Opciones de botones:",
            reply_markup=InlineKeyboardMarkup(build_buttons_menu_keyboard()),
        )

    # --- Guardar o no como predeterminados tras crear botones ---
    elif data == "SAVE_BUTTONS_YES":
        draft = get_draft(user_id)
        defaults = get_defaults(user_id)
        defaults["buttons"] = copy.deepcopy(draft.get("buttons") or [])
        await context.bot.send_message(
            chat_id=chat_id,
            text="Botones guardados como predeterminados.",
        )
        await _after_buttons_flow(user_id, chat_id, context)

    elif data == "SAVE_BUTTONS_NO":
        await context.bot.send_message(
            chat_id=chat_id,
            text="Botones usados solo en este borrador.",
        )
        await _after_buttons_flow(user_id, chat_id, context)

    # --- Plantillas desde menú ---
    elif data == "TEMPLATE_SAVE":
        draft = get_draft(user_id)
        text = (draft.get("text") or "").strip()
        if not text:
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay texto en el borrador para guardar como plantilla.",
            )
        else:
            title = save_template_from_text(user_id, text)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Plantilla guardada: {title}",
            )
        await send_main_menu_simple(context, chat_id, user_id)

    elif data == "TEMPLATE_INSERT":
        templates = get_templates(user_id)
        if not templates:
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay plantillas guardadas para insertar.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
        else:
            keyboard_rows: List[List[InlineKeyboardButton]] = []
            for idx, tpl in enumerate(templates):
                keyboard_rows.append(
                    [
                        InlineKeyboardButton(
                            tpl["title"],
                            callback_data=f"TEMPLATE_INSERT_PICK_{idx}",
                        )
                    ]
                )
            keyboard_rows.append(
                [InlineKeyboardButton("⬅️ Volver al menú", callback_data="BACK_TO_MENU")]
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text="Elige la plantilla que quieres insertar en el borrador:",
                reply_markup=InlineKeyboardMarkup(keyboard_rows),
            )

    elif data.startswith("TEMPLATE_INSERT_PICK_"):
        try:
            idx = int(data.split("_")[-1])
        except ValueError:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Plantilla no válida.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
            return
        templates = get_templates(user_id)
        if idx < 0 or idx >= len(templates):
            await context.bot.send_message(
                chat_id=chat_id,
                text="Plantilla no válida.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
            return

        tpl = templates[idx]
        draft = get_draft(user_id)
        existing_text = draft.get("text") or ""
        if not draft_has_content(draft):
            draft["type"] = "text"
            draft["file_id"] = None
            draft["text"] = tpl["text"]
        else:
            if existing_text.strip():
                draft["text"] = existing_text + "\n\n" + tpl["text"]
            else:
                draft["text"] = tpl["text"]

        await context.bot.send_message(
            chat_id=chat_id,
            text="Plantilla insertada en el borrador.",
        )
        await send_main_menu_simple(context, chat_id, user_id)

    elif data == "TEMPLATE_DELETE":
        templates = get_templates(user_id)
        if not templates:
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay plantillas guardadas para eliminar.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
        else:
            lines = []
            for idx, tpl in enumerate(templates, start=1):
                lines.append(f"{idx}. {tpl['title']}")
            listing = "\n".join(lines)
            context.user_data["state"] = "AWAITING_DELETE_TEMPLATE_INDEX"
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Plantillas guardadas:\n"
                    f"{listing}\n\n"
                    "Envía el número de la plantilla que quieres eliminar."
                ),
            )


    elif data == "TEMPLATE_VIEW":
        templates = get_templates(user_id)
        if not templates:
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay plantillas guardadas para mostrar.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
        else:
            keyboard_rows: List[List[InlineKeyboardButton]] = []
            for idx, tpl in enumerate(templates):
                keyboard_rows.append(
                    [
                        InlineKeyboardButton(
                            tpl["title"],
                            callback_data=f"TEMPLATE_VIEW_PICK_{idx}",
                        )
                    ]
                )
            keyboard_rows.append(
                [
                    InlineKeyboardButton(
                        "⬅️ Volver al menú de plantillas", callback_data="MENU_TEMPLATES"
                    )
                ]
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text="Elige la plantilla que quieres ver o editar:",
                reply_markup=InlineKeyboardMarkup(keyboard_rows),
            )

    elif data.startswith("TEMPLATE_VIEW_PICK_"):
        try:
            idx = int(data.split("_")[-1])
        except ValueError:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Plantilla no válida.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
            return
        templates = get_templates(user_id)
        if idx < 0 or idx >= len(templates):
            await context.bot.send_message(
                chat_id=chat_id,
                text="Plantilla no válida.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
            return

        context.user_data["template_edit_index"] = idx
        tpl = templates[idx]
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Plantilla seleccionada:\n"
                f"{tpl['title']}\n\n"
                "Texto actual:\n"
                f"{tpl['text']}"
            ),
        )
        keyboard = [
            [
                InlineKeyboardButton(
                    "✏ Editar esta plantilla", callback_data="TEMPLATE_EDIT_CURRENT"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Volver a la lista de plantillas", callback_data="TEMPLATE_VIEW"
                )
            ],
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text="¿Qué quieres hacer con esta plantilla?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif data == "TEMPLATE_EDIT_CURRENT":
        templates = get_templates(user_id)
        idx = context.user_data.get("template_edit_index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(templates):
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay una plantilla válida seleccionada para editar.",
            )
            await send_main_menu_simple(context, chat_id, user_id)
        else:
            context.user_data["state"] = "AWAITING_EDIT_TEMPLATE_TEXT"
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Envía ahora el TEXTO COMPLETO corregido para esta plantilla.\n"
                    "Este texto reemplazará al contenido anterior."
                ),
            )

    # --- Edición desde menú Editar ---
    elif data == "SHOW_DRAFT":
        draft = get_draft(user_id)
        if not draft_has_content(draft):
            await context.bot.send_message(
                chat_id=chat_id,
                text="No hay borrador actualmente.",
            )
        else:
            await send_draft_preview(user_id, chat_id, context)
        await send_main_menu_simple(context, chat_id, user_id)

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
            context.user_data["state"] = "AWAITING_NEW_BUTTONS_TEXT"
            context.user_data["buttons_context"] = "from_edit_menu"
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "Vas a reemplazar los botones actuales.\n"
                    "Envía todos los botones en un solo mensaje, uno por línea,\n"
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
                    "Envía ahora la nueva media (álbum de hasta 10 fotos/videos, foto, video o nota de voz).\n"
                    "Si no envías texto, se conservará el texto actual."
                ),
            )

    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Opción no reconocida.",
        )
        await send_main_menu_simple(context, chat_id, user_id)


async def _after_buttons_flow(
    user_id: int, chat_id: int, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Flujo después de crear o editar botones y contestar si se guardan como predeterminados."""
    context.user_data["state"] = None
    buttons_context = context.user_data.get("buttons_context")
    after_action = context.user_data.get("after_buttons_action")

    if after_action == "FINAL_MENU" or buttons_context in ("from_new", "from_edit_menu"):
        await send_draft_preview(user_id, chat_id, context)
        await context.bot.send_message(
            chat_id=chat_id,
            text="¿Qué quieres hacer ahora?",
            reply_markup=InlineKeyboardMarkup(build_final_action_keyboard()),
        )
    else:
        await send_main_menu_simple(context, chat_id, user_id)

    context.user_data.pop("buttons_context", None)
    context.user_data.pop("after_buttons_action", None)


# --------- Parsers ---------
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


# --------- Manejadores de mensajes según estado ---------
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

    draft["media"] = context.user_data.pop("received_album_media", [])
    album_caption = context.user_data.pop("received_album_caption", None)
    if album_caption is not None:
        text = album_caption

    selected_template = context.user_data.get("selected_template_text")
    if selected_template:
        draft["type"] = content_type
        draft["file_id"] = file_id
        draft["text"] = selected_template
        context.user_data["selected_template_text"] = None
    else:
        draft["type"] = content_type
        draft["file_id"] = file_id
        draft["text"] = text

    context.user_data["state"] = None

    await context.bot.send_message(
        chat_id=chat_id,
        text="Publicación guardada en el borrador.",
    )

    defaults = get_defaults(user_id)
    if defaults.get("buttons"):
        keyboard = [
            [
                InlineKeyboardButton(
                    "✔ Usar botones predeterminados",
                    callback_data="NEW_USE_DEFAULT_BUTTONS",
                )
            ],
            [
                InlineKeyboardButton(
                    "✏️ No, crear nuevos botones",
                    callback_data="NEW_CREATE_BUTTONS",
                )
            ],
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text="¿Quieres usar los botones predeterminados que tienes guardados?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        context.user_data["state"] = "AWAITING_NEW_BUTTONS_TEXT"
        context.user_data["buttons_context"] = "from_new"
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Envía todos los botones en un solo mensaje, uno por línea,\n"
                'con el formato "Texto del botón - URL".'
            ),
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
        text="Botones actualizados. ¿Quieres guardar estos botones como predeterminados?",
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
        scheduled_local = datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Formato inválido. Usa AAAA-MM-DD HH:MM (ejemplo: 2025-12-31 18:30).",
        )
        return

    # Convertir hora local (UTC-5) a UTC real
    local_tz = timezone(timedelta(hours=-5))
    local_dt = scheduled_local.replace(tzinfo=local_tz)
    utc_dt = local_dt.astimezone(timezone.utc)

    now_utc = datetime.now(timezone.utc)
    delta = (utc_dt - now_utc).total_seconds()

    # Aceptamos cualquier hora futura aunque falten pocos segundos
    if delta < 1:
        await context.bot.send_message(
            chat_id=chat_id,
            text="La fecha y hora deben ser futuras.",
        )
        return

    delay = delta

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

    draft["scheduled_at"] = scheduled_local  # hora local para mostrar
    draft["job"] = job
    context.user_data["state"] = None

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "✅ Publicación programada para "
            f"{scheduled_local.strftime('%Y-%m-%d %H:%M')}."
        ),
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
    await context.bot.send_message(
        chat_id=chat_id,
        text="¿Qué quieres hacer ahora?",
        reply_markup=InlineKeyboardMarkup(build_final_action_keyboard()),
    )


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
    draft["media"] = context.user_data.pop("received_album_media", [])
    album_caption = context.user_data.pop("received_album_caption", None)
    if album_caption is not None:
        new_text = album_caption

    if new_text is not None and new_text.strip() != "":
        draft["text"] = new_text

    context.user_data["state"] = None

    await context.bot.send_message(
        chat_id=chat_id,
        text="Media del borrador actualizada.",
    )
    await send_draft_preview(user_id, chat_id, context)
    await context.bot.send_message(
        chat_id=chat_id,
        text="¿Qué quieres hacer ahora?",
        reply_markup=InlineKeyboardMarkup(build_final_action_keyboard()),
    )


async def handle_delete_button_index(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    if message is None or message.text is None:
        return

    user_id = update.effective_user.id  # type: ignore[union-attr]
    chat_id = update.effective_chat.id  # type: ignore[union-attr]
    draft = get_draft(user_id)
    buttons = draft.get("buttons") or []

    try:
        idx = int(message.text.strip())
    except ValueError:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Debes enviar un número válido.",
        )
        return

    if idx < 1 or idx > len(buttons):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Número fuera de rango.",
        )
        return

    removed = buttons.pop(idx - 1)
    draft["buttons"] = buttons
    context.user_data["state"] = None

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Botón '{removed[0].text}' eliminado.",
    )
    await send_main_menu_simple(context, chat_id, user_id)


async def handle_delete_template_index(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    if message is None or message.text is None:
        return

    user_id = update.effective_user.id  # type: ignore[union-attr]
    chat_id = update.effective_chat.id  # type: ignore[union-attr]

    defaults = get_defaults(user_id)
    templates = defaults.get("templates", [])

    try:
        idx = int(message.text.strip())
    except ValueError:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Debes enviar un número válido.",
        )
        return

    if idx < 1 or idx > len(templates):
        await context.bot.send_message(
            chat_id=chat_id,
            text="Número fuera de rango.",
        )
        return

    removed = templates.pop(idx - 1)
    defaults["templates"] = templates
    context.user_data["state"] = None

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Plantilla '{removed['title']}' eliminada.",
    )
    await send_main_menu_simple(context, chat_id, user_id)


async def handle_edit_template_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    if message is None or message.text is None:
        return

    user_id = update.effective_user.id  # type: ignore[union-attr]
    chat_id = update.effective_chat.id  # type: ignore[union-attr]

    defaults = get_defaults(user_id)
    templates = defaults.get("templates", [])

    idx = context.user_data.get("template_edit_index")
    if not isinstance(idx, int) or idx < 0 or idx >= len(templates):
        await context.bot.send_message(
            chat_id=chat_id,
            text="No hay una plantilla válida seleccionada para guardar cambios.",
        )
        context.user_data["state"] = None
        return

    templates[idx]["text"] = message.text
    defaults["templates"] = templates
    context.user_data["state"] = None

    await context.bot.send_message(
        chat_id=chat_id,
        text="Plantilla actualizada correctamente.",
    )
    await send_main_menu_simple(context, chat_id, user_id)



# --------- JobQueue ---------
async def send_scheduled_publication(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    if job is None:
        return
    data = job.data or {}
    user_id = data.get("user_id")
    if user_id is None:
        return

    draft = DRAFTS.get(user_id)
    if not draft_has_content(draft):
        return

    try:
        message = await send_publication_to_target(draft, context)  # type: ignore[arg-type]
        draft["scheduled_at"] = None
        draft["job"] = None
        await context.bot.send_message(
            chat_id=user_id,
            text="✅ Publicación programada enviada correctamente al canal.",
        )

        post_id = None
        try:
            if message is not None:
                post_id = message.message_id
        except Exception:
            post_id = None

        base_url = "https://t.me/JohaaleTrader_es"
        url = base_url
        if post_id is not None:
            url = f"{base_url}/{post_id}"

        buttons_after_send = [
            [InlineKeyboardButton("🔗 Así se publicó en el canal", url=url)],
            [InlineKeyboardButton("Volver al menú", callback_data="BACK_TO_MENU")],
        ]
        await context.bot.send_message(
            chat_id=user_id,
            text="Selecciona una opción:",
            reply_markup=InlineKeyboardMarkup(buttons_after_send),
        )
    except Exception as exc:
        logging.error("Error enviando publicación programada: %s", exc)


# --------- Router de mensajes ---------
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin_private(update):
        return

    if update.message is None:
        return

    user_id = update.effective_user.id  # type: ignore[union-attr]
    chat_id = update.effective_chat.id  # type: ignore[union-attr]

    init_user_structs(user_id)
    state = context.user_data.get("state")

    message = update.message
    if message.media_group_id and (message.photo or message.video):
        pending = PENDING_ALBUMS.get(user_id)
        if pending is not None and pending["group_id"] != message.media_group_id:
            await context.bot.send_message(chat_id=chat_id, text="Espera a que termine de recibirse el álbum actual.")
            return
        if pending is None:
            if state not in ("AWAITING_NEW_PUBLICATION_MESSAGE", "AWAITING_NEW_MEDIA"):
                await context.bot.send_message(chat_id=chat_id, text="Usa Crear / cambiar publicación o Cambiar media antes de enviar un álbum.")
                return
            pending = {"group_id": message.media_group_id, "state": state, "updates": [], "job": None}
            PENDING_ALBUMS[user_id] = pending
        if not any(u.message.message_id == message.message_id for u in pending["updates"]):
            pending["updates"].append(update)
        if pending["job"] is not None:
            pending["job"].schedule_removal()
        pending["job"] = context.application.job_queue.run_once(
            finish_album, 2.0, data={"user_id": user_id}, user_id=user_id,
        )
        return
    if user_id in PENDING_ALBUMS:
        await context.bot.send_message(chat_id=chat_id, text="Espera a que termine de recibirse el álbum antes de continuar.")
        return

    if state == "AWAITING_NEW_PUBLICATION_MESSAGE":
        await handle_new_publication_message(update, context)
    elif state == "AWAITING_NEW_BUTTONS_TEXT":
        await handle_new_buttons_text(update, context)
    elif state == "AWAITING_SCHEDULE_DATETIME":
        await handle_schedule_datetime(update, context)
    elif state == "AWAITING_EDIT_TEXT":
        await handle_edit_text(update, context)
    elif state == "AWAITING_NEW_MEDIA":
        await handle_new_media(update, context)
    elif state == "AWAITING_DELETE_BUTTON_INDEX":
        await handle_delete_button_index(update, context)
    elif state == "AWAITING_DELETE_TEMPLATE_INDEX":
        await handle_delete_template_index(update, context)
    elif state == "AWAITING_EDIT_TEMPLATE_TEXT":
        await handle_edit_template_text(update, context)
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Usa el menú para gestionar la publicación.",
        )


# --------- Errores ---------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error("Excepción en el manejador", exc_info=context.error)


# --------- Educación automática: configuración y registro persistente ---------
import asyncio
import base64
import io
import json
import sqlite3
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

EDU_TZ = timezone(timedelta(hours=-5))
EDU_TOPICS = (
    'gestión de riesgo', 'psicotrading', 'disciplina operativa',
    'conceptos educativos de trading',
)


def edu_enabled():
    return os.getenv('EDU_ENABLED', 'false').lower() in ('true', '1', 'yes')


def edu_db():
    root = Path(os.getenv('EDU_DATA_DIR', '/data/education'))
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(root / 'education.sqlite3'), timeout=30)
    db.execute('''CREATE TABLE IF NOT EXISTS posts (
        day TEXT PRIMARY KEY, status TEXT NOT NULL, attempts INTEGER DEFAULT 0,
        title TEXT, caption TEXT, image BLOB, message_id INTEGER,
        updated REAL NOT NULL, category TEXT)''')
    columns = {row[1] for row in db.execute('PRAGMA table_info(posts)')}
    if 'publish_kind' not in columns:
        db.execute("ALTER TABLE posts ADD COLUMN publish_kind TEXT DEFAULT 'article'")
    if 'payload' not in columns:
        db.execute('ALTER TABLE posts ADD COLUMN payload TEXT')
    if 'last_error' not in columns:
        db.execute('ALTER TABLE posts ADD COLUMN last_error TEXT')
    db.commit()
    return db


def edu_get(day):
    with edu_db() as db:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT * FROM posts WHERE day=?', (day,)).fetchone()
        return dict(row) if row else None


def edu_claim(day):
    now = datetime.now(timezone.utc).timestamp()
    with edu_db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT status,attempts,updated FROM posts WHERE day=?', (day,)).fetchone()
        if row:
            status, attempts, updated = row
            if status in ('ready', 'sending', 'sent', 'uncertain') or attempts >= 3:
                return False
            # Allow a bounded retry after API failure, or recover interrupted generation.
            if now - updated < (900 if status == 'generating' else 300):
                return False
            db.execute("UPDATE posts SET status='generating', attempts=attempts+1, updated=? WHERE day=?", (now, day))
        else:
            db.execute("INSERT INTO posts(day,status,attempts,updated) VALUES (?,'generating',1,?)", (day, now))
        return True


def edu_api(endpoint, payload):
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        raise RuntimeError('Falta OPENAI_API_KEY')
    req = Request('https://api.openai.com/v1/' + endpoint,
                  data=json.dumps(payload).encode('utf-8'),
                  headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=240) as response:
            return json.load(response)
    except HTTPError as exc:
        # Do not expose request headers, keys or provider response bodies in logs.
        raise RuntimeError('OpenAI HTTP ' + str(exc.code)) from None
    except Exception:
        raise RuntimeError('No se pudo completar la conexión con OpenAI') from None


def edu_signature_path():
    return Path(os.getenv('EDU_SIGNATURE_IMAGE', str(Path(__file__).resolve().parent / 'assets' / 'brand_signature.png')))


def edu_apply_signature(image_bytes, greeting=False):
    # Fixed PNG: spelling and handwriting never depend on image generation.
    from PIL import Image
    import io
    signature_path = edu_signature_path()
    if not signature_path.is_file():
        raise RuntimeError('Falta assets/brand_signature.png')
    with Image.open(signature_path) as source:
        if source.mode != 'RGBA' or source.getextrema()[3][0] == 255:
            raise RuntimeError('La firma debe ser un PNG con transparencia')
        signature = source.copy()
    bounds = signature.getchannel('A').getbbox()
    if not bounds:
        raise RuntimeError('La firma está vacía')
    signature = signature.crop(bounds)
    with Image.open(io.BytesIO(image_bytes)) as source:
        canvas = source.convert('RGBA')
    width, height = canvas.size
    scale = min(width * 0.35 / signature.width, height * 0.10 / signature.height)
    signature = signature.resize((max(1, round(signature.width * scale)),
                                  max(1, round(signature.height * scale))), Image.Resampling.LANCZOS)
    x = (width - signature.width) // 2
    y = height - round(height * (0.045 if greeting else 0.12)) - signature.height
    if greeting:
        # Subtle shadow improves gold visibility without a banner or a larger signature.
        from PIL import ImageFilter
        shadow = Image.new('RGBA', signature.size, (0, 0, 0, 0))
        shadow.putalpha(signature.getchannel('A'))
        layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        layer.alpha_composite(shadow, (x + 1, y + 2))
        canvas = Image.alpha_composite(canvas, layer.filter(ImageFilter.GaussianBlur(2)))
    canvas.alpha_composite(signature, (x, y))
    output = io.BytesIO()
    canvas.convert('RGB').save(output, format='JPEG', quality=95)
    return output.getvalue()


def edu_reference_image(payload):
    # Keep the shared call interface; generate backgrounds without branding.
    # Validate the asset before paying for image generation.
    if not edu_signature_path().is_file():
        raise RuntimeError('Falta assets/brand_signature.png')
    payload = dict(payload)
    payload.pop('input_fidelity', None)
    greeting = payload.pop('_greeting', False)
    if greeting:
        payload['prompt'] += (
            '\nDIRECCIÓN FINAL PARA SALUDOS: fotografía profesional hiperrealista de una sola escena, '
            'luminosa y alegre, con colores naturales variados y vivos sin sobresaturación. '
            'Evita interiores totalmente beige, marrones, grises o de un solo color; combina '
            'materiales reales con vegetación verde, cielo azul, agua turquesa, flores o alimentos '
            'de colores cuando correspondan al lugar. Luz blanca natural, sin filtro sepia ni tinte uniforme. '
            'Respeta el escenario solicitado; no lo sustituyas siempre por un amanecer. '
            'SIN imponer negro, morado ni dorado de la marca. Arquitectura y objetos plausibles, '
            'sin personas, caricaturas, collage, aspecto de render ni fantasía. '
            'Puede haber un gráfico de trading realista ÚNICAMENTE dentro de la pantalla de un computador '
            'si el escenario es un escritorio; nunca gráficos flotantes. '
            'NO generes título, letras, firmas, marcas, logotipos ni marcas de agua. '
            'La imagen NO llevará título: solo se añadirá después una firma fija desde un archivo. '
            'Ignora cualquier petición anterior de escribir texto. Reserva del 85% al 96% de '
            'la altura una zona sencilla con contraste para una firma dorada pequeña, sin '
            'objetos importantes detrás, franjas negras ni paneles artificiales. '
            'El escenario continúa hasta los bordes. Estas instrucciones prevalecen sobre las anteriores.')
        return edu_api('images/generations', payload)
    payload['prompt'] = payload.get('prompt', '') + (
        '\nDIRECCIÓN VISUAL FINAL OBLIGATORIA: fotografía editorial realista, nivel profesional. '
        'Usa una única escena principal coherente, luz natural o de estudio creíble, '
        'materiales y texturas reales, perspectiva y profundidad de campo naturales. '
        'Estética de la referencia: negro profundo, morado intenso, oro metálico brillante, '
        'texturas reales nítidas, reflejos controlados y profundidad cinematográfica. '
        'Composición limpia y profesional, sin saturación ni exceso de elementos. '
        'Para educación, objetos reales o espacios reales que transmitan el concepto; '
        'para saludos, paisaje fotográfico luminoso. No llenes la escena de símbolos. '
        'PROHIBIDO: caricaturas, dibujos infantiles, ilustración vectorial o plana, '
        'clipart, iconos gigantes, bombillas simbólicas, flechas y curvas flotantes, '
        'collage de objetos, render plástico, fantasía, halos de neón o humo sobre el texto. '
        'Título grande y legible con alto contraste, letras gruesas nítidas, '
        'combinando oro metálico y blanco como en la referencia, '
        'máximo tres líneas y sin efecto transparente ni dorado sobre fondo dorado. '
        'Estas reglas prevalecen sobre cualquier descripción visual anterior. '
        '\nREGLA FINAL OBLIGATORIA: incluye únicamente el título solicitado. '
        'NO dibujes firmas, nombres de marca, logotipos, marcas de agua ni letras adicionales. '
        'Ignora cualquier instrucción anterior que pida una firma o marca. '
        'Mantén el título por encima del 65% de la altura. Entre el 72% y el 88% '
        'deja un fondo tranquilo y oscuro, sin texto ni objetos importantes, para añadir '
        'después una firma dorada desde un archivo. El paisaje continúa hasta el borde.'
    )
    reference = Path(os.getenv('EDU_STYLE_REFERENCE_IMAGE',
        str(Path(__file__).resolve().parent / 'assets' / 'style_reference.png')))
    if not reference.is_file():
        # Preserve image generation if the asset hasn't been uploaded yet.
        logging.warning('Falta assets/style_reference.png; se usa la dirección fotográfica sin referencia')
        return edu_api('images/generations', payload)
    payload['prompt'] += (
        '\nLa imagen adjunta es EXCLUSIVAMENTE una referencia de estética y calidad: '
        'crea una escena NUEVA acorde al tema solicitado. No copies el cuaderno, escritorio, '
        'pantalla ni objetos cuando no correspondan al tema. Para saludos conserva el paisaje '
        'luminoso y adapta la paleta con naturalidad. No copies el título original, la palabra '
        'PLAN, los gráficos, la firma ni la marca de la referencia. El único texto es el título '
        'nuevo solicitado. No reproduzcas una firma: se añadirá después desde el PNG fijo. '
        'Mantén la zona inferior reservada limpia, sin ningún trazo ni letra.'
    )
    return edu_style_edit(payload, reference)


def edu_style_edit(payload, reference):
    # Multipart upload uses the official image-edit endpoint, no additional dependency.
    import uuid
    key = os.getenv('OPENAI_API_KEY', '').strip()
    if not key:
        raise RuntimeError('Falta OPENAI_API_KEY')
    data = reference.read_bytes()
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data) > 25 * 1024 * 1024:
        raise RuntimeError('Referencia de estilo PNG inválida o demasiado grande')
    fields = dict(payload)
    if fields.get('model') in ('gpt-image-1', 'gpt-image-1.5'):
        fields['input_fidelity'] = 'high'
    boundary = 'style_' + uuid.uuid4().hex
    parts = []
    for field, value in fields.items():
        parts.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="' +
                      field + '"\r\n\r\n' + str(value) + '\r\n').encode('utf-8'))
    parts.append(('--' + boundary + '\r\nContent-Disposition: form-data; name="image"; '
                  'filename="style_reference.png"\r\nContent-Type: image/png\r\n\r\n').encode() + data + b'\r\n')
    parts.append(('--' + boundary + '--\r\n').encode())
    request = Request('https://api.openai.com/v1/images/edits', data=b''.join(parts),
                      headers={'Authorization': 'Bearer ' + key,
                               'Content-Type': 'multipart/form-data; boundary=' + boundary})
    try:
        with urlopen(request, timeout=240) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError('OpenAI HTTP ' + str(exc.code)) from None
    except Exception:
        raise RuntimeError('No se pudo completar la conexión con OpenAI') from None


def edu_safe_error(exc):
    # Only our own fixed error messages are exposed; never provider bodies/headers.
    message = str(exc)
    allowed = (
        'Falta OPENAI_API_KEY', 'Falta assets/brand_signature.png',
        'La firma debe ser un PNG con transparencia', 'La firma está vacía',
        'Referencia de estilo PNG inválida o demasiado grande',
        'No se pudo completar la conexión con OpenAI',
        'El artículo no cumplió los límites de formato', 'Encuesta fuera de formato',
        'Resumen inválido', 'Resumen no corresponde a los artículos publicados',
        'Resumen demasiado largo', 'Imagen vacía o demasiado grande para Telegram',
    )
    if message in allowed:
        return message
    if message.startswith('OpenAI HTTP ') and message[12:].isdigit():
        return message
    return type(exc).__name__


def edu_record_error(day, stage, exc):
    detail = stage + ': ' + edu_safe_error(exc)
    logging.warning('Educación automática [%s] %s', day, detail)
    with edu_db() as db:
        db.execute('UPDATE posts SET last_error=? WHERE day=?', (detail, day))


def edu_backup_article(day, category):
    # Reviewed local content: no external API is needed to keep the educational slot.
    lessons = {
        'gestión de riesgo': (
            'Define tu límite antes de empezar',
            'La gestión de riesgo empieza antes de cualquier entrada. Decide cuánto puedes perder '
            'en una operación y cuál será el límite de la sesión. Esos límites ayudan a cuidar tu '
            'capital y a tomar decisiones con calma.\n\nSi tu capital es de 100 USD y defines una '
            'pérdida máxima del 1%, el límite es 1 USD. La cantidad que inviertes y la pérdida posible '
            'no siempre son iguales: dependen del instrumento y sus condiciones.\n\nHoy revisa tus '
            'límites y déjalos por escrito. ¿Qué regla te ayudará a respetarlos?',
            'Una libreta con un plan junto a una brújula, metáfora de límites y dirección'),
        'psicotrading': (
            'Una pausa también es una decisión',
            'Reconocer lo que sientes te ayuda a decidir con más claridad. Antes de una entrada, '
            'haz una pausa y observa si estás siguiendo tu plan o reaccionando a una emoción. '
            'La calma se practica con hábitos pequeños.\n\nDespués de una pérdida, evita buscar '
            'una entrada solo para compensarla. Respira, revisa el contexto y recuerda tus límites. '
            'No necesitas resolver todo en una sola sesión.\n\nHoy registra una emoción y cómo '
            'influyó en una decisión. ¿Qué pausa puedes incorporar a tu rutina?',
            'Un lago tranquilo al amanecer y una libreta, metáfora de claridad emocional'),
        'disciplina operativa': (
            'Convierte tu plan en un hábito',
            'La disciplina crece cuando tu plan se vuelve fácil de consultar. Una lista breve '
            'puede ayudarte: contexto claro, condición de entrada, riesgo definido y límite de '
            'sesión. Revisa cada punto antes de decidir.\n\nSi falta una condición, esperar también '
            'forma parte del proceso. Seguir un plan no garantiza ganancias, pero te permite '
            'evaluar decisiones con criterios consistentes.\n\nHoy elige una regla y registra '
            'si la respetaste. ¿Qué hábito quieres fortalecer en tu próxima sesión?',
            'Una agenda ordenada junto a un reloj, metáfora de constancia y planificación'),
        'conceptos educativos de trading': (
            'Observa el contexto de cada nivel',
            'Un soporte o una resistencia es una zona de interés, no una garantía de giro. '
            'Observa cómo llega el precio, qué reacción aparece y qué condiciones exige tu plan '
            'antes de tomar una decisión.\n\nEl mismo nivel puede mostrar respuestas diferentes '
            'según el contexto. Evita interpretar un solo toque como confirmación suficiente y '
            'mantén definidos tus límites de riesgo.\n\nHoy marca una zona y describe lo que '
            'observas sin anticipar el resultado. ¿Qué señal de contexto revisarás primero?',
            'Un camino con puntos de observación, metáfora de contexto y zonas de interés'),
    }
    title, body, visual = lessons[category]
    with edu_db() as db:
        exists = db.execute("SELECT 1 FROM posts WHERE status='sent' AND title=?", (title,)).fetchone()
    if exists:
        title += ' · ' + day[5:]
    return title, body, visual


def edu_generate_article(day):
    with edu_db() as db:
        history = db.execute("SELECT title,category FROM posts WHERE status='sent' AND day NOT LIKE 'greeting:%' AND publish_kind='article' ORDER BY day DESC LIMIT 60").fetchall()
        count = db.execute("SELECT COUNT(*) FROM posts WHERE status='sent' AND day NOT LIKE 'greeting:%' AND publish_kind='article'").fetchone()[0]
    category = EDU_TOPICS[count % len(EDU_TOPICS)]
    instructions = '''Crea un miniartículo original en español para el canal de JOHAALETRADER,
comunidad JT TRADERS TEAMS. Tutea, tono cercano, concreto y educativo.
Lenguaje totalmente neutro respecto al género de quien lee: evita adjetivos o
sustantivos que asignen género; usa tú, quien opera, la comunidad y expresiones neutras.
Tono siempre positivo, motivador, constructivo y realista, sin culpabilizar ni alarmar.
Termina body con un llamado a la acción educativo específico: revisar el plan,
registrar una emoción, definir un límite o guardar el aprendizaje. No incites a
operar, depositar o recuperar pérdidas. El llamado cuenta dentro del límite de body.
Devuelve JSON con title, body, image_prompt. Título máximo 60 caracteres;
body entre 450 y 650 caracteres en TOTAL, incluyendo espacios y saltos de línea, con párrafos cortos, una idea útil explicada y
un ejemplo cuando corresponda. Sin markdown, enlaces, hashtags ni firma.
Usa 2 o 3 emojis discretos y pertinentes en TOTAL dentro de body, al inicio de
párrafos para destacar el aprendizaje y el llamado a la acción (por ejemplo
🧠, 💡, 🎯). No los pongas en title ni image_prompt, ni junto a cada frase.
Los emojis y espacios cuentan dentro del límite de longitud de body.
No inventes resultados, estadísticas, citas, noticias o experiencias personales.
No recomiendes activos ni prometas ganancias. No presentes martingala como
protección: aumenta exposición; las pérdidas acumuladas cuentan para el riesgo.
Los ejemplos de riesgo deben ser matemáticamente correctos y distinguir tamaño
de posición de pérdida máxima. Explica que la disciplina no garantiza ganancias.
image_prompt: descripción visual coherente con el tema, sin cifras ni diagramas exactos.
Evita repetir títulos, enfoques y ejemplos del historial proporcionado.'''
    if count % 2 == 0:
        instructions += '\nTermina body con una pregunta breve y concreta sobre el tema que invite a reflexionar o comentar. Inclúyela dentro de los 650 caracteres; no asumas que hay comentarios habilitados.'
    messages = [{'role': 'system', 'content': instructions},
                {'role': 'user', 'content': json.dumps({'tema': category, 'fecha': day, 'historial': history}, ensure_ascii=False)}]
    repair = ''
    article = None
    api_failed = False
    for attempt in range(3):
        try:
            result = edu_api('chat/completions', {
                'model': os.getenv('EDU_TEXT_MODEL', 'gpt-4.1-mini'),
                'messages': messages,
                'response_format': {'type': 'json_object'}, 'max_tokens': 1300,
            })
            raw_content = result['choices'][0]['message']['content']
            messages.append({'role': 'assistant', 'content': raw_content})
            obj = json.loads(raw_content)
            if not isinstance(obj, dict):
                raise ValueError('Respuesta JSON inválida')
            title = obj.get('title', ''); body = obj.get('body', ''); visual = obj.get('image_prompt', '')
            if not all(isinstance(v, str) for v in (title, body, visual)):
                raise ValueError('Campos de texto inválidos')
            title, body, visual = title.strip(), body.strip(), visual.strip()
            if not visual:
                visual = 'Fotografía editorial de un espacio sereno de planificación, coherente con: ' + title
            caption = title + '\n\n' + body + '\n\nJohanna Alegría | JOHAALETRADER'
            # 450–650 remains the writing target. A useful shorter article is valid.
            if (title and len(title) <= 60 and 180 <= len(body) <= 760 and visual and
                    len(caption.encode('utf-16-le')) // 2 <= 1024 and
                    title.casefold() not in [str(t).casefold() for t, _ in history]):
                article = (title, body, visual, caption)
                break
            logging.warning('Formato artículo [%s] intento %s: título=%s, cuerpo=%s, caption_utf16=%s, título_repetido=%s',
                            day, attempt + 1, len(title), len(body),
                            len(caption.encode('utf-16-le')) // 2,
                            title.casefold() in [str(t).casefold() for t, _ in history])
            repair = ('\nCORRECCIÓN DEL INTENTO ANTERIOR: title tuvo ' + str(len(title)) +
                      ' caracteres y body ' + str(len(body)) + '. Usa un título NUEVO de hasta 60 '
                      'caracteres, body de 450 a 650 y image_prompt no vacío. '
                      'Acorta sin cortar frases; conserva la idea, el ejemplo y el llamado a la acción.')
            messages.append({'role': 'user', 'content': repair})
        except RuntimeError as exc:
            edu_record_error(day, 'texto', exc)
            api_failed = True
            break  # Quota/auth/connectivity: use the local educational backup.
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logging.warning('Formato artículo [%s] intento %s: estructura JSON inválida (%s)', day, attempt + 1, type(exc).__name__)
            repair = '\nCORRECCIÓN: entrega JSON válido con title, body e image_prompt como texto.'
            messages.append({'role': 'user', 'content': repair})
    if article is None:
        if not api_failed:
            edu_record_error(day, 'formato del artículo', RuntimeError('El artículo no cumplió los límites de formato'))
        title, body, visual = edu_backup_article(day, category)
        caption = title + '\n\n' + body + '\n\nJohanna Alegría | JOHAALETRADER'
    else:
        title, body, visual, caption = article
    # Save usable text BEFORE requesting the image; image failure cannot discard it.
    with edu_db() as db:
        db.execute("UPDATE posts SET publish_kind='article',title=?,caption=?,category=?,payload=NULL,updated=? "
                   "WHERE day=? AND status='generating'",
                   (title, caption, category, datetime.now(timezone.utc).timestamp(), day))
    style = os.getenv('EDU_IMAGE_STYLE',
        'Crea una imagen educativa NUEVA acorde al concepto del artículo. '
        'Representa el aprendizaje con objetos, ambientes o metáforas claras y variadas. '
        'No incluyas personas. Paleta morado, negro y dorado oro brillante. '
        'Estilo moderno, cercano, positivo, limpio, sin lujo excesivo ni sobrecarga. '
        'Incluye únicamente el título educativo. Sin firmas ni marcas. '
        'Sin cifras, gráficos exactos, resultados ficticios ni promesas de ganancias. '
        'Texto neutro respecto al género.')
    image = None
    try:
        generated = edu_reference_image({
            'model': os.getenv('EDU_IMAGE_MODEL', 'gpt-image-1'),
            'prompt': style + '\nTítulo exacto: ' + title + '\nConcepto: ' + visual,
            'size': '1024x1024', 'quality': 'medium', 'n': 1,
        })
        image = edu_apply_signature(base64.b64decode(generated['data'][0]['b64_json'], validate=True))
        if not image or len(image) > 10 * 1024 * 1024:
            raise RuntimeError('Imagen vacía o demasiado grande para Telegram')
    except Exception as exc:
        edu_record_error(day, 'imagen', exc)
        # Automatic continuity: publish the complete article as text at its usual slot.
        image = None
    with edu_db() as db:
        db.execute("UPDATE posts SET status='ready',image=?,updated=? WHERE day=? AND status='generating'",
                   (image, datetime.now(timezone.utc).timestamp(), day))


async def edu_alert(bot, text):
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=text)
    except Exception:
        logging.warning('No se pudo entregar el aviso educativo al administrador')


# --------- Interacción semanal y resumen mensual ---------
def education_kind(day):
    date = datetime.strptime(day, '%Y-%m-%d')
    if date.weekday() in (2, 5):
        return 'poll'
    if date.weekday() == 1 and date.day <= 7:
        return 'summary'
    return 'article'


def education_schedule(day):
    # Minutes in Colombia time: preparation, publication, end of catch-up window.
    weekday = datetime.strptime(day, '%Y-%m-%d').weekday()
    if weekday == 2:
        return (920, 930, 960)  # Wednesday 15:20 / 15:30 / 16:00.
    if weekday in (1, 3, 5):
        return (650, 660, 690)  # Tuesday/Thursday/Saturday 10:50 / 11:00 / 11:30.
    return None


def previous_month_articles(day):
    date = datetime.strptime(day, '%Y-%m-%d')
    first = date.replace(day=1)
    start = (first - timedelta(days=1)).replace(day=1).date().isoformat()
    end = first.date().isoformat()
    with edu_db() as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(
            "SELECT day,title,caption,message_id FROM posts WHERE day>=? AND day<? "
            "AND status='sent' AND publish_kind='article' AND message_id IS NOT NULL ORDER BY day", (start, end))]


def save_interaction(day, kind, title, payload):
    with edu_db() as db:
        db.execute("UPDATE posts SET status='ready',publish_kind=?,title=?,payload=?,image=NULL,updated=? "
                   "WHERE day=? AND status='generating'",
                   (kind, title, json.dumps(payload, ensure_ascii=False), datetime.now(timezone.utc).timestamp(), day))


def generate_poll(day):
    focus = ('Mitad de semana: cómo va tu disciplina, qué hábito ajustar hoy o qué tema quieres aprender.'
             if datetime.strptime(day, '%Y-%m-%d').weekday() == 2 else
             'Cierre de semana: reflexionar sobre hábitos y aprendizajes y preparar la próxima semana.')
    with edu_db() as db:
        previous = db.execute("SELECT title FROM posts WHERE publish_kind='poll' AND status='sent' ORDER BY day DESC LIMIT 20").fetchall()
    for _ in range(2):
        result = edu_api('chat/completions', {
            'model': os.getenv('EDU_TEXT_MODEL', 'gpt-4.1-mini'),
            'messages': [{'role': 'system', 'content':
                'Crea una encuesta de opinión para JT TRADERS TEAMS, en español, tuteando, '
                'totalmente neutra en género, positiva y motivadora. Pregunta sobre hábitos, '
                'disciplina, emociones o temas educativos que interesa aprender. No es un examen '
                'ni tiene respuesta correcta. Sin promesas, resultados inventados o ventas. '
                'Devuelve JSON: question de máximo 220 caracteres y options con 3 o 4 opciones '
                'distintas de máximo 80 caracteres, claras y mutuamente diferenciadas. Sin markdown. '
                'No repitas preguntas del historial.'},
                {'role': 'user', 'content': json.dumps({'fecha': day, 'enfoque': focus, 'historial': previous}, ensure_ascii=False)}],
            'response_format': {'type': 'json_object'}, 'max_tokens': 500})
        obj = json.loads(result['choices'][0]['message']['content'])
        q = obj.get('question'); options = obj.get('options')
        if (isinstance(q, str) and 5 <= len(q) <= 220 and isinstance(options, list) and
                3 <= len(options) <= 4 and all(isinstance(o, str) and 1 <= len(o.strip()) <= 80 for o in options) and
                len({o.strip().casefold() for o in options}) == len(options) and
                q.casefold() not in [str(t).casefold() for (t,) in previous]):
            save_interaction(day, 'poll', q, {'question': q, 'options': [o.strip() for o in options]})
            return
    raise RuntimeError('Encuesta fuera de formato')


def generate_summary(day, sources):
    # Only confirmed published articles are provided, never greetings or invented links.
    result = edu_api('chat/completions', {
        'model': os.getenv('EDU_TEXT_MODEL', 'gpt-4.1-mini'),
        'messages': [{'role': 'system', 'content':
            'Resume los aprendizajes de los artículos recibidos. Español, tuteo, sin género, '
            'positivo, motivador y fiel al contenido. No inventes resultados ni hechos. '
            'Devuelve JSON con intro (máximo 220 caracteres), closing (máximo 130 caracteres, '
            'llamado a aplicar un aprendizaje) y lessons: lista de objetos con day y learning '
            '(máximo 100 caracteres). Una lección por cada artículo; no inventes fechas ni enlaces.'},
            {'role': 'user', 'content': json.dumps(sources, ensure_ascii=False)}],
        'response_format': {'type': 'json_object'}, 'max_tokens': 1600})
    obj = json.loads(result['choices'][0]['message']['content'])
    lessons = obj.get('lessons', [])
    if not isinstance(lessons, list):
        raise RuntimeError('Resumen inválido')
    by_date = {x.get('day'): str(x.get('learning', '')).strip() for x in lessons if isinstance(x, dict)}
    if set(by_date) != {x['day'] for x in sources} or any(not v or len(v) > 100 for v in by_date.values()):
        raise RuntimeError('Resumen no corresponde a los artículos publicados')
    intro = str(obj.get('intro', '')).strip(); closing = str(obj.get('closing', '')).strip()
    if not intro or len(intro) > 220 or not closing or len(closing) > 130:
        raise RuntimeError('Resumen demasiado largo')
    for item in sources:
        item['learning'] = by_date[item['day']]
    month = sources[0]['day'][:7]
    save_interaction(day, 'summary', 'Aprendizajes del mes · ' + month,
                     {'intro': intro, 'closing': closing, 'sources': sources})


def edu_generate(day):
    kind = education_kind(day)
    if kind == 'poll':
        try:
            generate_poll(day)
        except Exception as exc:
            edu_record_error(day, 'encuesta', exc)
            question = ('¿Qué hábito quieres reforzar en lo que queda de semana?'
                        if datetime.strptime(day, '%Y-%m-%d').weekday() == 2 else
                        '¿Qué hábito quieres fortalecer la próxima semana?')
            save_interaction(day, 'poll', question,
                             {'question': question,
                              'options': ['Respetar mis límites de riesgo', 'Registrar mis decisiones',
                                          'Hacer pausas conscientes', 'Revisar mi plan antes de empezar']})
    elif kind == 'summary':
        sources = previous_month_articles(day)
        if sources:
            try:
                generate_summary(day, sources)
            except Exception as exc:
                edu_record_error(day, 'resumen', exc)
                for source in sources:
                    source['learning'] = 'Revisa este aprendizaje y elige una acción para tu rutina.'
                save_interaction(day, 'summary', 'Aprendizajes del mes · ' + sources[0]['day'][:7],
                                 {'intro': 'Retoma los aprendizajes compartidos durante el mes.',
                                  'closing': 'Elige una idea y conviértela en una acción esta semana.',
                                  'sources': sources})
        else:
            edu_generate_article(day)
    else:
        edu_generate_article(day)


async def send_education_content(bot, row, chat_id):
    kind = row['publish_kind'] or 'article'
    if kind == 'poll':
        payload = json.loads(row['payload'])
        return await bot.send_poll(chat_id=chat_id, question=payload['question'], options=payload['options'],
                                   is_anonymous=True, allows_multiple_answers=False, type='regular', read_timeout=120)
    if kind == 'summary':
        import html
        payload = json.loads(row['payload'])
        chat = await bot.get_chat(TARGET_CHAT_ID)
        if chat.username:
            base = 'https://t.me/' + chat.username
        elif str(chat.id).startswith('-100'):
            base = 'https://t.me/c/' + str(chat.id)[4:]
        else:
            raise RuntimeError('No se pudo construir el enlace al canal')
        pieces = [html.escape(row['title']), '', html.escape(payload['intro']), '']
        for source in payload['sources']:
            # URLs are derived from Telegram IDs, never supplied by the text model.
            url = base + '/' + str(int(source['message_id']))
            pieces.append('• <a href="' + url + '">' + html.escape(source['title'][:60]) + '</a>\n' + html.escape(source['learning']))
        pieces += ['', html.escape(payload['closing']), '', 'Johanna Alegría | JOHAALETRADER']
        text = '\n'.join(pieces)
        # Telegram counts visible text; this conservative bound includes markup too.
        if len(text.encode('utf-16-le')) // 2 > 4096:
            raise RuntimeError('Resumen excede el límite de Telegram')
        return await bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML', disable_web_page_preview=True, read_timeout=120)
    if not row['image']:
        return await bot.send_message(chat_id=chat_id, text=row['caption'], parse_mode=None,
                                      disable_web_page_preview=True, read_timeout=120)
    photo = io.BytesIO(row['image']); photo.name = 'educacion.jpg'
    return await bot.send_photo(chat_id=chat_id, photo=photo, caption=row['caption'],
                               parse_mode=None, write_timeout=120, read_timeout=120)


async def education_tick(context):
    now = datetime.now(EDU_TZ)
    schedule = education_schedule(now.date().isoformat())
    if not edu_enabled() or schedule is None:
        return
    minute = now.hour * 60 + now.minute
    if not schedule[0] <= minute < schedule[2]:  # Never dump old posts outside today's window.
        return
    await education_run(context)


async def education_run(context, recover=False):
    day = datetime.now(EDU_TZ).date().isoformat()
    if edu_claim(day):
        try:
            await asyncio.to_thread(edu_generate, day)
        except Exception as exc:
            with edu_db() as db:
                db.execute("UPDATE posts SET status='failed',updated=? WHERE day=? AND status='generating'",
                           (datetime.now(timezone.utc).timestamp(), day))
            edu_record_error(day, 'preparación', exc)
            await edu_alert(context.bot, '⚠️ No se pudo preparar la publicación: ' + edu_safe_error(exc) + '. Revisa /educacion_estado.')
            return
    row = edu_get(day)
    current = datetime.now(EDU_TZ)
    schedule = education_schedule(day)
    if not row or row['status'] != 'ready' or (not recover and
            (schedule is None or not schedule[1] <= current.hour * 60 + current.minute < schedule[2])):
        return
    # Persist the claim BEFORE contacting Telegram; an ambiguous timeout is not retried.
    with edu_db() as db:
        claimed = db.execute("UPDATE posts SET status='sending',updated=? WHERE day=? AND status='ready'",
                             (datetime.now(timezone.utc).timestamp(), day)).rowcount
    if not claimed:
        return
    try:
        message = await send_education_content(context.bot, row, TARGET_CHAT_ID)
    except Exception:
        with edu_db() as db:
            db.execute("UPDATE posts SET status='uncertain' WHERE day=?", (day,))
        await edu_alert(context.bot, '⚠️ El envío educativo no quedó confirmado. No se repetirá automáticamente para evitar duplicados. Revisa el canal y /educacion_estado.')
        return
    with edu_db() as db:
        db.execute("UPDATE posts SET status='sent',message_id=?,image=NULL,updated=? WHERE day=?",
                   (message.message_id, datetime.now(timezone.utc).timestamp(), day))
    notice = '✅ Publicación educativa enviada: ' + row['title']
    if row.get('last_error'):
        notice += '\nSe usó una alternativa: ' + row['last_error']
        if row['publish_kind'] == 'article' and not row['image']:
            notice += '\nEl artículo se publicó completo como texto porque la imagen no estuvo disponible.'
    await edu_alert(context.bot, notice)


async def education_test(update, context):
    # Preview only: a separate temporary record cannot replace the scheduled article.
    if not is_admin_private(update):
        return
    import uuid
    key = 'preview:' + datetime.now(EDU_TZ).date().isoformat() + ':' + uuid.uuid4().hex[:8]
    await update.message.reply_text('Estoy preparando una muestra de artículo e imagen. La recibirás aquí; no se publicará en el canal.')
    try:
        if not edu_claim(key):
            return
        await asyncio.to_thread(edu_generate_article, key)
        row = edu_get(key)
        if not row or row['status'] != 'ready':
            raise RuntimeError('No se pudo preparar la muestra')
        await send_education_content(context.bot, row, ADMIN_ID)
        if row.get('last_error'):
            await update.message.reply_text('La muestra usó respaldo: ' + row['last_error'])
        else:
            await update.message.reply_text('Muestra creada con contenido nuevo de la IA y firma fija. La programación del canal sigue igual.')
    except Exception as exc:
        await update.message.reply_text('No se pudo completar la prueba: ' + edu_safe_error(exc))
    finally:
        with edu_db() as db:
            db.execute("DELETE FROM posts WHERE day=? AND day LIKE 'preview:%'", (key,))


async def education_retry(update, context):
    # Explicit recovery only for TODAY. The persistent send claim still prevents duplicates.
    if not is_admin_private(update):
        return
    if not edu_enabled():
        await update.message.reply_text('La educación automática está desactivada.')
        return
    day = datetime.now(EDU_TZ).date().isoformat()
    with edu_db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT status FROM posts WHERE day=?', (day,)).fetchone()
        if not row or row[0] not in ('failed', 'ready'):
            await update.message.reply_text('Solo se puede recuperar la publicación de hoy si está fallida o lista. No se repetirá un envío confirmado o incierto.')
            return
        if row[0] == 'failed':
            db.execute("UPDATE posts SET attempts=0,updated=0,last_error=NULL WHERE day=? AND status='failed'", (day,))
    await update.message.reply_text('Voy a recuperar la publicación de hoy y enviarla al canal una sola vez.')
    await education_run(context, recover=True)


async def education_status(update, context):
    if not is_admin_private(update):
        return
    with edu_db() as db:
        rows = db.execute('SELECT day,status,title,last_error FROM posts ORDER BY updated DESC LIMIT 8').fetchall()
    text = ('Educación automática: ' + ('ACTIVA' if edu_enabled() else 'INACTIVA') +
            '\nArtículos: martes y jueves · 11:00 a. m. Colombia\nEncuestas: miércoles · 3:30 p. m. y sábado · 11:00 a. m.\nResumen: primer martes del mes · 11:00 a. m. (reemplaza artículo)\n' +
            'Saludos: ' + ('ACTIVOS' if greeting_enabled() and edu_enabled() else 'INACTIVOS') +
            '\nLunes a sábado 8:00 a. m. · Domingo 10:00 a. m. Colombia\n' +
            '\n'.join(f'{d}: {s} — {t or "sin título"}' + (f'\nMotivo: {e}' if e else '') for d, s, t, e in rows))
    await update.message.reply_text(text)


async def education_preview(update, context):
    if not is_admin_private(update):
        return
    row = edu_get(datetime.now(EDU_TZ).date().isoformat())
    if row and row['status'] == 'ready':
        await send_education_content(context.bot, row, ADMIN_ID)
    else:
        await update.message.reply_text('No hay una publicación preparada pendiente. La preparación comienza a las 3:20 p. m. los miércoles y a las 10:50 a. m. los martes, jueves y sábados.')


# --------- Saludos diarios automáticos ---------
def greeting_enabled():
    return os.getenv('GREETING_ENABLED', 'true').lower() in ('true', '1', 'yes')


def greeting_generate(key, sunday):
    with edu_db() as db:
        history = db.execute("SELECT caption FROM posts WHERE day LIKE 'greeting:%' AND status='sent' ORDER BY updated DESC LIMIT 60").fetchall()
    # Rotate scenarios and occasional trading focus using confirmed greetings only.
    with edu_db() as db:
        index = db.execute("SELECT COUNT(*) FROM posts WHERE day LIKE 'greeting:%' AND status='sent'").fetchone()[0]
    scenes = (
        'terraza de una casa contemporánea espectacular con piscina y jardín',
        'playa tropical con agua cristalina y luz de mañana',
        'vista de una ciudad desde el balcón de un apartamento elegante',
        'casa hermosa entre montañas, con ventanales y vistas abiertas',
        'río transparente entre vegetación natural',
        'interior luminoso de una casa hermosa, con materiales naturales',
        'cascada real rodeada de bosque',
        'centro comercial moderno con arquitectura real y luz natural',
        'panorama de montañas con cielo despejado',
        'patio de una residencia de lujo con piscina y vista al mar',
        'escritorio junto a una ventana: computador con gráfico de trading en pantalla, taza de café, plato de desayuno con frutas frescas y vista urbana',
        'mesa de desayuno en una terraza con flores, jardín verde y piscina azul',
    )
    scene = scenes[index % len(scenes)]
    trading = not sunday and index % 3 == 2
    theme = ('Domingo con alegría y energía: reconocer aprendizajes de la semana y animar '
             'a preparar un primer paso concreto para el lunes. Sin inventar resultados.' if sunday else
             'Buenos días con alegría, impulso y energía para ponerse en marcha y avanzar hoy.')
    theme += (' Incluye una referencia breve al trading: preparación, disciplina, gestión '
              'del riesgo o seguir el plan; nunca urgencia por operar ni ganancias prometidas.' if trading else
              ' Motivación para la vida diaria; no es necesario mencionar trading.')
    instruction = ('Escribe para JT TRADERS TEAMS en español, tuteando y SIN asignar género a quien lee. '
        'Tono alegre, electrizante, vital, cercano y muy positivo: que despierte ganas de actuar. '
        'Usa entusiasmo natural, exclamaciones breves y frases como ¡Vamos con toda! sin repetir siempre la misma. '
        'Frases concretas, ritmo ágil y una acción pequeña que se pueda empezar hoy. '
        'Evita mensajes contemplativos o religiosos, bendiciones, sermones, calma, serenidad, '
        'respira profundo y clichés repetidos de luz y gratitud. Sin gritos ni presión. '
        'No culpabilices a quien tiene poca energía ni sugieras que la motivación cura depresión. '
        'Nada de miedo, culpa, ventas ni promesas financieras o de riqueza. '
        'Mensaje breve de 180 a 380 caracteres, 2 párrafos cortos y 2 o 3 emojis '
        'de energía como ☀️, ⚡, 🚀 o 💪 distribuidos al comienzo de párrafos o en el cierre. '
        'Termina con una invitación concreta, alegre y positiva a dar un primer paso. '
        'Sin llamados a depositar ni a operar. No inventes citas ni experiencias personales. '
        'Sin markdown, enlaces, hashtags ni firma. '
        'Devuelve JSON con title (máximo 45 caracteres), body e image_prompt. '
        'image_prompt describe una fotografía profesional del escenario asignado, sin personas, '
        'con colores naturales variados, vegetación, detalles vivos y luz blanca de mañana; '
        'evita ambientes monocromáticos beige, marrones o sepia. No impongas los colores de la marca. '
        'Las casas de lujo son escenarios, nunca una promesa de resultados del trading. '
        'Varía composición, detalles y enfoque respecto al historial. Título sin emojis.')
    for _ in range(2):
        response = edu_api('chat/completions', {
            'model': os.getenv('EDU_TEXT_MODEL', 'gpt-4.1-mini'),
            'messages': [{'role': 'system', 'content': instruction},
                         {'role': 'user', 'content': json.dumps({'tema': theme, 'escenario': scene, 'historial': history}, ensure_ascii=False)}],
            'response_format': {'type': 'json_object'}, 'max_tokens': 600})
        obj = json.loads(response['choices'][0]['message']['content'])
        title = str(obj.get('title', '')).strip()
        body = str(obj.get('body', '')).strip()
        visual = str(obj.get('image_prompt', '')).strip()
        caption = title + '\n\n' + body + '\n\nJohanna Alegría | JOHAALETRADER'
        if (title and len(title) <= 45 and 180 <= len(body) <= 380 and visual and
                len(caption.encode('utf-16-le')) // 2 <= 1024 and
                all(body.casefold() not in c.casefold() for (c,) in history)):
            break
    else:
        raise RuntimeError('Saludo fuera de los límites de formato')
    generated = edu_reference_image({
        'model': os.getenv('EDU_IMAGE_MODEL', 'gpt-image-1'),
        'prompt': ('Crea una imagen NUEVA luminosa y motivadora para un saludo de buenos días. '
            'Fotografía hiperrealista del escenario asignado, atractiva, alegre y luminosa. '
            'Paleta natural del lugar; arquitectura y texturas creíbles. '
            'Sin personas, firmas, marcas ni textos. Si hay un computador, permite un gráfico '
            'de trading realista dentro de su pantalla. No escribas ningún título ni texto. '
            '\nEscenario asignado: ' + scene + '\nEscena: ' + visual),
        'size': '1024x1024', 'quality': 'medium', 'n': 1, '_greeting': True})
    background = base64.b64decode(generated['data'][0]['b64_json'], validate=True)
    image = edu_apply_signature(background, greeting=True)
    if not image or len(image) > 10 * 1024 * 1024:
        raise RuntimeError('Imagen de saludo inválida')
    with edu_db() as db:
        db.execute("UPDATE posts SET status='ready',title=?,caption=?,image=?,category=?,updated=? WHERE day=? AND status='generating'",
                   (title, caption, image, 'domingo' if sunday else 'buenos días', datetime.now(timezone.utc).timestamp(), key))


async def greeting_test(update, context):
    # Private preview with isolated storage; no scheduled send or history mutation.
    if not is_admin_private(update):
        return
    import uuid
    key = 'preview:greeting:' + uuid.uuid4().hex
    await update.message.reply_text('Estoy preparando un saludo con imagen. Lo recibirás aquí por privado.')
    try:
        if not edu_claim(key):
            return
        sunday = 'domingo' in (context.args or [])
        await asyncio.to_thread(greeting_generate, key, sunday)
        row = edu_get(key)
        if not row or row['status'] != 'ready':
            raise RuntimeError('No se pudo preparar la muestra')
        photo = io.BytesIO(row['image'])
        photo.name = 'saludo.jpg'
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo, caption=row['caption'],
                                     parse_mode=None, read_timeout=120, write_timeout=120)
        await update.message.reply_text('Muestra enviada. Los horarios del canal siguen igual.')
    except Exception as exc:
        await update.message.reply_text('No se pudo completar la prueba: ' + edu_safe_error(exc))
    finally:
        with edu_db() as db:
            db.execute("DELETE FROM posts WHERE day=? AND day LIKE 'preview:greeting:%'", (key,))


async def greeting_tick(context):
    if not edu_enabled() or not greeting_enabled():
        return
    now = datetime.now(EDU_TZ)
    sunday = now.weekday() == 6
    target = 600 if sunday else 480
    minute = now.hour * 60 + now.minute
    if not target - 10 <= minute < target + 30:
        return
    key = 'greeting:' + now.date().isoformat()
    if edu_claim(key):
        try:
            await asyncio.to_thread(greeting_generate, key, sunday)
        except Exception as exc:
            with edu_db() as db:
                db.execute("UPDATE posts SET status='failed',updated=? WHERE day=? AND status='generating'",
                           (datetime.now(timezone.utc).timestamp(), key))
            edu_record_error(key, 'saludo', exc)
            await edu_alert(context.bot, '⚠️ No se pudo crear el saludo: ' + edu_safe_error(exc) + '. Hasta 3 intentos; revisa /educacion_estado.')
            return
    now = datetime.now(EDU_TZ)
    row = edu_get(key)
    if not row or row['status'] != 'ready' or not target <= now.hour * 60 + now.minute < target + 30:
        return
    with edu_db() as db:
        claimed = db.execute("UPDATE posts SET status='sending',updated=? WHERE day=? AND status='ready'",
                             (datetime.now(timezone.utc).timestamp(), key)).rowcount
    if not claimed:
        return
    try:
        photo = io.BytesIO(row['image']); photo.name = 'saludo.png'
        message = await context.bot.send_photo(chat_id=TARGET_CHAT_ID, photo=photo,
            caption=row['caption'], parse_mode=None, write_timeout=120, read_timeout=120)
    except Exception:
        with edu_db() as db:
            db.execute("UPDATE posts SET status='uncertain' WHERE day=?", (key,))
        await edu_alert(context.bot, '⚠️ El saludo no quedó confirmado. No se repetirá automáticamente para evitar duplicados; revisa el canal.')
        return
    with edu_db() as db:
        db.execute("UPDATE posts SET status='sent',message_id=?,image=NULL,updated=? WHERE day=?",
                   (message.message_id, datetime.now(timezone.utc).timestamp(), key))
    await edu_alert(context.bot, '✅ Saludo automático enviado: ' + row['title'])


async def education_startup(application):
    if not edu_enabled():
        return
    if not os.getenv('OPENAI_API_KEY'):
        await edu_alert(application.bot, '⚠️ Educación automática inactiva: falta OPENAI_API_KEY. El posteo manual sigue disponible.')
        return
    try:
        edu_db().close()
    except Exception:
        await edu_alert(application.bot, '⚠️ No se pudo abrir el registro educativo. Revisa EDU_DATA_DIR y el volumen de Railway.')
        return
    application.job_queue.run_repeating(education_tick, interval=30, first=2,
        name='education_automatic', job_kwargs={'max_instances': 1, 'coalesce': True})
    if greeting_enabled():
        application.job_queue.run_repeating(greeting_tick, interval=30, first=3,
            name='greetings_automatic', job_kwargs={'max_instances': 1, 'coalesce': True})
    logging.info('Artículos mar/jue, encuesta sáb, resumen primer martes 11:00; encuesta miércoles 15:30; saludos lun-sáb 08:00 y domingo 10:00 Colombia')


# --------- Main ---------
def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

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

    application = ApplicationBuilder().token(token).post_init(education_startup).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("educacion_estado", education_status))
    application.add_handler(CommandHandler("educacion_vista", education_preview))
    application.add_handler(CommandHandler("educacion_reintentar", education_retry))
    application.add_handler(CommandHandler("educacion_prueba", education_test))
    application.add_handler(CommandHandler("saludo_prueba", greeting_test))
    application.add_handler(CallbackQueryHandler(on_button))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, on_message))
    application.add_error_handler(error_handler)

    application.run_polling()


if __name__ == "__main__":
    main()
