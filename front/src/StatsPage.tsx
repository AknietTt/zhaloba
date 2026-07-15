import { useEffect, useState, useCallback, useMemo } from 'react';
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

const PALETTE = ['#3b82f6','#f59e0b','#10b981','#ef4444','#8b5cf6','#06b6d4','#f97316','#84cc16','#ec4899','#6366f1'];

const STATUS_CFG: Record<string, { bg: string; accent: string; label: string }> = {
  new:         { bg: '#dbeafe', accent: '#2563eb', label: 'Новые' },
  in_progress: { bg: '#fef3c7', accent: '#d97706', label: 'В работе' },
  replied:     { bg: '#d1fae5', accent: '#059669', label: 'Отвечено' },
  closed:      { bg: '#f1f5f9', accent: '#64748b', label: 'Закрыто' },
};

const DAYS_RU = ['Вс','Пн','Вт','Ср','Чт','Пт','Сб'];
const MONTHS_RU: Record<string, string> = {
  '01':'Янв','02':'Фев','03':'Мар','04':'Апр','05':'Май','06':'Июн',
  '07':'Июл','08':'Авг','09':'Сен','10':'Окт','11':'Ноя','12':'Дек',
};

function formatMonth(key: string) {
  const [y, m] = key.split('-');
  return `${MONTHS_RU[m] ?? m} ${y}`;
}

const TZ = 'Asia/Almaty';
function toUtcDate(iso: string): Date {
  if (iso && !iso.endsWith('Z') && !iso.includes('+')) return new Date(iso + 'Z');
  return new Date(iso);
}
function isoInAstana(iso: string): string {
  return toUtcDate(iso).toLocaleDateString('sv-SE', { timeZone: TZ });
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
    const dowMap: Record<string, number> = { Sun:0,Mon:1,Tue:2,Wed:3,Thu:4,Fri:5,Sat:6 };
    byDow[dowMap[dowStr] ?? 0]++;
  }

  const sort = (obj: Record<string, number>) =>
    Object.entries(obj).sort((a, b) => b[1] - a[1]) as [string, number][];
  const sortByKey = (obj: Record<string, number>) =>
    Object.entries(obj).sort((a, b) => a[0].localeCompare(b[0])) as [string, number][];

  return {
    total: items.length,
    today: items.filter(c => isoInAstana(c.created_at) === today).length,
    week: items.filter(c => isoInAstana(c.created_at) >= weekAgo).length,
    new_count: byStatus['new'] || 0,
    by_status: sort(byStatus),
    top_routes: sort(byRoute).slice(0, 15),
    top_buses: sort(byBus).slice(0, 12),
    by_month: sortByKey(byMonth).slice(-12),
    by_hour: byHour,
    by_dow: byDow,
  };
}

/* ── Горизонтальный бар-чарт ── */
function BarChart({ rows, unit = '' }: { rows: [string, number][]; unit?: string }) {
  if (!rows.length) return <p style={{ color: '#94a3b8', fontSize: 13, padding: '8px 0' }}>Нет данных</p>;
  const max = Math.max(...rows.map(r => r[1])) || 1;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
      {rows.map(([label, count], i) => {
        const pct = Math.round((count / max) * 100);
        return (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 120, fontSize: 12, color: 'var(--ink-2)', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flexShrink: 0 }} title={label}>
              {label}
            </div>
            <div style={{ flex: 1, background: 'var(--border)', borderRadius: 6, height: 20, overflow: 'hidden', position: 'relative' }}>
              <div style={{
                width: `${pct}%`, height: '100%',
                background: PALETTE[i % PALETTE.length],
                borderRadius: 6,
                transition: 'width .4s ease',
                minWidth: count > 0 ? 6 : 0,
              }} />
            </div>
            <div style={{ width: 32, fontSize: 12, fontWeight: 700, color: 'var(--ink)', textAlign: 'left', flexShrink: 0 }}>
              {count}{unit}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ── Колончатый мини-график (часы) ── */
function ColumnChart({ values, labels }: { values: number[]; labels?: string[] }) {
  const max = Math.max(...values) || 1;
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 90, paddingBottom: 20, position: 'relative' }}>
      {values.map((v, i) => {
        const h = max > 0 ? Math.max((v / max) * 70, v > 0 ? 4 : 0) : 0;
        const active = v === max && v > 0;
        return (
          <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
            <div
              title={`${labels?.[i] ?? i}: ${v} жалоб`}
              style={{
                width: '100%', height: h,
                background: active ? '#3b82f6' : 'var(--brand-light)',
                borderRadius: '3px 3px 0 0',
                transition: 'height .3s ease',
                cursor: 'default',
              }}
            />
            {labels && (
              <div style={{ fontSize: 9, color: 'var(--ink-4)', marginTop: 2, textAlign: 'center', lineHeight: 1 }}>
                {labels[i]}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── Статус-бар (сегментированный) ── */
function StatusBar({ data }: { data: [string, number][] }) {
  const total = data.reduce((s, [, n]) => s + n, 0) || 1;
  return (
    <div style={{ display: 'flex', borderRadius: 8, overflow: 'hidden', height: 10, marginBottom: 20 }}>
      {data.map(([s, n]) => {
        const cfg = STATUS_CFG[s] || { accent: '#94a3b8' };
        return (
          <div key={s} style={{ width: `${(n / total) * 100}%`, background: cfg.accent, transition: 'width .4s ease', minWidth: n > 0 ? 4 : 0 }} />
        );
      })}
    </div>
  );
}

const MEDAL = ['🥇','🥈','🥉'];

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
      if (!r.ok) throw new Error();
      const j = await r.json();
      setDriverItems(j.items ?? []);
    } catch { setDriverItems([]); }
    finally { setDriverLoading(false); }
  }, []);

  const stats = useMemo(() => computeStats(allItems), [allItems]);
  const dStats = useMemo(() => driverItems ? computeStats(driverItems) : null, [driverItems]);
  const driverName = driverItems?.find(c => c.driver_name)?.driver_name;

  const hourLabels = Array.from({ length: 24 }, (_, h) => h % 3 === 0 ? `${String(h).padStart(2,'0')}` : '');
  const maxDow = Math.max(...stats.by_dow) || 1;
  const maxDriver = topDrivers[0]?.count || 1;

  const kpiCards = [
    { icon: '📋', val: stats.total,     label: 'Всего жалоб',   accent: '#3b82f6', lightBg: '#eff6ff' },
    { icon: '📅', val: stats.today,     label: 'Сегодня',       accent: '#8b5cf6', lightBg: '#f5f3ff' },
    { icon: '📆', val: stats.week,      label: 'За 7 дней',     accent: '#10b981', lightBg: '#f0fdf4' },
    { icon: '🔔', val: stats.new_count, label: 'Не обработано', accent: '#f59e0b', lightBg: '#fffbeb' },
  ];

  return (
    <Layout user={user} onLogout={onLogout} title="Статистика" breadcrumb="Главная / Статистика">
      {loading && <div className="loading-state"><div className="spinner" /><p>Загружаем данные…</p></div>}
      {error   && <div className="error-state"><span className="state-icon">⚠️</span><p>{error}</p></div>}

      {!loading && !error && (
        <>
          {/* ── KPI ── */}
          <div className="kpi-grid" style={{ marginBottom: 20 }}>
            {kpiCards.map(k => (
              <div key={k.label} style={{
                background: 'var(--surface)', borderRadius: 14, padding: '20px 22px',
                boxShadow: 'var(--shadow-sm)', border: '1px solid var(--border)',
                borderLeft: `4px solid ${k.accent}`,
                display: 'flex', alignItems: 'center', gap: 16,
              }}>
                <div style={{
                  width: 48, height: 48, borderRadius: 12,
                  background: k.lightBg, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 22, flexShrink: 0,
                }}>{k.icon}</div>
                <div>
                  <div style={{ fontSize: 30, fontWeight: 800, color: k.accent, letterSpacing: '-0.03em', lineHeight: 1 }}>{k.val}</div>
                  <div style={{ fontSize: 11.5, color: 'var(--ink-3)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.4px', marginTop: 4 }}>{k.label}</div>
                </div>
              </div>
            ))}
          </div>

          {/* ── Статусы ── */}
          <div style={{
            background: 'var(--surface)', borderRadius: 14, padding: '20px 24px',
            boxShadow: 'var(--shadow-sm)', border: '1px solid var(--border)', marginBottom: 16,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>📊 Распределение по статусам</h3>
              <span style={{ fontSize: 12, color: 'var(--ink-4)' }}>Всего: {stats.total}</span>
            </div>
            <StatusBar data={stats.by_status} />
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {stats.by_status.map(([s, n]) => {
                const cfg = STATUS_CFG[s] || { bg: '#f1f5f9', accent: '#64748b', label: s };
                const pct = stats.total > 0 ? Math.round((n / stats.total) * 100) : 0;
                return (
                  <div key={s} style={{
                    background: cfg.bg, borderRadius: 12, padding: '14px 20px',
                    minWidth: 120, flex: '1 1 120px',
                    borderTop: `3px solid ${cfg.accent}`,
                  }}>
                    <div style={{ fontSize: 28, fontWeight: 800, color: cfg.accent, letterSpacing: '-0.03em', lineHeight: 1 }}>{n}</div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: cfg.accent, opacity: .75, marginTop: 4, textTransform: 'uppercase', letterSpacing: '.4px' }}>{cfg.label}</div>
                    <div style={{ fontSize: 18, fontWeight: 700, color: cfg.accent, opacity: .45, marginTop: 2 }}>{pct}%</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* ── Маршруты + Автобусы ── */}
          <div className="stats-grid">
            <div style={{ background: 'var(--surface)', borderRadius: 14, boxShadow: 'var(--shadow-sm)', border: '1px solid var(--border)', overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 16 }}>🚌</span>
                <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>Топ маршрутов</h3>
              </div>
              <div style={{ padding: '16px 20px' }}>
                <BarChart rows={stats.top_routes} />
              </div>
            </div>
            <div style={{ background: 'var(--surface)', borderRadius: 14, boxShadow: 'var(--shadow-sm)', border: '1px solid var(--border)', overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 16 }}>🔢</span>
                <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>Топ автобусов</h3>
              </div>
              <div style={{ padding: '16px 20px' }}>
                <BarChart rows={stats.top_buses} />
              </div>
            </div>
          </div>

          {/* ── Топ водителей ── */}
          <div style={{
            background: 'var(--surface)', borderRadius: 14, boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--border)', overflow: 'hidden', marginBottom: 16,
          }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 16 }}>👤</span>
              <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>Топ водителей по жалобам</h3>
            </div>
            <div style={{ padding: '8px 0' }}>
              {topDrivers.length === 0 ? (
                <p style={{ color: '#94a3b8', fontSize: 13, padding: '16px 20px' }}>
                  Данные водителей появятся после открытия путевых листов из 1С
                </p>
              ) : (
                topDrivers.map((d, i) => {
                  const barW = Math.round((d.count / maxDriver) * 100);
                  const isTop3 = i < 3;
                  return (
                    <div
                      key={d.driver_tab || d.driver_name}
                      onClick={() => { setDriverQuery(d.driver_tab || d.driver_name); searchDriver(d.driver_tab || d.driver_name); }}
                      style={{
                        display: 'grid', gridTemplateColumns: '36px 1fr 90px 56px',
                        alignItems: 'center', gap: 12, padding: '10px 20px',
                        borderBottom: '1px solid var(--border)', cursor: 'pointer',
                        transition: 'background .15s',
                        background: isTop3 ? (i === 0 ? 'linear-gradient(90deg,#fffbeb,transparent)' : i === 1 ? 'linear-gradient(90deg,#f8fafc,transparent)' : 'transparent') : 'transparent',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-raised)')}
                      onMouseLeave={e => (e.currentTarget.style.background = i === 0 ? 'linear-gradient(90deg,#fffbeb,transparent)' : i === 1 ? 'linear-gradient(90deg,#f8fafc,transparent)' : 'transparent')}
                    >
                      <div style={{ fontSize: i < 3 ? 20 : 13, fontWeight: 700, color: 'var(--ink-4)', textAlign: 'center' }}>
                        {i < 3 ? MEDAL[i] : i + 1}
                      </div>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)' }}>{d.driver_name}</div>
                        <div style={{ fontSize: 11, color: 'var(--ink-4)', marginTop: 1 }}>таб. {d.driver_tab || '—'}</div>
                        <div style={{ marginTop: 5, background: 'var(--border)', borderRadius: 4, height: 4, overflow: 'hidden' }}>
                          <div style={{ width: `${barW}%`, height: '100%', background: i === 0 ? '#f59e0b' : i === 1 ? '#94a3b8' : '#3b82f6', borderRadius: 4 }} />
                        </div>
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--ink-4)', textAlign: 'center' }}>{d.driver_tab || '—'}</div>
                      <div style={{ textAlign: 'center' }}>
                        <span style={{
                          display: 'inline-block', padding: '3px 10px', borderRadius: 20,
                          fontSize: 13, fontWeight: 700,
                          background: i === 0 ? '#fee2e2' : i === 1 ? '#fef3c7' : 'var(--surface-raised)',
                          color: i === 0 ? '#dc2626' : i === 1 ? '#d97706' : 'var(--ink-2)',
                        }}>{d.count}</span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* ── По часам + дни недели ── */}
          <div className="stats-grid">
            <div style={{ background: 'var(--surface)', borderRadius: 14, boxShadow: 'var(--shadow-sm)', border: '1px solid var(--border)', overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 16 }}>🕐</span>
                <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>По часам суток</h3>
              </div>
              <div style={{ padding: '20px 16px 8px' }}>
                <ColumnChart values={stats.by_hour} labels={hourLabels} />
              </div>
            </div>
            <div style={{ background: 'var(--surface)', borderRadius: 14, boxShadow: 'var(--shadow-sm)', border: '1px solid var(--border)', overflow: 'hidden' }}>
              <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 16 }}>📆</span>
                <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>По дням недели</h3>
              </div>
              <div style={{ padding: '20px' }}>
                <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                  {DAYS_RU.map(d => (
                    <div key={d} style={{ flex: 1, textAlign: 'center', fontSize: 11, fontWeight: 700, color: 'var(--ink-3)', textTransform: 'uppercase' }}>{d}</div>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  {stats.by_dow.map((v, i) => {
                    const intensity = maxDow > 0 ? v / maxDow : 0;
                    const bg = intensity === 0 ? 'var(--surface-raised)' : `rgba(59,130,246,${0.12 + intensity * 0.88})`;
                    const isMax = v === maxDow && v > 0;
                    return (
                      <div key={i} style={{ flex: 1 }}>
                        <div style={{
                          background: bg, borderRadius: 10, padding: '12px 4px', textAlign: 'center',
                          border: isMax ? '2px solid #3b82f6' : '2px solid transparent',
                          transition: 'all .2s',
                        }}>
                          <div style={{ fontSize: 16, fontWeight: 800, color: intensity > 0.5 ? '#fff' : intensity > 0.1 ? '#1d4ed8' : 'var(--ink-4)' }}>{v || '—'}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                  <div style={{ fontSize: 10, color: 'var(--ink-4)', flex: 1, textAlign: 'center' }}>меньше</div>
                  <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                    {[0,.25,.5,.75,1].map(i => (
                      <div key={i} style={{ width: 14, height: 14, borderRadius: 3, background: `rgba(59,130,246,${0.12 + i * 0.88})` }} />
                    ))}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--ink-4)', flex: 1, textAlign: 'center' }}>больше</div>
                </div>
              </div>
            </div>
          </div>

          {/* ── По месяцам ── */}
          <div style={{
            background: 'var(--surface)', borderRadius: 14, boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--border)', overflow: 'hidden', marginBottom: 16,
          }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 16 }}>📅</span>
              <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>Тренд по месяцам</h3>
            </div>
            <div style={{ padding: '20px' }}>
              <BarChart rows={stats.by_month.map(([k, v]) => [formatMonth(k), v])} />
            </div>
          </div>

          {/* ── Поиск по водителю ── */}
          <div style={{
            background: 'var(--surface)', borderRadius: 14, boxShadow: 'var(--shadow-sm)',
            border: '1px solid var(--border)', overflow: 'hidden', marginBottom: 16,
          }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 16 }}>🔍</span>
              <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)' }}>Поиск по водителю</h3>
            </div>
            <div style={{ padding: '20px' }}>
              <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap', marginBottom: 20 }}>
                <div style={{ flex: 1, minWidth: 200 }}>
                  <label className="filter-label" style={{ marginBottom: 6, display: 'block' }}>Таб. № или ФИО</label>
                  <input
                    className="filter-input"
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
                  <button className="btn btn-outline btn-sm" onClick={() => { setDriverItems(null); setDriverQuery(''); }}>✕ Сбросить</button>
                )}
              </div>

              {driverItems && dStats && (
                <>
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
                    {[
                      { label: 'Водитель',   val: driverName || driverQuery, bg: '#eff6ff', color: '#1d4ed8', big: false },
                      { label: 'Всего',      val: String(dStats.total),       bg: '#fffbeb', color: '#d97706', big: true },
                      { label: 'За 7 дней',  val: String(dStats.week),        bg: '#f0fdf4', color: '#059669', big: true },
                      { label: 'Не обраб.',  val: String(dStats.new_count),   bg: '#fef3c7', color: '#92400e', big: true },
                    ].map(x => (
                      <div key={x.label} style={{
                        background: x.bg, borderRadius: 12, padding: '14px 20px',
                        borderTop: `3px solid ${x.color}`, minWidth: 110,
                      }}>
                        <div style={{ fontSize: 10, color: x.color, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.4px' }}>{x.label}</div>
                        <div style={{ fontSize: x.big ? 28 : 15, fontWeight: 800, color: x.color, marginTop: 4 }}>{x.val}</div>
                      </div>
                    ))}
                  </div>
                  {dStats.total === 0 ? (
                    <p style={{ color: '#94a3b8', fontSize: 13 }}>Жалоб не найдено</p>
                  ) : (
                    <div className="stats-grid" style={{ marginBottom: 0 }}>
                      <div>
                        <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--ink-3)', textTransform: 'uppercase', marginBottom: 12 }}>По маршрутам</p>
                        <BarChart rows={dStats.top_routes} />
                      </div>
                      <div>
                        <p style={{ fontSize: 11, fontWeight: 700, color: 'var(--ink-3)', textTransform: 'uppercase', marginBottom: 12 }}>По месяцам</p>
                        <BarChart rows={dStats.by_month.map(([k, v]) => [formatMonth(k), v])} />
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </>
      )}
    </Layout>
  );
}
