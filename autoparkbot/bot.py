import os
import logging
from dotenv import load_dotenv
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import db
import lookup

load_dotenv()  # load variables from .env if present
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# States
LANGUAGE, ROUTE, COMMENT, PHOTO, CONFIRM = range(5)

# Кнопка меню — команда, чтобы не всплывать как обычный текст
COMPLAINT_BTN = '📝 Жана шағым / Новая жалоба'

# Multilingual strings
STRINGS = {
    'en': {
        'choose_language': 'Choose language:',
        'english': '🇬🇧 English',
        'russian': '🇷🇺 Русский',
        'kazakh': '🇰🇿 Қазақша',
        'enter_route': 'Enter the route number (e.g., 74, 36, 504):',
        'enter_comment': 'Describe your complaint:',
        'send_receipt': 'Send a photo or PDF of your payment receipt (or tap Skip):',
        'skip_receipt': '⏭ Skip',
        'found_number': '🔍 Transport number found: {number}',
        'found_bus': '\n🚌 Bus: {bus}',
        'confirm': '📋 Confirm complaint?\n\n🚏 Route: {route}\n💬 Comment: {comment}',
        'confirm_yes': '✅ Submit',
        'confirm_no': '❌ Cancel',
        'saved': '✅ Your complaint has been submitted. Thank you!',
        'cancelled': '❌ Cancelled.',
    },
    'ru': {
        'choose_language': 'Выберите язык:',
        'english': '🇬🇧 English',
        'russian': '🇷🇺 Русский',
        'kazakh': '🇰🇿 Қазақша',
        'enter_route': 'Введите номер маршрута (например: 74, 36, 504):',
        'enter_comment': 'Опишите вашу жалобу:',
        'send_receipt': 'Отправьте фото или PDF чека об оплате (или нажмите Пропустить):',
        'skip_receipt': '⏭ Пропустить',
        'found_number': '🔍 Найден номер транспорта: {number}',
        'found_bus': '\n🚌 Автобус: {bus}',
        'confirm': '📋 Подтвердить жалобу?\n\n🚏 Маршрут: {route}\n💬 Комментарий: {comment}',
        'confirm_yes': '✅ Подтвердить',
        'confirm_no': '❌ Отмена',
        'saved': '✅ Жалоба принята. Спасибо!',
        'cancelled': '❌ Отменено.',
    },
    'kk': {
        'choose_language': 'Тілді таңдаңыз:',
        'english': '🇬🇧 English',
        'russian': '🇷🇺 Русский',
        'kazakh': '🇰🇿 Қазақша',
        'enter_route': 'Маршрут нөмірін енгізіңіз (мысалы: 74, 36, 504):',
        'enter_comment': 'Пікіріңізді енгізіңіз:',
        'send_receipt': 'Төлем чегінің фотосын немесе PDF файлын жіберіңіз (немесе Өткізу басыңыз):',
        'skip_receipt': '⏭ Өткізу',
        'found_number': '🔍 Көлік нөмірі табылды: {number}',
        'found_bus': '\n🚌 Автобус: {bus}',
        'confirm': '📋 Шағымды растайсыз ба?\n\n🚏 Маршрут: {route}\n💬 Шағым: {comment}',
        'confirm_yes': '✅ Растау',
        'confirm_no': '❌ Бас тарту',
        'saved': '✅ Шағымыңыз қабылданды. Рахмет!',
        'cancelled': '❌ Бас тартылды.',
    }
}


def _lang(ctx: ContextTypes.DEFAULT_TYPE, key: str, **kwargs):
    """Get translated string."""
    lang = ctx.user_data.get('language', 'en')
    s = STRINGS.get(lang, STRINGS['en']).get(key, key)
    return s.format(**kwargs) if kwargs else s


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие + постоянная кнопка-команда внизу чата."""
    # Используем /жалоба как команду — не всплывает как обычный текст
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton('/new')]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
    # Очищаем старые данные на случай прерванной сессии
    context.user_data.clear()
    await update.message.reply_text(
        '🚌 *AutoPark*\n\n'
        '🇰🇿 Жаңа шағым беру үшін төмендегі батырманы басыңыз.\n'
        '🇷🇺 Нажмите кнопку ниже, чтобы подать новую жалобу.\n'
        '🇬🇧 Press the button below to file a new complaint.',
        reply_markup=keyboard,
        parse_mode='Markdown',
    )


async def complaint_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start complaint - immediately show language selection."""
    logger.info(f"complaint_start called by user {update.effective_user.id}")
    keyboard = [
        [InlineKeyboardButton(STRINGS['en']['english'], callback_data='lang_en')],
        [InlineKeyboardButton(STRINGS['ru']['russian'], callback_data='lang_ru')],
        [InlineKeyboardButton(STRINGS['ru']['kazakh'], callback_data='lang_kk')],
    ]
    await update.message.reply_text(
        STRINGS['en']['choose_language'],
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    logger.info(f"Language selection sent to user {update.effective_user.id}")
    return LANGUAGE


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set language and proceed to entering route."""
    query = update.callback_query
    await query.answer()
    
    # Map callback_data to language code
    lang_map = {'lang_en': 'en', 'lang_ru': 'ru', 'lang_kk': 'kk'}
    lang = lang_map.get(query.data, 'en')
    context.user_data['language'] = lang
    
    await query.edit_message_text(_lang(context, 'enter_route'))
    return ROUTE


async def route_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        text = update.message.text.strip()
        context.user_data['route'] = text
        await update.message.reply_text(_lang(context, 'enter_comment'))
    return COMMENT


async def comment_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        text = update.message.text.strip()
        context.user_data['comment'] = text
    keyboard = [
        [InlineKeyboardButton(_lang(context, 'skip_receipt'), callback_data='skip_photo')]
    ]
    await update.message.reply_text(
        _lang(context, 'send_receipt'),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return PHOTO


async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_path = None
    if update.message and update.message.photo:
        photos = update.message.photo
        os.makedirs('uploads', exist_ok=True)
        photo = photos[-1]
        file = await photo.get_file()
        filename = f"uploads/receipt_{update.effective_user.id}_{int(datetime.utcnow().timestamp())}.jpg"
        await file.download_to_drive(custom_path=filename)
        file_path = filename
    elif update.message and update.message.document:
        # Handle PDF
        doc = update.message.document
        if doc.mime_type == 'application/pdf':
            os.makedirs('uploads', exist_ok=True)
            file = await doc.get_file()
            filename = f"uploads/receipt_{update.effective_user.id}_{int(datetime.utcnow().timestamp())}.pdf"
            await file.download_to_drive(custom_path=filename)
            file_path = filename

    # try to extract number and bus info
    bus = None
    if file_path:
        number, bus, bus_entry = lookup.process_receipt(file_path)
        if number:
            note = _lang(context, 'found_number', number=number)
            if bus:
                note += _lang(context, 'found_bus', bus=bus)
            await update.message.reply_text(note)

    context.user_data['file_path'] = file_path
    context.user_data['bus_info'] = bus
    context.user_data['bus_entry'] = bus_entry
    await _show_confirm(update, context)
    return CONFIRM


async def skip_photo_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['file_path'] = None
    context.user_data['bus_info'] = None
    await _show_confirm(query, context)
    return CONFIRM


async def _show_confirm(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    route = context.user_data.get('route')
    comment = context.user_data.get('comment')
    keyboard = [
        [InlineKeyboardButton(_lang(context, 'confirm_yes'), callback_data='confirm_yes')],
        [InlineKeyboardButton(_lang(context, 'confirm_no'), callback_data='confirm_no')],
    ]
    msg = _lang(context, 'confirm', route=route, comment=comment)
    query = getattr(update_or_query, 'callback_query', None)
    if query is not None:
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif getattr(update_or_query, 'message', None) is not None:
        await update_or_query.message.reply_text(
            msg,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update_or_query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def confirm_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'confirm_yes':
        route = context.user_data.get('route')
        comment = context.user_data.get('comment')
        file_path = context.user_data.get('file_path')
        bus_info = context.user_data.get('bus_info')
        user = update.effective_user
        created_at = datetime.utcnow().isoformat()
        db.save_complaint(
            route=route,
            comment=comment,
            photo_path=file_path,
            user_id=user.id,
            created_at=created_at,
            bus_info=bus_info,
            bus_garage_number=(context.user_data.get('bus_entry') or {}).get('garage_number'),
            username=user.username or '',
            user_full_name=user.full_name or '',
        )
        await query.edit_message_text(_lang(context, 'saved'))
    else:
        await query.edit_message_text(_lang(context, 'cancelled'))
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(_lang(context, 'cancelled'))
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(_lang(context, 'cancelled'))
    context.user_data.clear()
    return ConversationHandler.END


_DATA_DIR = os.getenv('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(_DATA_DIR, 'uploads')


async def handle_user_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Входящие сообщения/файлы от пользователя вне ConversationHandler → в чат жалобы."""
    user = update.effective_user
    message = update.message
    if not message or not user:
        return

    # Пропустить системные кнопки меню
    if message.text and message.text.strip() in ('/new', '/start', '/complaint', '/cancel'):
        return

    # Пропустить если пользователь сейчас подаёт жалобу (есть активные ключи сессии)
    conv_keys = {'language', 'route', 'comment', 'file_path'}
    if any(k in context.user_data for k in conv_keys):
        return

    complaint = db.get_latest_complaint_for_user(user.id)
    if not complaint:
        await message.reply_text(
            "У вас нет активных жалоб. Отправьте /start чтобы подать новую жалобу."
        )
        return

    complaint_id = complaint['id']
    file_path = None
    text = message.text or message.caption or ''
    ts = int(datetime.utcnow().timestamp())
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    if message.photo:
        photo = message.photo[-1]
        file = await photo.get_file()
        fname = f"evidence_{user.id}_{ts}.jpg"
        fp = os.path.join(UPLOAD_DIR, fname)
        await file.download_to_drive(custom_path=fp)
        file_path = fp
        text = text or '📷 Фото'

    elif message.video:
        file = await message.video.get_file()
        fname = f"evidence_{user.id}_{ts}.mp4"
        fp = os.path.join(UPLOAD_DIR, fname)
        await file.download_to_drive(custom_path=fp)
        file_path = fp
        text = text or '🎥 Видео'

    elif message.document:
        doc = message.document
        file = await doc.get_file()
        ext = os.path.splitext(doc.file_name or '')[1] or ''
        fname = f"evidence_{user.id}_{ts}{ext}"
        fp = os.path.join(UPLOAD_DIR, fname)
        await file.download_to_drive(custom_path=fp)
        file_path = fp
        text = text or f'📎 {doc.file_name}'

    if not text and not file_path:
        return

    db.save_message(
        complaint_id=complaint_id,
        sender_id=user.id,
        sender_type='user',
        sender_name=user.full_name or user.username or str(user.id),
        text=text or '(файл)',
        file_path=file_path,
    )

    logger.info(f"Сообщение от {user.id} сохранено в жалобу #{complaint_id}")
    await message.reply_text(
        f"✅ Ваше сообщение получено по жалобе #{complaint_id} (маршрут {complaint['route']})."
    )


async def list_complaints(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.list_complaints(limit=20)
    if not rows:
        await update.message.reply_text("Жалоб пока нет.")
        return
    lines = []
    for r in rows:
        id_, route, comment, photo, user_id, created_at, bus_info, bus_garage, username, user_full_name, status, *_ = r
        name = user_full_name or username or str(user_id)
        lines.append(f"#{id_} {route} — {comment} | {name} ({created_at})")
    await update.message.reply_text("\n".join(lines))


async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log every incoming update without blocking other handlers."""
    if update.message:
        logger.info(f"📨 Message from {update.effective_user.id}: {update.message.text}")
    if update.callback_query:
        logger.info(f"🔘 Callback from {update.effective_user.id}: {update.callback_query.data}")


def main():
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        print('Set TELEGRAM_TOKEN environment variable')
        return

    logger.info(f"Starting bot with token: {token[:20]}...")
    db.init_db()

    app = ApplicationBuilder().token(token).build()
    
    # Add debug logging for all updates after normal handlers
    app.add_handler(MessageHandler(filters.ALL, log_update), group=99)
    app.add_handler(CallbackQueryHandler(log_update), group=99)

    # /start → меню, /complaint → сразу жалоба
    app.add_handler(CommandHandler('start', show_menu))

    conv = ConversationHandler(
        entry_points=[
            CommandHandler('complaint', complaint_start),
            CommandHandler('new',      complaint_start),
        ],
        states={
            LANGUAGE: [
                CallbackQueryHandler(set_language, pattern='^lang_(en|ru|kk)$'),
            ],
            ROUTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, route_received),
            ],
            COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, comment_received),
            ],
            PHOTO: [
                MessageHandler(filters.PHOTO | filters.Document.FileExtension('pdf'), photo_received),
                CallbackQueryHandler(skip_photo_button, pattern='^skip_photo$'),
            ],
            CONFIRM: [
                CallbackQueryHandler(confirm_complaint, pattern='^confirm_(yes|no)$'),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler('list', list_complaints))

    # Обработчик ответов пользователя (текст/фото/видео/файл) вне ConversationHandler
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND | filters.PHOTO | filters.VIDEO | filters.Document.ALL,
        handle_user_reply,
    ), group=1)
    
    logger.info("Handlers registered successfully")
    logger.info('Bot started...')
    print('Bot started...')
    app.run_polling()


if __name__ == '__main__':
    main()
