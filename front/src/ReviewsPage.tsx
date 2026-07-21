import { useState, useEffect, useCallback } from 'react';
import Layout from './Layout';

interface ReviewUser {
  name: string;
  photoPreviewUrls: { '64x64': string; url: string };
}

interface Review {
  id: string;
  rating: number;
  text: string;
  dateCreated: string;
  hasCompanyComment: boolean;
  firstAnswer: unknown;
  user: ReviewUser;
}

interface TwoGisResult {
  '2gisReviewsCount': number;
  '2gisRating': number;
  items: Review[];
}

interface Props { user: string; onLogout: () => void; }

const PAGE_SIZE = 20;

function Stars({ rating, size = 14 }: { rating: number; size?: number }) {
  return (
    <span className="stars-row" style={{ fontSize: size }}>
      {[1, 2, 3, 4, 5].map(i => (
        <span key={i} className={i <= rating ? 'star-filled' : 'star-empty'}>★</span>
      ))}
    </span>
  );
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: '2-digit', month: 'long', year: 'numeric',
  });
}

function answerText(v: unknown): string | null {
  if (!v) return null;
  if (typeof v === 'string') return v;
  if (typeof v === 'object' && v !== null && 'text' in v) return String((v as { text: unknown }).text);
  return null;
}

export default function ReviewsPage({ user, onLogout }: Props) {
  const [data, setData] = useState<TwoGisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [page, setPage] = useState(0);
  const [filterRating, setFilterRating] = useState<number | null>(null);

  const load = useCallback(async (p: number) => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`/reviews/2gis?limit=${PAGE_SIZE}&offset=${p * PAGE_SIZE}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json.result as TwoGisResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(page); }, [load, page]);

  const total      = data?.['2gisReviewsCount'] ?? 0;
  const avgRating  = data?.['2gisRating'] ?? 0;
  const items      = data?.items ?? [];
  const filtered   = filterRating != null ? items.filter(r => r.rating === filterRating) : items;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <Layout user={user} onLogout={onLogout} title="Отзывы 2GIS" breadcrumb="Сервисы">

      {/* ── Summary bar ── */}
      <div className="reviews-summary">
        <div className="reviews-summary-left">
          <div className="reviews-avg-num">{avgRating.toFixed(1)}</div>
          <div>
            <Stars rating={Math.round(avgRating)} size={22} />
            <div className="reviews-total-sub">{total} отзывов на 2GIS</div>
          </div>
        </div>

        <div className="reviews-filter-row">
          <span className="reviews-filter-label">Рейтинг:</span>
          {[null, 5, 4, 3, 2, 1].map(r => (
            <button
              key={r ?? 'all'}
              className={`status-chip${filterRating === r ? ' status-chip-all active' : ''}`}
              onClick={() => setFilterRating(prev => prev === r ? null : r)}
            >
              {r == null ? 'Все' : '★'.repeat(r)}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="loading-state">
          <div className="spinner" />
          <span>Загрузка отзывов...</span>
        </div>
      )}

      {error && <div className="error-banner">Ошибка загрузки: {error}</div>}

      {/* ── Reviews list ── */}
      {!loading && (
        <div className="reviews-list">
          {filtered.map(review => (
            <div key={review.id} className={`review-card review-r${review.rating}`}>
              <div className="review-row">
                <div className="review-avatar">
                  {review.user.photoPreviewUrls?.['64x64']
                    ? <img src={review.user.photoPreviewUrls['64x64']} alt="" />
                    : <div className="review-avatar-ph">{review.user.name?.[0] ?? '?'}</div>
                  }
                </div>

                <div className="review-body">
                  <div className="review-meta">
                    <span className="review-author">{review.user.name}</span>
                    <Stars rating={review.rating} size={13} />
                    <span className="review-date">{fmtDate(review.dateCreated)}</span>
                    {review.hasCompanyComment
                      ? <span className="review-badge review-answered">Есть ответ</span>
                      : <span className="review-badge review-no-answer">Без ответа</span>
                    }
                  </div>

                  {review.text
                    ? <p className="review-text">{review.text}</p>
                    : <p className="review-text review-no-text">— без текста —</p>
                  }

                  {answerText(review.firstAnswer) && (
                    <div className="review-company-answer">
                      <span className="review-answer-label">Ответ компании</span>
                      {answerText(review.firstAnswer)}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}

          {filtered.length === 0 && (
            <div className="empty-state">
              <div className="state-icon">🔍</div>
              <span>Отзывов не найдено</span>
            </div>
          )}
        </div>
      )}

      {/* ── Pagination ── */}
      {totalPages > 1 && (
        <div className="pagination">
          <button className="page-btn" disabled={page === 0} onClick={() => setPage(0)}>«</button>
          <button className="page-btn" disabled={page === 0} onClick={() => setPage(p => p - 1)}>‹</button>
          <span className="page-info">Стр. {page + 1} / {totalPages}</span>
          <button className="page-btn" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>›</button>
          <button className="page-btn" disabled={page >= totalPages - 1} onClick={() => setPage(totalPages - 1)}>»</button>
        </div>
      )}
    </Layout>
  );
}
