import React, { useState } from 'react';
import { buildHeatmapGrid, getCellColor } from './StrategyHeatmap';
import type { StrategyHeatmapProps, HeatmapCell } from './StrategyHeatmap';
import styles from './StrategyHeatmap.module.css';

export default function StrategyHeatmapWeb({ data }: StrategyHeatmapProps) {
  const [hoveredCell, setHoveredCell] = useState<HeatmapCell | null>(null);
  const { lookup, maxAbs, sessions, days } = buildHeatmapGrid(data);

  return (
    <div className={styles.heatmap}>
      <div className={styles.grid}>
        {/* Header row: empty corner + day labels */}
        <div className={styles.cornerCell} />
        {days.map((day) => (
          <div key={day} className={styles.headerCell}>{day}</div>
        ))}

        {/* Data rows */}
        {sessions.map((session) => (
          <React.Fragment key={session}>
            <div className={styles.rowLabel}>{session}</div>
            {days.map((day) => {
              const key = `${session}:${day}`;
              const cell = lookup.get(key);

              if (!cell) {
                return (
                  <div key={key} className={`${styles.cell} ${styles.cellEmpty}`} />
                );
              }

              return (
                <div
                  key={key}
                  className={styles.cell}
                  style={{ background: getCellColor(cell.avg_pnl, maxAbs) }}
                  onMouseEnter={() => setHoveredCell(cell)}
                  onMouseLeave={() => setHoveredCell(null)}
                >
                  <span className={styles.cellValue}>
                    {cell.trades}
                  </span>
                  {hoveredCell === cell && (
                    <div className={styles.tooltip}>
                      <div className={styles.tooltipRow}>
                        <span className={styles.tooltipLabel}>Session</span>
                        <span className={styles.tooltipValue}>{cell.session}</span>
                      </div>
                      <div className={styles.tooltipRow}>
                        <span className={styles.tooltipLabel}>Day</span>
                        <span className={styles.tooltipValue}>{cell.day}</span>
                      </div>
                      <div className={styles.tooltipRow}>
                        <span className={styles.tooltipLabel}>Trades</span>
                        <span className={styles.tooltipValue}>{cell.trades}</span>
                      </div>
                      <div className={styles.tooltipRow}>
                        <span className={styles.tooltipLabel}>Avg P&L</span>
                        <span className={styles.tooltipValue}>
                          {cell.avg_pnl >= 0 ? '+' : ''}${cell.avg_pnl.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}
