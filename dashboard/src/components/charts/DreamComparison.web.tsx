import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ReferenceLine,
  Label,
  LabelList,
} from 'recharts';
import ChartTooltip from '../ui/ChartTooltip';
import type { DreamComparisonBarData } from './DreamComparison';
import { PF_DISPLAY_CAP } from './DreamComparison';

export interface DreamComparisonWebProps {
  data: DreamComparisonBarData[];
}

export default function DreamComparisonWeb({ data }: DreamComparisonWebProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 20, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(26, 26, 40, 0.5)" />
        <XAxis
          dataKey="label"
          tick={{ fill: '#6a6a80', fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}
          tickLine={{ stroke: '#1a1a28' }}
          axisLine={{ stroke: '#1a1a28' }}
        />
        <YAxis
          domain={[0, PF_DISPLAY_CAP]}
          tick={{ fill: '#6a6a80', fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }}
          tickLine={{ stroke: '#1a1a28' }}
          axisLine={{ stroke: '#1a1a28' }}
          label={{
            value: 'Profit Factor',
            angle: -90,
            position: 'insideLeft',
            fill: '#6a6a80',
            fontSize: 11,
          }}
        />
        <ReferenceLine y={1} stroke="#ffaa00" strokeDasharray="4 4">
          <Label value="Breakeven" position="right" fill="#ffaa00" fontSize={10} />
        </ReferenceLine>
        <Tooltip
          content={<ChartTooltip formatValue={(v, name) => {
            if (name.toLowerCase().includes('profit factor') || name.toLowerCase().includes('pf')) {
              return v >= 999 ? '∞' : v.toFixed(2);
            }
            return v.toFixed(2);
          }} />}
        />
        <Bar dataKey="pf" name="Profit Factor" radius={[4, 4, 0, 0]} maxBarSize={80}>
          {data.map((entry, index) => (
            <Cell key={index} fill={entry.color} />
          ))}
          <LabelList
            dataKey="pfCapped"
            position="top"
            formatter={((value?: string | number) => value ? '∞' : '') as (label: unknown) => string}
            style={{ fill: '#ffaa00', fontSize: 14, fontWeight: 700 }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
