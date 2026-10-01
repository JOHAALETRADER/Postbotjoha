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


# --------- Main ---------
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
