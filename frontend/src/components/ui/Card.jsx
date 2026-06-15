import { clsx } from 'clsx';

export default function Card({ className, children, hover = false, ...props }) {
  return (
    <div
      className={clsx(
        'rounded-xl border border-surface-border bg-surface-card p-4',
        hover && 'hover:border-blue-500/30 hover:bg-white/[0.02] transition-all duration-200',
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}
