import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Bell, FileText, TrendingUp, TrendingDown, FilePlus, AlertTriangle,
  ChevronDown, ChevronUp, ToggleLeft, ToggleRight, Trash2, Plus,
  Mail, Zap, ShieldCheck,
} from 'lucide-react';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import Spinner from '../../components/ui/Spinner';
import { api } from '../../api/client';

// ─── helpers ────────────────────────────────────────────────────────────────

const ALERT_ICONS = {
  NEW_DOCUMENT: FilePlus,
  UPTIME_CHANGE: TrendingUp,
  DOWNTIME_CHANGE: TrendingDown,
  SLA_CHANGE: FileText,
  OTHER: AlertTriangle,
};
const ALERT_COLORS = {
  NEW_DOCUMENT: 'green',
  UPTIME_CHANGE: 'blue',
  DOWNTIME_CHANGE: 'red',
  SLA_CHANGE: 'amber',
  INFO: 'green',
  HIGH: 'red',
  MEDIUM: 'amber',
  LOW: 'slate',
};

function alertColor(type, severity) {
  return ALERT_COLORS[severity] || ALERT_COLORS[type] || 'slate';
}
function alertIcon(type) { return ALERT_ICONS[type] || AlertTriangle; }

function timeAgo(ts) {
  if (!ts) return '';
  const diff = Math.floor((Date.now() - new Date(ts)) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const METRIC_LABELS = {
  uptime_sla_pct: 'Uptime SLA (%)',
  rto_hours: 'RTO (hrs)',
  rpo_hours: 'RPO (hrs)',
  penalty_credit_pct: 'Penalty Credit (%)',
};

// ─── AlertCard ───────────────────────────────────────────────────────────────

function AlertCard({ alert, i }) {
  const [expanded, setExpanded] = useState(false);
  const Icon = alertIcon(alert.change_type);
  const color = alertColor(alert.change_type, alert.severity);

  const iconCls = {
    green: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400',
    blue:  'bg-blue-500/10  border-blue-500/20  text-blue-400',
    red:   'bg-red-500/10   border-red-500/20   text-red-400',
    amber: 'bg-amber-500/10 border-amber-500/20 text-amber-400',
    slate: 'bg-slate-500/10 border-slate-500/20 text-slate-400',
  }[color] || 'bg-slate-500/10 border-slate-500/20 text-slate-400';

  const hasDetail = alert.old_value || alert.new_value;

  return (
    <motion.div
      key={alert.id || i}
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: i * 0.04 }}
    >
      <Card hover className="space-y-0 overflow-hidden">
        <div className="flex items-start gap-4 p-4">
          <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 border ${iconCls}`}>
            <Icon className="w-4 h-4" />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className="text-sm font-semibold text-white">
                {alert.provider_name || 'Unknown'}
              </span>
              <Badge color={color}>
                {alert.change_type?.replace(/_/g, ' ') || 'Alert'}
              </Badge>
              {alert.severity && alert.severity !== 'INFO' && (
                <Badge color={alertColor(null, alert.severity)}>
                  {alert.severity}
                </Badge>
              )}
            </div>
            {alert.affected_clause && (
              <p className="text-sm text-slate-400 line-clamp-2">{alert.affected_clause}</p>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <span className="text-xs text-slate-600">{timeAgo(alert.detected_at)}</span>
            {hasDetail && (
              <button
                onClick={() => setExpanded(v => !v)}
                className="text-slate-600 hover:text-slate-300 transition-colors"
              >
                {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              </button>
            )}
          </div>
        </div>

        <AnimatePresence>
          {expanded && hasDetail && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden border-t border-slate-800"
            >
              <div className="grid grid-cols-2 gap-3 p-4">
                {alert.old_value && (
                  <div>
                    <p className="text-xs font-medium text-slate-500 mb-1">Before</p>
                    <p className="text-xs text-red-300 bg-red-950/30 rounded p-2 whitespace-pre-wrap">
                      {alert.old_value}
                    </p>
                  </div>
                )}
                {alert.new_value && (
                  <div>
                    <p className="text-xs font-medium text-slate-500 mb-1">After</p>
                    <p className="text-xs text-emerald-300 bg-emerald-950/30 rounded p-2 whitespace-pre-wrap">
                      {alert.new_value}
                    </p>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>
    </motion.div>
  );
}

// ─── ThresholdForm ───────────────────────────────────────────────────────────

function ThresholdForm({ providers, onCreated }) {
  const qc = useQueryClient();
  const [email, setEmail]       = useState('');
  const [providerId, setProvId] = useState('');
  const [metric, setMetric]     = useState('uptime_sla_pct');
  const [operator, setOp]       = useState('below');
  const [value, setValue]       = useState('');
  const [open, setOpen]         = useState(false);

  const mut = useMutation({
    mutationFn: () => api.createThreshold({
      email,
      provider_id: providerId || null,
      metric,
      operator,
      threshold_value: parseFloat(value),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['thresholds'] });
      setEmail(''); setProvId(''); setMetric('uptime_sla_pct');
      setOp('below'); setValue('');
      setOpen(false);
      onCreated?.();
    },
  });

  const valid = email && value && !isNaN(parseFloat(value));

  return (
    <div className="border border-slate-800 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-2 px-4 py-3 bg-slate-900 hover:bg-slate-800/60 transition-colors text-left"
      >
        <Plus className="w-4 h-4 text-indigo-400" />
        <span className="text-sm font-medium text-slate-300">Add Threshold Rule</span>
        <span className="ml-auto">{open ? <ChevronUp className="w-4 h-4 text-slate-500" /> : <ChevronDown className="w-4 h-4 text-slate-500" />}</span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="p-4 space-y-3 bg-slate-950/50 border-t border-slate-800">
              {/* email */}
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  Notify email *
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                {/* provider */}
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Provider (optional)</label>
                  <select
                    value={providerId}
                    onChange={e => setProvId(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  >
                    <option value="">All providers</option>
                    {providers.map(p => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>

                {/* metric */}
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Metric *</label>
                  <select
                    value={metric}
                    onChange={e => setMetric(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  >
                    {Object.entries(METRIC_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                </div>

                {/* operator */}
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Condition *</label>
                  <select
                    value={operator}
                    onChange={e => setOp(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                  >
                    <option value="below">Drops below</option>
                    <option value="above">Rises above</option>
                  </select>
                </div>

                {/* value */}
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1">Threshold value *</label>
                  <input
                    type="number"
                    value={value}
                    onChange={e => setValue(e.target.value)}
                    placeholder="e.g. 99.95"
                    step="0.01"
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-1">
                <button
                  onClick={() => setOpen(false)}
                  className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => mut.mutate()}
                  disabled={!valid || mut.isPending}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {mut.isPending ? <Spinner size="sm" /> : <Plus className="w-4 h-4" />}
                  Create rule
                </button>
              </div>
              {mut.isError && (
                <p className="text-xs text-red-400">{mut.error?.message || 'Failed to create rule'}</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── ThresholdRow ────────────────────────────────────────────────────────────

function ThresholdRow({ rule, i }) {
  const qc = useQueryClient();

  const toggleMut = useMutation({
    mutationFn: () => api.toggleThreshold(rule.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['thresholds'] }),
  });

  const deleteMut = useMutation({
    mutationFn: () => api.deleteThreshold(rule.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['thresholds'] }),
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: i * 0.04 }}
    >
      <Card className="flex items-center gap-3 flex-wrap">
        {/* toggle */}
        <button
          onClick={() => toggleMut.mutate()}
          disabled={toggleMut.isPending}
          className="shrink-0 text-slate-400 hover:text-indigo-400 transition-colors"
          title={rule.active ? 'Disable rule' : 'Enable rule'}
        >
          {rule.active
            ? <ToggleRight className="w-6 h-6 text-indigo-400" />
            : <ToggleLeft  className="w-6 h-6 text-slate-600"  />}
        </button>

        {/* info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-white">
              {rule.provider_name || <span className="text-slate-500">All providers</span>}
            </span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
              {METRIC_LABELS[rule.metric] || rule.metric}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              rule.operator === 'below'
                ? 'bg-red-950/40 text-red-400'
                : 'bg-amber-950/40 text-amber-400'
            }`}>
              {rule.operator} {rule.threshold_value}
            </span>
          </div>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-xs text-slate-500 flex items-center gap-1">
              <Mail className="w-3 h-3" /> {rule.email}
            </span>
            {rule.last_triggered_at && (
              <span className="text-xs text-slate-600">
                last triggered {timeAgo(rule.last_triggered_at)}
              </span>
            )}
          </div>
        </div>

        {!rule.active && (
          <span className="text-xs text-slate-600 italic">paused</span>
        )}

        {/* delete */}
        <button
          onClick={() => deleteMut.mutate()}
          disabled={deleteMut.isPending}
          className="shrink-0 text-slate-700 hover:text-red-400 transition-colors"
          title="Delete rule"
        >
          {deleteMut.isPending ? <Spinner size="sm" /> : <Trash2 className="w-4 h-4" />}
        </button>
      </Card>
    </motion.div>
  );
}

// ─── Main ────────────────────────────────────────────────────────────────────

export default function Alerts() {
  const [tab, setTab] = useState('changes');
  const [checkMsg, setCheckMsg] = useState(null);
  const qc = useQueryClient();

  const { data: alerts = [], isLoading: alertsLoading } = useQuery({
    queryKey: ['alerts'],
    queryFn: api.alerts,
    refetchInterval: 30_000,
  });

  const { data: thresholds = [], isLoading: tLoading } = useQuery({
    queryKey: ['thresholds'],
    queryFn: api.thresholds,
  });

  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: api.providers,
  });

  const checkNowMut = useMutation({
    mutationFn: api.checkThresholds,
    onSuccess: (data) => {
      setCheckMsg(`Checked ${data.checked} rules — ${data.triggered} alert(s) sent.`);
      qc.invalidateQueries({ queryKey: ['thresholds'] });
      setTimeout(() => setCheckMsg(null), 5000);
    },
  });

  const tabs = [
    { id: 'changes',    label: 'SLA Changes',     count: alerts.length },
    { id: 'thresholds', label: 'Threshold Rules',  count: thresholds.length },
  ];

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* header */}
      <div className="flex items-center gap-3">
        <Bell className="w-6 h-6 text-amber-400" />
        <div>
          <h1 className="text-2xl font-bold text-white">Alerts</h1>
          <p className="text-slate-500 text-sm">SLA change detection and custom threshold notifications.</p>
        </div>
      </div>

      {/* tabs */}
      <div className="flex gap-1 bg-slate-900 rounded-xl p-1 w-fit">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === t.id
                ? 'bg-indigo-600 text-white'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            {t.label}
            {t.count > 0 && (
              <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                tab === t.id ? 'bg-white/20 text-white' : 'bg-slate-800 text-slate-400'
              }`}>
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── SLA Changes tab ─────────────────────────────────────────────── */}
      {tab === 'changes' && (
        <div className="space-y-3">
          {alertsLoading && <div className="flex justify-center py-12"><Spinner size="lg" /></div>}

          {!alertsLoading && alerts.length === 0 && (
            <Card className="flex flex-col items-center py-16 text-center">
              <ShieldCheck className="w-12 h-12 text-slate-700 mb-4" />
              <p className="text-slate-400 font-medium mb-1">No alerts yet</p>
              <p className="text-slate-600 text-sm">SLA change alerts appear here after weekly re-fetch detects differences.</p>
            </Card>
          )}

          {alerts.map((alert, i) => (
            <AlertCard key={alert.id || i} alert={alert} i={i} />
          ))}
        </div>
      )}

      {/* ── Threshold Rules tab ──────────────────────────────────────────── */}
      {tab === 'thresholds' && (
        <div className="space-y-4">
          {/* Check Now bar */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => checkNowMut.mutate()}
              disabled={checkNowMut.isPending}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 disabled:opacity-40 transition-colors"
            >
              {checkNowMut.isPending ? <Spinner size="sm" /> : <Zap className="w-4 h-4 text-amber-400" />}
              Check Now
            </button>
            {checkMsg && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-sm text-emerald-400"
              >
                {checkMsg}
              </motion.span>
            )}
          </div>

          {/* form */}
          <ThresholdForm providers={providers} />

          {/* list */}
          {tLoading && <div className="flex justify-center py-8"><Spinner size="lg" /></div>}

          {!tLoading && thresholds.length === 0 && (
            <Card className="flex flex-col items-center py-12 text-center">
              <Bell className="w-10 h-10 text-slate-700 mb-3" />
              <p className="text-slate-400 font-medium mb-1">No threshold rules</p>
              <p className="text-slate-600 text-sm">
                Create a rule above to get email alerts when an SLA metric crosses your threshold.
              </p>
            </Card>
          )}

          <div className="space-y-3">
            {thresholds.map((rule, i) => (
              <ThresholdRow key={rule.id} rule={rule} i={i} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
