# Интеграция с 1С

## Настройка

Добавьте в файл `.env`:

```env
ONEC_URL=https://your-1c-server.com/api/complaints
ONEC_TOKEN=your_secret_token
```

## Как это работает

### 1. Отправка жалобы в 1С

Когда создаётся новая жалоба через API (`POST /complaints`), система:
1. Сохраняет жалобу в локальную БД
2. Отправляет данные в 1С асинхронно

**POST в 1С:**
```
POST {ONEC_URL}
Authorization: Bearer {ONEC_TOKEN}
Content-Type: application/json
```

**Тело:**
```json
{
  "complaint_id": 42,
  "route": "A→B",
  "comment": "Водитель грубил",
  "photo_path": "uploads/receipt_abc123.jpg",
  "bus_info": "Маршрут 5 | Автобус №42",
  "username": "ivan_petrov",
  "user_full_name": "Иван Петров",
  "user_id": 123456789,
  "created_at": "2024-01-15T10:30:00"
}
```

**Ответ от POST /complaints:**
```json
{
  "status": "ok",
  "id": 42,
  "onec_result": {
    "status": "ok",
    "status_code": 200,
    "body": "..."
  }
}
```

---

### 2. Обновление статуса в 1С

Когда меняется статус жалобы (`PATCH /complaints/{id}/status`):
1. Статус обновляется в локальной БД
2. Отправляется PATCH-запрос в 1С

**PATCH в 1С:**
```
PATCH {ONEC_URL}/status
Authorization: Bearer {ONEC_TOKEN}
Content-Type: application/json
```

**Тело:**
```json
{
  "complaint_id": 42,
  "status": "in_progress"
}
```

---

### 3. Ответ пользователю в Telegram

Когда вы отправляете ответ пользователю (`POST /complaints/{id}/reply`):
1. Сообщение отправляется в Telegram
2. Статус автоматически меняется на `replied`
3. Обновление отправляется в 1С

---

## Статусы

| Статус | Описание |
|--------|---------|
| `new` | Новая жалоба, не обработана |
| `in_progress` | В обработке |
| `replied` | Дан ответ пользователю |
| `closed` | Закрыта |

---

## Обработка ошибок

Если 1С недоступна:
- Жалоба всё равно сохраняется в локальную БД
- В ответе API появится `onec_result` с ошибкой
- Логи записываются в `stderr`

Пример ошибки:
```json
{
  "onec_result": {
    "status": "error",
    "error": "Connection timeout"
  }
}
```

---

## Примеры

### Фронтенд: создание жалобы

```js
async function createComplaint(route, comment, receiptFile) {
  const form = new FormData();
  form.append('route', route);
  form.append('comment', comment);
  if (receiptFile) form.append('receipt', receiptFile);

  const res = await fetch('/complaints', {
    method: 'POST',
    body: form,
  });
  return res.json();
}

const result = await createComplaint('A→B', 'Водитель грубил', file);
console.log(result.id); // ID жалобы в системе
console.log(result.onec_result); // статус отправки в 1С
```

### Фронтенд: обновление статуса

```js
async function updateComplaintStatus(complaintId, status) {
  const res = await fetch(`/complaints/${complaintId}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ status }),
  });
  return res.json();
}

await updateComplaintStatus(42, 'in_progress');
```

---

## 1С: как принять запрос

Ваша 1С должна обрабатывать:

1. **POST** на `{ONEC_URL}` — новая жалоба
2. **PATCH** на `{ONEC_URL}/status` — обновление статуса

Рекомендуется вернуть:
- **200 OK** если всё хорошо
- **400** если некорректные данные
- **500** если ошибка на стороне 1С
