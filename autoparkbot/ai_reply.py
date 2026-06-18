import os
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Только эти категории получают авто-ответ от ИИ.
# Жалобы на водителя (driver) и интервал (interval) требуют ручной проверки.
AUTO_REPLY_CATEGORIES = {'climate', 'condition', 'suggestion'}

_CATEGORY_CONTEXT = {
    'climate': {
        'ru': 'кондиционер или отопление в автобусе',
        'kk': 'автобустағы кондиционер немесе жылыту жүйесі',
        'en': 'air conditioning or heating on the bus',
    },
    'condition': {
        'ru': 'санитарное или техническое состояние автобуса',
        'kk': 'автобустың санитарлық немесе техникалық жай-күйі',
        'en': 'sanitary or technical condition of the bus',
    },
    'suggestion': {
        'ru': 'пожелание или благодарность',
        'kk': 'тілек немесе алғыс',
        'en': 'suggestion or words of gratitude',
    },
}

_SYSTEM_PROMPTS = {
    'ru': (
        'Ты — вежливый оператор службы поддержки городского автопарка города Астаны. '
        'Клиент написал обращение по городскому автобусу. '
        'Ответь клиенту кратко, уважительно и по-деловому: '
        'подтверди получение обращения, сообщи что оно зарегистрировано и будет рассмотрено '
        'в течение 3 рабочих дней. Если клиент выражает благодарность — поблагодари его в ответ. '
        'Пиши только на русском языке. Максимум 4 предложения.'
    ),
    'kk': (
        'Сіз — Астана қаласы автопаркі қолдау қызметінің сыпайы операторысыз. '
        'Клиент қалалық автобус бойынша өтініш жолдады. '
        'Клиентке қысқаша, сыйластықпен және іскери жауап беріңіз: '
        'өтінішті алғанын растаңыз, тіркелгенін және 3 жұмыс күні ішінде '
        'қаралатынын хабарлаңыз. Клиент алғысын білдірсе — оған алғыс айтыңыз. '
        'Тек қазақ тілінде жазыңыз. Ең көбі 4 сөйлем.'
    ),
    'en': (
        'You are a polite customer support operator of the city bus fleet in Astana, Kazakhstan. '
        'A passenger has submitted a complaint or suggestion about a city bus. '
        'Reply briefly, respectfully, and professionally: confirm receipt, say it is registered '
        'and will be reviewed within 3 business days. If the message is gratitude, thank the passenger. '
        'Write only in English. Maximum 4 sentences.'
    ),
}


async def generate_auto_reply(
    category: str,
    route: str,
    comment: str,
    lang: str = 'ru',
) -> str | None:
    """Сгенерировать авто-ответ для некритичных категорий жалоб.
    Возвращает текст ответа или None если OpenAI не настроен / ошибка.
    """
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        logger.warning('OPENAI_API_KEY не задан — авто-ответ пропущен')
        return None

    if category not in AUTO_REPLY_CATEGORIES:
        return None

    cat_ctx = _CATEGORY_CONTEXT.get(category, {}).get(lang, category)
    system = _SYSTEM_PROMPTS.get(lang, _SYSTEM_PROMPTS['ru'])
    user_content = (
        f'Маршрут/Route: {route}\n'
        f'Тема/Category: {cat_ctx}\n'
        f'Обращение клиента/Message: {comment}'
    )

    try:
        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': system},
                {'role': 'user',   'content': user_content},
            ],
            max_tokens=300,
            temperature=0.7,
        )
        text = response.choices[0].message.content
        return text.strip() if text else None
    except Exception as e:
        logger.error(f'OpenAI ошибка при генерации авто-ответа: {e}')
        return None
