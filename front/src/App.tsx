import { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import './App.css';
import ComplaintsPage from './ComplaintsPage';
import StatsPage from './StatsPage';
import ReviewsPage from './ReviewsPage';
import SuperAdminPage from './SuperAdminPage';

const ACCOUNTS = [
  { email: 'user@example.com', password: 'password123', role: 'user' },
  { email: 'admin@mail.com',   password: 'admin',       role: 'admin' },
];

function LoginPage({ onLogin }: { onLogin: (email: string, role: string) => void }) {
  const [email, setEmail]     = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]     = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const match = ACCOUNTS.find(a => a.email === email && a.password === password);
    if (match) {
      onLogin(match.email, match.role);
    } else {
      setError('Неверный email или пароль');
    }
  };

  return (
    <div className="login-wrapper">
      <div className="login-card">
        <div className="login-logo">
          <div className="login-logo-icon">🚌</div>
          <h1>AutoPark Admin</h1>
          <p>Система управления жалобами</p>
        </div>
        <form onSubmit={handleSubmit}>
          {error && <div className="login-error">{error}</div>}
          <div className="form-group">
            <label>Email</label>
            <input
              type="email" value={email} autoFocus required
              placeholder="email@example.com"
              onChange={e => { setEmail(e.target.value); setError(''); }}
            />
          </div>
          <div className="form-group">
            <label>Пароль</label>
            <input
              type="password" value={password} required
              placeholder="••••••••"
              onChange={e => { setPassword(e.target.value); setError(''); }}
            />
          </div>
          <button type="submit" className="btn-login">Войти</button>
        </form>
        <p className="login-hint">AutoPark Admin</p>
      </div>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState<string | null>(() => localStorage.getItem('authUser'));
  const [role, setRole] = useState<string | null>(() => localStorage.getItem('authRole'));

  const handleLogin = (u: string, r: string) => {
    localStorage.setItem('authUser', u);
    localStorage.setItem('authRole', r);
    setUser(u);
    setRole(r);
  };
  const handleLogout = () => {
    localStorage.removeItem('authUser');
    localStorage.removeItem('authRole');
    setUser(null);
    setRole(null);
  };

  const home = !user ? '/login' : role === 'admin' ? '/superadmin' : '/complaints';
  const isAdmin  = user && role === 'admin';
  const isUser   = user && role !== 'admin';

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login"
          element={user ? <Navigate to={home} replace /> : <LoginPage onLogin={handleLogin} />}
        />

        {/* Regular user routes */}
        <Route path="/complaints"
          element={isUser ? <ComplaintsPage user={user!} onLogout={handleLogout} /> : <Navigate to={home} replace />}
        />
        <Route path="/stats"
          element={isUser ? <StatsPage user={user!} onLogout={handleLogout} /> : <Navigate to={home} replace />}
        />
        <Route path="/reviews"
          element={isUser ? <ReviewsPage user={user!} onLogout={handleLogout} /> : <Navigate to={home} replace />}
        />

        {/* Admin route */}
        <Route path="/superadmin"
          element={isAdmin ? <SuperAdminPage user={user!} onLogout={handleLogout} /> : <Navigate to={home} replace />}
        />

        <Route path="*" element={<Navigate to={home} replace />} />
      </Routes>
    </BrowserRouter>
  );
}
