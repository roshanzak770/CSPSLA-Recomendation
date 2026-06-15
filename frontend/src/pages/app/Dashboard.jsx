import { useState } from 'react';
import { Outlet, Link } from 'react-router-dom';
import Sidebar from '../../components/layout/Sidebar';
import { Cloud, Activity } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../api/client';

export default function Dashboard() {
  const [collapsed, setCollapsed] = useState(false);

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 30_000,
    retry: false,
  });
  const online = health?.status === 'ok';

  return (
    <div className="h-screen flex overflow-hidden bg-surface">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="h-16 shrink-0 flex items-center justify-between px-6 bg-surface-card/50 border-b border-surface-border">
          <Link to="/" className="flex items-center gap-2">
            <Cloud className="w-5 h-5 text-blue-400" />
            <span className="text-slate-400 text-sm">SLAwise</span>
          </Link>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Activity className="w-3.5 h-3.5" />
            <span className={online ? 'text-emerald-400' : ''}>
              {online ? 'API Online' : 'Connecting…'}
            </span>
            <div className={`w-1.5 h-1.5 rounded-full ${online ? 'bg-emerald-400' : 'bg-slate-600'}`} />
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
