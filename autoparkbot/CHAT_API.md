# Chat API — Чат по жалобам

Система сообщений для общения между пользователями и администраторами по каждой жалобе.

---

## GET /complaints/{id}/messages — Получить чат

Получить все сообщения по жалобе.

### Запрос

```
GET /complaints/42/messages?limit=100&offset=0
```

| Параметр | Тип | Описание |
|----------|-----|---------|
| `id` | int | ID жалобы (path parameter) |
| `limit` | int | Макс. сообщений (по умолчанию 100) |
| `offset` | int | Сдвиг для пагинации (по умолчанию 0) |

### Ответ `200 OK`

```json
{
  "complaint_id": 42,
  "total_messages": 3,
  "messages": [
    {
      "id": 1,
      "sender_id": 123456789,
      "sender_type": "user",
      "sender_name": "Иван Петров",
      "text": "Я подал жалобу",
      "created_at": "2024-01-15T10:30:00"
    },
    {
      "id": 2,
      "sender_id": 0,
      "sender_type": "admin",
      "sender_name": "Админ",
      "text": "Спасибо, мы рассмотрим вашу жалобу",
      "created_at": "2024-01-15T11:00:00"
    },
    {
      "id": 3,
      "sender_id": 123456789,
      "sender_type": "user",
      "sender_name": "Иван Петров",
      "text": "А когда вы ответите?",
      "created_at": "2024-01-15T12:00:00"
    }
  ]
}
```

| Поле | Описание |
|------|---------|
| `sender_type` | `user` или `admin` |
| `sender_id` | 0 для админа, Telegram ID для пользователя |
| `sender_name` | Имя отправителя |
| `text` | Текст сообщения |
| `created_at` | ISO 8601 время отправки |

---

## POST /complaints/{id}/messages — Отправить сообщение

Добавить сообщение в чат жалобы. При отправке сообщения админом, оно автоматически отправляется в Telegram пользователю.

### Запрос

```
POST /complaints/42/messages
Content-Type: application/x-www-form-urlencoded
```

**Тело:**

| Поле | Тип | Обязателен | Описание |
|------|-----|-----------|---------|
| `text` | string | да | Текст сообщения |
| `sender_id` | int | нет | ID отправителя (0 = админ, Telegram ID = пользователь) |
| `sender_name` | string | нет | Имя отправителя (по умолчанию "Админ") |

```
text=Спасибо за жалобу, мы её рассмотрим&sender_id=0&sender_name=Поддержка
```

### Ответ `200 OK`

```json
{
  "id": 4,
  "complaint_id": 42,
  "sender_type": "admin",
  "sender_name": "Поддержка",
  "text": "Спасибо за жалобу, мы её рассмотрим"
}
```

### Ошибки

**`404`** — жалоба не найдена:
```json
{ "detail": "Жалоба не найдена" }
```

**`400`** — пустое сообщение:
```json
{ "detail": "Текст сообщения не может быть пустым" }
```

---

## Примеры

### JavaScript: получить чат

```js
async function getChat(complaintId) {
  const res = await fetch(`/complaints/${complaintId}/messages`);
  const data = await res.json();
  
  data.messages.forEach(msg => {
    const name = msg.sender_name || 'Unknown';
    const type = msg.sender_type === 'admin' ? '👤 Админ' : '👥 Пользователь';
    console.log(`[${name}] (${type}): ${msg.text}`);
  });
}
```

### JavaScript: отправить сообщение от админа

```js
async function sendAdminMessage(complaintId, message) {
  const res = await fetch(`/complaints/${complaintId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      text: message,
      sender_id: 0,
      sender_name: 'Поддержка',
    }),
  });
  return res.json();
}

// Использование:
await sendAdminMessage(42, 'Ваша жалоба принята в работу');
```

### cURL: отправить сообщение

```bash
curl -X POST "http://localhost:8000/complaints/42/messages" \
  -d "text=Спасибо за обращение" \
  -d "sender_id=0" \
  -d "sender_name=Support"
```

---

## Интеграция с Telegram

Когда **админ** отправляет сообщение (`sender_id=0`):
1. Сообщение сохраняется в БД
2. **Автоматически** отправляется в Telegram пользователю
3. Требуется `TELEGRAM_TOKEN` в `.env`

Если пользователь отправит сообщение в Telegram боту, оно должно быть сохранено в чат вручную через этот API.

---

## Схема БД

```sql
CREATE TABLE messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  complaint_id INTEGER NOT NULL,
  sender_id INTEGER NOT NULL,
  sender_type TEXT NOT NULL,      -- 'user' или 'admin'
  sender_name TEXT,
  text TEXT NOT NULL,
  created_at TEXT,
  FOREIGN KEY (complaint_id) REFERENCES complaints(id)
);
```
