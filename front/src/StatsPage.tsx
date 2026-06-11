import { useEffect, useState, useCallback } from 'react';
import Layout from './Layout';

interface Props { user: string; onLogout: () => void; }

interface Complaint {
  id: number; route: string; status: string;
  bus_garage_number: string | null; bus_info: string | null;
  created_at: string; comment: string;
  driver_name: string | null; driver_tab: string | null;
  user_full_name: string | null; username: string | null;
}
interface DriverStat { driver_name: string; driver_tab: string; count: number; }

const COLORS = ['#3b82f6','#f59e0b','#10b981','#ef4444','#8b5cf6','#06b6d4','#f97316','#84cc16','#ec4899','#6366f1'];
const STATUS_STYLE: Record<string, { bg: string; color: string; label: string }> = {
  new:         { bg: '#dbeafe', color: '#1d4ed8', label: 'Новые' },
  in_progress: { bg: '#fef3c7', color: '#92400e', label: 'В работе' },
  replied:     { bg: '#d1fae5', color: '#065f46', label: 'Отвечено' },
  closed:      { bg: '#f1f5f9', color: '#475569', label: 'Закрыто' },
};
const DAYS = ['Вс','Пн','Вт','Ср','Чт','Пт','Сб'];

function BarChart({ rows, unit = '' }: { rows: [string, number][]; unit?: string }) {
  if (!rows.length) return <p style={{ color: '#94a3b8', fontSize: 13 }}>Нет данных</p>;
  const max = Math.max(...rows.map(r => r[1])) || 1;
  return (
    <div className="bar-chart">
      {rows.map(([label, count], i) => (
        <div key={label} className="bar-row">
          <div className="bar-label" title={label}>{label}</div>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(count / max) * 100}%`, background: COLORS[i % COLORS.length] }} />
          </div>
          <div className="bar-count">{count}{unit}</div>
        </div>
      ))}
    </div>
  );
}

function HeatRow({ label, values, max }: { label: string; values: number[]; max: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
      <span style={{ width: 28, fontSize: 11, color: '#94a3b8', textAlign: 'right', flexShrink: 0 }}>{label}</span>
      {values.map((v, i) => {
        const intensity = max > 0 ? v / max : 0;
        const bg = intensity === 0 ? '#f8fafc' : `rgba(59,130,246,${0.1 + intensity * 0.9})`;
        return (
          <div key={i} title={`${v} жалоб`} style={{
            flex: 1, height: 22, background: bg, borderRadius: 3,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 10, color: intensity > 0.5 ? '#fff' : '#94a3b8', fontWeight: 600,
          }}>
            {v > 0 ? v : ''}
          </div>
        );
      })}
    </div>
  );
}

// UTC+5 Astana — принудительно парсим как UTC
const TZ = 'Asia/Almaty';
function toUtcDate(iso: string): Date {
  if (iso && !iso.endsWith('Z') && !iso.includes('+')) return new Date(iso + 'Z');
  return new Date(iso);
}
function isoInAstana(iso: string): string {
  return toUtcDate(iso).toLocaleDateString('sv-SE', { timeZone: TZ }); // sv-SE даёт YYYY-MM-DD
}

function computeStats(items: Complaint[]) {
  const byStatus: Record<string, number> = {};
  const byRoute: Record<string, number> = {};
  const byBus: Record<string, number> = {};
  const byMonth: Record<string, number> = {};
  const byHour: number[] = Array(24).fill(0);
  const byDow: number[] = Array(7).fill(0);

  const today   = new Date().toLocaleDateString('sv-SE', { timeZone: TZ });
  const weekAgo = new Date(Date.now() - 7 * 86400000).toLocaleDateString('sv-SE', { timeZone: TZ });

  for (const c of items) {
    byStatus[c.status] = (byStatus[c.status] || 0) + 1;
    if (c.route) byRoute[c.route] = (byRoute[c.route] || 0) + 1;
    if (c.bus_garage_number) byBus[c.bus_garage_number] = (byBus[c.bus_garage_number] || 0) + 1;
    const month = isoInAstana(c.created_at).slice(0, 7);
    byMonth[month] = (byMonth[month] || 0) + 1;
    const d = toUtcDate(c.created_at);
    byHour[parseInt(d.toLocaleTimeString('sv-SE', { timeZone: TZ }).slice(0, 2))]++;
    const dowStr = new Intl.DateTimeFormat('en-US', { timeZone: TZ, weekday: 'short' }).format(d);
    const dowMap: Record<string, number> = { Sun:0, Mon:1, Tue:2, Wed:3, Thu:4, Fri:5, Sat:6 };
    byDow[dowMap[dowStr] ?? 0]++;
  }

  const sort = (obj: Record<string, number>) =>
    Object.entries(obj).sort((a, b) => b[1] - a[1]) as [string, number][];
  const sortByKey = (obj: Record<string, number>) =>
    Object.entries(obj).sort((a, b) => a[0].localeCompare(b[0])) as [string, number][];

  return {
    total: items.length,
    today: items.filter(c => c.created_at.slice(0, 10) === today).length,
    week: items.filter(c => c.created_at.slice(0, 10) >= weekAgo).length,
    new_count: byStatus['new'] || 0,
    by_status: sort(byStatus),
    top_routes: sort(byRoute).slice(0, 15),
    top_buses: sort(byBus).slice(0, 12),
    by_month: sortByKey(byMonth).slice(-12),
    by_hour: byHour,
    by_dow: byDow,
  };
}

export default function StatsPage({ user, onLogout }: Props) {
  const [allItems, setAllItems] = useState<Complaint[]>([]);
  const [topDrivers, setTopDrivers] = useState<DriverStat[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [driverQuery, setDriverQuery] = useState('');
  const [driverItems, setDriverItems] = useState<Complaint[] | null>(null);
  const [driverLoading, setDriverLoading] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [r1, r2] = await Promise.all([
          fetch('/complaints?page=1&page_size=2000'),
          fetch('/stats/drivers'),
        ]);
        if (!r1.ok) throw new Error(`Ошибка ${r1.status}`);
        const j = await r1.json();
        setAllItems(j.items);
        if (r2.ok) setTopDrivers(await r2.json());
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Ошибка');
      } finally { setLoading(false); }
    })();
  }, []);

  const searchDriver = useCallback(async (q: string) => {
    if (!q.trim()) { setDriverItems(null); return; }
    setDriverLoading(true);
    try {
      const r = await fetch(`/complaints?page=1&page_size=2000&driver=${encodeURIComponent(q.trim())}`);
      if (!r.ok) throw new Error(`Ошибка ${r.status}`);
      const j = await r.json();
      setDriverItems(j.items ?? []);
    } catch { setDriverItems([]); }
    finally { setDriverLoading(false); }
  }, []);

  const stats = computeStats(allItems);
  const dStats = driverItems ? computeStats(driverItems) : null;
  const maxDow = Math.max(...stats.by_dow);

  const driverName = driverItems?.find(c => c.driver_name)?.driver_name;

  return (
    <Layout user={user} onLogout={onLogout} title="Статистика" breadcrumb="Главная / Статистика">
      {loading && <div className="loading-state"><div className="spinner" /><p>Загружаем данные…</p></div>}
      {error && <div className="error-state"><span className="state-icon">⚠️</span><p>{error}</p></div>}

      {!loading && !error && (
        <>
          {/* ── Поиск по водителю ── */}
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-header"><h3>👤 Поиск по водителю</h3></div>
            <div className="card-body">
              <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
                <div style={{ flex: 1, minWidth: 200 }}>
                  <label className="filter-label">Таб. № или ФИО</label>
                  <input
                    className="filter-input"
                    style={{ marginTop: 4 }}
                    placeholder="20817 или Сабытаев…"
                    value={driverQuery}
                    onChange={e => setDriverQuery(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && searchDriver(driverQuery)}
                  />
                </div>
                <button className="btn btn-primary btn-sm" onClick={() => searchDriver(driverQuery)} disabled={driverLoading}>
                  {driverLoading ? 'Поиск…' : '🔍 Найти'}
                </button>
                {driverItems && (
                  <button className="btn btn-outline btn-sm" onClick={() => { setDriverItems(null); setDriverQuery(''); }}>
                    ✕ Сбросить
                  </button>
                )}
              </div>

              {/* Результат поиска по водителю */}
              {driverItems && dStats && (
                <div style={{ marginTop: 20 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                    <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 10, padding: '10px 20px' }}>
                      <div style={{ fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase' }}>Водитель</div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: '#1e293b', marginTop: 2 }}>
                        {driverName || driverQuery}
                      </div>
                    </div>
                    <div style={{ background: '#fef3c7', border: '1px solid #fde68a', borderRadius: 10, padding: '10px 20px' }}>
                      <div style={{ fontSize: 11, color: '#92400e', fontWeight: 600, textTransform: 'uppercase' }}>Всего жалоб</div>
                      <div style={{ fontSize: 28, fontWeight: 700, color: '#d97706', marginTop: 2 }}>{dStats.total}</div>
                    </div>
                    <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 10, padding: '10px 20px' }}>
                      <div style={{ fontSize: 11, color: '#065f46', fontWeight: 600, textTransform: 'uppercase' }}>За 7 дней</div>
                      <div style={{ fontSize: 28, fontWeight: 700, color: '#10b981', marginTop: 2 }}>{dStats.week}</div>
                    </div>
                  </div>

                  {dStats.total === 0 ? (
                    <p style={{ color: '#94a3b8', fontSize: 13 }}>Жалоб не найдено</p>
                  ) : (
                    <div className="stats-grid" style={{ marginBottom: 0 }}>
                      <div>
                        <p style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: 10 }}>По маршрутам</p>
                        <BarChart rows={dStats.top_routes} />
                      </div>
                      <div>
                        <p style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: 10 }}>По месяцам</p>
                        <BarChart rows={dStats.by_month} />
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* ── KPI ── */}
          <div className="kpi-grid">
            {[
              { icon: '📋', val: stats.total,     label: 'Всего жалоб',     color: '#1e293b' },
              { icon: '📅', val: stats.today,     label: 'Сегодня',         color: '#3b82f6' },
              { icon: '📆', val: stats.week,      label: 'За 7 дней',       color: '#10b981' },
              { icon: '🔔', val: stats.new_count, label: 'Не обработано',   color: '#f59e0b' },
            ].map(k => (
              <div key={k.label} className="kpi-card">
                <div className="kpi-icon">{k.icon}</div>
                <div className="kpi-value" style={{ color: k.color }}>{k.val}</div>
                <div className="kpi-label">{k.label}</div>
              </div>
            ))}
          </div>

          {/* ── По статусам ── */}
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-header"><h3>📊 По статусам</h3></div>
            <div className="card-body">
              <div className="status-pills">
                {stats.by_status.map(([s, n]) => {
                  const st = STATUS_STYLE[s] || { bg: '#f1f5f9', color: '#475569', label: s };
                  return (
                    <div key={s} className="status-pill" style={{ background: st.bg, color: st.color }}>
                      <div className="status-pill-value">{n}</div>
                      <div className="status-pill-label">{st.label}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* ── Маршруты + Автобусы ── */}
          <div className="stats-grid">
            <div className="card">
              <div className="card-header"><h3>🚌 Топ маршрутов</h3></div>
              <div className="card-body"><BarChart rows={stats.top_routes} /></div>
            </div>
            <div className="card">
              <div className="card-header"><h3>🔢 Топ автобусов</h3></div>
              <div className="card-body"><BarChart rows={stats.top_buses} /></div>
            </div>
          </div>

          {/* ── Топ водителей ── */}
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-header"><h3>👤 Топ водителей по жалобам</h3></div>
            <div className="card-body">
              {topDrivers.length === 0 ? (
                <p style={{ color: '#94a3b8', fontSize: 13 }}>Данные водителей появятся после открытия путевых листов из 1С</p>
              ) : (
                <div className="drivers-table">
                  <div className="drivers-header">
                    <span>#</span><span>Водитель</span><span>Таб. №</span><span>Жалоб</span>
                  </div>
                  {topDrivers.map((d, i) => (
                    <div
                      key={d.driver_tab || d.driver_name}
                      className="drivers-row"
                      style={{ cursor: 'pointer' }}
                      onClick={() => { setDriverQuery(d.driver_tab || d.driver_name); searchDriver(d.driver_tab || d.driver_name); }}
                    >
                      <span className="driver-rank">{i + 1}</span>
                      <span className="driver-name">{d.driver_name}</span>
                      <span className="driver-tab">{d.driver_tab || '—'}</span>
                      <span className="driver-count">
                        <span className="driver-badge" style={{
                          background: i === 0 ? '#fee2e2' : i === 1 ? '#fef3c7' : '#f1f5f9',
                          color: i === 0 ? '#dc2626' : i === 1 ? '#d97706' : '#475569',
                        }}>{d.count}</span>
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* ── Время и день недели ── */}
          <div className="stats-grid">
            <div className="card">
              <div className="card-header"><h3>🕐 По часам суток</h3></div>
              <div className="card-body">
                <BarChart rows={stats.by_hour.map((v, h) => [`${String(h).padStart(2,'0')}:00`, v] as [string, number]).filter(r => r[1] > 0)} />
              </div>
            </div>
            <div className="card">
              <div className="card-header"><h3>📆 По дням недели</h3></div>
              <div className="card-body">
                <div style={{ padding: '8px 0' }}>
                  <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
                    {DAYS.map((d) => (
                      <div key={d} style={{ flex: 1, textAlign: 'center', fontSize: 11, color: '#94a3b8', fontWeight: 600 }}>{d}</div>
                    ))}
                  </div>
                  <HeatRow label="" values={stats.by_dow} max={maxDow} />
                  <div style={{ display: 'flex', gap: 6 }}>
                    {stats.by_dow.map((v, i) => (
                      <div key={i} style={{ flex: 1, textAlign: 'center', fontSize: 11, color: '#64748b' }}>{v}</div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* ── По месяцам ── */}
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-header"><h3>📅 По месяцам</h3></div>
            <div className="card-body"><BarChart rows={stats.by_month} /></div>
          </div>
        </>
      )}
    </Layout>
  );
}
