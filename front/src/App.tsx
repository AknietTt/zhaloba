import { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import './App.css';
import ComplaintsPage from './ComplaintsPage';
import StatsPage from './StatsPage';

const VALID_EMAIL = 'user@example.com';
const VALID_PASSWORD = 'password123';

function LoginPage({ onLogin }: { onLogin: (u: string) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (email === VALID_EMAIL && password === VALID_PASSWORD) {
      onLogin(email);
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
              placeholder="user@example.com"
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
        <p className="login-hint">user@example.com / password123</p>
      </div>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState<string | null>(() => localStorage.getItem('authUser'));

  const handleLogin = (u: string) => {
    localStorage.setItem('authUser', u);
    setUser(u);
  };
  const handleLogout = () => {
    localStorage.removeItem('authUser');
    setUser(null);
  };

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={user ? <Navigate to="/complaints" replace /> : <LoginPage onLogin={handleLogin} />}
        />
        <Route
          path="/complaints"
          element={user ? <ComplaintsPage user={user!} onLogout={handleLogout} /> : <Navigate to="/login" replace />}
        />
        <Route
          path="/stats"
          element={user ? <StatsPage user={user!} onLogout={handleLogout} /> : <Navigate to="/login" replace />}
        />
        <Route path="*" element={<Navigate to={user ? '/complaints' : '/login'} replace />} />
      </Routes>
    </BrowserRouter>
  );
}
