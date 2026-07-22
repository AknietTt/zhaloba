import { useState, useEffect } from 'react';
import Layout from './Layout';

type Source = 'bot' | 'complaint' | 'both';

interface BotUser {
  user_id: number;
  username: string | null;
  full_name: string | null;
  first_seen: string | null;
  last_seen: string | null;
  source: Source;
}

interface UsersData {
  total: number;
  bot_count: number;
  complaint_count: number;
  users: BotUser[];
}

interface BroadcastResult {
  success: number;
  failed: number;
  total: number;
}

interface TokenStatus {
  session_token_hint: string;
  session_id: string;
  has_refresh: boolean;
}

interface Props { user: string; onLogout: () => void; }

function fmtDate(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

const SOURCE_LABEL: Record<Source, string> = {
  bot:       '🤖 /start',
  complaint: '💬 Жалоба',
  both:      '✅ Оба',
};
const SOURCE_COLOR: Record<Source, string> = {
  bot:       'var(--brand)',
  complaint: 'oklch(0.55 0.14 155)',
  both:      'oklch(0.46 0.17 155)',
};

export default function SuperAdminPage({ user, onLogout }: Props) {
  const [data, setData]           = useState<UsersData | null>(null);
  const [loading, setLoading]     = useState(true);
  const [text, setText]           = useState('');
  const [sending, setSending]     = useState(false);
  const [result, setResult]       = useState<BroadcastResult | null>(null);
  const [sendError, setSendError] = useState('');

  // 2GIS token update form
  const [tokenStatus, setTokenStatus]       = useState<TokenStatus | null>(null);
  const [tkSession, setTkSession]           = useState('');
  const [tkRefresh, setTkRefresh]           = useState('');
  const [tkSessionId, setTkSessionId]       = useState('');
  const [tkSaving, setTkSaving]             = useState(false);
  const [tkMsg, setTkMsg]                   = useState('');

  useEffect(() => {
    fetch('/superadmin/users')
      .then(r => r.json())
      .then(d => setData(d as UsersData))
      .catch(() => {})
      .finally(() => setLoading(false));

    fetch('/superadmin/2gis-tokens')
      .then(r => r.json())
      .then(d => setTokenStatus(d as TokenStatus))
      .catch(() => {});
  }, []);

  const handleTokenSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!tkSession.trim() || !tkRefresh.trim() || !tkSessionId.trim()) return;
    setTkSaving(true);
    setTkMsg('');
    try {
      const res = await fetch('/superadmin/2gis-tokens', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          session_token: tkSession.trim(),
          refresh_token: tkRefresh.trim(),
          session_id: tkSessionId.trim(),
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setTkMsg('✓ Токены обновлены');
      setTkSession(''); setTkRefresh(''); setTkSessionId('');
      // Refresh status
      fetch('/superadmin/2gis-tokens').then(r => r.json()).then(d => setTokenStatus(d as TokenStatus)).catch(() => {});
    } catch {
      setTkMsg('✗ Ошибка сохранения');
    } finally {
      setTkSaving(false);
      setTimeout(() => setTkMsg(''), 4000);
    }
  };

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
    } catch (err) {
      setSendError(err instanceof Error ? err.message : 'Ошибка отправки');
    } finally {
      setSending(false);
    }
  };

  const total    = data?.total ?? 0;
  const botCount = data?.bot_count ?? 0;
  const cmpCount = data?.complaint_count ?? 0;

  return (
    <Layout user={user} onLogout={onLogout} title="Суперадмин" breadcrumb="Управление" role="admin">

      {/* KPI */}
      <div className="kpi-grid sa-kpi">
        <div className="kpi-card">
          <div className="kpi-icon">👥</div>
          <div className="kpi-value">{loading ? '…' : total}</div>
          <div className="kpi-label">Всего уникальных</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-icon">🤖</div>
          <div className="kpi-value">{loading ? '…' : botCount}</div>
          <div className="kpi-label">Нажали /start</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-icon">💬</div>
          <div className="kpi-value">{loading ? '…' : cmpCount}</div>
          <div className="kpi-label">Подали жалобу</div>
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
              placeholder="Текст сообщения для всех пользователей (HTML: <b>жирный</b>, <i>курсив</i>)..."
              onChange={e => { setText(e.target.value); setResult(null); setSendError(''); }}
            />
            <div className="sa-broadcast-footer">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={sending || !text.trim() || total === 0}
              >
                {sending ? '⏳ Отправка...' : `Отправить всем (${total})`}
              </button>

              {result && (
                <div className="sa-broadcast-result">
                  <span className="sa-ok">✓ {result.success} из {result.total} доставлено</span>
                  {result.failed > 0 && (
                    <span className="sa-fail"> · ✗ {result.failed} не доставлено (заблокировали бота)</span>
                  )}
                </div>
              )}
              {sendError && <span className="sa-fail">{sendError}</span>}
            </div>
          </form>
        </div>
      </div>

      {/* 2GIS Token Update */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <h3>⭐ 2GIS Токены</h3>
          {tokenStatus && (
            <span style={{ fontSize: 12, color: 'var(--ink-4)', fontWeight: 500 }}>
              Текущий: <code style={{ background: 'var(--surface-raised)', padding: '1px 5px', borderRadius: 4 }}>…{tokenStatus.session_token_hint}</code>
              {' · '}{tokenStatus.has_refresh ? '🔄 refresh есть' : '⚠️ нет refresh'}
            </span>
          )}
        </div>
        <div className="card-body">
          <p style={{ fontSize: 12, color: 'var(--ink-3)', marginBottom: 14, marginTop: 0 }}>
            Токены автоматически обновляются каждые 30 мин. Если 2GIS возвращает ошибку — вставьте свежие значения из DevTools (Application → Cookies на <strong>account.2gis.com</strong>).
          </p>
          <form onSubmit={handleTokenSave} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
              <div>
                <div className="filter-label" style={{ marginBottom: 4 }}>dg_session_token</div>
                <input className="filter-input" style={{ width: '100%', boxSizing: 'border-box' }}
                  value={tkSession} onChange={e => setTkSession(e.target.value)}
                  placeholder="a152fc1f..." disabled={tkSaving} />
              </div>
              <div>
                <div className="filter-label" style={{ marginBottom: 4 }}>dg_refresh_token</div>
                <input className="filter-input" style={{ width: '100%', boxSizing: 'border-box' }}
                  value={tkRefresh} onChange={e => setTkRefresh(e.target.value)}
                  placeholder="47a75c37..." disabled={tkSaving} />
              </div>
              <div>
                <div className="filter-label" style={{ marginBottom: 4 }}>dg_session_id</div>
                <input className="filter-input" style={{ width: '100%', boxSizing: 'border-box' }}
                  value={tkSessionId} onChange={e => setTkSessionId(e.target.value)}
                  placeholder="deb529fc-..." disabled={tkSaving} />
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <button type="submit" className="btn btn-primary btn-sm"
                disabled={tkSaving || !tkSession.trim() || !tkRefresh.trim() || !tkSessionId.trim()}>
                {tkSaving ? 'Сохранение...' : 'Обновить токены'}
              </button>
              {tkMsg && (
                <span style={{ fontSize: 13, fontWeight: 600,
                  color: tkMsg.startsWith('✓') ? 'oklch(0.42 0.15 155)' : 'oklch(0.48 0.18 25)' }}>
                  {tkMsg}
                </span>
              )}
            </div>
          </form>
        </div>
      </div>

      {/* Users table */}
      <div className="card">
        <div className="card-header">
          <h3>Пользователи</h3>
          {data && (
            <span style={{ fontSize: 12, color: 'var(--ink-4)', fontWeight: 500 }}>
              {total} чел.
            </span>
          )}
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Telegram ID</th>
                  <th>Username</th>
                  <th>Имя</th>
                  <th>Источник</th>
                  <th>Первый контакт</th>
                  <th>Последний /start</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: 32, color: 'var(--ink-4)' }}>
                      Загрузка...
                    </td>
                  </tr>
                )}
                {!loading && (data?.users ?? []).map(u => (
                  <tr key={u.user_id}>
                    <td style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--ink-3)' }}>
                      {u.user_id}
                    </td>
                    <td>
                      {u.username
                        ? <span style={{ color: 'var(--brand)' }}>@{u.username}</span>
                        : <span style={{ color: 'var(--ink-4)' }}>—</span>
                      }
                    </td>
                    <td style={{ fontWeight: 500 }}>{u.full_name || '—'}</td>
                    <td>
                      <span style={{
                        fontSize: 11, fontWeight: 700,
                        color: SOURCE_COLOR[u.source],
                      }}>
                        {SOURCE_LABEL[u.source]}
                      </span>
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--ink-4)' }}>
                      {fmtDate(u.first_seen)}
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--ink-4)' }}>
                      {fmtDate(u.last_seen)}
                    </td>
                  </tr>
                ))}
                {!loading && total === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: 48, color: 'var(--ink-4)' }}>
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
