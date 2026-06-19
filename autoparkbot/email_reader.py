"""
Читает входящие письма Gmail, парсит через OpenAI и создаёт жалобы в БД.
Запускается как отдельный фоновый процесс из start.sh.
"""
import asyncio
import email as email_lib
import email.utils
import imaplib
import json
import logging
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()
import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('email_reader')

GMAIL_USER         = os.getenv('GMAIL_USER', '')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD', '')
OPENAI_API_KEY     = os.getenv('OPENAI_API_KEY', '')
CHECK_INTERVAL     = int(os.getenv('EMAIL_CHECK_INTERVAL', '300'))  # секунды, по умолчанию 5 мин

VALID_CATEGORIES = {'interval', 'driver', 'climate', 'condition', 'suggestion'}

# Домены 2ГИС — письма от них требуют особой проверки
TWOGIS_DOMAINS = {'2gis.ru', '2gis.kz', '2gis.com', 'noreply.2gis.ru', 'noreply.2gis.kz'}


def is_from_2gis(from_addr: str) -> bool:
    domain = from_addr.split('@')[-1].lower().strip()
    return domain in TWOGIS_DOMAINS or '2gis' in domain


# ── OpenAI: проверить 2ГИС-письмо — жалоба ли это ───────────────────────────

async def extract_2gis_review(subject: str, body: str) -> dict | None:
    """Специальный парсер для писем из 2ГИС.
    Сначала определяет — жалоба ли это, потом извлекает детали.
    """
    if not OPENAI_API_KEY:
        return None
    try:
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        prompt = (
            'Это уведомление от сервиса 2ГИС с отзывом о городском автобусе или автопарке Астаны.\n'
            'Проанализируй текст и верни JSON со следующими полями:\n\n'
            '- is_complaint: true если отзыв содержит жалобу, проблему или негатив; '
            'false если это благодарность, нейтральный или положительный отзыв\n'
            '- rating: оценка в звёздах если упомянута (число 1-5, null если нет)\n'
            '- route: номер маршрута или автобуса (строка, null если не упомянут)\n'
            '- category: одно из значений (определи по содержанию отзыва):\n'
            '    interval  — нарушение расписания или интервала\n'
            '    driver    — поведение водителя\n'
            '    climate   — кондиционер или отопление\n'
            '    condition — техническое или санитарное состояние\n'
            '    suggestion — пожелание или благодарность\n'
            '- comment: текст отзыва/жалобы на русском (1-3 предложения)\n'
            '- reviewer_name: имя автора отзыва если есть (null если нет)\n\n'
            f'Тема письма: {subject}\n'
            f'Текст письма:\n{body[:2000]}\n\n'
            'Верни только JSON.'
        )
        resp = await client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=400,
            temperature=0.2,
            response_format={'type': 'json_object'},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.error(f'OpenAI ошибка при парсинге 2ГИС-письма: {e}')
        return None


# ── OpenAI: извлечь данные жалобы из обычного письма ────────────────────────

async def extract_complaint(subject: str, body: str) -> dict | None:
    if not OPENAI_API_KEY:
        return None
    try:
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        prompt = (
            'Из текста электронного письма извлеки информацию о жалобе или отзыве на городской автобус Астаны.\n'
            'Верни JSON со следующими полями:\n'
            '- route: номер маршрута (строка, например "74" или "36А"; null если не упомянут)\n'
            '- category: одно из значений:\n'
            '    interval  — нарушение интервала/расписания движения\n'
            '    driver    — жалоба на поведение водителя\n'
            '    climate   — кондиционер или отопление\n'
            '    condition — техническое или санитарное состояние автобуса\n'
            '    suggestion — пожелание или благодарность\n'
            '- comment: краткое описание жалобы на русском (1-3 предложения)\n'
            '- sender_name: имя отправителя из подписи или заголовка (null если не определить)\n\n'
            f'Тема письма: {subject}\n'
            f'Текст письма:\n{body[:2000]}\n\n'
            'Верни только JSON, без лишних пояснений.'
        )
        resp = await client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=400,
            temperature=0.2,
            response_format={'type': 'json_object'},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.error(f'OpenAI ошибка при парсинге письма: {e}')
        return None


# ── SMTP: отправить подтверждение ─────────────────────────────────────────────

def send_confirmation(to_addr: str, complaint_id: int, category: str, route: str | None):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        return
    try:
        category_ru = {
            'interval': 'Нарушение интервала движения',
            'driver':   'Жалоба на водителя',
            'climate':  'Кондиционер/Отопление',
            'condition':'Техническое/санитарное состояние',
            'suggestion':'Пожелание/Благодарность',
        }.get(category, category)

        route_str = f'Маршрут: {route}\n' if route else ''
        body = (
            f'Здравствуйте!\n\n'
            f'Ваше обращение зарегистрировано в системе AutoPark.\n\n'
            f'Номер обращения: #{complaint_id}\n'
            f'{route_str}'
            f'Категория: {category_ru}\n\n'
            f'Оно будет рассмотрено в течение 3 рабочих дней.\n\n'
            f'С уважением,\nАвтопарк Астаны'
        )
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = f'Обращение #{complaint_id} принято — AutoPark'
        msg['From']    = GMAIL_USER
        msg['To']      = to_addr

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.sendmail(GMAIL_USER, to_addr, msg.as_string())
        logger.info(f'Подтверждение отправлено на {to_addr}')
    except Exception as e:
        logger.error(f'Ошибка отправки подтверждения: {e}')


# ── IMAP: получить тело письма ───────────────────────────────────────────────

def get_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get('Content-Disposition', ''))
            if ct == 'text/plain' and 'attachment' not in cd:
                try:
                    return part.get_payload(decode=True).decode('utf-8', errors='ignore')
                except Exception:
                    pass
    else:
        try:
            return msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        except Exception:
            pass
    return ''


# ── Обработать одно письмо ───────────────────────────────────────────────────

def _decode_subject(msg) -> str:
    raw = email_lib.header.decode_header(msg.get('Subject', ''))[0]
    return raw[0].decode(raw[1] or 'utf-8') if isinstance(raw[0], bytes) else (raw[0] or '')


async def process_message(raw: bytes):
    """Парсит письмо, создаёт жалобу если нужно.
    Возвращает (from_addr, complaint_id, category, route) или None.
    """
    msg         = email_lib.message_from_bytes(raw)
    from_raw    = msg.get('From', '')
    from_addr   = email.utils.parseaddr(from_raw)[1]
    subject_str = _decode_subject(msg)
    body        = get_body(msg)

    if not body.strip() and not subject_str.strip():
        return None

    logger.info(f'Письмо от {from_addr}: «{subject_str[:60]}»')

    # ── Письмо от 2ГИС: сначала проверяем — жалоба ли ──────────────────────
    if is_from_2gis(from_addr):
        logger.info('Источник: 2ГИС — проверяю является ли отзыв жалобой')
        data = await extract_2gis_review(subject_str, body)
        if not data:
            return None

        if not data.get('is_complaint'):
            rating = data.get('rating')
            logger.info(
                f'2ГИС: отзыв не является жалобой (оценка={rating}) — пропускаю'
            )
            return None

        rating  = data.get('rating')
        route   = data.get('route') or None
        category = data.get('category') if data.get('category') in VALID_CATEGORIES else 'condition'
        comment  = data.get('comment') or body[:500]
        name     = data.get('reviewer_name') or '2ГИС-отзыв'

        rating_str = f' (оценка {rating}★)' if rating else ''
        comment_full = f'[2ГИС{rating_str}] {comment}'

        complaint_id = db.save_complaint(
            route=route or 'Не указан',
            comment=comment_full,
            photo_path=None,
            user_id=0,
            created_at=datetime.utcnow().isoformat(),
            username=from_addr,
            user_full_name=name,
            category=category,
        )
        logger.info(f'Жалоба #{complaint_id} создана из 2ГИС-отзыва | категория={category}{rating_str}')
        return from_addr, complaint_id, category, route

    # ── Обычное письмо ───────────────────────────────────────────────────────
    data = await extract_complaint(subject_str, body)
    if not data:
        logger.warning(f'OpenAI не вернул данные для письма от {from_addr}')
        return None

    route    = data.get('route') or None
    category = data.get('category') if data.get('category') in VALID_CATEGORIES else 'suggestion'
    comment  = data.get('comment') or body[:500]
    name     = data.get('sender_name') or from_addr

    complaint_id = db.save_complaint(
        route=route or 'Не указан',
        comment=comment,
        photo_path=None,
        user_id=0,
        created_at=datetime.utcnow().isoformat(),
        username=from_addr,
        user_full_name=name,
        category=category,
    )
    logger.info(f'Жалоба #{complaint_id} создана из email {from_addr} | категория={category}')
    return from_addr, complaint_id, category, route


# ── Основной цикл проверки почты ─────────────────────────────────────────────

async def check_inbox():
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        logger.warning('GMAIL_USER / GMAIL_APP_PASSWORD не заданы — email-ридер отключён')
        return

    try:
        mail = imaplib.IMAP4_SSL('imap.gmail.com', 993)
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select('INBOX')

        _, data = mail.search(None, 'UNSEEN')
        ids = data[0].split()

        if not ids:
            mail.close(); mail.logout()
            return

        logger.info(f'Найдено {len(ids)} непрочитанных писем')

        for mail_id in ids:
            _, msg_data = mail.fetch(mail_id, '(RFC822)')
            raw = msg_data[0][1]

            result = await process_message(raw)
            if result and len(result) == 4:
                from_addr, complaint_id, category, route = result
                if complaint_id:
                    mail.store(mail_id, '+FLAGS', '\\Seen')
                    send_confirmation(from_addr, complaint_id, category, route)

        mail.close()
        mail.logout()

    except imaplib.IMAP4.error as e:
        logger.error(f'IMAP ошибка (неверный логин/пароль?): {e}')
    except Exception as e:
        logger.error(f'Ошибка проверки почты: {e}')


async def main():
    db.init_db()
    logger.info(f'Email-ридер запущен. Интервал проверки: {CHECK_INTERVAL} сек.')
    while True:
        await check_inbox()
        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    asyncio.run(main())
