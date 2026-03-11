import type { DreamSession } from '../../api/types';
import DreamComparisonWeb from './DreamComparison.web';

export interface DreamComparisonProps {
  data: DreamSession[];
}

export const PF_DISPLAY_CAP = 10;

export interface DreamComparisonBarData {
  condition: string;
  label: string;
  pf: number;
  pfCapped: boolean;
  color: string;
  resonance: boolean;
}

const CONDITION_CONFIG: Record<string, { label: string; color: string }> = {
  no_memory: { label: 'No Memory', color: '#6a6a80' },
  naive_recall: { label: 'Naive Recall', color: '#ff3366' },
  hybrid_recall: { label: 'Hybrid Recall', color: '#00ff88' },
};

/**
 * Transform dream sessions into chart-ready bar data.
 * Business logic only — no chart library imports.
 */
function transformData(data: DreamSession[]): DreamComparisonBarData[] {
  return data.map((session) => {
    const config = CONDITION_CONFIG[session.condition] ?? {
      label: session.condition,
      color: '#6a6a80',
    };
    const rawPf = session.pf;
    const isCapped = !isFinite(rawPf) || rawPf > PF_DISPLAY_CAP;
    return {
      condition: session.condition,
      label: config.label,
      pf: isCapped ? PF_DISPLAY_CAP : rawPf,
      pfCapped: isCapped,
      color: config.color,
      resonance: session.resonance_detected,
    };
  });
}

export default function DreamComparison({ data }: DreamComparisonProps) {
  const chartData = transformData(data);
  return <DreamComparisonWeb data={chartData} />;
}
