import { useState, useEffect, useCallback, useRef } from 'react';
import Layout from './Layout';

type Status = 'new' | 'in_progress' | 'replied' | 'closed';

const STATUS_LABEL: Record<Status, string> = {
  new: 'Новая', in_progress: 'В работе', replied: 'Отвечено', closed: 'Закрыто',
};
const ALL_STATUSES: Status[] = ['new', 'in_progress', 'replied', 'closed'];

type CategoryCode = 'interval' | 'driver' | 'climate' | 'condition' | 'suggestion' | 'lost';

const CATEGORY_LABEL: Record<CategoryCode, string> = {
  interval:  '🕐 Нарушение интервала',
  driver:    '👨‍✈️ На водителя',
  climate:   '❄️ Кондиционер/Отопление',
  condition: '🚌 Тех. состояние',
  suggestion:'💌 Пожелание/Благодарность',
  lost:      '🎒 Потерянные вещи',
};

const CATEGORY_COLOR: Record<CategoryCode, string> = {
  interval:  '#fef3c7',
  driver:    '#fee2e2',
  climate:   '#dbeafe',
  condition: '#f0fdf4',
  suggestion:'#fdf4ff',
  lost:      '#fff7ed',
};
const CATEGORY_TEXT: Record<CategoryCode, string> = {
  interval:  '#92400e',
  driver:    '#991b1b',
  climate:   '#1e40af',
  condition: '#166534',
  suggestion:'#6b21a8',
  lost:      '#9a3412',
};

interface Complaint {
  id: number; route: string; comment: string;
  photo_path: string | null; user_id: number;
  username: string | null; user_full_name: string | null;
  created_at: string; bus_info: string | null;
  bus_garage_number: string | null; status: Status;
  driver_name: string | null; driver_tab: string | null;
  category: CategoryCode | null;
}
interface Message {
  id: number; sender_type: string; sender_name: string | null;
  text: string; created_at: string; file_path: string | null;
}
interface WaybillRecord {
  PL_ID: string; Date: string;
  Driver: { TabNo: string; FIO: string };
  Vehicle: { GarageNo: string; Plate: string; Model: string };
  Column: string; Route: string; Status: string;
  Mileage?: number;
}
interface ComplaintsResponse {
  page: number; page_size: number; total: number; total_pages: number; items: Complaint[];
}

const PAGE_SIZE = 20;

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState<T>(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// Строки без 'Z'/'+' интерпретируются JS как local — принудительно UTC
function toUtcDate(iso: string): Date {
  if (iso && !iso.endsWith('Z') && !iso.includes('+')) return new Date(iso + 'Z');
  return new Date(iso);
}
function formatDate(iso: string) {
  return toUtcDate(iso).toLocaleString('ru-RU', {
    timeZone: 'Asia/Almaty',
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}
function formatTime(iso: string) {
  return toUtcDate(iso).toLocaleTimeString('ru-RU', {
    timeZone: 'Asia/Almaty',
    hour: '2-digit', minute: '2-digit',
  });
}
function userLabel(c: Complaint) {
  if (c.user_id === 0) return 'API';
  const parts: string[] = [];
  if (c.user_full_name) parts.push(c.user_full_name);
  if (c.username) parts.push(`@${c.username}`);
  if (!parts.length) parts.push(`ID ${c.user_id}`);
  return parts.join(' · ');
}
function fileIcon(fp: string) {
  const ext = fp.split('.').pop()?.toLowerCase() || '';
  if (['jpg','jpeg','png','gif','webp'].includes(ext)) return '🖼';
  if (['mp4','mov','avi','mkv'].includes(ext)) return '🎥';
  if (ext === 'pdf') return '📄';
  return '📎';
}

interface Props { user: string; onLogout: () => void; }

export default function ComplaintsPage({ user, onLogout }: Props) {
  const [data, setData] = useState<ComplaintsResponse | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState('');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [draftStatus, setDraftStatus] = useState<Record<number, Status>>({});
  const [actLoading, setActLoading] = useState<Record<number, boolean>>({});
  const [actMsg, setActMsg] = useState<Record<number, string>>({});
  // IDs с несохранёнными изменениями статуса — ref чтобы fetchComplaints всегда видел актуальное значение
  const dirtyIdsRef = useRef<Set<number>>(new Set());

  // Waybill
  const [waybillData, setWaybillData] = useState<Record<number, WaybillRecord[] | null>>({});
  const [waybillLoading, setWaybillLoading] = useState<Record<number, boolean>>({});
  const [waybillError, setWaybillError] = useState<Record<number, string>>({});

  // Chat
  const [chatMessages, setChatMessages] = useState<Record<number, Message[]>>({});
  const [chatLoading, setChatLoading] = useState<Record<number, boolean>>({});
  const [chatInput, setChatInput] = useState<Record<number, string>>({});
  const [chatSending, setChatSending] = useState<Record<number, boolean>>({});
  const chatBottomRef = useRef<Record<number, HTMLDivElement | null>>({});

  // Filters
  const [filterRoute, setFilterRoute] = useState('');
  const [filterBus, setFilterBus] = useState('');
  const [filterDriver, setFilterDriver] = useState('');
  const [filterSearch, setFilterSearch] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [filterStatuses, setFilterStatuses] = useState<Status[]>([]);
  const [filterDateFrom, setFilterDateFrom] = useState('');
  const [filterDateTo, setFilterDateTo]   = useState('');
  const [sortBy, setSortBy]         = useState('id');
  const [sortOrder, setSortOrder]   = useState<'asc' | 'desc'>('desc');

  const dRoute    = useDebounce(filterRoute,    400);
  const dBus      = useDebounce(filterBus,      400);
  const dDriver   = useDebounce(filterDriver,   400);
  const dSearch   = useDebounce(filterSearch,   400);
  const dCategory = useDebounce(filterCategory, 0);
  const dDateFrom = useDebounce(filterDateFrom, 400);
  const dDateTo   = useDebounce(filterDateTo,   400);

  const toggleStatus = (s: Status) =>
    setFilterStatuses(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]);

  const hasFilters = !!(filterRoute || filterBus || filterDriver || filterSearch || filterCategory
    || filterStatuses.length || filterDateFrom || filterDateTo);

  const clearFilters = () => {
    setFilterRoute(''); setFilterBus(''); setFilterDriver('');
    setFilterSearch(''); setFilterCategory('');
    setFilterStatuses([]); setFilterDateFrom(''); setFilterDateTo('');
    setSortBy('id'); setSortOrder('desc');
  };

  const fetchComplaints = useCallback(async (
    p: number, route: string, bus: string, driver: string, search: string, category: string,
    statuses: Status[], dateFrom: string, dateTo: string, sb: string, so: string,
  ) => {
    setLoading(true); setFetchError('');
    try {
      const qs = new URLSearchParams({ page: String(p), page_size: String(PAGE_SIZE), sort_by: sb, sort_order: so });
      if (route.trim())    qs.set('route', route.trim());
      if (bus.trim())      qs.set('bus', bus.trim());
      if (driver.trim())   qs.set('driver', driver.trim());
      if (search.trim())   qs.set('search', search.trim());
      if (category.trim()) qs.set('category', category.trim());
      if (statuses.length) qs.set('status', statuses.join(','));
      if (dateFrom)        qs.set('date_from', dateFrom);
      if (dateTo)          qs.set('date_to', dateTo);
      const res = await fetch(`/complaints?${qs}`);
      if (!res.ok) throw new Error(`Ошибка ${res.status}`);
      const json: ComplaintsResponse = await res.json();
      setData(json);
      setDraftStatus(prev => {
        const next = { ...prev };
        // не перезаписываем ID с несохранёнными изменениями
        json.items.forEach(c => { if (!dirtyIdsRef.current.has(c.id)) next[c.id] = c.status; });
        return next;
      });
    } catch (err) {
      setFetchError(err instanceof Error ? err.message : 'Неизвестная ошибка');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { setPage(1); }, [dRoute, dBus, dDriver, dSearch, dCategory, filterStatuses, dDateFrom, dDateTo, sortBy, sortOrder]);
  useEffect(() => {
    fetchComplaints(page, dRoute, dBus, dDriver, dSearch, dCategory, filterStatuses, dDateFrom, dDateTo, sortBy, sortOrder);
  }, [page, dRoute, dBus, dDriver, dSearch, dCategory, filterStatuses, dDateFrom, dDateTo, sortBy, sortOrder, fetchComplaints]);

  // ── Waybill ──
  const loadWaybill = async (id: number) => {
    if (id in waybillData || waybillLoading[id]) return;
    setWaybillLoading(prev => ({ ...prev, [id]: true }));
    try {
      const res = await fetch(`/complaints/${id}/waybill`);
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `Ошибка ${res.status}`); }
      const json = await res.json();
      const waybill = json.waybill;
      if (waybill?.status === 'error') {
        const comment = waybill?.body?.comment || `Ошибка 1С (${waybill?.status_code})`;
        throw new Error(comment);
      }
      const body = waybill?.body ?? waybill;
      setWaybillData(prev => ({ ...prev, [id]: Array.isArray(body) ? body : body ? [body] : [] }));
    } catch (err) {
      setWaybillError(prev => ({ ...prev, [id]: err instanceof Error ? err.message : 'Ошибка' }));
      setWaybillData(prev => ({ ...prev, [id]: [] }));
    } finally { setWaybillLoading(prev => ({ ...prev, [id]: false })); }
  };

  // ── Chat ──
  const loadChat = useCallback(async (id: number) => {
    setChatLoading(prev => ({ ...prev, [id]: true }));
    try {
      const res = await fetch(`/complaints/${id}/messages?limit=200`);
      if (!res.ok) return;
      const json = await res.json();
      setChatMessages(prev => ({ ...prev, [id]: json.messages || [] }));
    } finally {
      setChatLoading(prev => ({ ...prev, [id]: false }));
    }
  }, []);

  const scrollToBottom = (id: number) => {
    setTimeout(() => chatBottomRef.current[id]?.scrollIntoView({ behavior: 'smooth' }), 50);
  };

  const sendMessage = async (c: Complaint) => {
    const text = (chatInput[c.id] ?? '').trim();
    if (!text) return;
    setChatSending(prev => ({ ...prev, [c.id]: true }));
    try {
      const fd = new FormData();
      fd.append('text', text);
      fd.append('sender_name', user);
      const res = await fetch(`/complaints/${c.id}/messages`, { method: 'POST', body: fd });
      if (!res.ok) throw new Error(`Ошибка ${res.status}`);
      const msg = await res.json();
      setChatMessages(prev => ({ ...prev, [c.id]: [...(prev[c.id] || []), msg] }));
      setChatInput(prev => ({ ...prev, [c.id]: '' }));
      scrollToBottom(c.id);
      if (c.status === 'new') {
        patchStatus(c.id, 'in_progress');
      }
    } finally { setChatSending(prev => ({ ...prev, [c.id]: false })); }
  };

  const requestEvidence = async (id: number) => {
    setChatSending(prev => ({ ...prev, [id]: true }));
    try {
      const res = await fetch(`/complaints/${id}/request-evidence`, { method: 'POST', body: new FormData() });
      if (!res.ok) return;
      const json = await res.json();
      const msg: Message = {
        id: json.message_id, sender_type: 'admin', sender_name: 'Админ',
        text: json.text, created_at: new Date().toISOString(), file_path: null,
      };
      setChatMessages(prev => ({ ...prev, [id]: [...(prev[id] || []), msg] }));
      scrollToBottom(id);
    } finally { setChatSending(prev => ({ ...prev, [id]: false })); }
  };

  // ── Status ──
  const patchStatus = async (id: number, status: Status) => {
    await fetch(`/complaints/${id}/status`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ status }),
    });
    setData(prev => prev ? { ...prev, items: prev.items.map(c => c.id === id ? { ...c, status } : c) } : prev);
    setDraftStatus(prev => ({ ...prev, [id]: status }));
  };

  const handleStatusSave = async (id: number) => {
    setActLoading(prev => ({ ...prev, [id]: true }));
    try {
      await patchStatus(id, draftStatus[id]);
      dirtyIdsRef.current.delete(id);
      setActMsg(prev => ({ ...prev, [id]: '✓ Статус сохранён' }));
      setTimeout(() => setActMsg(prev => ({ ...prev, [id]: '' })), 3000);
    } finally { setActLoading(prev => ({ ...prev, [id]: false })); }
  };

  const goTo = (p: number) => {
    if (p < 1 || (data && p > data.total_pages)) return;
    setPage(p); setExpandedId(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const st = (c: Complaint) => draftStatus[c.id] ?? c.status;

  return (
    <Layout user={user} onLogout={onLogout} title="Реестр жалоб" breadcrumb="Главная / Жалобы">

      {/* ── Фильтры: строка 1 ── */}
      <div className="filter-bar">
        <div className="filter-group">
          <label className="filter-label">🚏 Маршрут</label>
          <input className="filter-input" placeholder="74, 36…" value={filterRoute} onChange={e => setFilterRoute(e.target.value)} />
        </div>
        <div className="filter-group">
          <label className="filter-label">🚌 Автобус (гараж №)</label>
          <input className="filter-input" placeholder="A8021…" value={filterBus} onChange={e => setFilterBus(e.target.value)} />
        </div>
        <div className="filter-group">
          <label className="filter-label">👤 Водитель</label>
          <input className="filter-input" placeholder="ФИО или таб. №" value={filterDriver} onChange={e => setFilterDriver(e.target.value)} />
        </div>
        <div className="filter-group">
          <label className="filter-label">🏷 Категория</label>
          <select className="filter-input" value={filterCategory} onChange={e => setFilterCategory(e.target.value)}>
            <option value="">Все категории</option>
            {(Object.entries(CATEGORY_LABEL) as [CategoryCode, string][]).map(([code, label]) => (
              <option key={code} value={code}>{label}</option>
            ))}
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">🔍 Поиск</label>
          <input className="filter-input" placeholder="Текст жалобы…" value={filterSearch} onChange={e => setFilterSearch(e.target.value)} />
        </div>
        {hasFilters && (
          <button className="btn btn-outline btn-sm filter-clear" onClick={clearFilters}>✕ Сбросить</button>
        )}
      </div>

      {/* ── Фильтры: строка 2 — статусы, даты, сортировка ── */}
      <div className="filter-bar filter-bar-second">
        {/* Статусы */}
        <div className="filter-section-wide">
          <span className="filter-label">📊 Статус</span>
          <div className="status-chips">
            <button
              className={`status-chip${filterStatuses.length === 0 ? ' status-chip-all active' : ' status-chip-all'}`}
              onClick={() => setFilterStatuses([])}
            >Все</button>
            {ALL_STATUSES.map(s => (
              <button
                key={s}
                className={`status-chip status-chip-${s}${filterStatuses.includes(s) ? ' active' : ''}`}
                onClick={() => toggleStatus(s)}
              >{STATUS_LABEL[s]}</button>
            ))}
          </div>
        </div>

        {/* Дата от/до */}
        <div className="filter-group" style={{ minWidth: 140 }}>
          <label className="filter-label">📅 Дата от</label>
          <input type="date" className="filter-input" value={filterDateFrom} onChange={e => setFilterDateFrom(e.target.value)} />
        </div>
        <div className="filter-group" style={{ minWidth: 140 }}>
          <label className="filter-label">📅 Дата до</label>
          <input type="date" className="filter-input" value={filterDateTo} onChange={e => setFilterDateTo(e.target.value)} />
        </div>

        {/* Сортировка */}
        <div className="filter-group" style={{ minWidth: 180 }}>
          <label className="filter-label">↕ Сортировка</label>
          <div className="sort-row">
            <select className="filter-input" value={sortBy} onChange={e => setSortBy(e.target.value)}>
              <option value="id">По дате создания</option>
              <option value="route">По маршруту</option>
              <option value="status">По статусу</option>
              <option value="category">По категории</option>
            </select>
            <button
              className="btn btn-outline btn-sm sort-dir-btn"
              onClick={() => setSortOrder(o => o === 'desc' ? 'asc' : 'desc')}
              title={sortOrder === 'desc' ? 'Сначала новые' : 'Сначала старые'}
            >
              {sortOrder === 'desc' ? '↓' : '↑'}
            </button>
          </div>
        </div>
      </div>

      {loading && <div className="loading-state"><div className="spinner" /><p>Загружаем жалобы…</p></div>}
      {!loading && fetchError && (
        <div className="error-state">
          <span className="state-icon">⚠️</span><p>{fetchError}</p>
          <button className="btn btn-primary btn-sm" onClick={() => fetchComplaints(page, dRoute, dBus, dDriver, dSearch, dCategory, filterStatuses, dDateFrom, dDateTo, sortBy, sortOrder)}>Повторить</button>
        </div>
      )}
      {!loading && !fetchError && data?.items.length === 0 && (
        <div className="empty-state"><span className="state-icon">📭</span><p>Жалоб пока нет</p></div>
      )}

      {!loading && !fetchError && data && data.items.length > 0 && (
        <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <p style={{ fontSize: 13, color: '#64748b' }}>Всего: <strong style={{ color: '#1e293b' }}>{data.total}</strong></p>
          </div>

          <div className="complaints-grid">
            {data.items.map(c => {
              const isOpen = expandedId === c.id;
              const status = st(c);
              const msgs = chatMessages[c.id] || [];

              return (
                <div key={c.id} className={`complaint-card${isOpen ? ' open' : ''}`}>
                  {/* Header */}
                  <div className="complaint-card-header">
                    <span className="complaint-num">№ {c.id}</span>
                    <span className="complaint-route">{c.route}</span>
                    <span className={`badge badge-${status}`}>{STATUS_LABEL[status]}</span>
                    <span className="complaint-date">{formatDate(c.created_at)}</span>
                  </div>

                  {/* Body */}
                  <div className="complaint-body">
                    <p className="complaint-comment">{c.comment}</p>
                    <div className="complaint-meta">
                      {c.category && (
                        <span className="meta-chip" style={{
                          background: CATEGORY_COLOR[c.category] ?? '#f1f5f9',
                          color: CATEGORY_TEXT[c.category] ?? '#475569',
                          fontWeight: 600,
                        }}>
                          {CATEGORY_LABEL[c.category] ?? c.category}
                        </span>
                      )}
                      <span className="meta-chip"><span className="meta-key">От:</span> {userLabel(c)}</span>
                      {c.bus_garage_number && <span className="meta-chip"><span className="meta-key">Гараж №:</span> {c.bus_garage_number}</span>}
                      {c.bus_info && <span className="meta-chip"><span className="meta-key">Автобус:</span> {c.bus_info}</span>}
                      {c.driver_name && <span className="meta-chip"><span className="meta-key">Водитель:</span> {c.driver_name}{c.driver_tab ? ` (таб. ${c.driver_tab})` : ''}</span>}
                      {c.photo_path && (
                        <a href={`/uploads/${c.photo_path.split(/[\\/]/).pop()}`} target="_blank" rel="noreferrer"
                          className="meta-chip" style={{ color: '#3b82f6' }}>📎 Чек</a>
                      )}
                    </div>
                  </div>

                  {/* Toggle */}
                  <button className="complaint-toggle" onClick={() => {
                    const opening = !isOpen;
                    if (opening) {
                      if (c.bus_garage_number) loadWaybill(c.id);
                      loadChat(c.id);
                    }
                    setExpandedId(opening ? c.id : null);
                    if (opening) scrollToBottom(c.id);
                  }}>
                    {isOpen ? '▲ Свернуть' : '▼ Открыть чат и данные'}
                  </button>

                  {/* Panel */}
                  {isOpen && (
                    <div className="action-panel">

                      {/* ── Статус ── */}
                      <div className="action-section">
                        <p className="action-title">Статус жалобы</p>
                        <div className="action-row">
                          <select className="status-select" value={status}
                            onChange={e => {
                              dirtyIdsRef.current.add(c.id);
                              setDraftStatus(prev => ({ ...prev, [c.id]: e.target.value as Status }));
                            }}>
                            {ALL_STATUSES.map(s => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
                          </select>
                          <button className="btn btn-primary btn-sm"
                            disabled={actLoading[c.id] || status === c.status}
                            onClick={() => handleStatusSave(c.id)}>
                            {actLoading[c.id] ? 'Сохранение…' : 'Сохранить'}
                          </button>
                        </div>
                        {actMsg[c.id] && <p style={{ fontSize: 12, color: '#10b981', marginTop: 6 }}>{actMsg[c.id]}</p>}
                      </div>

                      {/* ── Чат ── */}
                      <div className="action-section">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                          <p className="action-title" style={{ margin: 0 }}>
                            💬 Чат
                            {c.user_id !== 0 && <span style={{ fontWeight: 400, color: '#94a3b8', marginLeft: 6, textTransform: 'none' }}>{userLabel(c)}</span>}
                          </p>
                          <button className="btn btn-outline btn-sm" onClick={() => loadChat(c.id)} title="Обновить">⟳</button>
                        </div>

                        {/* Сообщения */}
                        <div className="chat-window">
                          {chatLoading[c.id] && <p style={{ fontSize: 13, color: '#94a3b8', textAlign: 'center', padding: 16 }}>Загрузка…</p>}
                          {!chatLoading[c.id] && msgs.length === 0 && (
                            <p style={{ fontSize: 13, color: '#94a3b8', textAlign: 'center', padding: 16 }}>Сообщений пока нет</p>
                          )}
                          {msgs.map(m => {
                            const isAdmin = m.sender_type === 'admin';
                            return (
                              <div key={m.id} className={`chat-msg ${isAdmin ? 'chat-msg-admin' : 'chat-msg-user'}`}>
                                <div className="chat-bubble">
                                  {m.text && <span>{m.text}</span>}
                                  {m.file_path && (
                                    <a
                                      href={`/uploads/${m.file_path.split(/[\\/]/).pop()}`}
                                      target="_blank" rel="noreferrer"
                                      className="chat-file-link"
                                    >
                                      {fileIcon(m.file_path)} {m.file_path.split(/[\\/]/).pop()}
                                    </a>
                                  )}
                                </div>
                                <div className="chat-meta">
                                  {m.sender_name && <span>{m.sender_name}</span>}
                                  <span>{formatTime(m.created_at)}</span>
                                </div>
                              </div>
                            );
                          })}
                          <div ref={el => { chatBottomRef.current[c.id] = el; }} />
                        </div>

                        {/* Ввод */}
                        {c.user_id !== 0 ? (
                          <>
                            <div className="chat-input-row">
                              <textarea
                                className="chat-textarea"
                                rows={2}
                                placeholder="Введите сообщение…"
                                value={chatInput[c.id] ?? ''}
                                onChange={e => setChatInput(prev => ({ ...prev, [c.id]: e.target.value }))}
                                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(c); } }}
                              />
                              <button className="btn btn-primary chat-send-btn"
                                disabled={chatSending[c.id] || !(chatInput[c.id] ?? '').trim()}
                                onClick={() => sendMessage(c)}>
                                {chatSending[c.id] ? '…' : '➤'}
                              </button>
                            </div>
                            <button className="btn btn-outline btn-sm evidence-btn"
                              disabled={chatSending[c.id]}
                              onClick={() => requestEvidence(c.id)}>
                              📎 Запросить доказательства
                            </button>
                          </>
                        ) : (
                          <p className="no-reply-note">Жалоба через API — ответ в Telegram недоступен.</p>
                        )}
                      </div>

                      {/* ── Данные 1С ── */}
                      {c.bus_garage_number && (
                        <div className="action-section">
                          <p className="action-title">Данные из 1С — путевой лист</p>
                          {waybillLoading[c.id] && <p style={{ fontSize: 13, color: '#64748b' }}>Загружаем данные 1С…</p>}
                          {waybillError[c.id] && <p style={{ fontSize: 13, color: '#ef4444' }}>{waybillError[c.id]}</p>}
                          {!waybillLoading[c.id] && !waybillError[c.id] && (waybillData[c.id] ?? []).map(item => (
                            <div key={item.PL_ID} className="waybill-grid">
                              <div className="waybill-block">
                                <h4>Водитель</h4>
                                <div className="waybill-row"><span className="wk">ФИО</span><span className="wv">{item.Driver.FIO}</span></div>
                                <div className="waybill-row"><span className="wk">Таб. №</span><span className="wv">{item.Driver.TabNo}</span></div>
                              </div>
                              <div className="waybill-block">
                                <h4>Автобус</h4>
                                <div className="waybill-row"><span className="wk">Гараж №</span><span className="wv">{item.Vehicle.GarageNo}</span></div>
                                <div className="waybill-row"><span className="wk">Гос. номер</span><span className="wv">{item.Vehicle.Plate}</span></div>
                              </div>
                              <div className="waybill-block">
                                <h4>Рейс</h4>
                                <div className="waybill-row"><span className="wk">Маршрут</span><span className="wv">{item.Route}</span></div>
                                <div className="waybill-row"><span className="wk">Колонна</span><span className="wv">{item.Column}</span></div>
                                <div className="waybill-row"><span className="wk">Дата ПЛ</span><span className="wv">{item.Date}</span></div>
                                <div className="waybill-row"><span className="wk">Статус</span><span className="wv">{item.Status}</span></div>
                              </div>
                            </div>
                          ))}
                          {!waybillLoading[c.id] && !waybillError[c.id] && waybillData[c.id] !== undefined && (waybillData[c.id] ?? []).length === 0 && (
                            <p style={{ fontSize: 13, color: '#94a3b8' }}>Данные из 1С не найдены.</p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Pagination */}
          <div className="pagination">
            <button className="page-btn" onClick={() => goTo(1)} disabled={page === 1}>«</button>
            <button className="page-btn" onClick={() => goTo(page - 1)} disabled={page === 1}>‹</button>
            {Array.from({ length: data.total_pages }, (_, i) => i + 1)
              .filter(p => p === 1 || p === data.total_pages || Math.abs(p - page) <= 2)
              .reduce<(number | '…')[]>((acc, p, i, arr) => {
                if (i > 0 && p - (arr[i - 1] as number) > 1) acc.push('…');
                acc.push(p); return acc;
              }, [])
              .map((item, i) => item === '…'
                ? <span key={`e${i}`} className="page-ellipsis">…</span>
                : <button key={item} className={`page-btn${item === page ? ' active' : ''}`} onClick={() => goTo(item as number)}>{item}</button>
              )}
            <button className="page-btn" onClick={() => goTo(page + 1)} disabled={page === data.total_pages}>›</button>
            <button className="page-btn" onClick={() => goTo(data.total_pages)} disabled={page === data.total_pages}>»</button>
            <span className="page-info">Стр. {page} / {data.total_pages}</span>
          </div>
        </>
      )}
    </Layout>
  );
}
