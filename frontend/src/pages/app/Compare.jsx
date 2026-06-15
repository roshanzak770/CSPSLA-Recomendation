import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Trophy, Check, Minus, ChevronDown, ChevronUp, Info,
  Shield, MapPin, Zap, Clock, DollarSign, BarChart2, Filter,
} from 'lucide-react';
import Spinner from '../../components/ui/Spinner';
import Card from '../../components/ui/Card';
import { api } from '../../api/client';

// ── constants ─────────────────────────────────────────────────────────────────

const ALL_METRICS = [
  { field: 'uptime_sla_pct',       label: 'Uptime SLA (%)',       unit: '%',    icon: Zap,        higher: true,  category: 'SLA' },
  { field: 'rto_hours',            label: 'RTO (hours)',           unit: 'h',    icon: Clock,      higher: false, category: 'SLA' },
  { field: 'rpo_hours',            label: 'RPO (hours)',           unit: 'h',    icon: Clock,      higher: false, category: 'SLA' },
  { field: 'support_response_min', label: 'Support Response',      unit: 'min',  icon: Clock,      higher: false, category: 'SLA' },
  { field: 'penalty_credit_pct',   label: 'SLA Credit (%)',        unit: '%',    icon: DollarSign, higher: true,  category: 'SLA' },
  { field: 'region_count',         label: 'Regions Covered',       unit: '',     icon: MapPin,     higher: true,  category: 'Coverage' },
  { field: 'compliance_count',     label: 'Compliance Standards',  unit: '',     icon: Shield,     higher: true,  category: 'Coverage' },
  { field: 'min_compute_usd',      label: 'Min Compute Price',     unit: '$/hr', icon: DollarSign, higher: false, category: 'Pricing' },
];

const PROVIDER_COLORS = {
  aws: '#FF9900', amazon: '#FF9900',
  azure: '#0078D4', microsoft: '#0078D4',
  gcp: '#4285F4', google: '#4285F4',
  oracle: '#F80000', oci: '#F80000',
  ibm: '#1261FE',
};

function provColor(name = '') {
  const k = name.toLowerCase();
  for (const [key, c] of Object.entries(PROVIDER_COLORS)) if (k.includes(key)) return c;
  return '#60a5fa';
}

const INR_RATE = 83.5;

function fmtValue(field, value) {
  if (value === null || value === undefined) return null;
  if (field === 'uptime_sla_pct') return `${Number(value).toFixed(3)}%`;
  if (field === 'min_compute_usd') {
    const inr = value * INR_RATE;
    return inr < 1 ? `₹${inr.toFixed(4)}/hr` : `₹${inr.toFixed(2)}/hr`;
  }
  if (field === 'support_response_min') return value >= 60 ? `${value / 60}h` : `${value} min`;
  if (field === 'rto_hours' || field === 'rpo_hours') return `${value}h`;
  if (field === 'penalty_credit_pct') return `${value}%`;
  return String(value);
}

// ── MetricSelector dropdown ────────────────────────────────────────────────────

function MetricSelector({ selected, onChange }) {
  const [open, setOpen] = useState(false);
  const categories = [...new Set(ALL_METRICS.map(m => m.category))];

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 px-4 py-2 rounded-xl bg-surface-card border border-surface-border text-sm text-slate-300 hover:border-blue-500/40 transition-all"
      >
        <Filter className="w-3.5 h-3.5 text-blue-400" />
        Metrics ({selected.length}/{ALL_METRICS.length})
        {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
      </button>

      <AnimatePresence>
        {open && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
            <motion.div
              initial={{ opacity: 0, y: 6, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 4, scale: 0.97 }}
              transition={{ duration: 0.15 }}
              className="absolute top-full mt-2 right-0 z-50 w-72 bg-[#111827] border border-surface-border rounded-2xl shadow-2xl p-4 space-y-4"
            >
              <div className="flex items-center justify-between">
                <p className="text-xs font-semibold text-white">Select Metrics</p>
                <div className="flex gap-2 text-xs">
                  <button onClick={() => onChange(ALL_METRICS.map(m => m.field))} className="text-blue-400 hover:text-blue-300">All</button>
                  <span className="text-slate-600">·</span>
                  <button onClick={() => onChange([])} className="text-slate-500 hover:text-slate-300">None</button>
                </div>
              </div>
              {categories.map(cat => (
                <div key={cat}>
                  <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">{cat}</p>
                  <div className="space-y-1.5">
                    {ALL_METRICS.filter(m => m.category === cat).map(m => {
                      const on = selected.includes(m.field);
                      return (
                        <label key={m.field} className="flex items-center gap-2.5 cursor-pointer group" onClick={() => onChange(prev => on ? prev.filter(f => f !== m.field) : [...prev, m.field])}>
                          <div className={`w-4 h-4 rounded flex items-center justify-center border transition-all shrink-0 ${on ? 'bg-blue-600 border-blue-600' : 'border-surface-border group-hover:border-blue-500/50'}`}>
                            {on && <Check className="w-2.5 h-2.5 text-white" />}
                          </div>
                          <m.icon className="w-3 h-3 text-slate-500" />
                          <span className="text-xs text-slate-300 group-hover:text-white transition-colors">{m.label}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              ))}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── ComplianceBadges ───────────────────────────────────────────────────────────

function ComplianceBadges({ list }) {
  if (!list?.length) return <span className="text-slate-600 text-xs">—</span>;
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {list.slice(0, 5).map(c => (
        <span key={c} className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-medium">{c}</span>
      ))}
      {list.length > 5 && <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/5 text-slate-500">+{list.length - 5}</span>}
    </div>
  );
}

// ── main ───────────────────────────────────────────────────────────────────────

export default function Compare() {
  const [selected, setSelected] = useState([]);
  const [activeMetrics, setActiveMetrics] = useState(ALL_METRICS.map(m => m.field));

  const { data: providers = [], isLoading: loadingProviders } = useQuery({
    queryKey: ['ingested'],
    queryFn: api.ingestedProviders,
  });

  const metricsParam = activeMetrics.join(',');
  const enabled = selected.length >= 2 && activeMetrics.length > 0;

  const { data: comparison, isLoading: loadingCompare, error } = useQuery({
    queryKey: ['compare', selected.join(','), metricsParam],
    queryFn: () => api.compare(selected.join(','), metricsParam),
    enabled,
    retry: false,
  });

  function toggle(name) {
    setSelected(prev => prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]);
  }

  const rows = comparison?.comparison || [];
  const trophies = comparison?.trophies || {};
  const advantages = comparison?.advantages || {};
  const details = comparison?.details || {};
  const provNames = comparison?.providers || selected;

  const visibleRows = useMemo(() => rows.filter(r => activeMetrics.includes(r.field)), [rows, activeMetrics]);
  const metaDef = (field) => ALL_METRICS.find(m => m.field === field);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white mb-1">Compare</h1>
          <p className="text-slate-500 text-sm">Side-by-side SLA metrics, coverage, and pricing.</p>
        </div>
        {selected.length >= 2 && (
          <MetricSelector selected={activeMetrics} onChange={setActiveMetrics} />
        )}
      </div>

      {/* Provider selector */}
      <Card>
        <p className="text-xs text-slate-500 mb-3 font-semibold uppercase tracking-wider">Select Providers to Compare</p>
        {loadingProviders ? <Spinner /> : providers.length === 0 ? (
          <p className="text-slate-500 text-sm">No providers ingested yet. Go to Add SLA Docs first.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {providers.map(p => {
              const isOn = selected.includes(p.name);
              const color = provColor(p.name);
              return (
                <button
                  key={p.id}
                  onClick={() => toggle(p.name)}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl border text-sm font-medium transition-all"
                  style={isOn
                    ? { backgroundColor: color + '18', borderColor: color + '50', color }
                    : { borderColor: 'rgba(255,255,255,0.08)', color: '#64748b' }
                  }
                >
                  {isOn && <Check className="w-3.5 h-3.5" />}
                  <span className="w-5 h-5 rounded text-[9px] font-black flex items-center justify-center" style={{ backgroundColor: color + '20', color }}>
                    {p.name.slice(0, 2).toUpperCase()}
                  </span>
                  {p.name}
                  <span className="text-[10px] opacity-40">({p.document_count ?? 0})</span>
                </button>
              );
            })}
          </div>
        )}
        {selected.length === 1 && (
          <p className="text-xs text-slate-600 mt-3 flex items-center gap-1">
            <Info className="w-3 h-3" /> Select at least one more provider.
          </p>
        )}
      </Card>

      {loadingCompare && <div className="flex justify-center py-12"><Spinner size="lg" /></div>}
      {error && <Card><p className="text-red-400 text-sm">{error.message}</p></Card>}

      {/* Trophy strip */}
      {comparison && Object.keys(trophies).length > 0 && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex flex-wrap gap-2">
          {Object.entries(trophies)
            .filter(([field]) => activeMetrics.includes(field))
            .map(([field, winner]) => {
              const md = metaDef(field);
              const color = provColor(winner);
              return (
                <div key={field} className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs"
                  style={{ backgroundColor: color + '10', borderColor: color + '30' }}>
                  <Trophy className="w-3 h-3 text-amber-400" />
                  <span className="text-slate-400">{md?.label}</span>
                  <span className="font-semibold" style={{ color }}>{winner}</span>
                </div>
              );
            })}
        </motion.div>
      )}

      {/* Comparison table */}
      {comparison && visibleRows.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-surface-border bg-white/[0.02]">
                  <th className="px-5 py-3.5 text-left text-slate-500 text-xs font-semibold uppercase tracking-wider w-44">Metric</th>
                  {provNames.map(name => {
                    const color = provColor(name);
                    const src = details[name]?.data_source;
                    return (
                      <th key={name} className="px-5 py-3.5 text-left min-w-[150px]">
                        <div className="flex items-center gap-2">
                          <span className="w-6 h-6 rounded-md text-[9px] font-black flex items-center justify-center"
                            style={{ backgroundColor: color + '20', color }}>
                            {name.slice(0, 2).toUpperCase()}
                          </span>
                          <span className="text-white font-semibold">{name}</span>
                        </div>
                        {src === 'curated' && (
                          <span
                            title="Based on publicly documented SLA values, not extracted from ingested documents"
                            className="inline-flex items-center gap-1 text-[9px] text-amber-400/80 mt-0.5"
                          >
                            <Info className="w-2.5 h-2.5" /> curated
                          </span>
                        )}
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row, ri) => {
                  const winner = trophies[row.field];
                  const md = metaDef(row.field);

                  // Compliance row: show badges
                  if (row.field === 'compliance_count') {
                    return (
                      <tr key={row.field} className={`border-b border-surface-border/40 ${ri % 2 !== 0 ? 'bg-white/[0.015]' : ''}`}>
                        <td className="px-5 py-3.5">
                          <div className="flex items-center gap-2 text-slate-400">
                            {md && <md.icon className="w-3.5 h-3.5 shrink-0" />}
                            <span className="text-xs font-medium">{row.label}</span>
                          </div>
                        </td>
                        {provNames.map(name => {
                          const list = details[name]?.compliance || [];
                          const isWinner = name === winner;
                          return (
                            <td key={name} className="px-5 py-3">
                              <div className={`text-xs font-bold mb-1 flex items-center gap-1 ${isWinner ? 'text-emerald-400' : 'text-slate-300'}`}>
                                {isWinner && <Trophy className="w-3 h-3 text-amber-400" />}
                                {list.length} standards
                              </div>
                              <ComplianceBadges list={list} />
                            </td>
                          );
                        })}
                      </tr>
                    );
                  }

                  return (
                    <tr key={row.field} className={`border-b border-surface-border/40 hover:bg-white/[0.025] transition-colors ${ri % 2 !== 0 ? 'bg-white/[0.015]' : ''}`}>
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-2 text-slate-400">
                          {md && <md.icon className="w-3.5 h-3.5 shrink-0" />}
                          <span className="text-xs font-medium">{row.label}</span>
                        </div>
                      </td>
                      {provNames.map(name => {
                        const raw = row[name];
                        const isWinner = name === winner && raw != null;
                        const color = provColor(name);
                        const display = fmtValue(row.field, raw);

                        // Uptime bar
                        const showBar = row.field === 'uptime_sla_pct' && raw != null;
                        const barW = showBar ? Math.max(0, Math.min(100, ((raw - 99) / 1) * 100)) : 0;

                        return (
                          <td key={name} className="px-5 py-4">
                            {display == null ? (
                              <Minus className="w-4 h-4 text-slate-700" />
                            ) : (
                              <div>
                                <div className="flex items-center gap-1.5">
                                  {isWinner && <Trophy className="w-3.5 h-3.5 text-amber-400 shrink-0" />}
                                  <span className="text-sm font-bold" style={isWinner ? { color } : { color: '#cbd5e1' }}>
                                    {display}
                                  </span>
                                </div>
                                {showBar && (
                                  <div className="mt-1.5 h-1 w-full rounded-full bg-white/5">
                                    <motion.div
                                      initial={{ width: 0 }}
                                      animate={{ width: `${barW}%` }}
                                      transition={{ duration: 0.7, ease: 'easeOut' }}
                                      className="h-full rounded-full"
                                      style={{ background: color }}
                                    />
                                  </div>
                                )}
                              </div>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        </motion.div>
      )}

      {/* Provider detail cards */}
      {comparison && provNames.length > 0 && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {provNames.map(name => {
            const color = provColor(name);
            const det = details[name] || {};
            const adv = advantages[name] || [];
            return (
              <motion.div key={name} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                className="p-4 rounded-2xl border bg-surface-card space-y-3"
                style={{ borderColor: color + '25' }}>

                <div className="flex items-center gap-2">
                  <span className="w-7 h-7 rounded-lg text-[10px] font-black flex items-center justify-center"
                    style={{ backgroundColor: color + '20', color }}>
                    {name.slice(0, 2).toUpperCase()}
                  </span>
                  <div>
                    <p className="text-sm font-bold text-white">{name}</p>
                    <p className="text-[9px] text-slate-600">{det.data_source === 'curated' ? 'curated public values' : 'extracted from documents'}</p>
                  </div>
                </div>

                {adv.length > 0 && (
                  <div>
                    <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider mb-1.5">Leads on</p>
                    <div className="flex flex-wrap gap-1">
                      {adv.map(a => (
                        <span key={a} className="text-[10px] px-2 py-0.5 rounded-lg font-medium"
                          style={{ backgroundColor: color + '15', color }}>
                          🏆 {a}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {det.regions?.length > 0 && (
                  <div>
                    <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider mb-1.5">
                      <MapPin className="w-2.5 h-2.5 inline mr-1" />Regions ({det.regions.length})
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {det.regions.slice(0, 5).map(r => (
                        <span key={r} className="text-[9px] px-1.5 py-0.5 rounded bg-white/5 text-slate-400 border border-white/8">{r}</span>
                      ))}
                      {det.regions.length > 5 && <span className="text-[9px] text-slate-600">+{det.regions.length - 5} more</span>}
                    </div>
                  </div>
                )}

                {det.compliance?.length > 0 && (
                  <div>
                    <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider mb-1">
                      <Shield className="w-2.5 h-2.5 inline mr-1" />Compliance
                    </p>
                    <ComplianceBadges list={det.compliance} />
                  </div>
                )}
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Empty state */}
      {selected.length >= 2 && !loadingCompare && !comparison && !error && (
        <Card className="text-center py-12">
          <BarChart2 className="w-10 h-10 text-slate-700 mx-auto mb-3" />
          <p className="text-slate-400 text-sm font-medium mb-1">No data available</p>
          <p className="text-slate-600 text-xs">Ingest SLA documents for the selected providers first.</p>
        </Card>
      )}
    </div>
  );
}
