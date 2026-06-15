export default function ScoreBar({ score, max = 10, label, color }) {
  const pct = Math.min(100, Math.round((score / max) * 100));
  const barColor = color || (pct >= 75 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444');
  return (
    <div className="space-y-1">
      {label && (
        <div className="flex justify-between text-xs text-slate-400">
          <span>{label}</span>
          <span className="font-medium text-slate-200">{typeof score === 'number' ? score.toFixed(1) : score}</span>
        </div>
      )}
      <div className="h-1.5 rounded-full bg-surface-border overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, backgroundColor: barColor }}
        />
      </div>
    </div>
  );
}
