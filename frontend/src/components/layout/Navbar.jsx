import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Cloud, Activity } from 'lucide-react';
import { api } from '../../api/client';

export default function Navbar() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 30_000,
    retry: false,
  });

  const online = health?.status === 'ok';

  return (
    <nav className="fixed top-0 inset-x-0 z-50 glass border-b border-surface-border">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center">
            <Cloud className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-white tracking-tight">SLAwise</span>
          <span className="text-slate-500 font-light hidden sm:inline">by CloudSLA</span>
        </Link>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 text-xs">
            <Activity className="w-3.5 h-3.5 text-slate-500" />
            <span className={online ? 'text-emerald-400' : 'text-slate-500'}>
              {online ? 'API Online' : 'Connecting…'}
            </span>
            <div className={`w-1.5 h-1.5 rounded-full ${online ? 'bg-emerald-400 shadow-[0_0_6px_#10b981]' : 'bg-slate-600'}`} />
          </div>

          <Link
            to="/app"
            className="px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors"
          >
            Launch App
          </Link>
        </div>
      </div>
    </nav>
  );
}
