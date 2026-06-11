# Жалобный бот (Telegram)

Простой Telegram-бот для приёма жалоб: маршрут, комментарий и фото чека сохраняются в SQLite.

Установка

1. Создайте виртуальное окружение и установите зависимости:

```bash
python -m venv .venv
source .venv/bin/activate  # или .venv\Scripts\activate на Windows
pip install -r requirements.txt
```

2. Установите переменную окружения `TELEGRAM_TOKEN` с токеном вашего бота.

Альтернативный (удобный) способ — создать файл `.env` в корне проекта со строкой:

```
TELEGRAM_TOKEN=ВАШ_ТОКЕН_ЗДЕСЬ
```

Файл `.env` не должен попадать в репозиторий — в проект добавлен `.gitignore`, который его игнорирует.

Запуск

```bash
python bot.py
```

Команды бота

- `/start` — краткая инструкция
- `/complaint` — начать добавление жалобы
- Во время диалога отправьте маршрут, комментарий и фото чека (или `/skip`), жалоба сохранится.
- `/list` — показать последние жалобы (для отладки)

API
---
- `POST /complaints` — отправить жалобу с полями `route`, `comment` и файлом `receipt`.
- `GET /complaints` — получить последние жалобы.

Запуск API
```bash
uvicorn api:app --reload
```

Пример запроса:
```bash
curl -X POST "http://127.0.0.1:8000/complaints" \
  -F "route=A->B" \
  -F "comment=Проблема с оплатой" \
  -F "receipt=@/path/to/receipt.pdf"
```

Файлы

- `bot.py` — основной бот
- `db.py` — простая обёртка для SQLite (`complaints.db` создаётся рядом с файлами)
- `api.py` — REST API на FastAPI
- `onec.py` — интеграция с 1С
- `lookup.py` — обработка чеков (QR, OCR, PDF)
- `uploads/` — сюда будут сохраняться фото чеков

Интеграция с 1С
---
Подробная документация: [ONEC_INTEGRATION.md](ONEC_INTEGRATION.md)

Для подключения к 1С добавьте в `.env`:
```
ONEC_URL=https://your-1c-server.com/api/complaints
ONEC_TOKEN=your_secret_token
```

Жалобы автоматически будут отправляться в 1С при создании и при изменении статуса.

Admin Dashboard
---
Веб-интерфейс доступен на `GET /admin`

Вход через `GET /login` (по умолчанию `admin`/`password`, меняется в `.env`):
```
ADMIN_USER=admin
ADMIN_PASS=password
SECRET_KEY=your_secret
```

Чат с пользователями
---
Подробная документация: [CHAT_API.md](CHAT_API.md)

API:
- `GET /complaints/{id}/messages` — получить все сообщения по жалобе
- `POST /complaints/{id}/messages` — отправить сообщение (админ может отправлять прямо в Telegram)

Веб-интерфейс:
- `GET /chat/{id}` — открыть чат по жалобе (требуется вход в админку)
