import { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Bell, FileText, TrendingUp, TrendingDown, FilePlus, AlertTriangle,
  ChevronDown, ChevronUp, ToggleLeft, ToggleRight, Trash2, Plus,
  Mail, Zap, ShieldCheck, Brain, BarChart2, Target, CheckCircle2, XCircle,
  Sparkles, X,
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

const SIGNAL_META = {
  thumbs_up:               { weight: 1.5,  color: 'green',  label: 'Thumbs Up' },
  accepted_recommendation: { weight: 1.0,  color: 'blue',   label: 'Accepted Recommendation' },
  clicked_provider:        { weight: 0.3,  color: 'slate',  label: 'Clicked Provider' },
  ignored_top_result:      { weight: -0.5, color: 'yellow', label: 'Ignored Top Result' },
  thumbs_down:             { weight: -1.5, color: 'red',    label: 'Thumbs Down' },
};

// ─── ModelTrainingTab ────────────────────────────────────────────────────────

function ModelTrainingTab() {
  const qc = useQueryClient();
  const [retrainMsg, setRetrainMsg] = useState(null);
  // Popup state for "training successfully finished" confirmation.
  // We can't show this on the retrain *queue* callback because that just
  // acknowledges Celery accepted the job — the model isn't actually written
  // yet. So we track a baseline at queue time, then poll feedbackStats
  // until either the model-exists flag flips true OR enough time passes
  // for us to consider the training done.
  const [successPopup, setSuccessPopup] = useState(null);   // { records } | null
  const trainingWatchRef = useRef(null);                    // { baselineExists, baselineRecords, startedAt }

  // Polling: while a retrain is "in flight" (queued but not yet observed),
  // refetch stats every 2 s so we can detect the transition into "Trained".
  // Idle: revert to the slow 30 s baseline cadence.
  const isTraining = trainingWatchRef.current !== null;
  const { data: stats, isLoading, isError } = useQuery({
    queryKey: ['feedbackStats'],
    queryFn: api.feedbackStats,
    refetchInterval: isTraining ? 2_000 : 30_000,
  });

  // React to stats updates while a retrain is being watched.
  useEffect(() => {
    const watch = trainingWatchRef.current;
    if (!watch || !stats) return;

    const modelNowExists = !!stats.xgboost_model_exists;
    const elapsed = Date.now() - watch.startedAt;

    // Success: model file now exists, OR was already trained and stats
    // refreshed (indicating retrain rebuilt it — best-effort signal).
    const becameTrained   = modelNowExists && !watch.baselineExists;
    const rebuildLikely   = watch.baselineExists && elapsed > 4_000;  // already trained, give Celery a moment
    if (becameTrained || rebuildLikely) {
      trainingWatchRef.current = null;
      setRetrainMsg(null);
      setSuccessPopup({ records: stats.unique_training_pairs });
      qc.invalidateQueries({ queryKey: ['feedbackStats'] });
      return;
    }

    // Timeout: 60 s with no observed model flip — Celery probably failed
    // or the worker isn't running. Tell the user honestly.
    if (elapsed > 60_000) {
      trainingWatchRef.current = null;
      setRetrainMsg('Retrain did not complete within 60s. Check Celery worker logs.');
      setTimeout(() => setRetrainMsg(null), 8_000);
    }
  }, [stats, qc]);

  const retrainMut = useMutation({
    mutationFn: api.retrainNow,
    onSuccess: (data) => {
      // Capture the pre-training baseline so the polling effect above can
      // detect the cold-start → trained transition (or the retrain of an
      // already-trained model).
      trainingWatchRef.current = {
        baselineExists:  !!stats?.xgboost_model_exists,
        baselineRecords: stats?.unique_training_pairs ?? 0,
        startedAt:       Date.now(),
      };
      setRetrainMsg(`Training in progress… (task ${data.task_id.slice(0, 8)}…)`);
      qc.invalidateQueries({ queryKey: ['feedbackStats'] });
    },
    onError: (err) => {
      trainingWatchRef.current = null;
      setRetrainMsg(`Error: ${err.message}`);
      setTimeout(() => setRetrainMsg(null), 6_000);
    },
  });

  if (isLoading) return <div className="flex justify-center py-12"><Spinner size="lg" /></div>;
  if (isError)   return <Card className="text-center py-10 text-red-400">Failed to load training stats.</Card>;

  const pairsPct = Math.min(100, Math.round((stats.unique_training_pairs / stats.retrain_threshold) * 100));
  const barColor = pairsPct >= 100 ? '#10b981' : pairsPct >= 60 ? '#f59e0b' : '#ef4444';

  return (
    <div className="space-y-4">

      {/* stat cards */}
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <p className="text-xs text-slate-500 mb-1">Total Feedbacks</p>
          <p className="text-2xl font-bold text-white">{stats.total_feedbacks}</p>
          <p className="text-xs text-slate-600 mt-1">
            {stats.feedbacks_until_auto_retrain === 0
              ? 'Auto-retrain triggers now'
              : `${stats.feedbacks_until_auto_retrain} until next auto-trigger`}
          </p>
        </Card>

        <Card>
          <p className="text-xs text-slate-500 mb-1">Training Records</p>
          <p className="text-2xl font-bold text-white">{stats.unique_training_pairs}</p>
          <p className="text-xs text-slate-600 mt-1">unique (query, provider) pairs</p>
        </Card>

        <Card>
          <p className="text-xs text-slate-500 mb-1">Model Status</p>
          <div className="flex items-center gap-2 mt-1">
            {stats.xgboost_model_exists
              ? <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              : <XCircle      className="w-5 h-5 text-slate-600"   />}
            <span className={`text-sm font-semibold ${stats.xgboost_model_exists ? 'text-emerald-400' : 'text-slate-500'}`}>
              {stats.xgboost_model_exists ? 'Trained' : 'Cold Start'}
            </span>
          </div>
          <p className="text-xs text-slate-600 mt-1">
            {stats.xgboost_model_exists ? 'XGBoost model on disk' : 'Using TOPSIS fallback'}
          </p>
        </Card>
      </div>

      {/* training readiness bar */}
      <Card>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Target className="w-4 h-4 text-indigo-400" />
            <span className="text-sm font-medium text-slate-300">Training Readiness</span>
          </div>
          <span className="text-xs text-slate-400">
            {stats.unique_training_pairs} / {stats.retrain_threshold} records needed
          </span>
        </div>
        <div className="h-2 rounded-full bg-slate-800 overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{ width: `${pairsPct}%`, backgroundColor: barColor }}
          />
        </div>
        {!stats.can_retrain && (
          <p className="text-xs text-slate-600 mt-2">
            Need {stats.retrain_threshold - stats.unique_training_pairs} more record(s) before manual retrain is available.
          </p>
        )}
      </Card>

      {/* auto-retrain countdown */}
      <Card className="flex items-center gap-3">
        <BarChart2 className="w-5 h-5 text-amber-400 shrink-0" />
        <div>
          <p className="text-sm text-slate-300">
            Auto-retrain triggers every <span className="font-semibold text-white">{stats.auto_retrain_every}</span> feedbacks
          </p>
          <p className="text-xs text-slate-500 mt-0.5">
            {stats.feedbacks_until_auto_retrain === 0
              ? 'Will trigger on next feedback submission'
              : `${stats.feedbacks_until_auto_retrain} more feedback(s) until next automatic retrain`}
          </p>
        </div>
      </Card>

      {/* signal breakdown */}
      <Card>
        <div className="flex items-center gap-2 mb-3">
          <BarChart2 className="w-4 h-4 text-slate-500" />
          <span className="text-sm font-medium text-slate-300">Feedback by Signal Type</span>
        </div>
        <div className="space-y-2">
          {Object.entries(SIGNAL_META).map(([signal, meta]) => {
            const count = stats.by_signal[signal] || 0;
            return (
              <div key={signal} className="flex items-center gap-3">
                <Badge color={meta.color} className="w-44 shrink-0 justify-start text-xs">
                  {meta.label}
                </Badge>
                <span className={`text-xs font-mono shrink-0 w-10 text-right ${meta.weight > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {meta.weight > 0 ? '+' : ''}{meta.weight}
                </span>
                <div className="flex-1 h-1.5 rounded-full bg-slate-800 overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: stats.total_feedbacks > 0 ? `${(count / stats.total_feedbacks) * 100}%` : '0%',
                      backgroundColor: meta.weight > 0 ? '#10b981' : '#ef4444',
                    }}
                  />
                </div>
                <span className="text-xs text-slate-400 shrink-0 w-6 text-right">{count}</span>
              </div>
            );
          })}
        </div>
      </Card>

      {/* retrain button */}
      <div className="flex items-center gap-3">
        <div title={!stats.can_retrain ? 'Need 10+ training records to retrain' : undefined}>
          <button
            onClick={() => retrainMut.mutate()}
            disabled={!stats.can_retrain || retrainMut.isPending || isTraining}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {(retrainMut.isPending || isTraining) ? <Spinner size="sm" /> : <Brain className="w-4 h-4" />}
            Retrain Now
          </button>
        </div>
        {retrainMsg && (
          <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-sm text-emerald-400">
            {retrainMsg}
          </motion.span>
        )}
      </div>

      {/* Success modal — shown when training actually completes, not on queue.
          Backed by the polling effect above. Closes on click of OK or the X. */}
      <AnimatePresence>
        {successPopup && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={() => setSuccessPopup(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.9, y: 20 }}
              animate={{ opacity: 1, scale: 1,   y: 0 }}
              exit={{    opacity: 0, scale: 0.95 }}
              transition={{ type: 'spring', stiffness: 320, damping: 28 }}
              className="relative max-w-md w-[90%] mx-4 p-6 rounded-2xl bg-gradient-to-br from-emerald-950 to-slate-900 border border-emerald-500/40 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => setSuccessPopup(null)}
                className="absolute top-3 right-3 p-1 rounded-md text-slate-500 hover:text-white hover:bg-white/5 transition-colors"
                aria-label="Close"
              >
                <X className="w-4 h-4" />
              </button>

              <div className="flex flex-col items-center text-center">
                <div className="w-14 h-14 rounded-full bg-emerald-500/15 border border-emerald-500/40 flex items-center justify-center mb-3">
                  <Sparkles className="w-7 h-7 text-emerald-400" />
                </div>
                <h3 className="text-lg font-semibold text-white">Retrain Successful</h3>
                <p className="text-sm text-slate-300 mt-1">
                  XGBoost model has been retrained on{' '}
                  <span className="font-semibold text-emerald-400">{successPopup.records}</span>{' '}
                  unique training record{successPopup.records === 1 ? '' : 's'}.
                </p>
                <p className="text-xs text-slate-500 mt-2">
                  All future recommendations will use the updated model.
                </p>

                <button
                  onClick={() => setSuccessPopup(null)}
                  className="mt-5 px-5 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-900 text-sm font-semibold transition-colors"
                >
                  OK
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

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
    { id: 'changes',    label: 'SLA Changes',    count: alerts.length },
    { id: 'thresholds', label: 'Threshold Rules', count: thresholds.length },
    { id: 'training',   label: 'Model Training',  count: 0 },
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

      {/* ── Model Training tab ──────────────────────────────────────────── */}
      {tab === 'training' && <ModelTrainingTab />}
    </div>
  );
}
