import { NavLink, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  FilePlus2, Search, BarChart3, MessageSquare,
  DollarSign, Bell, ChevronLeft, ChevronRight, Cloud,
} from 'lucide-react';
import { clsx } from 'clsx';
import { api } from '../../api/client';

const nav = [
  { to: 'upload', icon: FilePlus2, label: 'Add SLA Docs' },
  { to: 'recommend', icon: Search, label: 'Recommend' },
  { to: 'compare', icon: BarChart3, label: 'Compare' },
  { to: 'chat', icon: MessageSquare, label: 'Chat with SLA' },
  { to: 'pricing', icon: DollarSign, label: 'Pricing' },
  { to: 'alerts', icon: Bell, label: 'Alerts' },
];

export default function Sidebar({ collapsed, onToggle }) {
  const { data: alerts } = useQuery({
    queryKey: ['alerts'],
    queryFn: api.alerts,
    refetchInterval: 60_000,
    retry: false,
  });
  const alertCount = alerts?.length || 0;

  return (
    <aside
      className={clsx(
        'flex flex-col h-full bg-surface-card border-r border-surface-border transition-all duration-300 relative z-20',
        collapsed ? 'w-16' : 'w-56'
      )}
    >
      {/* Logo — clicks anywhere on the icon or the "SLAwise" wordmark
          route back to the landing page. Wrapped as a single Link so the
          hit area is the whole logo cell, not just the wordmark. */}
      <Link
        to="/"
        title="Back to home"
        className="h-16 flex items-center px-4 border-b border-surface-border shrink-0 hover:bg-white/[0.03] transition-colors"
      >
        <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center shrink-0">
          <Cloud className="w-4 h-4 text-white" />
        </div>
        {!collapsed && (
          <span className="ml-3 font-bold text-white text-sm whitespace-nowrap">SLAwise</span>
        )}
      </Link>

      {/* Nav */}
      <nav className="flex-1 py-4 space-y-1 px-2 overflow-y-auto">
        {nav.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150 group relative',
                isActive
                  ? 'bg-blue-600/20 text-blue-400 border border-blue-600/30'
                  : 'text-slate-400 hover:text-white hover:bg-white/5 border border-transparent'
              )
            }
            title={collapsed ? label : undefined}
          >
            <Icon className="w-4 h-4 shrink-0" />
            {!collapsed && <span className="whitespace-nowrap">{label}</span>}
            {!collapsed && label === 'Alerts' && alertCount > 0 && (
              <span className="ml-auto text-xs bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded-full px-1.5 py-0.5">
                {alertCount}
              </span>
            )}
            {collapsed && label === 'Alerts' && alertCount > 0 && (
              <div className="absolute top-1 right-1 w-2 h-2 rounded-full bg-amber-500" />
            )}
          </NavLink>
        ))}
      </nav>

      {/* Toggle */}
      <button
        onClick={onToggle}
        className="absolute -right-3 top-20 w-6 h-6 rounded-full bg-surface-card border border-surface-border flex items-center justify-center text-slate-400 hover:text-white hover:border-blue-500/50 transition-all z-10"
      >
        {collapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronLeft className="w-3 h-3" />}
      </button>
    </aside>
  );
}
