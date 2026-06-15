import { clsx } from 'clsx';

const variants = {
  primary: 'bg-blue-600 hover:bg-blue-500 text-white shadow-lg hover:shadow-blue-500/25',
  secondary: 'bg-surface-card border border-surface-border hover:border-blue-500/50 text-slate-200',
  ghost: 'hover:bg-white/5 text-slate-300 hover:text-white',
  danger: 'bg-red-600/20 hover:bg-red-600/30 border border-red-600/40 text-red-400',
};

const sizes = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2 text-sm',
  lg: 'px-6 py-3 text-base',
};

export default function Button({ variant = 'primary', size = 'md', className, disabled, children, ...props }) {
  return (
    <button
      disabled={disabled}
      className={clsx(
        'inline-flex items-center gap-2 rounded-lg font-medium transition-all duration-200 cursor-pointer',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        variants[variant],
        sizes[size],
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}
