import { useState, useEffect } from 'react';
import Layout from './Layout';

interface BotUser {
  user_id: number;
  username: string | null;
  full_name: string | null;
  first_seen: string;
  last_seen: string;
}

interface UsersData {
  total: number;
  users: BotUser[];
}

interface BroadcastResult {
  success: number;
  failed: number;
  total: number;
}

interface Props { user: string; onLogout: () => void; }

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export default function SuperAdminPage({ user, onLogout }: Props) {
  const [data, setData]               = useState<UsersData | null>(null);
  const [loading, setLoading]         = useState(true);
  const [text, setText]               = useState('');
  const [sending, setSending]         = useState(false);
  const [result, setResult]           = useState<BroadcastResult | null>(null);
  const [sendError, setSendError]     = useState('');

  useEffect(() => {
    fetch('/superadmin/users')
      .then(r => r.json())
      .then(d => setData(d as UsersData))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleBroadcast = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim() || sending) return;
    setSending(true);
    setResult(null);
    setSendError('');
    try {
      const res = await fetch('/superadmin/broadcast', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ text }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const r: BroadcastResult = await res.json();
      setResult(r);
      if (r.success > 0) setText('');
    } catch (e) {
      setSendError(e instanceof Error ? e.message : 'Ошибка отправки');
    } finally {
      setSending(false);
    }
  };

  return (
    <Layout user={user} onLogout={onLogout} title="Суперадмин" breadcrumb="Управление" role="admin">

      {/* KPI */}
      <div className="kpi-grid sa-kpi">
        <div className="kpi-card">
          <div className="kpi-icon">👥</div>
          <div className="kpi-value">{loading ? '…' : (data?.total ?? 0)}</div>
          <div className="kpi-label">Пользователей в боте</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-icon">🟢</div>
          <div className="kpi-value">{loading ? '…' : (data?.users.filter(u => {
            const d = new Date(u.last_seen);
            return Date.now() - d.getTime() < 30 * 24 * 3600 * 1000;
          }).length ?? 0)}</div>
          <div className="kpi-label">Активны за 30 дней</div>
        </div>
      </div>

      {/* Broadcast */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header"><h3>📢 Рассылка</h3></div>
        <div className="card-body">
          <form onSubmit={handleBroadcast}>
            <textarea
              className="reply-textarea"
              rows={5}
              value={text}
              disabled={sending}
              placeholder="Введите текст сообщения для всех пользователей бота (поддерживается HTML: <b>жирный</b>, <i>курсив</i>)..."
              onChange={e => { setText(e.target.value); setResult(null); setSendError(''); }}
            />
            <div className="sa-broadcast-footer">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={sending || !text.trim()}
              >
                {sending
                  ? '⏳ Отправка...'
                  : `Отправить всем (${data?.total ?? 0})`}
              </button>

              {result && (
                <div className="sa-broadcast-result">
                  <span className="sa-ok">✓ {result.success} доставлено</span>
                  {result.failed > 0 && (
                    <span className="sa-fail"> · ✗ {result.failed} не доставлено</span>
                  )}
                </div>
              )}
              {sendError && <span className="sa-fail">{sendError}</span>}
            </div>
          </form>
        </div>
      </div>

      {/* Users table */}
      <div className="card">
        <div className="card-header">
          <h3>Пользователи бота</h3>
          {data && <span style={{ fontSize: 12, color: 'var(--ink-4)', fontWeight: 500 }}>{data.total} чел.</span>}
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Telegram ID</th>
                  <th>Username</th>
                  <th>Имя</th>
                  <th>Первый /start</th>
                  <th>Последний /start</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={5} style={{ textAlign: 'center', padding: 32, color: 'var(--ink-4)' }}>Загрузка...</td></tr>
                )}
                {!loading && (data?.users ?? []).map(u => (
                  <tr key={u.user_id}>
                    <td style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--ink-3)' }}>{u.user_id}</td>
                    <td>{u.username ? <span style={{ color: 'var(--brand)' }}>@{u.username}</span> : <span style={{ color: 'var(--ink-4)' }}>—</span>}</td>
                    <td style={{ fontWeight: 500 }}>{u.full_name || '—'}</td>
                    <td style={{ fontSize: 12, color: 'var(--ink-4)' }}>{fmtDate(u.first_seen)}</td>
                    <td style={{ fontSize: 12, color: 'var(--ink-4)' }}>{fmtDate(u.last_seen)}</td>
                  </tr>
                ))}
                {!loading && (data?.users ?? []).length === 0 && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: 48, color: 'var(--ink-4)' }}>
                      <div style={{ fontSize: 32, marginBottom: 8 }}>👥</div>
                      Пока нет пользователей
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

    </Layout>
  );
}
