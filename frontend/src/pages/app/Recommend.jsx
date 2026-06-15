import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, ThumbsUp, ThumbsDown, ChevronDown, ChevronUp, SlidersHorizontal, AlertTriangle, Zap, Globe, CloudDownload } from 'lucide-react';
import toast from 'react-hot-toast';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import Badge from '../../components/ui/Badge';
import ScoreBar from '../../components/ui/ScoreBar';
import Spinner from '../../components/ui/Spinner';
import { api } from '../../api/client';

const WEIGHT_LABELS = {
  uptime: 'Uptime',
  support: 'Support Level',
  penalties: 'SLA Penalties',
  geographic: 'Geographic Coverage',
  security: 'Security & Compliance',
};

const LANGUAGES = [
  { code: 'English',    label: 'English' },
  { code: 'Hindi',      label: 'Hindi (हिंदी)' },
  { code: 'Kannada',    label: 'Kannada (ಕನ್ನಡ)' },
  { code: 'Tamil',      label: 'Tamil (தமிழ்)' },
  { code: 'Telugu',     label: 'Telugu (తెలుగు)' },
  { code: 'Malayalam',  label: 'Malayalam (മലയാളം)' },
  { code: 'Bengali',    label: 'Bengali (বাংলা)' },
  { code: 'Arabic',     label: 'Arabic (العربية)' },
  { code: 'French',     label: 'French (Français)' },
  { code: 'German',     label: 'German (Deutsch)' },
  { code: 'Spanish',    label: 'Spanish (Español)' },
  { code: 'Portuguese', label: 'Portuguese (Português)' },
  { code: 'Chinese',    label: 'Chinese (中文)' },
  { code: 'Japanese',   label: 'Japanese (日本語)' },
  { code: 'Korean',     label: 'Korean (한국어)' },
  { code: 'Italian',    label: 'Italian (Italiano)' },
  { code: 'Russian',    label: 'Russian (Русский)' },
  { code: 'Turkish',    label: 'Turkish (Türkçe)' },
];

const LANGUAGE_NAMES = {
  ar: 'Arabic', fr: 'French', de: 'German', es: 'Spanish', zh: 'Chinese',
  pt: 'Portuguese', hi: 'Hindi', ja: 'Japanese', ko: 'Korean', it: 'Italian',
  nl: 'Dutch', ru: 'Russian', tr: 'Turkish', pl: 'Polish', sv: 'Swedish',
  kn: 'Kannada', ta: 'Tamil', te: 'Telugu', ml: 'Malayalam', bn: 'Bengali',
};

const PROVIDER_COLORS = {
  aws: '#FF9900', azure: '#0078D4', gcp: '#4285F4', oracle: '#F80000', ibm: '#1261FE',
};

function provColor(name) {
  const k = (name || '').toLowerCase();
  for (const [key, c] of Object.entries(PROVIDER_COLORS)) if (k.includes(key)) return c;
  return '#60a5fa';
}

export default function Recommend() {
  const [query, setQuery] = useState('');
  const [showWeights, setShowWeights] = useState(false);
  const [weights, setWeights] = useState({ uptime: 1, support: 1, penalties: 1, geographic: 1, security: 1 });
  const [selectedLang, setSelectedLang] = useState('English');
  const [results, setResults] = useState(null);
  const [feedbackSent, setFeedbackSent] = useState({});

  const { data: ingested = [] } = useQuery({ queryKey: ['ingested'], queryFn: api.ingestedProviders });

  const queryMut = useMutation({
    mutationFn: () => api.query(query, weights, selectedLang),
    onSuccess: (data) => { setResults(data); setFeedbackSent({}); },
    onError: (e) => toast.error(e.message),
  });

  const feedbackMut = useMutation({
    mutationFn: ({ queryId, providerId, signal }) => api.feedback(queryId, providerId, signal),
    onSuccess: (_, vars) => setFeedbackSent(prev => ({ ...prev, [vars.providerId]: vars.signal })),
    onError: (e) => toast.error(e.message),
  });

  const autoFetchMut = useMutation({
    mutationFn: () => api.autoFetch(query.trim() || 'cloud SLA', null),
    onSuccess: (data) => {
      toast.success(data.message || 'SLA documents fetched successfully.');
      if (query.trim()) queryMut.mutate();
    },
    onError: (e) => toast.error(e.message),
  });

  const lowConfidence = results?.low_confidence;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold text-white mb-1">Recommend</h1>
            <p className="text-slate-500 text-sm">Describe your workload to get ranked cloud provider recommendations.</p>
          </div>
          {/* Language selector */}
          <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20 shrink-0">
            <Globe className="w-3.5 h-3.5 text-blue-400 shrink-0" />
            <select
              value={selectedLang}
              onChange={e => setSelectedLang(e.target.value)}
              className="bg-transparent text-blue-300 text-xs font-medium focus:outline-none cursor-pointer"
              title="Explanation language"
            >
              {LANGUAGES.map(l => (
                <option key={l.code} value={l.code} className="bg-slate-900 text-slate-200">
                  {l.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        {selectedLang !== 'English' && (
          <motion.div
            initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}
            className="mt-2 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs w-fit"
          >
            <Globe className="w-3.5 h-3.5 shrink-0" />
            Explanations will be in&nbsp;<span className="font-semibold">{selectedLang}</span>
          </motion.div>
        )}
      </div>

      {ingested.length === 0 && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-sm">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          No SLA documents ingested yet. Add documents in the <strong className="ml-1">Add SLA Docs</strong> tab first.
        </div>
      )}

      {/* Query input */}
      <Card>
        <textarea
          value={query}
          onChange={e => setQuery(e.target.value)}
          rows={4}
          placeholder="e.g. I need a cloud provider with 99.99% uptime SLA for a financial application with strict EU data residency requirements and 24/7 premium support…"
          className="w-full bg-transparent text-slate-200 placeholder:text-slate-600 focus:outline-none text-sm resize-none"
        />
        <div className="flex items-center justify-between mt-4 pt-4 border-t border-surface-border">
          <button
            onClick={() => setShowWeights(w => !w)}
            className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
          >
            <SlidersHorizontal className="w-4 h-4" />
            Weight Factors
            {showWeights ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
          <Button onClick={() => query.trim() && queryMut.mutate()} disabled={!query.trim() || queryMut.isPending}>
            {queryMut.isPending ? <Spinner size="sm" /> : <><Search className="w-4 h-4" /> Recommend</>}
          </Button>
        </div>

        <AnimatePresence>
          {showWeights && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
              <div className="pt-4 grid sm:grid-cols-2 gap-4">
                {Object.entries(WEIGHT_LABELS).map(([key, label]) => (
                  <div key={key}>
                    <div className="flex justify-between text-xs text-slate-400 mb-1">
                      <span>{label}</span>
                      <span className="text-slate-200">{weights[key].toFixed(1)}</span>
                    </div>
                    <input type="range" min="0" max="2" step="0.1" value={weights[key]}
                      onChange={e => setWeights(w => ({ ...w, [key]: parseFloat(e.target.value) }))}
                      className="w-full accent-blue-500" />
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>

      {/* Auto-fetch prompt */}
      {results?.auto_fetch_available && (
        <div className="flex items-start gap-3 p-4 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 text-sm">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p>{results.message || 'No SLA documents have been ingested yet.'}</p>
            <button
              onClick={() => autoFetchMut.mutate()}
              disabled={autoFetchMut.isPending}
              className="mt-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-500/20 border border-blue-500/40 text-blue-300 text-xs font-medium hover:bg-blue-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {autoFetchMut.isPending ? <Spinner size="sm" /> : <CloudDownload className="w-3.5 h-3.5" />}
              Auto-fetch SLA Docs
            </button>
          </div>
        </div>
      )}

      {/* Results */}
      {lowConfidence && (
        <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-sm">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p>Low confidence — no SLA content strongly matched your query. Try refining your query or fetch updated documents.</p>
            <button
              onClick={() => autoFetchMut.mutate()}
              disabled={autoFetchMut.isPending}
              className="mt-3 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-300 text-xs font-medium hover:bg-amber-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {autoFetchMut.isPending ? <Spinner size="sm" /> : <CloudDownload className="w-3.5 h-3.5" />}
              Fetch Updated SLAs
            </button>
          </div>
        </div>
      )}

      {results && (results.rankings || []).length > 0 && (
        <div className="space-y-4">
          {/* Detected language indicator — always shown when results exist */}
          {results.detected_lang && (
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs w-fit">
              <Globe className="w-3.5 h-3.5 shrink-0" />
              Query language:&nbsp;
              <span className="font-semibold">
                {LANGUAGE_NAMES[results.detected_lang] || results.detected_lang.toUpperCase()}
              </span>
              {results.detected_lang !== 'en' && (
                <span className="text-blue-500/60 ml-1">— explanations shown in your language</span>
              )}
            </div>
          )}
          {(results.rankings || []).map((r, i) => {
            const name = r.provider_name;
            const score = r.final_score ?? 0;          // already 0–100
            const color = provColor(name);
            const fbKey = r.provider_id || name;
            return (
              <motion.div key={name} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.08 }}>
                <Card className="relative overflow-hidden">
                  {i === 0 && (
                    <div className="absolute top-0 left-0 right-0 h-0.5" style={{ background: `linear-gradient(90deg, ${color}80, transparent)` }} />
                  )}
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl flex items-center justify-center text-xs font-bold"
                        style={{ backgroundColor: color + '20', border: `1px solid ${color}40`, color }}>
                        {name.slice(0, 3).toUpperCase()}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-semibold text-white">{name}</h3>
                          {i === 0 && <Badge color="blue"><Zap className="w-2.5 h-2.5" /> Best Match</Badge>}
                          {i === 1 && <Badge color="purple">Runner-up</Badge>}
                        </div>
                        {r.meets_uptime != null && (
                          <p className="text-xs text-slate-500">
                            Uptime: {r.sla_uptime_pct != null ? `${r.sla_uptime_pct}%` : '—'}
                            {r.meets_uptime ? ' ✓' : ' ✗'}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="text-2xl font-bold" style={{ color }}>{score.toFixed(1)}</div>
                      <div className="text-xs text-slate-500">/ 100</div>
                    </div>
                  </div>

                  <div className="mt-4 space-y-2">
                    <ScoreBar score={score} max={100} label="Final Score" />
                    {r.topsis_score != null && (
                      <ScoreBar score={r.topsis_score * 100} max={100} label="TOPSIS (SLA metrics)" />
                    )}
                    {r.xgb_score != null && r.xgb_score !== r.topsis_score && (
                      <ScoreBar score={r.xgb_score * 100} max={100} label="XGBoost (learned)" />
                    )}
                    {r.xgb_score != null && r.xgb_score === r.topsis_score && (
                      <div className="text-[10px] text-slate-600 italic pl-0.5">
                        XGBoost = TOPSIS (cold start — needs 100 feedback signals to train)
                      </div>
                    )}
                    {r.cosine_score != null && (
                      <ScoreBar score={r.cosine_score * 100} max={100} label="Semantic Match (query)" />
                    )}
                  </div>

                  {r.compliance_tags?.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1">
                      {r.compliance_tags.map(tag => (
                        <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">{tag}</span>
                      ))}
                    </div>
                  )}

                  {r.explanation && (
                    <div className="mt-3">
                      <p className="text-sm text-slate-400 leading-relaxed">{r.explanation}</p>
                      {results.lang && results.lang !== 'English' && (
                        <div className="flex items-center gap-1 text-[10px] text-blue-400/60 mt-1">
                          <Globe className="w-3 h-3" /> Explained in {results.lang}
                        </div>
                      )}
                    </div>
                  )}

                  <div className="mt-4 flex items-center gap-2">
                    <span className="text-xs text-slate-500 mr-1">Helpful?</span>
                    {(['up', 'down']).map(sig => (
                      <button key={sig} onClick={() => feedbackMut.mutate({ queryId: results.query_id, providerId: fbKey, signal: sig })}
                        className={`p-1.5 rounded-md transition-colors ${feedbackSent[fbKey] === sig ? (sig === 'up' ? 'text-emerald-400 bg-emerald-400/10' : 'text-red-400 bg-red-400/10') : 'text-slate-600 hover:text-slate-300'}`}>
                        {sig === 'up' ? <ThumbsUp className="w-3.5 h-3.5" /> : <ThumbsDown className="w-3.5 h-3.5" />}
                      </button>
                    ))}
                  </div>
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
