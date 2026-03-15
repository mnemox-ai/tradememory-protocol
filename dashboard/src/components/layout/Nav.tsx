import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink } from 'react-router-dom';
import styles from './Nav.module.css';

const NAV_KEYS = [
  { to: '/', key: 'nav.overview' },
  { to: '/intelligence', key: 'nav.intelligence' },
  { to: '/strategies', key: 'nav.strategies' },
  { to: '/reflections', key: 'nav.reflections' },
  { to: '/dreams', key: 'nav.dreams' },
  { to: '/evolution', key: 'nav.evolution' },
] as const;

export default function Nav() {
  const { t, i18n } = useTranslation();
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const toggleLang = () => {
    const next = i18n.language === 'zh-TW' ? 'en' : 'zh-TW';
    i18n.changeLanguage(next);
  };

  return (
    <nav className={`${styles.nav} glassmorphism`}>
      <div className={styles.logo}>MNEMOX</div>
      <button
        className={styles.hamburger}
        onClick={() => setIsMenuOpen((v) => !v)}
        aria-label="Toggle navigation"
      >
        <span className={`${styles.hamburgerLine} ${isMenuOpen ? styles.hamburgerOpen : ''}`} />
        <span className={`${styles.hamburgerLine} ${isMenuOpen ? styles.hamburgerOpen : ''}`} />
        <span className={`${styles.hamburgerLine} ${isMenuOpen ? styles.hamburgerOpen : ''}`} />
      </button>
      <div className={`${styles.links} ${isMenuOpen ? styles.linksOpen : ''}`}>
        {NAV_KEYS.map(({ to, key }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `${styles.link} ${isActive ? styles.linkActive : ''}`
            }
            onClick={() => setIsMenuOpen(false)}
          >
            {t(key)}
          </NavLink>
        ))}
        <button className={styles.langToggle} onClick={toggleLang}>
          {i18n.language === 'zh-TW' ? 'EN' : '\u4E2D'}
        </button>
      </div>
    </nav>
  );
}
