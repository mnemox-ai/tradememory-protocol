import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import PageShell from '../components/layout/PageShell';
import Skeleton from '../components/ui/Skeleton';
import ErrorState from '../components/ui/ErrorState';
import EmptyState from '../components/ui/EmptyState';
import { useEvolution } from '../api/hooks';
import { useScrollReveal } from '../hooks/useScrollReveal';
import { formatRelativeTime } from '../utils/formatRelativeTime';
import styles from './EvolutionPage.module.css';

function RevealDiv({ children, className }: { children: React.ReactNode; className?: string }) {
  const { ref, isVisible } = useScrollReveal();
  return (
    <div ref={ref} className={`reveal ${isVisible ? 'visible' : ''} ${className ?? ''}`}>
      {children}
    </div>
  );
}

function formatSharpe(v: number): string {
  return v.toFixed(2);
}

function formatPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

export default function EvolutionPage() {
  const { t } = useTranslation();
  const { data, error, isLoading, mutate } = useEvolution();
  const [fetchedAt] = useState(() => new Date());

  if (isLoading) {
    return (
      <PageShell>
        <div className={`${styles.page} pageFadeIn`}>
          <Skeleton variant="card" />
          <Skeleton variant="chart" />
          <Skeleton variant="chart" />
        </div>
      </PageShell>
    );
  }

  if (error) {
    return (
      <PageShell>
        <ErrorState message={t('common.error')} onRetry={() => mutate()} />
      </PageShell>
    );
  }

  if (!data) {
    return (
      <PageShell>
        <EmptyState
          icon="&#129516;"
          title={t('common.empty')}
          description={t('evolution.noRuns')}
        />
      </PageShell>
    );
  }

  const d = data;

  return (
    <PageShell>
      <div className={`${styles.page} pageFadeIn`}>
        <span className="lastUpdated">{formatRelativeTime(fetchedAt)}</span>

        {/* Run Summary */}
        <RevealDiv className={styles.section}>
          <p className={styles.sectionTitle}>{t('evolution.runSummary')}</p>
          <div className={styles.summaryGrid}>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>{t('evolution.runId')}</span>
              <span className={styles.summaryValue}>{d.run_id}</span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>{t('evolution.symbol')}</span>
              <span className={styles.summaryValue}>{d.symbol} / {d.timeframe}</span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>{t('evolution.generations')}</span>
              <span className={styles.summaryValue}>{d.generations}</span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>{t('evolution.graduated')}</span>
              <span className={`${styles.summaryValue} ${styles.textGreen}`}>{d.total_graduated}</span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>{t('evolution.eliminated')}</span>
              <span className={`${styles.summaryValue} ${styles.textRed}`}>{d.total_graveyard}</span>
            </div>
            <div className={styles.summaryItem}>
              <span className={styles.summaryLabel}>{t('evolution.backtests')}</span>
              <span className={styles.summaryValue}>{d.total_backtests}</span>
            </div>
          </div>
        </RevealDiv>

        {/* Fitness Trend (text) */}
        <RevealDiv className={styles.section}>
          <p className={styles.sectionTitle}>{t('evolution.fitnessTrend')}</p>
          <div className={styles.trendRows}>
            {d.per_generation.map((g) => (
              <div key={g.generation} className={styles.trendRow}>
                <span className={styles.trendGen}>Gen {g.generation}</span>
                <div className={styles.trendBar}>
                  <div
                    className={styles.trendGraduated}
                    style={{ width: `${(g.graduated_count / g.hypotheses_count) * 100}%` }}
                  />
                  <div
                    className={styles.trendEliminated}
                    style={{ width: `${(g.eliminated_count / g.hypotheses_count) * 100}%` }}
                  />
                </div>
                <span className={styles.trendLabel}>
                  <span className={styles.textGreen}>{g.graduated_count}</span>
                  {' / '}
                  <span className={styles.textRed}>{g.eliminated_count}</span>
                </span>
              </div>
            ))}
          </div>
        </RevealDiv>

        {/* Surviving Strategies */}
        <RevealDiv className={styles.section}>
          <p className={styles.sectionTitle}>{t('evolution.surviving')}</p>
          <div className={styles.tableWrap}>
            <table className={styles.evoTable}>
              <thead>
                <tr>
                  <th>{t('evolution.strategy')}</th>
                  <th>Gen</th>
                  <th>{t('evolution.sharpeIS')}</th>
                  <th>{t('evolution.sharpeOOS')}</th>
                  <th>{t('evolution.winRate')}</th>
                  <th>PF</th>
                  <th>{t('evolution.trades')}</th>
                  <th>MDD</th>
                </tr>
              </thead>
              <tbody>
                {d.graduated.map((s) => (
                  <tr key={s.hypothesis_id}>
                    <td className={styles.stratName}>{s.pattern_name}</td>
                    <td>{s.generation}</td>
                    <td className={styles.textGreen}>{formatSharpe(s.fitness_is.sharpe_ratio)}</td>
                    <td className={s.fitness_oos && s.fitness_oos.sharpe_ratio >= 1.0 ? styles.textGreen : styles.textAmber}>
                      {s.fitness_oos ? formatSharpe(s.fitness_oos.sharpe_ratio) : '—'}
                    </td>
                    <td>{formatPct(s.fitness_oos?.win_rate ?? s.fitness_is.win_rate)}</td>
                    <td>{(s.fitness_oos?.profit_factor ?? s.fitness_is.profit_factor).toFixed(2)}</td>
                    <td>{s.fitness_oos?.trade_count ?? s.fitness_is.trade_count}</td>
                    <td className={styles.textRed}>{(s.fitness_oos?.max_drawdown_pct ?? s.fitness_is.max_drawdown_pct).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </RevealDiv>

        {/* Strategy Graveyard */}
        <RevealDiv className={styles.section}>
          <p className={styles.sectionTitle}>{t('evolution.graveyard')}</p>
          <div className={styles.tableWrap}>
            <table className={styles.evoTable}>
              <thead>
                <tr>
                  <th>{t('evolution.strategy')}</th>
                  <th>Gen</th>
                  <th>{t('evolution.reason')}</th>
                  <th>{t('evolution.sharpeIS')}</th>
                  <th>{t('evolution.winRate')}</th>
                  <th>{t('evolution.trades')}</th>
                </tr>
              </thead>
              <tbody>
                {d.graveyard.map((s) => (
                  <tr key={s.hypothesis_id} className={styles.graveyardRow}>
                    <td className={styles.stratNameDead}>{s.pattern_name}</td>
                    <td>{s.generation}</td>
                    <td className={styles.reason}>{s.elimination_reason}</td>
                    <td className={styles.textRed}>
                      {s.fitness_is ? formatSharpe(s.fitness_is.sharpe_ratio) : '—'}
                    </td>
                    <td>{s.fitness_is ? formatPct(s.fitness_is.win_rate) : '—'}</td>
                    <td>{s.fitness_is?.trade_count ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </RevealDiv>
      </div>
    </PageShell>
  );
}
