"""
Парсер отзывов 2GIS через официальный API.
Ключ: зарегистрируйся на dev.2gis.ru → бесплатно.
"""
import httpx
import json
import sys
import os

# Вставь свой ключ с dev.2gis.ru
API_KEY = os.getenv('GIS_API_KEY', 'YOUR_KEY_HERE')

# ID организации из URL 2GIS:
# https://2gis.kz/astana/firm/70000001018076362
#                               ↑ это и есть firm_id
FIRM_ID = '70000001018076362'

REVIEWS_URL = 'https://public-api.reviews.2gis.com/2.0/branches/{firm_id}/reviews'


def fetch_reviews(firm_id: str, limit: int = 50, offset: int = 0) -> dict:
    url = REVIEWS_URL.format(firm_id=firm_id)
    params = {
        'key':    API_KEY,
        'limit':  limit,
        'offset': offset,
        'locale': 'ru_KZ',
        'sort':   'date_desc',
    }
    r = httpx.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_all_reviews(firm_id: str, max_reviews: int = 500) -> list[dict]:
    """Получить все отзывы постранично."""
    reviews = []
    offset = 0
    limit = 50

    while len(reviews) < max_reviews:
        data = fetch_reviews(firm_id, limit=limit, offset=offset)
        items = data.get('reviews', [])
        if not items:
            break
        reviews.extend(items)

        total = data.get('total', 0)
        print(f'  Загружено: {len(reviews)} / {total}')

        offset += limit
        if offset >= total:
            break

    return reviews


def parse_review(r: dict) -> dict:
    return {
        'id':      r.get('id', ''),
        'author':  r.get('user', {}).get('name', 'Аноним'),
        'rating':  r.get('rating', 0),
        'text':    (r.get('text') or '').strip(),
        'date':    (r.get('date_created') or '')[:10],
        'likes':   r.get('likes_count', 0),
        'answer':  (r.get('official_answer') or {}).get('text', ''),
    }


def print_reviews(reviews: list[dict]):
    print(f'\nВсего отзывов: {len(reviews)}\n' + '─' * 60)
    for r in reviews:
        p = parse_review(r)
        stars = '⭐' * (p['rating'] or 0)
        print(f"\n{stars}  {p['author']}  |  {p['date']}")
        if p['text']:
            print(f"  {p['text'][:400]}")
        if p['answer']:
            print(f"\n  💬 Ответ компании:\n  {p['answer'][:200]}")


def save_to_json(reviews: list[dict], path: str = 'reviews.json'):
    data = [parse_review(r) for r in reviews]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'\nСохранено в {path}')


def stats(reviews: list[dict]):
    if not reviews:
        return
    parsed = [parse_review(r) for r in reviews]
    ratings = [p['rating'] for p in parsed if p['rating']]
    avg = sum(ratings) / len(ratings) if ratings else 0
    by_rating = {i: ratings.count(i) for i in range(1, 6)}
    print(f'\n── Статистика ────────────────────')
    print(f'Средняя оценка: {avg:.1f} ⭐')
    for stars, count in sorted(by_rating.items(), reverse=True):
        bar = '█' * count
        print(f'  {stars}⭐ {bar} ({count})')


if __name__ == '__main__':
    firm_id = sys.argv[1] if len(sys.argv) > 1 else FIRM_ID

    if API_KEY == 'YOUR_KEY_HERE':
        print('❌ Укажи API ключ:')
        print('   1. Зарегистрируйся на https://dev.2gis.ru')
        print('   2. Создай проект → скопируй ключ')
        print('   3. Вставь в переменную API_KEY в этом файле')
        print('      или запусти: GIS_API_KEY=твой_ключ python gis_reviews.py')
        sys.exit(1)

    print(f'Получаем отзывы для организации {firm_id}...')
    reviews = fetch_all_reviews(firm_id)
    print_reviews(reviews)
    stats(reviews)
    save_to_json(reviews)
