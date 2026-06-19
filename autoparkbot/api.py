import os
import uuid
import logging
from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv
load_dotenv()

import db
import lookup
import onec
import conversation_ai
import httpx
import itsdangerous
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

app = FastAPI(title='Complaint API')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

_DATA_DIR = os.getenv('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(_DATA_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.mount('/uploads', StaticFiles(directory=UPLOAD_DIR), name='uploads')

db.init_db()

# session signer
SECRET_KEY = os.getenv('SECRET_KEY', os.getenv('TELEGRAM_TOKEN', 'dev-secret'))
signer = itsdangerous.URLSafeTimedSerializer(SECRET_KEY)

SESSION_COOKIE = 'session'

def create_session_token(username: str) -> str:
    return signer.dumps({'user': username})

def verify_session_token(token: str, max_age: int = 3600) -> Optional[str]:
    try:
        data = signer.loads(token, max_age=max_age)
        return data.get('user')
    except Exception:
        return None


@app.post('/complaints')
async def create_complaint(
    route: str = Form(...),
    comment: str = Form(...),
    receipt: Optional[UploadFile] = File(None),
):
    file_path = None
    bus_info = None

    if receipt:
        filename = f"receipt_{uuid.uuid4().hex}_{receipt.filename}"
        file_path = os.path.join(UPLOAD_DIR, filename)
        with open(file_path, 'wb') as f:
            f.write(await receipt.read())  

        number, bus_info, bus_entry = lookup.process_receipt(file_path)
        garage_number = bus_entry.get('garage_number') if bus_entry else None
    else:
        garage_number = None

    created_at = datetime.utcnow().isoformat()
    complaint_id = db.save_complaint(
        route=route,
        comment=comment,
        photo_path=file_path,
        user_id=0,
        created_at=created_at,
        bus_info=bus_info,
        bus_garage_number=garage_number,
    )

    # Send to 1C
    onec_result = None
    if complaint_id:
        onec_result = await onec.send_complaint_to_onec(
            complaint_id=complaint_id,
            route=route,
            comment=comment,    
            photo_path=file_path,
            bus_info=bus_info,
            username=None,
            user_full_name=None,
            user_id=0,
            created_at=created_at,
        )

    return JSONResponse({
        'status': 'ok',
        'id': complaint_id,
        'route': route,
        'comment': comment,
        'receipt_path': file_path,
        'bus_info': bus_info,
        'garage_number': garage_number,
        'onec_result': onec_result,
    })


@app.get('/stats/drivers')
def driver_stats():
    rows = db.get_driver_stats(limit=30)
    return [{'driver_name': r[0], 'driver_tab': r[1], 'count': r[2]} for r in rows]


@app.get('/complaints')
def list_complaints(
    page: int = 1, page_size: int = 20,
    route: Optional[str] = None,
    bus: Optional[str] = None,
    search: Optional[str] = None,
    driver: Optional[str] = None,
    category: Optional[str] = None,
):
    if page < 1 or page_size < 1:
        raise HTTPException(status_code=400, detail='page and page_size must be positive integers')
    total = db.count_complaints(route=route, bus=bus, search=search, driver=driver, category=category)
    offset = (page - 1) * page_size
    rows = db.list_complaints(limit=page_size, offset=offset, route=route, bus=bus, search=search, driver=driver, category=category)
    data = []
    for row in rows:
        id_, r, comment, photo_path, user_id, created_at, bus_info, bus_garage_number, username, user_full_name, status, driver_name, driver_tab, cat = row
        data.append({
            'id': id_,
            'route': r,
            'comment': comment,
            'photo_path': photo_path,
            'user_id': user_id,
            'username': username,
            'user_full_name': user_full_name,
            'created_at': created_at,
            'bus_info': bus_info,
            'bus_garage_number': bus_garage_number,
            'status': status,
            'driver_name': driver_name,
            'driver_tab': driver_tab,
            'category': cat,
        })
    return {
        'page': page,
        'page_size': page_size,
        'total': total,
        'total_pages': (total + page_size - 1) // page_size,
        'items': data,
    }


@app.get('/complaints/{complaint_id}/waybill')
async def get_complaint_waybill(complaint_id: int):
    complaint = db.get_complaint_by_id(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail='Жалоба не найдена')

    garage_number = complaint.get('bus_garage_number')

    # Если гаражный номер не сохранён — ищем в сообщениях чата
    if not garage_number:
        messages = db.get_messages_for_complaint(complaint_id, limit=50)
        for msg in messages:
            if msg[3] != 'user':
                continue
            identifier = conversation_ai.extract_bus_identifier(msg[5] or '')
            if not identifier:
                continue
            id_type, id_value = identifier['type'], identifier['value']
            if id_type == 'garage':
                # Гаражный → нормализуем и сразу в 1С
                garage_number = conversation_ai.normalize_garage(id_value)
                db.update_complaint_bus(complaint_id, bus_garage_number=garage_number)
                break
            elif id_type == 'board':
                bus_entry = lookup.find_bus_entry(id_value)
                if bus_entry:
                    garage_number = bus_entry['garage_number']
                    db.update_complaint_bus(complaint_id,
                                            bus_info=lookup.format_bus_info(bus_entry),
                                            bus_garage_number=garage_number)
                    break
            elif id_type == 'plate':
                bus_entry = lookup.find_bus_by_plate(id_value)
                if bus_entry:
                    garage_number = bus_entry['garage_number']
                    db.update_complaint_bus(complaint_id,
                                            bus_info=lookup.format_bus_info(bus_entry),
                                            bus_garage_number=garage_number)
                    break

    if not garage_number:
        raise HTTPException(status_code=400, detail='Гаражный номер не найден в жалобе')

    waybill = await onec.get_waybill_by_garage_number(garage_number)

    # Сохраняем данные водителя если 1С вернул путевой лист
    if waybill.get('status') == 'ok':
        body = waybill.get('body') or {}
        entry = body[0] if isinstance(body, list) and body else body if isinstance(body, dict) else {}
        driver = entry.get('Driver') or {}
        if driver.get('FIO'):
            db.update_driver_info(complaint_id, driver['FIO'], driver.get('TabNo', ''))

    return {
        'complaint_id': complaint_id,
        'garage_number': garage_number,
        'waybill': waybill,
    }


@app.post('/complaints/{complaint_id}/reply')
async def reply_to_user(complaint_id: int, message: str = Form(...)):
    complaint = db.get_complaint_by_id(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail='Жалоба не найдена')

    user_id = complaint.get('user_id')
    if not user_id:
        raise HTTPException(status_code=400, detail='Telegram ID не указан для этой жалобы')

    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        raise HTTPException(status_code=500, detail='TELEGRAM_TOKEN не настроен')

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': user_id, 'text': message},
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f'Telegram вернул ошибку: {resp.text}')

    db.update_status(complaint_id, 'replied')
    await onec.update_status_in_onec(complaint_id, 'replied')

    return {'status': 'ok', 'sent_to': user_id, 'message': message}


ALLOWED_STATUSES = {'new', 'replied', 'in_progress', 'closed'}

@app.patch('/complaints/{complaint_id}/status')
async def update_status(complaint_id: int, status: str = Form(...)):
    if status not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f'Недопустимый статус. Разрешены: {", ".join(ALLOWED_STATUSES)}',
        )
    complaint = db.get_complaint_by_id(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail='Жалоба не найдена')

    db.update_status(complaint_id, status)

    # Send status update to 1C
    await onec.update_status_in_onec(complaint_id, status)

    return {'id': complaint_id, 'status': status}


@app.get('/')
def root():
    return {'message': 'Complaint API is running'}


@app.get('/stats')
def stats_page(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    user = None
    if token:
        user = verify_session_token(token)
    if not user:
        return RedirectResponse(url='/login')

    import sqlite3
    conn = sqlite3.connect(db.DB_PATH)
    cur = conn.cursor()

    # Топ маршрутов
    cur.execute("""
        SELECT route, COUNT(*) as cnt FROM complaints
        WHERE route IS NOT NULL AND route != ''
        GROUP BY route ORDER BY cnt DESC LIMIT 15
    """)
    top_routes = cur.fetchall()

    # Топ автобусов по гаражному номеру
    cur.execute("""
        SELECT bus_garage_number, bus_info, COUNT(*) as cnt FROM complaints
        WHERE bus_garage_number IS NOT NULL AND bus_garage_number != ''
        GROUP BY bus_garage_number ORDER BY cnt DESC LIMIT 15
    """)
    top_buses = cur.fetchall()

    # Жалобы по месяцам
    cur.execute("""
        SELECT substr(created_at, 1, 7) as month, COUNT(*) as cnt FROM complaints
        GROUP BY month ORDER BY month DESC LIMIT 12
    """)
    by_month = cur.fetchall()

    # Жалобы по неделям (последние 10 недель)
    cur.execute("""
        SELECT strftime('%Y-W%W', created_at) as week, COUNT(*) as cnt FROM complaints
        GROUP BY week ORDER BY week DESC LIMIT 10
    """)
    by_week = cur.fetchall()

    # По статусам
    cur.execute("SELECT status, COUNT(*) FROM complaints GROUP BY status")
    by_status = cur.fetchall()

    # Общее
    cur.execute("SELECT COUNT(*) FROM complaints")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM complaints WHERE date(created_at) = date('now')")
    today = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM complaints WHERE date(created_at) >= date('now', '-7 days')")
    week_total = cur.fetchone()[0]

    conn.close()

    def bar_chart(rows, max_width=300):
        if not rows:
            return '<p style="color:#999">Нет данных</p>'
        max_val = max(r[-1] for r in rows) or 1
        html = '<div style="font-size:13px">'
        colors = ['#4e79a7','#f28e2b','#e15759','#76b7b2','#59a14f','#edc948','#b07aa1','#ff9da7','#9c755f','#bab0ac']
        for i, row in enumerate(rows):
            label = str(row[0]) if row[0] else '—'
            count = row[-1]
            width = int(count / max_val * max_width)
            color = colors[i % len(colors)]
            html += f'''<div style="display:flex;align-items:center;margin:4px 0">
                <div style="width:120px;text-align:right;padding-right:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#333" title="{label}">{label}</div>
                <div style="background:{color};height:20px;width:{width}px;border-radius:3px;min-width:4px"></div>
                <div style="margin-left:6px;color:#555;font-weight:bold">{count}</div>
            </div>'''
        html += '</div>'
        return html

    status_colors = {'new': '#ffc107', 'replied': '#28a745', 'in_progress': '#17a2b8', 'closed': '#6c757d'}

    html = '''<html><head><meta charset="utf-8"><style>
    body{font-family:Arial,sans-serif;margin:0;background:#f8f9fa}
    .topbar{background:#343a40;color:white;padding:12px 24px;display:flex;align-items:center;gap:20px}
    .topbar a{color:#adb5bd;text-decoration:none;font-size:14px}
    .topbar a:hover{color:white}
    .container{max-width:1100px;margin:24px auto;padding:0 16px}
    .kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}
    .kpi{background:white;border-radius:8px;padding:20px;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,.08)}
    .kpi .val{font-size:36px;font-weight:bold;color:#343a40}
    .kpi .lbl{font-size:13px;color:#888;margin-top:4px}
    .grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
    .card{background:white;border-radius:8px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
    .card h3{margin:0 0 16px 0;font-size:16px;color:#343a40;border-bottom:2px solid #f0f0f0;padding-bottom:8px}
    .status-badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:bold;margin:2px}
    @media(max-width:700px){.grid2{grid-template-columns:1fr}.kpi-row{grid-template-columns:1fr 1fr}}
    </style></head><body>'''

    html += f'''<div class="topbar">
        <strong style="font-size:18px">📊 Статистика жалоб</strong>
        <a href="/admin">← Назад в админку</a>
    </div>
    <div class="container">'''

    # KPI карточки
    status_map = dict(by_status)
    html += '<div class="kpi-row">'
    html += f'<div class="kpi"><div class="val">{total}</div><div class="lbl">Всего жалоб</div></div>'
    html += f'<div class="kpi"><div class="val" style="color:#007bff">{today}</div><div class="lbl">Сегодня</div></div>'
    html += f'<div class="kpi"><div class="val" style="color:#17a2b8">{week_total}</div><div class="lbl">За 7 дней</div></div>'
    html += f'<div class="kpi"><div class="val" style="color:#ffc107">{status_map.get("new", 0)}</div><div class="lbl">Новых (не обработано)</div></div>'
    html += '</div>'

    # Строка 1: маршруты + автобусы
    html += '<div class="grid2">'

    html += '<div class="card"><h3>🚌 Топ маршрутов</h3>'
    html += bar_chart(top_routes)
    html += '</div>'

    html += '<div class="card"><h3>🔢 Топ автобусов (гараж. №)</h3>'
    html += bar_chart([(r[0], r[2]) for r in top_buses])
    html += '</div>'

    html += '</div>'

    # Строка 2: по месяцам + по неделям
    html += '<div class="grid2">'

    html += '<div class="card"><h3>📅 По месяцам</h3>'
    html += bar_chart(list(reversed(by_month)))
    html += '</div>'

    html += '<div class="card"><h3>📆 По неделям</h3>'
    html += bar_chart(list(reversed(by_week)))
    html += '</div>'

    html += '</div>'

    # Статусы
    html += '<div class="card" style="margin-bottom:24px"><h3>📋 По статусам</h3><div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center">'
    for status, cnt in by_status:
        color = status_colors.get(status, '#6c757d')
        html += f'<div style="background:{color};color:white;padding:10px 20px;border-radius:8px;font-size:15px"><strong>{cnt}</strong><br><span style="font-size:12px">{status.upper()}</span></div>'
    html += '</div></div>'

    html += '</div></body></html>'
    return HTMLResponse(content=html)


@app.get('/complaints/{complaint_id}/messages')
def get_chat(complaint_id: int, limit: int = 100, offset: int = 0):
    complaint = db.get_complaint_by_id(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail='Жалоба не найдена')

    rows = db.get_messages_for_complaint(complaint_id, limit=limit, offset=offset)
    total = db.count_messages_for_complaint(complaint_id)

    messages = []
    for row in rows:
        id_, cid, sender_id, sender_type, sender_name, text, created_at, file_path = row
        messages.append({
            'id': id_,
            'sender_id': sender_id,
            'sender_type': sender_type,
            'sender_name': sender_name,
            'text': text,
            'created_at': created_at,
            'file_path': file_path,
        })

    return {
        'complaint_id': complaint_id,
        'total_messages': total,
        'messages': messages,
    }


@app.post('/complaints/{complaint_id}/messages')
async def add_message(
    complaint_id: int,
    text: str = Form(...),
    sender_id: int = Form(default=0),
    sender_name: str = Form(default='Админ'),
):
    complaint = db.get_complaint_by_id(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail='Жалоба не найдена')

    if not text or not text.strip():
        raise HTTPException(status_code=400, detail='Текст сообщения не может быть пустым')

    # sender_type определяется по sender_id (0 = админ/система)
    sender_type = 'admin' if sender_id == 0 else 'user'
    msg_id = db.save_message(
        complaint_id=complaint_id,
        sender_id=sender_id,
        sender_type=sender_type,
        text=text.strip(),
        sender_name=sender_name,
    )

    # Отправить сообщение в Telegram если это админ отвечает
    if sender_type == 'admin' and complaint.get('user_id'):
        token = os.getenv('TELEGRAM_TOKEN')
        if token:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(
                        f'https://api.telegram.org/bot{token}/sendMessage',
                        json={'chat_id': complaint['user_id'], 'text': text.strip()},
                    )
            except Exception as e:
                logger.error(f'Ошибка отправки в Telegram: {e}')

    return {
        'id': msg_id,
        'complaint_id': complaint_id,
        'sender_type': sender_type,
        'sender_name': sender_name,
        'text': text.strip(),
        'file_path': None,
        'created_at': datetime.utcnow().isoformat(),
    }


@app.post('/complaints/{complaint_id}/request-evidence')
async def request_evidence(complaint_id: int, message: str = Form(default='')):
    """Отправить пользователю запрос на доп. доказательства."""
    complaint = db.get_complaint_by_id(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail='Жалоба не найдена')

    text = message.strip() or (
        '📎 Пожалуйста, пришлите дополнительные доказательства по вашей жалобе: '
        'фото, видео или документы, подтверждающие нарушение.'
    )

    token = os.getenv('TELEGRAM_TOKEN')
    if token and complaint.get('user_id'):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f'https://api.telegram.org/bot{token}/sendMessage',
                    json={'chat_id': complaint['user_id'], 'text': text},
                )
        except Exception as e:
            logger.error(f'Ошибка отправки запроса доказательств: {e}')

    msg_id = db.save_message(
        complaint_id=complaint_id,
        sender_id=0,
        sender_type='admin',
        sender_name='Админ',
        text=text,
    )
    db.update_status(complaint_id, 'in_progress')

    return {'status': 'ok', 'message_id': msg_id, 'text': text}


_SIDEBAR_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;background:#f1f5f9;color:#1e293b;min-height:100vh;display:flex}
.sidebar{width:240px;min-height:100vh;background:#1e2940;display:flex;flex-direction:column;flex-shrink:0;position:fixed;top:0;left:0;bottom:0;z-index:100}
.sidebar-logo{padding:24px 20px 16px;border-bottom:1px solid rgba(255,255,255,.08)}
.sidebar-logo .logo-title{color:#fff;font-size:16px;font-weight:700;line-height:1.3}
.sidebar-logo .logo-sub{color:#94a3b8;font-size:11px;margin-top:2px}
.sidebar-nav{padding:16px 0;flex:1}
.nav-section{padding:0 12px 8px;color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px}
.nav-item{display:flex;align-items:center;gap:10px;padding:10px 16px;color:#94a3b8;text-decoration:none;font-size:14px;transition:all .15s;margin:1px 8px;border-radius:8px}
.nav-item:hover{background:rgba(255,255,255,.08);color:#fff}
.nav-item.active{background:#3b82f6;color:#fff}
.nav-item .icon{font-size:16px;width:20px;text-align:center}
.sidebar-footer{padding:16px;border-top:1px solid rgba(255,255,255,.08)}
.sidebar-user{color:#94a3b8;font-size:12px;display:flex;align-items:center;gap:8px}
.sidebar-user .avatar{width:28px;height:28px;background:#3b82f6;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:12px}
.main{margin-left:240px;flex:1;min-height:100vh;display:flex;flex-direction:column}
.topbar{background:#fff;border-bottom:1px solid #e2e8f0;padding:0 24px;height:56px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0;position:sticky;top:0;z-index:50}
.topbar-title{font-size:16px;font-weight:600;color:#1e293b}
.topbar-breadcrumb{font-size:13px;color:#64748b}
.topbar-breadcrumb a{color:#3b82f6;text-decoration:none}
.content{padding:24px;flex:1}
.card{background:#fff;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.06),0 1px 2px rgba(0,0,0,.04);overflow:hidden}
.card-header{padding:16px 20px;border-bottom:1px solid #f1f5f9;display:flex;align-items:center;justify-content:space-between}
.card-header h3{font-size:15px;font-weight:600;color:#1e293b}
.card-body{padding:20px}
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}
.kpi{background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.kpi-value{font-size:32px;font-weight:700;line-height:1}
.kpi-label{font-size:12px;color:#64748b;margin-top:6px;font-weight:500}
.kpi-icon{font-size:24px;margin-bottom:8px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.badge{display:inline-flex;align-items:center;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.4px}
.badge-new{background:#fef3c7;color:#92400e}
.badge-replied{background:#d1fae5;color:#065f46}
.badge-in_progress{background:#dbeafe;color:#1e40af}
.badge-closed{background:#f1f5f9;color:#475569}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;padding:10px 14px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#64748b;background:#f8fafc;border-bottom:1px solid #e2e8f0}
td{padding:12px 14px;border-bottom:1px solid #f1f5f9;vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:#f8fafc}
.btn{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:8px;font-size:13px;font-weight:500;text-decoration:none;border:none;cursor:pointer;transition:all .15s}
.btn-primary{background:#3b82f6;color:#fff}
.btn-primary:hover{background:#2563eb}
.btn-sm{padding:4px 10px;font-size:12px;border-radius:6px}
.btn-outline{background:#fff;color:#475569;border:1px solid #e2e8f0}
.btn-outline:hover{background:#f8fafc}
.pagination{display:flex;align-items:center;gap:6px;margin-top:16px}
.page-btn{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:8px;font-size:13px;text-decoration:none;color:#475569;background:#fff;border:1px solid #e2e8f0;transition:all .15s}
.page-btn:hover,.page-btn.active{background:#3b82f6;color:#fff;border-color:#3b82f6}
.page-info{font-size:13px;color:#64748b;padding:0 8px}
.msg-bubble{max-width:75%;padding:10px 14px;border-radius:12px;margin:4px 0;font-size:14px;line-height:1.5}
.msg-user{background:#eff6ff;border-bottom-left-radius:4px;align-self:flex-start}
.msg-admin{background:#3b82f6;color:#fff;border-bottom-right-radius:4px;align-self:flex-end}
.msg-meta{font-size:11px;color:#94a3b8;margin-top:2px}
.msg-meta-admin{color:rgba(255,255,255,.7)}
.chat-area{display:flex;flex-direction:column;gap:8px;min-height:300px;max-height:500px;overflow-y:auto;padding:16px;background:#f8fafc;border-radius:10px;margin-bottom:16px}
.chat-input-row{display:flex;gap:10px;align-items:flex-end}
.chat-input-row textarea{flex:1;padding:12px;border:1px solid #e2e8f0;border-radius:10px;font-size:14px;resize:none;font-family:inherit;outline:none;transition:border .15s}
.chat-input-row textarea:focus{border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.1)}
.waybill-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}
.waybill-block{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px}
.waybill-block h4{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#64748b;margin-bottom:10px}
.waybill-row{display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid #f1f5f9;font-size:13px}
.waybill-row:last-child{border-bottom:none}
.waybill-key{color:#94a3b8;font-size:12px}
.waybill-val{font-weight:500;color:#1e293b}
.bar-wrap{font-size:13px}
.bar-row{display:flex;align-items:center;gap:8px;margin:5px 0}
.bar-label{width:130px;text-align:right;color:#475569;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:12px}
.bar-track{flex:1;background:#f1f5f9;border-radius:4px;height:18px;overflow:hidden}
.bar-fill{height:100%;border-radius:4px;transition:width .3s}
.bar-count{width:30px;text-align:left;font-weight:600;color:#1e293b;font-size:12px}
.alert{padding:12px 16px;border-radius:8px;font-size:13px;margin-bottom:12px}
.alert-warn{background:#fef3c7;color:#92400e;border:1px solid #fde68a}
.alert-info{background:#eff6ff;color:#1e40af;border:1px solid #bfdbfe}
"""


def _sidebar(active: str, user: str) -> str:
    items = [
        ('admin',  '📋', 'Жалобы',     '/admin'),
        ('stats',  '📊', 'Статистика', '/stats'),
    ]
    nav = ''
    for key, icon, label, href in items:
        cls = 'nav-item active' if active == key else 'nav-item'
        nav += f'<a href="{href}" class="{cls}"><span class="icon">{icon}</span>{label}</a>'
    initial = user[0].upper() if user else 'A'
    return f'''<div class="sidebar">
  <div class="sidebar-logo">
    <div class="logo-title">🚌 AutoPark Admin</div>
    <div class="logo-sub">Система жалоб</div>
  </div>
  <div class="sidebar-nav">
    <div class="nav-section" style="margin-top:8px">Навигация</div>
    {nav}
  </div>
  <div class="sidebar-footer">
    <div class="sidebar-user">
      <div class="avatar">{initial}</div>
      <div>{user}</div>
    </div>
  </div>
</div>'''


def _page(title: str, active: str, user: str, breadcrumb: str, content: str) -> str:
    return f'''<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — AutoPark Admin</title>
<style>{_SIDEBAR_CSS}</style>
</head><body>
{_sidebar(active, user)}
<div class="main">
  <div class="topbar">
    <div>
      <div class="topbar-breadcrumb">{breadcrumb}</div>
      <div class="topbar-title">{title}</div>
    </div>
  </div>
  <div class="content">{content}</div>
</div>
</body></html>'''


@app.get('/login')
def login_form():
    html = '''<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="utf-8">
<title>Вход — AutoPark Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#1e2940 0%,#2d3f5e 100%);min-height:100vh;display:flex;align-items:center;justify-content:center}
.login-card{background:#fff;border-radius:16px;padding:40px;width:360px;box-shadow:0 20px 60px rgba(0,0,0,.3)}
.login-logo{text-align:center;margin-bottom:28px}
.login-logo .icon{font-size:48px}
.login-logo h1{font-size:20px;font-weight:700;color:#1e293b;margin-top:8px}
.login-logo p{font-size:13px;color:#64748b;margin-top:4px}
.form-group{margin-bottom:16px}
label{display:block;font-size:13px;font-weight:600;color:#475569;margin-bottom:6px}
input{width:100%;padding:11px 14px;border:1.5px solid #e2e8f0;border-radius:8px;font-size:14px;outline:none;transition:border .15s;font-family:inherit}
input:focus{border-color:#3b82f6;box-shadow:0 0 0 3px rgba(59,130,246,.1)}
.btn-login{width:100%;padding:12px;background:#3b82f6;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;margin-top:8px;transition:background .15s}
.btn-login:hover{background:#2563eb}
</style>
</head><body>
<div class="login-card">
  <div class="login-logo">
    <div class="icon">🚌</div>
    <h1>AutoPark Admin</h1>
    <p>Система управления жалобами</p>
  </div>
  <form action="/login" method="post">
    <div class="form-group">
      <label>Логин</label>
      <input type="text" name="username" placeholder="admin" autofocus>
    </div>
    <div class="form-group">
      <label>Пароль</label>
      <input type="password" name="password" placeholder="••••••••">
    </div>
    <button type="submit" class="btn-login">Войти</button>
  </form>
</div>
</body></html>'''
    return HTMLResponse(content=html)


@app.post('/login')
async def do_login(username: str = Form(...), password: str = Form(...)):
    admin_user = os.getenv('ADMIN_USER', 'admin')
    admin_pass = os.getenv('ADMIN_PASS', 'password')
    if username == admin_user and password == admin_pass:
        token = create_session_token(username)
        resp = RedirectResponse(url='/admin', status_code=302)
        resp.set_cookie(SESSION_COOKIE, token, httponly=True, max_age=3600)
        return resp
    return HTMLResponse(content='Invalid credentials', status_code=401)


@app.get('/admin')
def admin(request: Request, page: int = 1, page_size: int = 20):
    token = request.cookies.get(SESSION_COOKIE)
    user = None
    if token:
        user = verify_session_token(token)
    if not user:
        return RedirectResponse(url='/login')

    total = db.count_complaints()
    offset = (page - 1) * page_size
    rows = db.list_complaints(limit=page_size, offset=offset)

    html = '<html><head><style>'
    html += 'body { font-family: Arial; margin: 20px; }'
    html += 'h2 { color: #333; }'
    html += '.complaint { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }'
    html += '.status { padding: 5px 10px; border-radius: 3px; display: inline-block; font-size: 12px; }'
    html += '.status.new { background: #ffc107; color: black; }'
    html += '.status.replied { background: #28a745; color: white; }'
    html += '.status.in_progress { background: #17a2b8; color: white; }'
    html += '.status.closed { background: #6c757d; color: white; }'
    html += 'a { color: #007bff; text-decoration: none; margin-left: 10px; }'
    html += 'a:hover { text-decoration: underline; }'
    html += '.pagination { margin-top: 20px; }'
    html += '</style></head><body>'
    html += f'<h2>Админка — пользователь: {user}</h2>'
    html += f'<p>Всего жалоб: {total} | <a href="/stats">📊 Статистика</a></p>'

    for row in rows:
        id_, route, comment, photo_path, user_id, created_at, bus_info, bus_garage_number, username, user_full_name, status = row
        sender_name = user_full_name or username or f'User {user_id}'
        msg_count = db.count_messages_for_complaint(id_)

        html += '<div class="complaint">'
        html += f'<strong>#{id_} {route}</strong><br>'
        html += f'От: {sender_name}<br>'
        html += f'Комментарий: {comment}<br>'
        html += f'Дата: {created_at}<br>'
        if bus_info:
            html += f'Автобус: {bus_info}<br>'
        if bus_garage_number:
            html += f'Гаражный №: {bus_garage_number}<br>'
        html += f'<span class="status {status}">{status.upper()}</span>'
        html += f' <a href="/api/complaint/{id_}/chat">💬 Чат ({msg_count})</a>'
        html += '</div>'

    # Pagination
    total_pages = (total + page_size - 1) // page_size
    html += '<div class="pagination">'
    if page > 1:
        html += f'<a href="/admin?page=1">← Первая</a>'
        html += f'<a href="/admin?page={page-1}">← Предыдущая</a>'
    html += f' Страница {page} из {total_pages} '
    if page < total_pages:
        html += f'<a href="/admin?page={page+1}">Следующая →</a>'
        html += f'<a href="/admin?page={total_pages}">Последняя →</a>'
    html += '</div>'

    html += '</body></html>'
    return HTMLResponse(content=html)


@app.get('/chat/{complaint_id}')
async def chat_page(request: Request, complaint_id: int):
    """Веб-интерфейс для чата по жалобе."""
    token = request.cookies.get(SESSION_COOKIE)
    user = None
    if token:
        user = verify_session_token(token)
    if not user:
        return RedirectResponse(url='/login')

    complaint = db.get_complaint_by_id(complaint_id)
    if not complaint:
        return HTMLResponse(content='<html><body>Жалоба не найдена</body></html>', status_code=404)

    messages = db.get_messages_for_complaint(complaint_id, limit=1000)

    # Подтянуть данные путевого листа из 1С по гаражному номеру
    waybill_data = None
    garage_number = complaint.get('bus_garage_number')
    if garage_number:
        try:
            result = await onec.get_waybill_by_garage_number(garage_number)
            body = result.get('body')
            if isinstance(body, list) and body:
                waybill_data = body[0]
            elif isinstance(body, dict):
                waybill_data = body
        except Exception as e:
            logger.error(f'Ошибка получения путевого листа: {e}')

    html = '<html><head><style>'
    html += 'body { font-family: Arial; margin: 20px; max-width: 900px; }'
    html += '.header { background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }'
    html += '.waybill { background: #fff8e1; border: 1px solid #ffc107; padding: 15px; border-radius: 5px; margin-bottom: 20px; }'
    html += '.waybill h3 { margin-top: 0; color: #856404; }'
    html += '.waybill-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }'
    html += '.waybill-block { background: white; padding: 10px; border-radius: 4px; border: 1px solid #ffd54f; }'
    html += '.waybill-block h4 { margin: 0 0 8px 0; font-size: 13px; color: #666; text-transform: uppercase; }'
    html += '.waybill-block p { margin: 3px 0; font-size: 14px; }'
    html += '.waybill-block .label { color: #888; font-size: 12px; }'
    html += '.chat-container { border: 1px solid #ddd; padding: 15px; border-radius: 5px; min-height: 400px; }'
    html += '.message { margin: 10px 0; padding: 10px; border-radius: 5px; }'
    html += '.message.user { background: #e7f3ff; border-left: 4px solid #007bff; }'
    html += '.message.admin { background: #f0f0f0; border-left: 4px solid #28a745; }'
    html += '.message-sender { font-weight: bold; font-size: 12px; margin-bottom: 5px; }'
    html += '.message-text { margin: 5px 0; }'
    html += '.message-time { font-size: 11px; color: #666; }'
    html += '.message-form { margin-top: 20px; }'
    html += 'textarea { width: 100%; padding: 10px; font-family: Arial; font-size: 14px; box-sizing: border-box; }'
    html += 'button { padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }'
    html += 'button:hover { background: #0056b3; }'
    html += 'a { color: #007bff; text-decoration: none; }'
    html += '.no-data { color: #999; font-style: italic; font-size: 13px; }'
    html += '</style></head><body>'

    sender_label = complaint['user_full_name'] or complaint['username'] or f"User {complaint['user_id']}"
    html += '<div class="header">'
    html += f'<h2>Чат — Жалоба #{complaint_id}</h2>'
    html += f'<p><strong>Маршрут:</strong> {complaint["route"]}</p>'
    html += f'<p><strong>От:</strong> {sender_label}</p>'
    if complaint.get('bus_info'):
        html += f'<p><strong>Автобус (из чека):</strong> {complaint["bus_info"]}</p>'
    if garage_number:
        html += f'<p><strong>Гаражный №:</strong> {garage_number}</p>'
    html += f'<p><strong>Статус:</strong> {complaint["status"].upper()}</p>'
    html += f'<a href="/admin">← Назад в админку</a>'
    html += '</div>'

    # Блок данных из 1С
    html += '<div class="waybill">'
    html += '<h3>🚌 Данные из 1С (путевой лист)</h3>'
    if waybill_data:
        driver = waybill_data.get('Driver', {})
        vehicle = waybill_data.get('Vehicle', {})
        html += '<div class="waybill-grid">'

        html += '<div class="waybill-block">'
        html += '<h4>Водитель</h4>'
        html += f'<p>{driver.get("FIO", "—")}</p>'
        html += f'<p><span class="label">Таб. №:</span> {driver.get("TabNo", "—")}</p>'
        html += f'<p><span class="label">Стаж:</span> {driver.get("Tenure", "—")}</p>'
        html += f'<p><span class="label">Принят:</span> {driver.get("HireDate", "—")}</p>'
        html += f'<p><span class="label">Мед. осмотр:</span> {driver.get("MedCheckDate", "—")}</p>'
        html += '</div>'

        html += '<div class="waybill-block">'
        html += '<h4>Автобус</h4>'
        html += f'<p>{vehicle.get("Model", "—")}</p>'
        html += f'<p><span class="label">Гос. номер:</span> {vehicle.get("Plate", "—")}</p>'
        html += f'<p><span class="label">Гараж. №:</span> {vehicle.get("GarageNo", "—")}</p>'
        html += f'<p><span class="label">Пробег:</span> {waybill_data.get("Mileage", "—")} км</p>'
        html += '</div>'

        html += '<div class="waybill-block">'
        html += '<h4>Маршрут / Рейс</h4>'
        html += f'<p><span class="label">Маршрут:</span> {waybill_data.get("Route", "—")}</p>'
        html += f'<p><span class="label">Колонна:</span> {waybill_data.get("Column", "—")}</p>'
        html += f'<p><span class="label">Дата ПЛ:</span> {waybill_data.get("Date", "—")}</p>'
        html += f'<p><span class="label">Статус ПЛ:</span> {waybill_data.get("Status", "—")}</p>'
        html += '</div>'

        html += '<div class="waybill-block">'
        html += '<h4>Техосмотр / Страховка</h4>'
        html += f'<p><span class="label">Страховка до:</span> {waybill_data.get("Insurance", "—")}</p>'
        html += f'<p><span class="label">Техосмотр до:</span> {waybill_data.get("Inspection", "—")}</p>'
        html += f'<p><span class="label">№ ПЛ:</span> {waybill_data.get("PL_Number", "—")}</p>'
        html += '</div>'

        html += '</div>'
    elif garage_number:
        html += '<p class="no-data">Не удалось получить данные из 1С. Проверьте подключение к серверу.</p>'
    else:
        html += '<p class="no-data">Гаражный номер не определён — данные из 1С недоступны.</p>'
    html += '</div>'

    html += '<div class="chat-container">'
    if not messages:
        html += '<p><i>Сообщений нет. Начните разговор:</i></p>'
    else:
        for msg in messages:
            msg_id, cid, sender_id, sender_type, sender_name, text, created_at, *_ = msg
            msg_class = 'admin' if sender_type == 'admin' else 'user'
            html += f'<div class="message {msg_class}">'
            html += f'<div class="message-sender">{sender_name} ({sender_type})</div>'
            html += f'<div class="message-text">{text}</div>'
            html += f'<div class="message-time">{created_at}</div>'
            html += '</div>'
    html += '</div>'

    html += '<div class="message-form">'
    html += '<h3>Отправить ответ:</h3>'
    html += '<form method="post" action="/api/send-chat-message">'
    html += f'<input type="hidden" name="complaint_id" value="{complaint_id}">'
    html += '<textarea name="text" placeholder="Введите ваше сообщение..." required></textarea><br><br>'
    html += '<button type="submit">Отправить</button>'
    html += '</form>'
    html += '</div>'

    html += '</body></html>'
    return HTMLResponse(content=html)


@app.post('/api/send-chat-message')
async def send_chat_message_form(
    complaint_id: int = Form(...),
    text: str = Form(...),
    request: Request = None,
):
    """Отправить сообщение из веб-формы в админке."""
    token = request.cookies.get(SESSION_COOKIE) if request else None
    user = None
    if token:
        user = verify_session_token(token)
    if not user:
        return RedirectResponse(url='/login')

    # Добавить сообщение
    await add_message(complaint_id, text, sender_id=0, sender_name=user)

    # Редирект обратно в чат
    return RedirectResponse(url=f'/chat/{complaint_id}', status_code=302)
