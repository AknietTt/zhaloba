import sqlite3
import os
from datetime import datetime

_DATA_DIR = os.getenv('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_DATA_DIR, 'complaints.db')


def init_db(path: str | None = None):
    p = path or DB_PATH
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route TEXT,
            comment TEXT,
            photo_path TEXT,
            user_id INTEGER,
            created_at TEXT,
            bus_info TEXT,
            bus_garage_number TEXT,
            username TEXT,
            user_full_name TEXT,
            status TEXT DEFAULT 'new'
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            sender_type TEXT NOT NULL,
            sender_name TEXT,
            text TEXT NOT NULL,
            created_at TEXT,
            FOREIGN KEY (complaint_id) REFERENCES complaints(id)
        )
        """
    )
    # Migrate older DBs: add missing columns
    cur.execute("PRAGMA table_info(complaints)")
    cols = [r[1] for r in cur.fetchall()]
    for col, definition in [
        ('bus_info', 'TEXT'),
        ('bus_garage_number', 'TEXT'),
        ('username', 'TEXT'),
        ('user_full_name', 'TEXT'),
        ('status', "TEXT DEFAULT 'new'"),
        ('driver_name', 'TEXT'),
        ('driver_tab', 'TEXT'),
        ('category', 'TEXT'),
        ('language', 'TEXT'),
    ]:
        if col not in cols:
            try:
                cur.execute(f"ALTER TABLE complaints ADD COLUMN {col} {definition}")
            except Exception:
                pass

    # Migrate messages table
    cur.execute("PRAGMA table_info(messages)")
    msg_cols = [r[1] for r in cur.fetchall()]
    if 'file_path' not in msg_cols:
        try:
            cur.execute("ALTER TABLE messages ADD COLUMN file_path TEXT")
        except Exception:
            pass

    conn.commit()
    conn.close()


def save_complaint(
    route: str,
    comment: str,
    photo_path: str | None,
    user_id: int,
    created_at: str,
    bus_info: str | None = None,
    bus_garage_number: str | None = None,
    username: str | None = None,
    user_full_name: str | None = None,
    category: str | None = None,
    language: str | None = None,
    path: str | None = None,
):
    p = path or DB_PATH
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO complaints
           (route, comment, photo_path, user_id, created_at, bus_info, bus_garage_number, username, user_full_name, status, category, language)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?)""",
        (route, comment, photo_path, user_id, created_at, bus_info, bus_garage_number, username, user_full_name, category, language),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_status(complaint_id: int, status: str, path: str | None = None):
    p = path or DB_PATH
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    cur.execute("UPDATE complaints SET status = ? WHERE id = ?", (status, complaint_id))
    updated = cur.rowcount
    conn.commit()
    conn.close()
    return updated > 0


def list_complaints(
    limit: int = 50, offset: int = 0,
    route: str | None = None,
    bus: str | None = None,
    search: str | None = None,
    driver: str | None = None,
    category: str | None = None,
    status: str | None = None,
    sort_by: str = 'id',
    sort_order: str = 'desc',
    date_from: str | None = None,
    date_to: str | None = None,
    path: str | None = None,
):
    p = path or DB_PATH
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    conditions, params = [], []
    if route:
        conditions.append("route LIKE ?")
        params.append(f"%{route}%")
    if bus:
        conditions.append("(bus_garage_number LIKE ? OR bus_info LIKE ?)")
        params.extend([f"%{bus}%", f"%{bus}%"])
    if driver:
        conditions.append("(driver_name LIKE ? OR driver_tab LIKE ?)")
        params.extend([f"%{driver}%", f"%{driver}%"])
    if category:
        conditions.append("category = ?")
        params.append(category)
    if search:
        conditions.append("(comment LIKE ? OR username LIKE ? OR user_full_name LIKE ? OR bus_info LIKE ?)")
        params.extend([f"%{search}%"] * 4)
    if status:
        sl = [s.strip() for s in status.split(',') if s.strip()]
        if len(sl) == 1:
            conditions.append("status = ?")
            params.append(sl[0])
        elif sl:
            conditions.append(f"status IN ({','.join('?'*len(sl))})")
            params.extend(sl)
    if date_from:
        conditions.append("created_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("created_at <= ?")
        params.append(date_to + 'T23:59:59')
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    valid_cols = {'id', 'created_at', 'status', 'route', 'category'}
    col = sort_by if sort_by in valid_cols else 'id'
    direction = 'ASC' if sort_order.lower() == 'asc' else 'DESC'
    cur.execute(
        f"""SELECT id, route, comment, photo_path, user_id, created_at, bus_info, bus_garage_number, username, user_full_name, status, driver_name, driver_tab, category
           FROM complaints{where} ORDER BY {col} {direction} LIMIT ? OFFSET ?""",
        params + [limit, offset],
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_complaint_by_id(complaint_id: int, path: str | None = None) -> dict | None:
    p = path or DB_PATH
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    cur.execute(
        """SELECT id, route, comment, photo_path, user_id, created_at, bus_info, bus_garage_number, username, user_full_name, status, driver_name, driver_tab, category, language
           FROM complaints WHERE id = ?""",
        (complaint_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    id_, route, comment, photo_path, user_id, created_at, bus_info, bus_garage_number, username, user_full_name, status, driver_name, driver_tab, category, language = row
    return {
        'id': id_, 'route': route, 'comment': comment,
        'photo_path': photo_path, 'user_id': user_id, 'created_at': created_at,
        'bus_info': bus_info, 'bus_garage_number': bus_garage_number,
        'username': username, 'user_full_name': user_full_name, 'status': status,
        'driver_name': driver_name, 'driver_tab': driver_tab,
        'category': category, 'language': language,
    }


def count_complaints(
    route: str | None = None,
    bus: str | None = None,
    search: str | None = None,
    driver: str | None = None,
    category: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    path: str | None = None,
) -> int:
    p = path or DB_PATH
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    conditions, params = [], []
    if route:
        conditions.append("route LIKE ?")
        params.append(f"%{route}%")
    if bus:
        conditions.append("(bus_garage_number LIKE ? OR bus_info LIKE ?)")
        params.extend([f"%{bus}%", f"%{bus}%"])
    if driver:
        conditions.append("(driver_name LIKE ? OR driver_tab LIKE ?)")
        params.extend([f"%{driver}%", f"%{driver}%"])
    if category:
        conditions.append("category = ?")
        params.append(category)
    if search:
        conditions.append("(comment LIKE ? OR username LIKE ? OR user_full_name LIKE ? OR bus_info LIKE ?)")
        params.extend([f"%{search}%"] * 4)
    if status:
        sl = [s.strip() for s in status.split(',') if s.strip()]
        if len(sl) == 1:
            conditions.append("status = ?")
            params.append(sl[0])
        elif sl:
            conditions.append(f"status IN ({','.join('?'*len(sl))})")
            params.extend(sl)
    if date_from:
        conditions.append("created_at >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("created_at <= ?")
        params.append(date_to + 'T23:59:59')
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    cur.execute(f"SELECT COUNT(*) FROM complaints{where}", params)
    total = cur.fetchone()[0]
    conn.close()
    return total


def update_complaint_bus(
    complaint_id: int,
    bus_info: str | None = None,
    bus_garage_number: str | None = None,
    path: str | None = None,
):
    """Обновить данные автобуса в жалобе (bus_info, bus_garage_number)."""
    p = path or DB_PATH
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    updates, params = [], []
    if bus_info is not None:
        updates.append('bus_info = ?')
        params.append(bus_info)
    if bus_garage_number is not None:
        updates.append('bus_garage_number = ?')
        params.append(bus_garage_number)
    if updates:
        cur.execute(f"UPDATE complaints SET {', '.join(updates)} WHERE id = ?", params + [complaint_id])
        conn.commit()
    conn.close()


def update_driver_info(complaint_id: int, driver_name: str, driver_tab: str, path: str | None = None):
    p = path or DB_PATH
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    cur.execute(
        "UPDATE complaints SET driver_name = ?, driver_tab = ? WHERE id = ?",
        (driver_name, driver_tab, complaint_id),
    )
    conn.commit()
    conn.close()


def get_driver_stats(limit: int = 20, path: str | None = None) -> list:
    p = path or DB_PATH
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    cur.execute("""
        SELECT driver_name, driver_tab, COUNT(*) as cnt
        FROM complaints
        WHERE driver_name IS NOT NULL AND driver_name != ''
        GROUP BY driver_name, driver_tab
        ORDER BY cnt DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def save_message(
    complaint_id: int,
    sender_id: int,
    sender_type: str,
    text: str,
    sender_name: str | None = None,
    created_at: str | None = None,
    file_path: str | None = None,
    path: str | None = None,
):
    """Сохранить сообщение в чате жалобы."""
    p = path or DB_PATH
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    ts = created_at or datetime.utcnow().isoformat()
    cur.execute(
        """INSERT INTO messages (complaint_id, sender_id, sender_type, sender_name, text, created_at, file_path)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (complaint_id, sender_id, sender_type, sender_name, text, ts, file_path),
    )
    msg_id = cur.lastrowid
    conn.commit()
    conn.close()
    return msg_id


def get_latest_complaint_for_user(user_id: int, path: str | None = None) -> dict | None:
    """Найти последнюю жалобу пользователя по user_id."""
    p = path or DB_PATH
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    cur.execute(
        """SELECT id, route, comment, photo_path, user_id, created_at, bus_info, bus_garage_number,
                  username, user_full_name, status, driver_name, driver_tab, category, language
           FROM complaints WHERE user_id = ? AND status != 'closed'
           ORDER BY id DESC LIMIT 1""",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    id_, route, comment, photo_path, user_id, created_at, bus_info, bus_garage_number, username, user_full_name, status, driver_name, driver_tab, category, language = row
    return {
        'id': id_, 'route': route, 'comment': comment,
        'photo_path': photo_path, 'user_id': user_id,
        'created_at': created_at, 'bus_info': bus_info,
        'bus_garage_number': bus_garage_number,
        'username': username, 'user_full_name': user_full_name,
        'status': status, 'driver_name': driver_name, 'driver_tab': driver_tab,
        'category': category, 'language': language,
    }


def get_messages_for_complaint(complaint_id: int, limit: int = 100, offset: int = 0, path: str | None = None):
    """Получить все сообщения по жалобе."""
    p = path or DB_PATH
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    cur.execute(
        """SELECT id, complaint_id, sender_id, sender_type, sender_name, text, created_at, file_path
           FROM messages WHERE complaint_id = ? ORDER BY created_at ASC LIMIT ? OFFSET ?""",
        (complaint_id, limit, offset),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def count_messages_for_complaint(complaint_id: int, path: str | None = None) -> int:
    """Количество сообщений по жалобе."""
    p = path or DB_PATH
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM messages WHERE complaint_id = ?", (complaint_id,))
    total = cur.fetchone()[0]
    conn.close()
    return total
