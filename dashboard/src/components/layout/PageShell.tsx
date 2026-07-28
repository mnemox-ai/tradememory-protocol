import type { ReactNode } from 'react';
import styles from './PageShell.module.css';

interface PageShellProps {
  children: ReactNode;
}

const USING_MOCK = import.meta.env.VITE_USE_MOCK === 'true';

export default function PageShell({ children }: PageShellProps) {
  return (
    <div className={styles.shell}>
      {USING_MOCK && (
        <div
          role="note"
          style={{
            background: 'var(--warning, #7a5c00)',
            color: '#fff',
            textAlign: 'center',
            padding: '6px 12px',
            fontSize: '13px',
            fontWeight: 600,
            letterSpacing: '0.04em',
          }}
        >
          SIMULATED DATA — all figures on this dashboard are demo/mock values, not real trading results.
        </div>
      )}
      {children}
    </div>
  );
}
