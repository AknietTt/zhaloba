"""
Диалог ИИ с клиентом для уточнения деталей жалобы.
Использует историю сообщений из БД как «мини-память» разговора.
"""
import logging
import os
import re

from openai import AsyncOpenAI

import db

logger = logging.getLogger(__name__)

# Максимум AI-сообщений в диалоге (потом диалог закрывается)
MAX_AI_MESSAGES = 4


# ── Первое сообщение после подачи жалобы ────────────────────────────────────

INITIAL_MSG = {
    'ru': (
        "Спасибо, жалоба принята! 📋\n\n"
        "Чтобы установить автобус и водителя, достаточно *одного* из этих номеров:\n\n"
        "🔢 *Гос. номер* (на номерном знаке, например 123 ABC 02)\n"
        "🔢 *Бортовой номер* (цифры на лобовом стекле под QR-кодом)\n"
        "🔢 *Гаражный номер* (обычно начинается с «А», например А1004)\n\n"
        "Если не запомнили ни один — напишите «не помню» 👍"
    ),
    'kk': (
        "Рақмет, шағымыңыз қабылданды! 📋\n\n"
        "Автобус пен жүргізушіні анықтау үшін мына нөмірлердің *біреуі* жеткілікті:\n\n"
        "🔢 *Мемлекеттік нөмір* (мысалы: 123 ABC 02)\n"
        "🔢 *Бортовой нөмір* (алдыңғы шынының QR-коды астындағы цифрлар)\n"
        "🔢 *Гараж нөмірі* (мысалы: А1004)\n\n"
        "Есіңізде жоқ болса — «есімде жоқ» деп жазыңыз 👍"
    ),
    'en': (
        "Thank you, your complaint has been received! 📋\n\n"
        "To identify the bus and driver, *any one* of these is enough:\n\n"
        "🔢 *License plate* (e.g. 123 ABC 02)\n"
        "🔢 *Board number* (digits on the windshield under the QR code)\n"
        "🔢 *Garage number* (usually starts with 'A', e.g. A1004)\n\n"
        "If you don't remember any — just write 'don't remember' 👍"
    ),
}

_SYSTEM = {
    'ru': """Ты — оператор поддержки городского автопарка Астаны.
Клиент подал жалобу. Тебе нужно узнать ОДИН любой номер автобуса для его идентификации.

Подходит любой из трёх (достаточно одного!):
- Гос. номер (номерной знак, например: 123 ABC 02)
- Бортовой номер (цифры на лобовом стекле под QR-кодом)
- Гаражный номер (например: А1004)

Правила:
- Отвечай коротко — 1–2 предложения
- Как только клиент дал ЛЮБОЙ один номер — подтверди его и сразу заверши: «жалоба будет рассмотрена в течение 3 рабочих дней»
- Не проси остальные номера если один уже есть
- Если клиент говорит что не помнит номер — объясни: «На линии одновременно работает много автобусов, без номера мы не сможем точно определить водителя или автобус.»
  Затем спроси: «Если вы оплачивали проезд, в чеке есть бортовой номер автобуса — можете его прислать?»
- Если клиент говорит что нет ни номера ни чека — скажи: «К сожалению, без идентификатора автобуса мы не сможем установить конкретного водителя. Жалоба будет зарегистрирована, но привязать её к определённому сотруднику не получится.» и заверши диалог.
- Если клиент прислал фото или чек — подтверди получение и заверши диалог
- Никогда не придумывай номера
- Пиши только по-русски""",

    'kk': """Сіз — Астана қалалық автопаркінің қолдау операторысыз.
Клиент шағым берді. Автобусты анықтау үшін кез келген БІР нөмір жеткілікті.

Қолайлы нөмірлер (біреуі жеткілікті!):
- Мемлекеттік нөмір (мысалы: 123 ABC 02)
- Бортовой нөмір (алдыңғы шынының QR-коды астындағы цифрлар)
- Гараж нөмірі (мысалы: А1004)

Ережелер:
- Қысқаша жауап беріңіз — 1–2 сөйлем
- Клиент кез келген БІР нөмір берсе — растап, диалогты аяқтаңыз: «шағым 3 жұмыс күні ішінде қаралады»
- Бір нөмір болса, қалғандарын сұрамаңыз
- Клиент нөмірді есіне түсіре алмаса — түсіндіріңіз: «Жолда бір уақытта көп автобус жүреді, нөмірсіз жүргізушіні немесе автобусты дәл анықтай алмаймыз.»
  Содан кейін сұраңыз: «Жол ақысын төлесеңіз, чекте автобустың бортовой нөмірі болады — жібере аласыз ба?»
- Клиент нөмір де, чек те жоқ десе — айтыңыз: «Өкінішке орай, автобус идентификаторынсыз нақты жүргізушіні анықтай алмаймыз. Шағым тіркеледі, бірақ белгілі бір қызметкерге байланыстыру мүмкін болмайды.» және диалогты аяқтаңыз.
- Тек қазақ тілінде жазыңыз""",

    'en': """You are a support operator of Astana city bus fleet.
The client filed a complaint. You need just ONE bus identifier to locate it.

Any one of these works (one is enough!):
- License plate (e.g. 123 ABC 02)
- Board number (digits on the windshield under the QR code)
- Garage number (e.g. A1004)

Rules:
- Keep replies short — 1–2 sentences
- As soon as the client provides ANY one identifier — confirm it and close: 'your complaint will be reviewed within 3 business days'
- Do NOT ask for the other numbers once you have one
- If client says they don't remember any number — explain: 'Many buses operate at the same time, so without a number we cannot identify the specific driver or bus.'
  Then ask: 'If you paid for the ride, your receipt contains the bus board number — could you share it?'
- If client has neither a number nor a receipt — say: 'Unfortunately, without a bus identifier we cannot determine the specific driver. Your complaint will be registered, but we won't be able to link it to a specific employee.' Then close the dialogue.
- If client sends a photo or receipt — confirm receipt and close
- Never invent numbers
- Write only in English""",
}


# ── Логика ──────────────────────────────────────────────────────────────────

# Латинские буквы → кириллические двойники (визуально одинаковые)
_LAT_TO_CYR = str.maketrans('ABCEHKMOPTXabcehkmoptx',
                              'АВСЕНКМОРТХавсенкмортх')


def normalize_garage(value: str) -> str:
    """Приводит гаражный номер к единому виду: латиница → кириллица, верхний регистр."""
    return value.translate(_LAT_TO_CYR).upper()


def extract_bus_identifier(text: str) -> dict | None:
    """Извлекает идентификатор автобуса из текста клиента с помощью regex.

    Возвращает {'type': 'garage'|'board'|'plate', 'value': str} или None.
    Порядок приоритетов: гаражный → бортовой → гос.номер.
    """
    if not text:
        return None

    # Гаражный номер: А1004, Е035, K729 — одна буква (любая) + 3-4 цифры
    m = re.search(r'\b([А-ЯЁA-Zа-яёa-z]\s*\d{3,4})\b', text)
    if m:
        val = normalize_garage(re.sub(r'\s+', '', m.group(1)))
        return {'type': 'garage', 'value': val}

    # Бортовой / QR-номер: отдельное 5-значное число
    m = re.search(r'(?<!\d)(\d{5})(?!\d)', text)
    if m:
        return {'type': 'board', 'value': m.group(1)}

    # Гос. номер РК: 3 цифры + 2-3 буквы + 2 цифры, с пробелами или без
    m = re.search(r'(\d{3})\s*([A-ZА-ЯЁa-zа-яё]{2,3})\s*(\d{2})\b', text)
    if m:
        letters = m.group(2).upper()
        plate = f"{m.group(1)} {letters} {m.group(3)}"
        return {'type': 'plate', 'value': plate}

    return None


def should_clarify(complaint: dict) -> bool:
    """Нужен ли диалог уточнения для этой жалобы."""
    # Благодарности/пожелания — не нужен номер автобуса
    if complaint.get('category') == 'suggestion':
        return False
    # Уже есть и гаражный номер и инфо об автобусе из чека — достаточно
    if complaint.get('bus_garage_number') and complaint.get('bus_info'):
        return False
    return True


def _count_ai_messages(complaint_id: int) -> int:
    """Сколько раз ИИ уже ответил в этом диалоге."""
    history = db.get_messages_for_complaint(complaint_id, limit=50)
    return sum(1 for m in history if m[3] == 'admin')  # m[3] = sender_type


async def generate_reply(
    complaint: dict,
    new_message: str,
    has_file: bool = False,
    lang: str = 'ru',
) -> str | None:
    """Генерирует ответ ИИ на сообщение пользователя.

    Загружает историю из БД (мини-память), передаёт в OpenAI как контекст.
    Возвращает None если диалог завершён или OpenAI недоступен.
    """
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        return None

    complaint_id = complaint['id']

    # Диалог уже завершён — не отвечаем
    if _count_ai_messages(complaint_id) >= MAX_AI_MESSAGES:
        return None

    # Контекст жалобы для системного промпта
    ctx = (
        f"\n\nДетали жалобы: маршрут={complaint.get('route') or '?'}, "
        f"категория={complaint.get('category') or '?'}, "
        f"описание={complaint.get('comment') or '?'}, "
        f"гараж_из_чека={complaint.get('bus_garage_number') or 'нет'}, "
        f"автобус_из_чека={complaint.get('bus_info') or 'нет'}"
    )

    system = _SYSTEM.get(lang, _SYSTEM['ru']) + ctx

    # ── Загружаем историю из БД как память разговора ─────────────────────────
    history = db.get_messages_for_complaint(complaint_id, limit=20)

    openai_msgs = [{'role': 'system', 'content': system}]

    for m in history:
        # m = (id, complaint_id, sender_id, sender_type, sender_name, text, created_at, file_path)
        sender_type = m[3]
        text        = m[5] or ''
        file_path   = m[7]

        role = 'assistant' if sender_type == 'admin' else 'user'
        content = text
        if file_path:
            content += ' [прикреплён файл]'
        if content.strip():
            openai_msgs.append({'role': role, 'content': content})

    # Текущее сообщение пользователя
    current = new_message or ''
    if has_file:
        current += ' [прикреплён файл/чек]'
    if current.strip():
        openai_msgs.append({'role': 'user', 'content': current})

    try:
        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model='gpt-4o-mini',
            messages=openai_msgs,
            max_tokens=300,
            temperature=0.5,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f'OpenAI ошибка в диалоге уточнения: {e}')
        return None
