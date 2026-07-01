import os
import asyncio
import random
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
import onec
import ai_reply
import conversation_ai

load_dotenv()  # load variables from .env if present
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# States
LANGUAGE, CATEGORY, ROUTE, COMMENT, PHOTO, CONFIRM = range(6)

# Кнопка меню — команда, чтобы не всплывать как обычный текст
COMPLAINT_BTN = '📝 Жана шағым / Новая жалоба'

# Категории обращений (code → {lang: label})
CATEGORIES = [
    ('interval',   {'ru': '🕐 Нарушение интервала движения',   'kk': '🕐 Қозғалыс интервалын бұзу',        'en': '🕐 Schedule violation'}),
    ('driver',     {'ru': '👨‍✈️ На водителя',                    'kk': '👨‍✈️ Жүргізуші туралы',               'en': '👨‍✈️ Driver complaint'}),
    ('climate',    {'ru': '❄️ Кондиционер / Отопление',         'kk': '❄️ Кондиционер / Жылыту',            'en': '❄️ AC / Heating'}),
    ('condition',  {'ru': '🚌 Санитарное / Тех. состояние',     'kk': '🚌 Автобустың техникалық жағдайы',   'en': '🚌 Bus condition'}),
    ('suggestion', {'ru': '💌 Пожелание / Благодарность',       'kk': '💌 Тілек / Алғыс',                   'en': '💌 Suggestion / Thanks'}),
    ('lost',       {'ru': '🎒 Потерянные вещи',                 'kk': '🎒 Жоғалған заттар',                 'en': '🎒 Lost items'}),
]

# Multilingual strings
STRINGS = {
    'en': {
        'choose_language': 'Choose language:',
        'english': '🇬🇧 English',
        'russian': '🇷🇺 Русский',
        'kazakh': '🇰🇿 Қазақша',
        'choose_category': 'Choose complaint category:',
        'enter_route': 'Enter the route number (e.g., 74, 36, 504):',
        'enter_comment': 'Describe your complaint:',
        'send_receipt': 'Send a photo or PDF of your payment receipt (or tap Skip):',
        'skip_receipt': '⏭ Skip',
        'found_number': '🔍 Transport number found: {number}',
        'found_bus': '\n🚌 Bus: {bus}',
        'confirm': '📋 Confirm complaint?\n\n🚏 Route: {route}\n🏷 Category: {category}\n💬 Comment: {comment}',
        'confirm_yes': '✅ Submit',
        'confirm_no': '❌ Cancel',
        'saved': '✅ Your complaint has been submitted. Thank you!',
        'cancelled': '❌ Cancelled.',
        'enter_comment_lost': 'Describe the lost item (what is it, color, brand if applicable):',
        'send_receipt_lost': 'If you paid by card/phone, send your receipt — it has the bus board number. Or tap Skip:',
    },
    'ru': {
        'choose_language': 'Выберите язык:',
        'english': '🇬🇧 English',
        'russian': '🇷🇺 Русский',
        'kazakh': '🇰🇿 Қазақша',
        'choose_category': 'Выберите категорию обращения:',
        'enter_route': 'Введите номер маршрута (например: 74, 36, 504):',
        'enter_comment': 'Опишите вашу жалобу:',
        'send_receipt': 'Отправьте фото или PDF чека об оплате (или нажмите Пропустить):',
        'skip_receipt': '⏭ Пропустить',
        'found_number': '🔍 Найден номер транспорта: {number}',
        'found_bus': '\n🚌 Автобус: {bus}',
        'confirm': '📋 Подтвердить жалобу?\n\n🚏 Маршрут: {route}\n🏷 Категория: {category}\n💬 Комментарий: {comment}',
        'confirm_yes': '✅ Подтвердить',
        'confirm_no': '❌ Отмена',
        'saved': '✅ Жалоба принята. Спасибо!',
        'cancelled': '❌ Отменено.',
        'enter_comment_lost': 'Опишите потерянную вещь (что это, цвет, марка если есть):',
        'send_receipt_lost': 'Если оплачивали картой или телефоном — пришлите чек, в нём есть бортовой номер автобуса. Или нажмите Пропустить:',
    },
    'kk': {
        'choose_language': 'Тілді таңдаңыз:',
        'english': '🇬🇧 English',
        'russian': '🇷🇺 Русский',
        'kazakh': '🇰🇿 Қазақша',
        'choose_category': 'Өтініш санатын таңдаңыз:',
        'enter_route': 'Маршрут нөмірін енгізіңіз (мысалы: 74, 36, 504):',
        'enter_comment': 'Пікіріңізді енгізіңіз:',
        'send_receipt': 'Төлем чегінің фотосын немесе PDF файлын жіберіңіз (немесе Өткізу басыңыз):',
        'skip_receipt': '⏭ Өткізу',
        'found_number': '🔍 Көлік нөмірі табылды: {number}',
        'found_bus': '\n🚌 Автобус: {bus}',
        'confirm': '📋 Шағымды растайсыз ба?\n\n🚏 Маршрут: {route}\n🏷 Санат: {category}\n💬 Шағым: {comment}',
        'confirm_yes': '✅ Растау',
        'confirm_no': '❌ Бас тарту',
        'saved': '✅ Шағымыңыз қабылданды. Рахмет!',
        'cancelled': '❌ Бас тартылды.',
        'enter_comment_lost': 'Жоғалған затты сипаттаңыз (не екенін, түсін, маркасын):',
        'send_receipt_lost': 'Карта немесе телефонмен төлесеңіз — чекті жіберіңіз, онда бортовой нөмір бар. Немесе Өткізу басыңыз:',
    }
}


DISPATCH_PHONE = os.getenv('DISPATCH_PHONE', '')

_DEPOT_INFO = {
    'ru': (
        "✅ Водитель установлен!\n\n"
        "🚌 Найденные вещи водители сдают диспетчеру автопарка *в конце смены*.\n"
        "📍 Приходите *вечером после 20:00* и обратитесь к диспетчеру на проходной.\n\n"
        "{phone}"
        "Ваше обращение зарегистрировано под номером — диспетчер будет в курсе."
    ),
    'kk': (
        "✅ Жүргізуші анықталды!\n\n"
        "🚌 Табылған заттарды жүргізушілер *ауысым соңында* автопарк диспетчеріне тапсырады.\n"
        "📍 *Кешке сағат 20:00-ден кейін* келіп, кіреберістегі диспетчерге хабарласыңыз.\n\n"
        "{phone}"
        "Өтінішіңіз тіркелді — диспетчер хабардар болады."
    ),
    'en': (
        "✅ Driver identified!\n\n"
        "🚌 Found items are handed to the depot dispatcher *at the end of the shift*.\n"
        "📍 Please come *after 20:00 in the evening* and ask the dispatcher at the entrance.\n\n"
        "{phone}"
        "Your request has been registered — the dispatcher will be informed."
    ),
}

_DEPOT_INFO_NO_BUS = {
    'ru': (
        "😔 К сожалению, без номера автобуса мы не можем установить конкретного водителя.\n\n"
        "📍 Вы можете прийти в автобусный парк *вечером после 20:00* и обратиться к диспетчеру лично — "
        "он поможет проверить найденные вещи.\n\n"
        "{phone}"
        "Ваше обращение зарегистрировано."
    ),
    'kk': (
        "😔 Өкінішке орай, автобус нөмірінсіз нақты жүргізушіні анықтай алмаймыз.\n\n"
        "📍 *Кешке сағат 20:00-ден кейін* автопаркке барып диспетчерге жеке хабарласа аласыз — "
        "ол табылған заттарды тексеруге көмектеседі.\n\n"
        "{phone}"
        "Өтінішіңіз тіркелді."
    ),
    'en': (
        "😔 Unfortunately, without a bus number we cannot identify the specific driver.\n\n"
        "📍 You can visit the depot *after 20:00 in the evening* and speak with the dispatcher in person — "
        "they can help check found items.\n\n"
        "{phone}"
        "Your request has been registered."
    ),
}

_BUS_FOUND_ACK = {
    'ru': "✅ Данные получены, спасибо! Автобус определён, жалоба передана в работу.\nОтвет поступит в течение 10 рабочих дней.",
    'kk': "✅ Мәліметтер алынды, рахмет! Автобус анықталды, шағым өңдеуге жіберілді.\nЖауап 10 жұмыс күні ішінде келеді.",
    'en': "✅ Got it, thank you! The bus has been identified and your complaint is now in review.\nYou'll receive a response within 10 business days.",
}

_BUS_NOT_FOUND_ACK = {
    'ru': "✅ Данные записаны, спасибо! Жалоба передана в работу.\nОтвет поступит в течение 10 рабочих дней.",
    'kk': "✅ Мәліметтер жазылды, рахмет! Шағым өңдеуге жіберілді.\nЖауап 10 жұмыс күні ішінде келеді.",
    'en': "✅ Details noted, thank you! Your complaint has been forwarded for review.\nYou'll receive a response within 10 business days.",
}

_RECEIPT_ACK = {
    'ru': (
        "✅ Чек получен! По нему мы определим автобус и водителя.\n"
        "Жалоба будет рассмотрена в течение 10 рабочих дней."
    ),
    'kk': (
        "✅ Чек алынды! Ол арқылы автобус пен жүргізушіні анықтаймыз.\n"
        "Шағымыңыз 10 жұмыс күні ішінде қаралады."
    ),
    'en': (
        "✅ Receipt received! We'll use it to identify the bus and driver.\n"
        "Your complaint will be reviewed within 10 business days."
    ),
}


def _category_label(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Вернуть человекочитаемую метку категории на языке пользователя."""
    cat_code = context.user_data.get('category', '')
    lang = context.user_data.get('language', 'en')
    for code, labels in CATEGORIES:
        if code == cat_code:
            return labels.get(lang, labels['en'])
    return cat_code


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
    """Set language and proceed to category selection."""
    query = update.callback_query
    await query.answer()

    lang_map = {'lang_en': 'en', 'lang_ru': 'ru', 'lang_kk': 'kk'}
    lang = lang_map.get(query.data, 'en')
    context.user_data['language'] = lang

    keyboard = [
        [InlineKeyboardButton(labels[lang], callback_data=f'cat_{code}')]
        for code, labels in CATEGORIES
    ]
    await query.edit_message_text(
        _lang(context, 'choose_category'),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CATEGORY


async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save category and proceed to route."""
    query = update.callback_query
    await query.answer()
    context.user_data['category'] = query.data[4:]  # strip 'cat_'
    await query.edit_message_text(_lang(context, 'enter_route'))
    return ROUTE


async def route_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        text = update.message.text.strip()
        context.user_data['route'] = text
        category = context.user_data.get('category', '')
        key = 'enter_comment_lost' if category == 'lost' else 'enter_comment'
        await update.message.reply_text(_lang(context, key))
    return COMMENT


async def comment_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        text = update.message.text.strip()
        context.user_data['comment'] = text
    category = context.user_data.get('category', '')
    receipt_key = 'send_receipt_lost' if category == 'lost' else 'send_receipt'
    keyboard = [
        [InlineKeyboardButton(_lang(context, 'skip_receipt'), callback_data='skip_photo')]
    ]
    await update.message.reply_text(
        _lang(context, receipt_key),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return PHOTO


async def photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_path = None
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    uid = update.effective_user.id
    ts  = int(datetime.utcnow().timestamp())

    if update.message and update.message.photo:
        photo = update.message.photo[-1]
        file  = await photo.get_file()
        fp    = os.path.join(UPLOAD_DIR, f"receipt_{uid}_{ts}.jpg")
        await file.download_to_drive(custom_path=fp)
        file_path = fp
    elif update.message and update.message.document:
        doc = update.message.document
        if doc.mime_type == 'application/pdf':
            file = await doc.get_file()
            fp   = os.path.join(UPLOAD_DIR, f"receipt_{uid}_{ts}.pdf")
            await file.download_to_drive(custom_path=fp)
            file_path = fp

    bus = None
    bus_entry = None
    if file_path:
        number, bus, bus_entry = lookup.process_receipt(file_path)
        if number:
            note = _lang(context, 'found_number', number=number)
            if bus:
                note += _lang(context, 'found_bus', bus=bus)
            await update.message.reply_text(note)

    context.user_data['file_path'] = file_path
    context.user_data['bus_info']   = bus
    context.user_data['bus_entry']  = bus_entry
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
    category = _category_label(context)
    keyboard = [
        [InlineKeyboardButton(_lang(context, 'confirm_yes'), callback_data='confirm_yes')],
        [InlineKeyboardButton(_lang(context, 'confirm_no'), callback_data='confirm_no')],
    ]
    msg = _lang(context, 'confirm', route=route, comment=comment, category=category)
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


async def _start_clarification(bot, user_id: int, complaint_id: int, lang: str, category: str = ''):
    """Отправляет первое сообщение уточнения сразу после подачи жалобы."""
    msg_map = conversation_ai.INITIAL_MSG_LOST if category == 'lost' else conversation_ai.INITIAL_MSG
    msg = msg_map.get(lang, msg_map['ru'])
    db.save_message(
        complaint_id=complaint_id,
        sender_id=0,
        sender_type='admin',
        sender_name='AutoPark AI',
        text=msg,
    )
    try:
        await bot.send_message(chat_id=user_id, text=msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f'Ошибка отправки уточнения: {e}')


async def _send_ai_reply_delayed(
    bot,
    complaint_id: int,
    user_id: int,
    category: str,
    route: str,
    comment: str,
    lang: str,
):
    """Отправляет AI-ответ через случайную задержку 2–10 минут.
    Запускается как фоновая задача — не блокирует бота.
    """
    delay = random.randint(2 * 60, 10 * 60)
    logger.info(f'AI-ответ по жалобе #{complaint_id} через {delay} сек.')
    await asyncio.sleep(delay)

    reply_text = await ai_reply.generate_auto_reply(
        category=category,
        route=route,
        comment=comment,
        lang=lang,
    )
    if reply_text:
        db.save_message(
            complaint_id=complaint_id,
            sender_id=0,
            sender_type='admin',
            sender_name='AutoPark AI',
            text=reply_text,
        )
        try:
            await bot.send_message(chat_id=user_id, text=reply_text)
            logger.info(f'AI-ответ отправлен пользователю {user_id} по жалобе #{complaint_id}')
        except Exception as e:
            logger.error(f'Ошибка отправки AI-ответа: {e}')


async def confirm_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'confirm_yes':
        route   = context.user_data.get('route')
        comment = context.user_data.get('comment')
        file_path = context.user_data.get('file_path')
        bus_info  = context.user_data.get('bus_info')
        category  = context.user_data.get('category')
        lang      = context.user_data.get('language', 'ru')
        user      = update.effective_user
        created_at = datetime.utcnow().isoformat()

        bus_garage = (context.user_data.get('bus_entry') or {}).get('garage_number')

        complaint_id = db.save_complaint(
            route=route,
            comment=comment,
            photo_path=file_path,
            user_id=user.id,
            created_at=created_at,
            bus_info=bus_info,
            bus_garage_number=bus_garage,
            username=user.username or '',
            user_full_name=user.full_name or '',
            category=category,
            language=lang,
        )
        await query.edit_message_text(_lang(context, 'saved'))

        if complaint_id:
            needs_clarify = conversation_ai.should_clarify({
                'category': category,
                'bus_garage_number': bus_garage,
                'bus_info': bus_info,
            })
            if file_path and category != 'lost':
                # Чек/фото содержит бортовой номер — уточнять не нужно (кроме lost)
                ack = _RECEIPT_ACK.get(lang, _RECEIPT_ACK['ru'])
                await context.bot.send_message(chat_id=user.id, text=ack)
            elif needs_clarify:
                # Запускаем диалог уточнения (для lost — всегда, для остальных — если нет данных)
                asyncio.create_task(_start_clarification(
                    bot=context.bot,
                    user_id=user.id,
                    complaint_id=complaint_id,
                    lang=lang,
                    category=category or '',
                ))
            elif category in ai_reply.AUTO_REPLY_CATEGORIES:
                asyncio.create_task(_send_ai_reply_delayed(
                    bot=context.bot,
                    complaint_id=complaint_id,
                    user_id=user.id,
                    category=category,
                    route=route or '',
                    comment=comment or '',
                    lang=lang,
                ))
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
    conv_keys = {'language', 'category', 'route', 'comment', 'file_path'}
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

    lang = complaint.get('language', 'ru')

    # ── Попытка извлечь идентификатор автобуса и запросить ПЛ из 1С ──────────
    if conversation_ai.should_clarify(complaint):
        identifier = conversation_ai.extract_bus_identifier(text or '')

        if identifier:
            id_type  = identifier['type']
            id_value = identifier['value']
            logger.info(f"Идентификатор автобуса из диалога: {id_type}={id_value}")

            # Поиск в Excel-таблице
            bus_entry = None
            if id_type in ('board', 'garage'):
                bus_entry = lookup.find_bus_entry(id_value)
            elif id_type == 'plate':
                bus_entry = lookup.find_bus_by_plate(id_value)

            garage_number = None

            if id_type == 'garage':
                # Гаражный → сразу в 1С, Excel не нужен
                garage_number = id_value
                db.update_complaint_bus(complaint_id, bus_garage_number=garage_number)

            elif id_type in ('board', 'plate'):
                # Бортовой / гос. номер → Excel чтобы найти гаражный
                if id_type == 'board':
                    bus_entry = lookup.find_bus_entry(id_value)
                else:
                    bus_entry = lookup.find_bus_by_plate(id_value)

                if bus_entry:
                    garage_number = bus_entry['garage_number']
                    db.update_complaint_bus(
                        complaint_id,
                        bus_info=lookup.format_bus_info(bus_entry),
                        bus_garage_number=garage_number,
                    )
                else:
                    # Не нашли в Excel — сохраняем то что есть
                    db.update_complaint_bus(complaint_id, bus_info=f"{id_type}: {id_value}")

            # Запрос ПЛ из 1С по гаражному номеру
            if garage_number:
                try:
                    waybill = await onec.get_waybill_by_garage_number(garage_number)
                    if waybill.get('status') == 'ok':
                        body = waybill.get('body')
                        entry_data = (body[0] if isinstance(body, list) and body
                                      else body if isinstance(body, dict) else {})
                        driver = entry_data.get('Driver', {}) if isinstance(entry_data, dict) else {}
                        if driver.get('FIO'):
                            db.update_driver_info(
                                complaint_id, driver['FIO'], driver.get('TabNo', ''))
                            logger.info(f"Водитель #{complaint_id}: {driver['FIO']}")
                except Exception as e:
                    logger.error(f'Ошибка запроса ПЛ из 1С: {e}')

            # Для lost — отправляем инфо про автопарк, для остальных — стандартное подтверждение
            if complaint.get('category') == 'lost':
                phone_line = f"📞 Если срочно — позвоните диспетчеру: *{DISPATCH_PHONE}*\n\n" if DISPATCH_PHONE else ''
                ack = _DEPOT_INFO.get(lang, _DEPOT_INFO['ru']).format(phone=phone_line)
            else:
                ack = _BUS_FOUND_ACK.get(lang, _BUS_FOUND_ACK['ru'])

            db.save_message(complaint_id=complaint_id, sender_id=0, sender_type='admin',
                            sender_name='AutoPark AI', text=ack)
            await message.reply_text(ack, parse_mode='Markdown')
            return

        # Идентификатор не найден — продолжаем AI-диалог
        ai_response = await conversation_ai.generate_reply(
            complaint=complaint,
            new_message=text,
            has_file=bool(file_path),
            lang=lang,
            category=complaint.get('category'),
        )
        if ai_response:
            db.save_message(complaint_id=complaint_id, sender_id=0, sender_type='admin',
                            sender_name='AutoPark AI', text=ai_response)
            await message.reply_text(ai_response, parse_mode='Markdown')
            return

    await message.reply_text(
        f"✅ Ваше сообщение получено по жалобе #{complaint_id}."
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
            CATEGORY: [
                CallbackQueryHandler(category_selected, pattern='^cat_(interval|driver|climate|condition|suggestion)$'),
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
