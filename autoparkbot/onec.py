import os
import json
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

ONEC_URL = os.getenv('ONEC_URL')
ONEC_TOKEN = os.getenv('ONEC_TOKEN')
ONEC_WAYBILL_URL = os.getenv('ONEC_WAYBILL_URL')
ONEC_WAYBILL_TOKEN = os.getenv('ONEC_WAYBILL_TOKEN', ONEC_TOKEN)


async def send_complaint_to_onec(
    complaint_id: int,
    route: str,
    comment: str,
    photo_path: Optional[str],
    bus_info: Optional[str],
    username: Optional[str],
    user_full_name: Optional[str],
    user_id: int,
    created_at: str,
) -> dict:
    """Отправить жалобу в 1С."""
    if not ONEC_URL:
        return {'status': 'skipped', 'reason': 'ONEC_URL не настроен'}

    payload = {
        'complaint_id': complaint_id,
        'route': route,
        'comment': comment,
        'photo_path': photo_path,
        'bus_info': bus_info,
        'username': username,
        'user_full_name': user_full_name,
        'user_id': user_id,
        'created_at': created_at,
    }

    headers = {}
    if ONEC_TOKEN:
        headers['Authorization'] = f'Bearer {ONEC_TOKEN}'

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(ONEC_URL, json=payload, headers=headers)
            result = {
                'status': 'ok' if resp.status_code == 200 else 'error',
                'status_code': resp.status_code,
                'body': resp.text[:500],
            }
            logger.info(f'Жалоба {complaint_id} отправлена в 1С: {result}')
            return result
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Ошибка при отправке жалобы {complaint_id} в 1С: {error_msg}')
        return {'status': 'error', 'error': error_msg}


async def update_status_in_onec(complaint_id: int, status: str) -> dict:
    """Обновить статус жалобы в 1С."""
    if not ONEC_URL:
        return {'status': 'skipped', 'reason': 'ONEC_URL не настроен'}

    endpoint = f"{ONEC_URL.rstrip('/')}/status"
    payload = {
        'complaint_id': complaint_id,
        'status': status,
    }

    headers = {}
    if ONEC_TOKEN:
        headers['Authorization'] = f'Bearer {ONEC_TOKEN}'

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.patch(endpoint, json=payload, headers=headers)
            result = {
                'status': 'ok' if resp.status_code == 200 else 'error',
                'status_code': resp.status_code,
                'body': resp.text[:500],
            }
            logger.info(f'Статус жалобы {complaint_id} обновлён в 1С: {result}')
            return result
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Ошибка при обновлении статуса {complaint_id} в 1С: {error_msg}')
        return {'status': 'error', 'error': error_msg}


async def get_waybill_by_garage_number(garage_number: str, event_id: str = 'engineerBD') -> dict:
    """Получить данные путевого листа по гаражному номеру из 1С."""
    if not ONEC_WAYBILL_URL:
        return {'status': 'skipped', 'reason': 'ONEC_WAYBILL_URL не настроен'}

    payload = {
        'garage_number': garage_number,
        'event_id': event_id,
    }
    headers = {}
    if ONEC_WAYBILL_TOKEN:
        headers['Authorization'] = f'Bearer {ONEC_WAYBILL_TOKEN}'

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                'GET', ONEC_WAYBILL_URL,
                content=json.dumps(payload).encode('utf-8'),
                headers={**headers, 'Content-Type': 'application/json'},
            )
            body = None
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            result = {
                'status': 'ok' if resp.status_code == 200 else 'error',
                'status_code': resp.status_code,
                'body': body,
            }
            logger.info(f'Путевой лист для {garage_number} получен из 1С: {result}')
            return result
    except Exception as e:
        error_msg = str(e)
        logger.error(f'Ошибка при получении путевого листа для {garage_number}: {error_msg}')
        return {'status': 'error', 'error': error_msg}
