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

# En Railway debes configurar la variable de entorno:
# POST_BOT_TOKEN = <token_de_este_bot>
TOKEN = os.environ.get("POST_BOT_TOKEN")

# Canal donde se publicará
CHANNEL_USERNAME = "@JohaaleTrader_es"

# Solo tú puedes usar este panel
ADMIN_ID = 5958164558  # tu ID

# Archivo donde se guardan los botones por defecto
DEFAULT_BUTTONS_FILE = "default_buttons.json"

# Estados de usuario y borradores
user_states: dict[int, str] = {}
drafts: dict[int, dict] = {}

# Info de la última publicación enviada al canal
last_post_message_id: int | None = None
last_post_info: dict | None = None  # {"type": "text|photo|video|audio", "buttons_data": [...]}

# Índice para edición de botón individual
edit_button_index: dict[int, int] = {}

# Lista de botones guardados
default_buttons: list[dict] = []


# ======================================================
#            CARGA / GUARDADO DE BOTONES
# ======================================================

def load_default_buttons():
    """Carga los botones por defecto desde disco."""
    global default_buttons
    try:
        with open(DEFAULT_BUTTONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                default_buttons = [b for b in data if "label" in b and "url" in b]
            else:
                default_buttons = []
    except FileNotFoundError:
        default_buttons = []
    except Exception:
        default_buttons = []


def save_default_buttons():
    """Guarda los botones por defecto en disco."""
    try:
        with open(DEFAULT_BUTTONS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_buttons, f, ensure_ascii=False, indent=2)
    except Exception:
        # No queremos tumbar el bot si hay un error de disco
        pass


def parse_buttons_from_text(text: str):
    """
    Convierte texto a lista de botones.
    Formato esperado por línea:
    Texto del botón - https://enlace
    """
    buttons = []
    for line in text.splitlines():
        line = line.strip()
        if not line or "-" not in line:
            continue
        label, url = line.split("-", 1)
        label = label.strip()
        url = url.strip()
        if label and url:
            buttons.append({"label": label, "url": url})
    return buttons


def buttons_list_to_markup(button_list: list[dict]) -> InlineKeyboardMarkup | None:
    """Convierte lista [{'label','url'}] a InlineKeyboardMarkup."""
    rows: list[list[InlineKeyboardButton]] = []
    for b in button_list:
        rows.append([InlineKeyboardButton(b["label"], url=b["url"])])
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


# ======================================================
#               MENÚ PRINCIPAL
# ======================================================

def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        ["📝 Crear publicación"],
        ["✏️ Editar publicación"],
        ["🧷 Editar botones guardados"],
        ["⏰ Programar publicación"],
        ["❌ Cancelar"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ======================================================
#                   HELPERS GENERALES
# ======================================================

def extract_content_from_message(message) -> dict | None:
    """Extrae el contenido (tipo + file_id/text) desde un mensaje."""
    if message.photo:
        return {
            "type": "photo",
            "file_id": message.photo[-1].file_id,
            "caption": message.caption or "",
        }
    if message.video:
        return {
            "type": "video",
            "file_id": message.video.file_id,
            "caption": message.caption or "",
        }
    if message.audio:
        return {
            "type": "audio",
            "file_id": message.audio.file_id,
        }
    if message.text:
        return {
            "type": "text",
            "text": message.text,
        }
    return None


async def send_preview_for_draft(user_id: int, bot) -> None:
    """Manda la vista previa completa (contenido + botones) al admin."""
    draft = drafts.get(user_id)
    if not draft:
        return

    chat_id = ADMIN_ID
    markup = draft.get("buttons")

    if draft["type"] == "text":
        await bot.send_message(chat_id, draft["text"], reply_markup=markup)
    elif draft["type"] == "photo":
        await bot.send_photo(
            chat_id,
            draft["file_id"],
            caption=draft.get("caption", ""),
            reply_markup=markup,
        )
    elif draft["type"] == "video":
        await bot.send_video(
            chat_id,
            draft["file_id"],
            caption=draft.get("caption", ""),
            reply_markup=markup,
        )
    elif draft["type"] == "audio":
        await bot.send_audio(chat_id, draft["file_id"], reply_markup=markup)


async def start_button_flow_for_new_draft(
    user_id: int, context: ContextTypes.DEFAULT_TYPE, chat_id: int
) -> None:
    """
    Una vez tenemos contenido (texto/foto/video/audio) en drafts[user_id],
    preguntamos cómo manejar los botones.
    """
    global default_buttons

    if default_buttons:
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "✅ Usar botones guardados", callback_data="use_saved_buttons"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🆕 Usar nuevos enlaces", callback_data="use_new_buttons"
                    )
                ],
                [
                    InlineKeyboardButton("🚫 Sin botones", callback_data="use_no_buttons")
                ],
                [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")],
            ]
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Contenido recibido.\n"
                "¿Cómo quieres manejar los botones?"
            ),
            reply_markup=keyboard,
        )
        user_states[user_id] = "CHOOSE_BUTTON_SOURCE"
    else:
        user_states[user_id] = "WAITING_BUTTONS"
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Agrega los enlaces (uno por línea).\n"
                "Formato: Texto - https://enlace"
            ),
        )


def build_view_publication_button(message_id: int) -> InlineKeyboardMarkup:
    chan_link = CHANNEL_USERNAME.lstrip("@")
    url = f"https://t.me/{chan_link}/{message_id}"
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔗 Ver publicación", url=url)]]
    )


# ======================================================
#                        START
# ======================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        if update.message:
            await update.message.reply_text("Este bot es solo para el administrador.")
        return

    load_default_buttons()
    user_states[user_id] = "IDLE"
    drafts[user_id] = {}

    if update.message:
        await update.message.reply_text(
            "Panel listo. Selecciona una opción:",
            reply_markup=get_main_menu_keyboard(),
        )


# ======================================================
#       MENÚ EDICIÓN DE PUBLICACIONES (OPCIÓN C)
# ======================================================

async def show_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✏️ Editar borrador", callback_data="edit_draft"
                )
            ],
            [
                InlineKeyboardButton(
                    "📝 Editar publicación enviada", callback_data="edit_last"
                )
            ],
            [
                InlineKeyboardButton(
                    "♻️ Rehacer desde cero", callback_data="edit_reset"
                )
            ],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")],
        ]
    )
    if update.message:
        await update.message.reply_text(
            "¿Qué deseas hacer?", reply_markup=keyboard
        )
    user_states[update.effective_user.id] = "EDIT_MENU"


# ======================================================
#        MENÚ BOTONES GUARDADOS
# ======================================================

async def show_buttons_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📋 Ver botones actuales", callback_data="btn_view"
                )
            ],
            [
                InlineKeyboardButton(
                    "✏️ Reemplazar todos", callback_data="btn_replace"
                )
            ],
            [
                InlineKeyboardButton(
                    "➕ Agregar nuevos", callback_data="btn_add"
                )
            ],
            [
                InlineKeyboardButton(
                    "✏️ / 🗑️ Editar o eliminar uno",
                    callback_data="btn_editone_menu",
                )
            ],
            [
                InlineKeyboardButton(
                    "🗑️ Eliminar todos", callback_data="btn_clear"
                )
            ],
            [InlineKeyboardButton("🔙 Volver", callback_data="btn_back")],
        ]
    )
    if update.message:
        await update.message.reply_text(
            "Menú de botones guardados:", reply_markup=keyboard
        )
    user_states[update.effective_user.id] = "EDIT_BUTTONS_MENU"


# ======================================================
#               MANEJO DE MENSAJES
# ======================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user_id = update.effective_user.id
    message = update.message
    text = message.text or ""
    state = user_states.get(user_id, "IDLE")

    if user_id != ADMIN_ID:
        # Silencioso para otros usuarios
        return

    # CANCELAR GLOBAL (botón del menú)
    if text.strip().startswith("❌"):
        user_states[user_id] = "IDLE"
        drafts[user_id] = {}
        await message.reply_text(
            "❌ Proceso cancelado.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # ========================
    # MENÚ PRINCIPAL
    # ========================

    if state == "IDLE":
        if text == "📝 Crear publicación":
            drafts[user_id] = {}
            user_states[user_id] = "WAITING_CONTENT"
            await message.reply_text(
                "Envíame el contenido (texto, foto, video o audio)."
            )
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
            await message.reply_text(
                "Envíame el contenido que quieres programar."
            )
            return

    # ==================================================
    #   CONTENIDO NUEVO (CREAR / PROGRAMAR / EDITAR BORRADOR)
    # ==================================================

    if state in ["WAITING_CONTENT", "WAITING_CONTENT_SCHEDULE", "EDITING_DRAFT"]:
        content = extract_content_from_message(message)
        if not content:
            await message.reply_text("Formato no soportado.")
            return

        # Si venía de programar, mantenemos la marca
        if state == "WAITING_CONTENT_SCHEDULE":
            content["schedule"] = True

        drafts[user_id] = content
        await start_button_flow_for_new_draft(
            user_id, context, message.chat_id
        )
        return

    # ==================================================
    #   EDICIÓN DE PUBLICACIÓN ENVIADA (OPCIÓN C)
    # ==================================================

    if state == "EDIT_LAST_WAIT_CONTENT":
        global last_post_message_id, last_post_info

        if last_post_message_id is None or last_post_info is None:
            await message.reply_text(
                "No tengo ninguna publicación reciente para editar."
            )
            user_states[user_id] = "IDLE"
            return

        new_content = extract_content_from_message(message)
        if not new_content:
            await message.reply_text("Formato no soportado.")
            return

        prev_type = last_post_info.get("type")
        prev_buttons_data = last_post_info.get("buttons_data", [])
        markup = buttons_list_to_markup(prev_buttons_data)

        # Caso 1: envías SOLO TEXTO
        if new_content["type"] == "text":
            new_text = new_content["text"]

            if prev_type == "text":
                # Editar texto directamente
                await context.bot.edit_message_text(
                    chat_id=CHANNEL_USERNAME,
                    message_id=last_post_message_id,
                    text=new_text,
                    reply_markup=markup,
                )
                last_post_info["text"] = new_text
                await message.reply_text(
                    "✅ Publicación actualizada.",
                    reply_markup=build_view_publication_button(
                        last_post_message_id
                    ),
                )
                user_states[user_id] = "IDLE"
                return

            if prev_type in ["photo", "video"]:
                # Editar solo caption
                await context.bot.edit_message_caption(
                    chat_id=CHANNEL_USERNAME,
                    message_id=last_post_message_id,
                    caption=new_text,
                    reply_markup=markup,
                )
                last_post_info["caption"] = new_text
                await message.reply_text(
                    "✅ Caption actualizado.",
                    reply_markup=build_view_publication_button(
                        last_post_message_id
                    ),
                )
                user_states[user_id] = "IDLE"
                return

            if prev_type == "audio":
                await message.reply_text(
                    "Por ahora esta publicación no se puede editar. "
                    "Mejor reházla desde cero con 'Crear publicación'."
                )
                user_states[user_id] = "IDLE"
                return

        # Caso 2: envías FOTO / VIDEO / AUDIO NUEVO
        # Pedimos confirmación para borrar y rehacer
        if new_content["type"] in ["photo", "video", "audio"]:
            drafts[user_id] = {"pending_media": new_content}
            user_states[user_id] = "CONFIRM_REBUILD_MEDIA"

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🗑 Sí, eliminar y rehacer",
                            callback_data="rebuild_yes",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "❌ No, cancelar", callback_data="rebuild_no"
                        )
                    ],
                ]
            )
            await message.reply_text(
                "Esta publicación es multimedia.\n"
                "Para cambiarla debo eliminar la publicación del canal y crearla de nuevo.\n"
                "¿Quieres hacerlo?",
                reply_markup=keyboard,
            )
            return

    # ==================================================
    #   EDICIÓN DE BOTONES: ELEGIR UNO
    # ==================================================

    if state == "EDIT_BUTTONS_CHOOSE_ONE":
        try:
            idx = int(text.strip()) - 1
        except ValueError:
            await message.reply_text(
                "Envía solo el número del botón que quieres editar o eliminar."
            )
            return

        if idx < 0 or idx >= len(default_buttons):
            await message.reply_text("Número fuera de rango.")
            return

        edit_button_index[user_id] = idx
        user_states[user_id] = "EDIT_BUTTONS_CHOOSE_ACTION"
        btn = default_buttons[idx]
        await message.reply_text(
            f"Botón {idx + 1}:\n{btn['label']} - {btn['url']}\n\n"
            "Escribe 'editar' para cambiarlo o 'eliminar' para borrarlo."
        )
        return

    if state == "EDIT_BUTTONS_CHOOSE_ACTION":
        idx = edit_button_index.get(user_id)
        if idx is None or idx < 0 or idx >= len(default_buttons):
            await message.reply_text("No tengo un botón seleccionado.")
            user_states[user_id] = "IDLE"
            return

        lower = text.strip().lower()
        if lower.startswith("editar"):
            user_states[user_id] = "EDIT_BUTTONS_EDIT_ONE"
            await message.reply_text(
                "Envíame el nuevo botón en formato:\nTexto - https://enlace"
            )
            return
        elif lower.startswith("eliminar"):
            removed = default_buttons.pop(idx)
            save_default_buttons()
            user_states[user_id] = "IDLE"
            await message.reply_text(
                f"🗑️ Botón eliminado:\n{removed['label']} - {removed['url']}",
                reply_markup=get_main_menu_keyboard(),
            )
            return
        else:
            await message.reply_text(
                "Responde solo 'editar' o 'eliminar'."
            )
            return

    if state == "EDIT_BUTTONS_EDIT_ONE":
        idx = edit_button_index.get(user_id)
        if idx is None or idx < 0 or idx >= len(default_buttons):
            await message.reply_text("No tengo un botón seleccionado.")
            user_states[user_id] = "IDLE"
            return

        new_button = parse_buttons_from_text(text)
        if not new_button:
            await message.reply_text(
                "Formato inválido. Usa: Texto - https://enlace"
            )
            return

        default_buttons[idx] = new_button[0]
        save_default_buttons()
        user_states[user_id] = "IDLE"
        await message.reply_text(
            "✅ Botón actualizado.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # ==================================================
    #   ESPERANDO BOTONES (CREAR / REEMPLAZAR / AÑADIR)
    # ==================================================

    if state in ["WAITING_BUTTONS", "EDIT_BUTTONS_REPLACE_ALL", "EDIT_BUTTONS_ADD"]:
        btns = parse_buttons_from_text(text)
        if not btns:
            await message.reply_text(
                "No encontré enlaces válidos.\n"
                "Formato: Texto - https://enlace"
            )
            return

        # Botones para el borrador actual
        if state == "WAITING_BUTTONS":
            drafts[user_id]["buttons_data"] = btns
            drafts[user_id]["buttons"] = buttons_list_to_markup(btns)

            # Vista previa completa
            await send_preview_for_draft(user_id, context.bot)

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "💾 Guardar como predeterminados",
                            callback_data="save_buttons_yes",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "No guardar", callback_data="save_buttons_no"
                        )
                    ],
                ]
            )
            await message.reply_text(
                "¿Guardar estos botones como predeterminados?",
                reply_markup=keyboard,
            )
            user_states[user_id] = "ASK_SAVE_BUTTONS"
            return

        # Edición global de botones guardados
        if state == "EDIT_BUTTONS_REPLACE_ALL":
            default_buttons.clear()
            default_buttons.extend(btns)
            save_default_buttons()
            user_states[user_id] = "IDLE"
            await message.reply_text(
                "✅ Botones reemplazados.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        if state == "EDIT_BUTTONS_ADD":
            default_buttons.extend(btns)
            save_default_buttons()
            user_states[user_id] = "IDLE"
            await message.reply_text(
                "✅ Botones añadidos.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

    # ==================================================
    #  FECHA/HORA PARA PROGRAMACIÓN
    # ==================================================

    if state == "WAITING_DATETIME":
        text_clean = text.strip()
        try:
            dt = datetime.strptime(text_clean, "%Y-%m-%d %H:%M")
        except ValueError:
            await message.reply_text(
                "Formato inválido. Usa: 2025-12-02 18:30"
            )
            return

        draft = drafts.get(user_id)
        if not draft:
            await message.reply_text("No tengo borrador.")
            user_states[user_id] = "IDLE"
            return

        async def send_later(job_context: ContextTypes.DEFAULT_TYPE):
            """Callback del JobQueue para enviar la publicación programada."""
            global last_post_message_id, last_post_info
            bot = job_context.bot
            ch_name = CHANNEL_USERNAME
            buttons = draft.get("buttons")
            buttons_data = draft.get("buttons_data", [])

            if draft["type"] == "text":
                msg = await bot.send_message(
                    ch_name, draft["text"], reply_markup=buttons
                )
            elif draft["type"] == "photo":
                msg = await bot.send_photo(
                    ch_name,
                    draft["file_id"],
                    caption=draft.get("caption", ""),
                    reply_markup=buttons,
                )
            elif draft["type"] == "video":
                msg = await bot.send_video(
                    ch_name,
                    draft["file_id"],
                    caption=draft.get("caption", ""),
                    reply_markup=buttons,
                )
            elif draft["type"] == "audio":
                msg = await bot.send_audio(
                    ch_name, draft["file_id"], reply_markup=buttons
                )
            else:
                return

            last_post_message_id = msg.message_id
            last_post_info = {
                "type": draft["type"],
                "buttons_data": buttons_data,
            }

            # Aviso al admin con botón "Ver publicación"
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text="✅ Publicación programada enviada al canal.",
                    reply_markup=build_view_publication_button(msg.message_id),
                )
            except Exception:
                pass

        delay = (dt - datetime.now()).total_seconds()
        if delay <= 0:
            await message.reply_text("La fecha/hora ya pasó.")
            return

        context.application.job_queue.run_once(send_later, delay)

        user_states[user_id] = "IDLE"
        drafts[user_id] = {}

        await message.reply_text(
            f"⏳ Publicación programada para {dt}.",
            reply_markup=get_main_menu_keyboard(),
        )
        return


# ======================================================
#              CALLBACKS INLINE
# ======================================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_post_message_id, last_post_info

    query = update.callback_query
    if not query:
        return

    user_id = query.from_user.id
    data = query.data

    await query.answer()

    if user_id != ADMIN_ID:
        return

    draft = drafts.get(user_id, {})
    state = user_states.get(user_id, "IDLE")

    # CANCELAR DESDE INLINE
    if data == "cancel":
        drafts[user_id] = {}
        user_states[user_id] = "IDLE"
        await query.message.reply_text(
            "❌ Proceso cancelado.", reply_markup=get_main_menu_keyboard()
        )
        return

    # ===================================
    #  MENÚ EDICIÓN PUBLICACIÓN (OPCIÓN C)
    # ===================================

    if state == "EDIT_MENU":
        if data == "edit_draft":
            if not drafts.get(user_id):
                await query.message.reply_text(
                    "No hay borrador para editar. Usa 'Crear publicación'."
                )
                user_states[user_id] = "IDLE"
                return
            user_states[user_id] = "EDITING_DRAFT"
            await query.message.reply_text(
                "Envía el nuevo contenido para el borrador."
            )
            return

        if data == "edit_last":
            if last_post_message_id is None or last_post_info is None:
                await query.message.reply_text(
                    "No tengo ninguna publicación reciente para editar.\n"
                    "Primero envía algo con 'Crear publicación'."
                )
                user_states[user_id] = "IDLE"
                return

            user_states[user_id] = "EDIT_LAST_WAIT_CONTENT"
            await query.message.reply_text(
                "Envía el nuevo contenido para la publicación.\n"
                "- Si envías solo TEXTO, se actualizará el texto/caption.\n"
                "- Si envías una nueva FOTO/VIDEO/AUDIO, te preguntaré "
                "si quieres eliminar la publicación anterior y rehacerla desde cero."
            )
            return

        if data == "edit_reset":
            drafts[user_id] = {}
            user_states[user_id] = "WAITING_CONTENT"
            await query.message.reply_text(
                "Vamos a rehacer la publicación. Envíame el contenido."
            )
            return

    # ===================================
    #  MENÚ BOTONES GUARDADOS
    # ===================================

    if state == "EDIT_BUTTONS_MENU":
        if data == "btn_view":
            if not default_buttons:
                await query.message.reply_text("No hay botones guardados.")
            else:
                lines = [
                    f"{i+1}. {b['label']} - {b['url']}"
                    for i, b in enumerate(default_buttons)
                ]
                await query.message.reply_text(
                    "Botones guardados:\n" + "\n".join(lines)
                )
            return

        if data == "btn_replace":
            user_states[user_id] = "EDIT_BUTTONS_REPLACE_ALL"
            await query.message.reply_text(
                "Envía todos los botones NUEVOS (uno por línea):\n"
                "Texto - https://enlace"
            )
            return

        if data == "btn_add":
            user_states[user_id] = "EDIT_BUTTONS_ADD"
            await query.message.reply_text(
                "Envía los botones a AÑADIR (uno por línea):\n"
                "Texto - https://enlace"
            )
            return

        if data == "btn_editone_menu":
            if not default_buttons:
                await query.message.reply_text("No hay botones guardados.")
                return
            lines = [
                f"{i+1}. {b['label']} - {b['url']}"
                for i, b in enumerate(default_buttons)
            ]
            await query.message.reply_text(
                "Botones actuales:\n"
                + "\n".join(lines)
                + "\n\nEnvía el NÚMERO del botón que quieres editar o eliminar."
            )
            user_states[user_id] = "EDIT_BUTTONS_CHOOSE_ONE"
            return

        if data == "btn_clear":
            default_buttons.clear()
            save_default_buttons()
            await query.message.reply_text(
                "🗑️ Se eliminaron todos los botones guardados."
            )
            user_states[user_id] = "IDLE"
            return

        if data == "btn_back":
            user_states[user_id] = "IDLE"
            await query.message.reply_text(
                "Volviendo al menú principal.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

    # ===================================
    #  ELECCIÓN FUENTE DE BOTONES
    # ===================================

    if state == "CHOOSE_BUTTON_SOURCE":
        if data == "use_saved_buttons":
            if not default_buttons:
                await query.message.reply_text(
                    "No hay botones guardados."
                )
                user_states[user_id] = "WAITING_BUTTONS"
                await query.message.reply_text(
                    "Agrega los enlaces (uno por línea)."
                )
                return

            drafts[user_id]["buttons_data"] = list(default_buttons)
            drafts[user_id]["buttons"] = buttons_list_to_markup(
                default_buttons
            )

            # Vista previa
            await send_preview_for_draft(user_id, context.bot)

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📤 Publicar ahora", callback_data="publish_now"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "⏳ Programar", callback_data="schedule"
                        )
                    ],
                    [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")],
                ]
            )
            await query.message.reply_text(
                "Preview listo. Elige una opción:", reply_markup=keyboard
            )
            user_states[user_id] = "CONFIRM"
            return

        if data == "use_new_buttons":
            user_states[user_id] = "WAITING_BUTTONS"
            await query.message.reply_text(
                "Agrega los enlaces (uno por línea).\n"
                "Formato: Texto - https://enlace"
            )
            return

        if data == "use_no_buttons":
            drafts[user_id]["buttons"] = None
            drafts[user_id]["buttons_data"] = []

            # Vista previa
            await send_preview_for_draft(user_id, context.bot)

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📤 Publicar ahora", callback_data="publish_now"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "⏳ Programar", callback_data="schedule"
                        )
                    ],
                    [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")],
                ]
            )
            await query.message.reply_text(
                "Preview listo. Elige una opción:", reply_markup=keyboard
            )
            user_states[user_id] = "CONFIRM"
            return

    # ===================================
    #  GUARDAR BOTONES NUEVOS COMO PREDETERMINADOS
    # ===================================

    if state == "ASK_SAVE_BUTTONS":
        if data == "save_buttons_yes":
            default_buttons.clear()
            default_buttons.extend(drafts[user_id].get("buttons_data", []))
            save_default_buttons()
            await query.message.reply_text("✔ Botones guardados.")
        elif data == "save_buttons_no":
            await query.message.reply_text("No se guardaron los botones.")

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📤 Publicar ahora", callback_data="publish_now"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⏳ Programar", callback_data="schedule"
                    )
                ],
                [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")],
            ]
        )
        await query.message.reply_text(
            "Preview listo. Elige una opción:", reply_markup=keyboard
        )
        user_states[user_id] = "CONFIRM"
        return

    # ===================================
    #  CONFIRMACIÓN PARA REHACER MULTIMEDIA
    # ===================================

    if state == "CONFIRM_REBUILD_MEDIA":
        if data == "rebuild_no":
            drafts[user_id] = {}
            user_states[user_id] = "IDLE"
            await query.message.reply_text(
                "Edición cancelada.",
                reply_markup=get_main_menu_keyboard(),
            )
            return

        if data == "rebuild_yes":
            # Borrar publicación anterior del canal
            if last_post_message_id is not None:
                try:
                    await context.bot.delete_message(
                        chat_id=CHANNEL_USERNAME,
                        message_id=last_post_message_id,
                    )
                except Exception:
                    pass

            last_post_message_id = None
            last_post_info = None

            pending = drafts[user_id].get("pending_media")
            if not pending:
                user_states[user_id] = "IDLE"
                await query.message.reply_text(
                    "No tengo contenido nuevo para rehacer."
                )
                return

            drafts[user_id] = pending
            # A partir de aquí es como crear desde cero
            await start_button_flow_for_new_draft(
                user_id, context, query.message.chat_id
            )
            return

    # ===================================
    #         PUBLICAR AHORA
    # ===================================

    if data == "publish_now" and state == "CONFIRM":
        if not draft:
            await query.message.reply_text("No tengo borrador.")
            return

        buttons = draft.get("buttons")
        buttons_data = draft.get("buttons_data", [])
        ch_name = CHANNEL_USERNAME

        if draft["type"] == "text":
            msg = await context.bot.send_message(
                ch_name, draft["text"], reply_markup=buttons
            )
        elif draft["type"] == "photo":
            msg = await context.bot.send_photo(
                ch_name,
                draft["file_id"],
                caption=draft.get("caption", ""),
                reply_markup=buttons,
            )
        elif draft["type"] == "video":
            msg = await context.bot.send_video(
                ch_name,
                draft["file_id"],
                caption=draft.get("caption", ""),
                reply_markup=buttons,
            )
        elif draft["type"] == "audio":
            msg = await context.bot.send_audio(
                ch_name, draft["file_id"], reply_markup=buttons
            )
        else:
            await query.message.reply_text(
                "Tipo de contenido no soportado."
            )
            return

        last_post_message_id = msg.message_id
        last_post_info = {"type": draft["type"], "buttons_data": buttons_data}

        drafts[user_id] = {}
        user_states[user_id] = "IDLE"

        await query.message.reply_text(
            "✅ Publicación enviada al canal.",
            reply_markup=build_view_publication_button(msg.message_id),
        )
        await query.message.reply_text(
            "Volviendo al menú principal.",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    # ===================================
    #         PROGRAMAR DESDE CONFIRM
    # ===================================

    if data == "schedule" and state == "CONFIRM":
        user_states[user_id] = "WAITING_DATETIME"
        await query.message.reply_text(
            "Envía la fecha y hora (formato 2025-12-02 18:30)."
        )
        return


# ======================================================
#                       MAIN
# ======================================================

def main():
    if not TOKEN:
        raise RuntimeError(
            "POST_BOT_TOKEN no está definido en las variables de entorno."
        )

    application = ApplicationBuilder().token(TOKEN).build()

    load_default_buttons()

    text_or_media = (
        (filters.TEXT & ~filters.COMMAND)
        | filters.PHOTO
        | filters.VIDEO
        | filters.AUDIO
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(text_or_media, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))

    application.run_polling()


if __name__ == "__main__":
    main()
