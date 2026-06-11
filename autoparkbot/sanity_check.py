from datetime import datetime
import db


def run():
    db.init_db()
    created_at = datetime.utcnow().isoformat()
    db.save_complaint(route='TestRoute', comment='Тестовая жалоба', photo_path=None, user_id=0, created_at=created_at, bus_info='TestBus')
    rows = db.list_complaints(limit=5)
    print('Последние жалобы:')
    for r in rows:
        print(r)


if __name__ == '__main__':
    run()
