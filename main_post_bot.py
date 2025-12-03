import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.environ.get("POST_BOT_TOKEN")
CHANNEL_USERNAME = "@JohaaleTrader_es"
ADMIN_ID = 5958164558

user_states = {}
drafts = {}
button_template = []  # lista de (texto, url)


def main_menu():
    kb = [
        ["📝 Crear publicación"],
        ["✏️ Editar publicación"],
        ["⏰ Programar publicación"],
        ["❌ Cancelar"],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u or u.id != ADMIN_ID:
        if update.message:
            await update.message.reply_text("Acceso restringido.")
        return
    user_states[u.id] = "IDLE"
    await update.message.reply_text("Panel listo. Elige una opción:", reply_markup=main_menu())


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    if not m or not m.from_user:
        return
    uid = m.from_user.id
    if uid != ADMIN_ID:
        await m.reply_text("Acceso restringido.")
        return

    txt = m.text or ""
    state = user_states.get(uid, "IDLE")

    if txt == "/start":
        user_states[uid] = "IDLE"
        await m.reply_text("Panel listo. Elige una opción:", reply_markup=main_menu())
        return

    # ----- MENÚ PRINCIPAL -----
    if state == "IDLE":
        if txt == "📝 Crear publicación":
            user_states[uid] = "WAITING_CONTENT"
            drafts[uid] = {}
            await m.reply_text("Envía el contenido (texto o multimedia).")
            return

        if txt == "✏️ Editar publicación":
            user_states[uid] = "WAITING_EDIT_MSG"
            await m.reply_text("Reenvía desde el canal el mensaje a editar.")
            return

        if txt == "⏰ Programar publicación":
            d = drafts.get(uid)
            if not d:
                await m.reply_text("Primero crea una publicación.")
                return
            user_states[uid] = "WAITING_SCHEDULE"
            await m.reply_text("Envía fecha y hora (2025-12-03 14:30 o 03/12 14:30).")
            return

        if txt == "❌ Cancelar":
            drafts.pop(uid, None)
            await m.reply_text("Acción cancelada.", reply_markup=main_menu())
            return

        await m.reply_text("Usa el menú para elegir una opción.", reply_markup=main_menu())
        return

    # ----- CREAR: CONTENIDO -----
    if state == "WAITING_CONTENT":
        drafts[uid] = {
            "from_chat_id": m.chat_id,
            "message_id": m.message_id,
            "buttons": None,
        }
        user_states[uid] = "WAITING_BUTTONS"
        await m.reply_text("Añade enlaces y botones.")
        return

    # ----- CREAR: BOTONES -----
    if state == "WAITING_BUTTONS":
        lines = txt.splitlines()
        btns = []
        for line in lines:
            if "-" not in line:
                continue
            label, url = line.split("-", 1)
            label, url = label.strip(), url.strip()
            if label and url:
                btns.append([InlineKeyboardButton(label, url=url)])
        if not btns:
            await m.reply_text("No detecté botones válidos.")
            return

        markup = InlineKeyboardMarkup(btns)
        drafts[uid]["buttons"] = markup

        # Vista previa completa
        d = drafts[uid]
        await context.bot.copy_message(
            chat_id=m.chat_id,
            from_chat_id=d["from_chat_id"],
            message_id=d["message_id"],
            reply_markup=markup,
        )

        kb = [
            ["📤 Publicar ahora"],
            ["⏰ Programar"],
            ["💾 Guardar botones predet."],
            ["❌ Cancelar"],
        ]
        user_states[uid] = "CONFIRM_ACTION"
        await m.reply_text("Vista previa lista. Elige una opción:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return

    # ----- CONFIRMAR ACCIÓN -----
    if state == "CONFIRM_ACTION":
        d = drafts.get(uid)
        if not d:
            user_states[uid] = "IDLE"
            await m.reply_text("No hay borrador.", reply_markup=main_menu())
            return

        if txt == "📤 Publicar ahora":
            sent = await context.bot.copy_message(
                chat_id=CHANNEL_USERNAME,
                from_chat_id=d["from_chat_id"],
                message_id=d["message_id"],
                reply_markup=d.get("buttons"),
            )
            user_states[uid] = "IDLE"
            link = "https://t.me/{}/{}".format(CHANNEL_USERNAME.lstrip("@"), sent.message_id)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Ver publicación", url=link)]])
            await m.reply_text("Publicación enviada.", reply_markup=main_menu())
            await m.reply_text("Vista en canal:", reply_markup=kb)
            return

        if txt == "⏰ Programar":
            user_states[uid] = "WAITING_SCHEDULE"
            await m.reply_text("Envía fecha y hora (2025-12-03 14:30 o 03/12 14:30).")
            return

        if txt == "💾 Guardar botones predet.":
            if not d.get("buttons"):
                await m.reply_text("No hay botones para guardar.")
                return
            global button_template
            button_template = []
            for row in d["buttons"].inline_keyboard:
                for b in row:
                    button_template.append((b.text, b.url))
            user_states[uid] = "IDLE"
            await m.reply_text("Botones guardados como predeterminados.", reply_markup=main_menu())
            return

        if txt == "❌ Cancelar":
            drafts.pop(uid, None)
            user_states[uid] = "IDLE"
            await m.reply_text("Acción cancelada.", reply_markup=main_menu())
            return

        await m.reply_text("Elige una opción usando los botones.")
        return

    # ----- PROGRAMAR PUBLICACIÓN -----
    if state == "WAITING_SCHEDULE":
        d = drafts.get(uid)
        if not d:
            user_states[uid] = "IDLE"
            await m.reply_text("No hay borrador.", reply_markup=main_menu())
            return

        s = txt.strip()
        now = datetime.now()
        dt = None
        try:
            dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
        except Exception:
            try:
                fecha, hora = s.split(" ")
                d_str, m_str = fecha.split("/")
                h_str, mi_str = hora.split(":")
                d_i, m_i, h_i, mi_i = int(d_str), int(m_str), int(h_str), int(mi_str)
                dt = datetime(now.year, m_i, d_i, h_i, mi_i)
            except Exception:
                dt = None

        if dt is None:
            await m.reply_text("Formato inválido. Usa 2025-12-03 14:30 o 03/12 14:30.")
            return

        if dt <= now:
            dt = dt + timedelta(days=1)

        job_data = {
            "from_chat_id": d["from_chat_id"],
            "message_id": d["message_id"],
            "buttons": d.get("buttons"),
        }
        context.job_queue.run_once(send_scheduled_post, when=dt, data=job_data)
        user_states[uid] = "IDLE"
        await m.reply_text(
            "Publicación programada para {} a las {}.".format(
                dt.strftime("%d/%m"), dt.strftime("%H:%M")
            ),
            reply_markup=main_menu(),
        )
        return

    # ----- EDITAR PUBLICACIÓN -----
    if state == "WAITING_EDIT_MSG":
        if not (m.forward_from_chat and m.forward_from_chat.username == CHANNEL_USERNAME.lstrip("@")):
            await m.reply_text("Reenvía un mensaje del canal {}.".format(CHANNEL_USERNAME))
            return
        drafts[uid] = {
            "edit_chat_id": m.forward_from_chat.id,
            "edit_message_id": m.forward_from_message_id,
        }
        user_states[uid] = "WAITING_EDIT_TEXT"
        await m.reply_text("Envía el nuevo texto/caption para la publicación.")
        return

    if state == "WAITING_EDIT_TEXT":
        d = drafts.get(uid)
        if not d:
            user_states[uid] = "IDLE"
            await m.reply_text("No hay mensaje a editar.", reply_markup=main_menu())
            return
        chat_id = d["edit_chat_id"]
        msg_id = d["edit_message_id"]
        # Intentar editar como texto, si falla, como caption
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=txt)
        except Exception:
            try:
                await context.bot.edit_message_caption(chat_id=chat_id, message_id=msg_id, caption=txt)
            except Exception:
                await m.reply_text("No pude editar el mensaje.")
                user_states[uid] = "IDLE"
                return
        user_states[uid] = "IDLE"
        await m.reply_text("Publicación editada.", reply_markup=main_menu())
        return

    # Cualquier cosa rara: reset
    user_states[uid] = "IDLE"
    await m.reply_text("Estado reiniciado.", reply_markup=main_menu())


async def send_scheduled_post(context: ContextTypes.DEFAULT_TYPE):
    d = context.job.data
    if not d:
        return
    await context.bot.copy_message(
        chat_id=CHANNEL_USERNAME,
        from_chat_id=d["from_chat_id"],
        message_id=d["message_id"],
        reply_markup=d.get("buttons"),
    )


def main():
    if not TOKEN:
        raise RuntimeError("POST_BOT_TOKEN no está configurado.")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
