import { NavLink, useNavigate } from 'react-router-dom';

interface Props {
  user: string;
  onLogout: () => void;
  children: React.ReactNode;
  title: string;
  breadcrumb?: string;
}

export default function Layout({ user, onLogout, children, title, breadcrumb }: Props) {
  const navigate = useNavigate();

  const handleLogout = () => {
    onLogout();
    navigate('/login');
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="sidebar-logo-title">🚌 AutoPark Admin</div>
          <div className="sidebar-logo-sub">Система жалоб</div>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section-label">Навигация</div>
          <NavLink to="/complaints" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <span className="nav-icon">📋</span> Жалобы
          </NavLink>
          <NavLink to="/stats" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <span className="nav-icon">📊</span> Статистика
          </NavLink>
        </nav>

        <div className="sidebar-footer">
          <div className="avatar">{user[0]?.toUpperCase()}</div>
          <span className="sidebar-user-name">{user}</span>
          <button className="sidebar-logout" title="Выйти" onClick={handleLogout}>⏻</button>
        </div>
      </aside>

      <div className="main">
        <div className="topbar">
          <div className="topbar-left">
            {breadcrumb && <div className="topbar-breadcrumb">{breadcrumb}</div>}
            <div className="topbar-title">{title}</div>
          </div>
        </div>
        <div className="content">{children}</div>
      </div>
    </div>
  );
}
