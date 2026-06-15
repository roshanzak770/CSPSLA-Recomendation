import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RefreshCw, DollarSign, MapPin, Server, ArrowUpDown,
  ArrowUp, ArrowDown, Clock, Database, Filter, ChevronDown,
  IndianRupee,
} from 'lucide-react';
import toast from 'react-hot-toast';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import Spinner from '../../components/ui/Spinner';
import { api } from '../../api/client';

const PROVIDER_COLORS = {
  aws: '#FF9900',
  amazon: '#FF9900',
  azure: '#0078D4',
  microsoft: '#0078D4',
  gcp: '#4285F4',
  google: '#4285F4',
  oracle: '#F80000',
  oci: '#F80000',
  ibm: '#1261FE',
};

function provColor(name) {
  const k = (name || '').toLowerCase();
  for (const [key, c] of Object.entries(PROVIDER_COLORS)) {
    if (k.includes(key)) return c;
  }
  return '#60a5fa';
}

function provAbbr(name) {
  const k = (name || '').toLowerCase();
  if (k.includes('amazon') || k.includes('aws')) return 'AWS';
  if (k.includes('azure') || k.includes('microsoft')) return 'AZ';
  if (k.includes('google') || k.includes('gcp')) return 'GCP';
  if (k.includes('oracle') || k.includes('oci')) return 'OCI';
  if (k.includes('ibm')) return 'IBM';
  return name.slice(0, 3).toUpperCase();
}

function timeAgo(iso) {
  if (!iso) return null;
  const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const INR_FALLBACK = 83.5;

async function fetchInrRate() {
  const res = await fetch('https://open.er-api.com/v6/latest/USD');
  if (!res.ok) throw new Error('rate fetch failed');
  const data = await res.json();
  return data.rates?.INR ?? INR_FALLBACK;
}

function formatINR(usd, rate = INR_FALLBACK) {
  const inr = usd * rate;
  if (inr >= 1_00_000) return `₹${(inr / 1_00_000).toFixed(2)}L`;
  if (inr >= 1000) return `₹${inr.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
  if (inr >= 1) return `₹${inr.toFixed(2)}`;
  if (inr >= 0.01) return `₹${inr.toFixed(4)}`;
  return `₹${inr.toExponential(2)}`;
}

function PriceCard({ item, index, rate }) {
  const color = provColor(item.provider);
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03, duration: 0.25 }}
      className="p-4 rounded-xl bg-surface border border-surface-border hover:border-opacity-50 transition-all hover:-translate-y-0.5 group"
      onMouseEnter={e => (e.currentTarget.style.borderColor = color + '50')}
      onMouseLeave={e => (e.currentTarget.style.borderColor = '')}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-white truncate">{item.service}</p>
          {item.sku && (
            <p className="text-xs text-slate-500 mt-0.5 font-mono truncate">{item.sku}</p>
          )}
        </div>
        <div className="text-right shrink-0">
          <div className="text-xl font-black" style={{ color }}>
            {formatINR(item.price_usd, rate)}
          </div>
          <div className="text-[10px] text-slate-600">{item.unit || 'per unit'}</div>
        </div>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {item.region && item.region !== 'global' && (
          <span className="flex items-center gap-1 text-[10px] text-slate-500 bg-white/4 px-2 py-0.5 rounded-md border border-white/6">
            <MapPin className="w-2.5 h-2.5" /> {item.region}
          </span>
        )}
        {item.fetched_at && (
          <span className="flex items-center gap-1 text-[10px] text-slate-600">
            <Clock className="w-2.5 h-2.5" /> {timeAgo(item.fetched_at)}
          </span>
        )}
      </div>
    </motion.div>
  );
}

export default function Pricing() {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState(null);
  const [serviceFilter, setServiceFilter] = useState('');
  const [regionFilter, setRegionFilter] = useState('');
  const [sortDir, setSortDir] = useState('asc');

  const { data: inrRate = INR_FALLBACK } = useQuery({
    queryKey: ['inr-rate'],
    queryFn: fetchInrRate,
    staleTime: 60 * 60_000,
    retry: 1,
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ['pricing-live'],
    queryFn: api.pricingLive,
    staleTime: 5 * 60_000,
  });

  const refresh = useMutation({
    mutationFn: api.refreshPricing,
    onSuccess: (result) => {
      qc.setQueryData(['pricing-live'], result);
      toast.success(`Pricing refreshed — ${result.total} items loaded`);
    },
    onError: (e) => toast.error(e.message),
  });

  const allItems = data?.items || [];

  // Derive unique provider tabs from data
  const providers = useMemo(() => {
    const names = [...new Set(allItems.map(i => i.provider))].sort();
    return names;
  }, [allItems]);

  // Set default tab when data arrives
  const currentTab = activeTab || providers[0] || null;

  // Items for active tab
  const tabItems = useMemo(
    () => allItems.filter(i => i.provider === currentTab),
    [allItems, currentTab]
  );

  // Unique services and regions for filters
  const services = useMemo(() => [...new Set(tabItems.map(i => i.service))].sort(), [tabItems]);
  const regions = useMemo(() => [...new Set(tabItems.map(i => i.region).filter(Boolean))].sort(), [tabItems]);

  // Apply filters + sort
  const filtered = useMemo(() => {
    let items = tabItems;
    if (serviceFilter) items = items.filter(i => i.service === serviceFilter);
    if (regionFilter) items = items.filter(i => i.region === regionFilter);
    items = [...items].sort((a, b) =>
      sortDir === 'asc' ? a.price_usd - b.price_usd : b.price_usd - a.price_usd
    );
    return items;
  }, [tabItems, serviceFilter, regionFilter, sortDir]);

  // Stats for active tab
  const stats = useMemo(() => {
    if (!filtered.length) return null;
    const prices = filtered.map(i => i.price_usd);
    return {
      count: filtered.length,
      min: Math.min(...prices),
      max: Math.max(...prices),
      lastFetched: filtered[0]?.fetched_at,
    };
  }, [filtered]);

  // Clear filters when tab changes
  function switchTab(name) {
    setActiveTab(name);
    setServiceFilter('');
    setRegionFilter('');
  }

  const color = provColor(currentTab || '');

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white mb-1">Pricing</h1>
          <p className="text-slate-500 text-sm">
            Real-time pricing from free public cloud APIs — displayed in Indian Rupees (₹).
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-surface-card border border-surface-border text-xs text-slate-400">
            <IndianRupee className="w-3.5 h-3.5 text-emerald-400" />
            <span>1 USD = <span className="text-white font-semibold">₹{inrRate.toFixed(2)}</span></span>
          </div>
          <Button
            variant="secondary"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
          >
          <RefreshCw className={`w-4 h-4 ${refresh.isPending ? 'animate-spin' : ''}`} />
          {refresh.isPending ? 'Fetching…' : 'Refresh'}
          </Button>
        </div>
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <Spinner size="lg" />
          <p className="text-slate-500 text-sm">Fetching pricing from cloud APIs…</p>
          <p className="text-slate-600 text-xs">First load may take 15–30 seconds</p>
        </div>
      )}

      {/* Error state */}
      {error && !isLoading && (
        <Card>
          <p className="text-red-400 text-sm">Failed to load pricing: {error.message}</p>
        </Card>
      )}

      {/* Empty (shouldn't normally happen — backend auto-fetches) */}
      {!isLoading && !error && allItems.length === 0 && (
        <Card className="flex flex-col items-center py-16 gap-4 text-center">
          <DollarSign className="w-12 h-12 text-slate-700" />
          <div>
            <p className="text-slate-400 font-medium mb-1">No pricing data yet</p>
            <p className="text-slate-600 text-sm">Click Refresh to fetch from cloud APIs</p>
          </div>
          <Button onClick={() => refresh.mutate()} disabled={refresh.isPending}>
            {refresh.isPending ? <Spinner size="sm" /> : 'Fetch Now'}
          </Button>
        </Card>
      )}

      {/* Main content */}
      {!isLoading && allItems.length > 0 && (
        <>
          {/* Provider tabs */}
          <div className="flex gap-2 flex-wrap p-1 bg-surface-card border border-surface-border rounded-xl w-fit">
            {providers.map(name => {
              const c = provColor(name);
              const isActive = name === currentTab;
              return (
                <button
                  key={name}
                  onClick={() => switchTab(name)}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
                  style={
                    isActive
                      ? { backgroundColor: c + '20', border: `1px solid ${c}40`, color: c }
                      : { color: '#64748b', border: '1px solid transparent' }
                  }
                >
                  <span className="w-5 h-5 rounded-md text-[9px] font-black flex items-center justify-center"
                    style={{ backgroundColor: c + (isActive ? '30' : '15'), color: c }}>
                    {provAbbr(name)}
                  </span>
                  {name}
                </button>
              );
            })}
          </div>

          {/* Stats strip */}
          {stats && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { icon: Database, label: 'Services', value: stats.count },
                { icon: ArrowDown, label: 'Lowest', value: formatINR(stats.min, inrRate) },
                { icon: ArrowUp, label: 'Highest', value: formatINR(stats.max, inrRate) },
                { icon: Clock, label: 'Updated', value: timeAgo(stats.lastFetched) || '—' },
              ].map(({ icon: Icon, label, value }) => (
                <div key={label} className="flex items-center gap-3 p-3 rounded-xl bg-surface-card border border-surface-border">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
                    style={{ backgroundColor: color + '15', border: `1px solid ${color}25` }}>
                    <Icon className="w-3.5 h-3.5" style={{ color }} />
                  </div>
                  <div>
                    <p className="text-[11px] text-slate-500">{label}</p>
                    <p className="text-sm font-bold text-white">{value}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Filters + sort */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-1.5 text-xs text-slate-500">
              <Filter className="w-3.5 h-3.5" />
              <span>Filter:</span>
            </div>

            <div className="relative">
              <select
                value={serviceFilter}
                onChange={e => setServiceFilter(e.target.value)}
                className="appearance-none pl-3 pr-7 py-1.5 rounded-lg bg-surface-card border border-surface-border text-slate-300 text-xs focus:outline-none focus:border-blue-500/50 cursor-pointer"
              >
                <option value="">All services</option>
                {services.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-500 pointer-events-none" />
            </div>

            <div className="relative">
              <select
                value={regionFilter}
                onChange={e => setRegionFilter(e.target.value)}
                className="appearance-none pl-3 pr-7 py-1.5 rounded-lg bg-surface-card border border-surface-border text-slate-300 text-xs focus:outline-none focus:border-blue-500/50 cursor-pointer"
              >
                <option value="">All regions</option>
                {regions.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
              <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-500 pointer-events-none" />
            </div>

            <button
              onClick={() => setSortDir(d => d === 'asc' ? 'desc' : 'asc')}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-card border border-surface-border text-xs text-slate-400 hover:text-white hover:border-blue-500/40 transition-all"
            >
              <ArrowUpDown className="w-3.5 h-3.5" />
              Price {sortDir === 'asc' ? '↑' : '↓'}
            </button>

            {(serviceFilter || regionFilter) && (
              <button
                onClick={() => { setServiceFilter(''); setRegionFilter(''); }}
                className="text-xs text-slate-600 hover:text-slate-300 transition-colors"
              >
                Clear filters
              </button>
            )}

            <span className="ml-auto text-xs text-slate-600">{filtered.length} items</span>
          </div>

          {/* Card grid */}
          <AnimatePresence mode="wait">
            <motion.div
              key={currentTab + serviceFilter + regionFilter + sortDir}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.15 }}
              className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3"
            >
              {filtered.map((item, i) => (
                <PriceCard key={`${item.provider}-${item.service}-${item.sku}-${item.region}-${i}`} item={item} index={i} rate={inrRate} />
              ))}
            </motion.div>
          </AnimatePresence>

          {filtered.length === 0 && (
            <Card className="text-center py-8">
              <p className="text-slate-500 text-sm">No items match the current filters.</p>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
