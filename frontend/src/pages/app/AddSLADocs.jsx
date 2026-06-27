import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Upload, Globe, FileText, Link2, Type, Trash2,
  Search, Check, X, CloudDownload, AlertCircle, FileDown,
  Sparkles, ChevronDown, ChevronUp,
} from 'lucide-react';
import toast from 'react-hot-toast';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import Spinner from '../../components/ui/Spinner';
import { api } from '../../api/client';

const PROVIDERS = ['AWS', 'Azure', 'GCP', 'Oracle', 'IBM'];
const UPLOAD_MODES = [
  { id: 'pdf', icon: FileText, label: 'PDF' },
  { id: 'url', icon: Link2, label: 'URL' },
  { id: 'text', icon: Type, label: 'Text' },
];

function SummaryPanel({ summary, metrics, onClose }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
      className="mt-2 p-4 rounded-xl bg-blue-500/5 border border-blue-500/20 space-y-3"
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-blue-400 uppercase tracking-wider flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5" /> AI-Parsed SLA Summary
        </span>
        <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {metrics && Object.keys(metrics).length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {metrics.uptime_sla_pct != null && (
            <div className="px-3 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
              <p className="text-[10px] text-emerald-400/70 uppercase">Uptime SLA</p>
              <p className="text-sm font-bold text-emerald-400">{metrics.uptime_sla_pct}%</p>
            </div>
          )}
          {metrics.rto_hours != null && (
            <div className="px-3 py-2 rounded-lg bg-blue-500/10 border border-blue-500/20">
              <p className="text-[10px] text-blue-400/70 uppercase">RTO</p>
              <p className="text-sm font-bold text-blue-400">{metrics.rto_hours} hrs</p>
            </div>
          )}
          {metrics.rpo_hours != null && (
            <div className="px-3 py-2 rounded-lg bg-blue-500/10 border border-blue-500/20">
              <p className="text-[10px] text-blue-400/70 uppercase">RPO</p>
              <p className="text-sm font-bold text-blue-400">{metrics.rpo_hours} hrs</p>
            </div>
          )}
          {metrics.penalty_credit_pct != null && (
            <div className="px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20">
              <p className="text-[10px] text-amber-400/70 uppercase">Penalty Credit</p>
              <p className="text-sm font-bold text-amber-400">{metrics.penalty_credit_pct}%</p>
            </div>
          )}
        </div>
      )}

      {metrics?.compliance?.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {metrics.compliance.map(c => (
            <span key={c} className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">{c}</span>
          ))}
        </div>
      )}

      <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">{summary}</p>
    </motion.div>
  );
}

// Max PDF size users can upload through the browser. The backend enforces
// the same ceiling — keep both numbers in sync.
// 50 MB allows multi-language master SLAs (e.g. Microsoft Online Services SLA
// in all languages, which can hit ~30 MB) without rejecting legitimate uploads.
const MAX_PDF_MB = 50;
const MAX_PDF_BYTES = MAX_PDF_MB * 1024 * 1024;

export default function AddSLADocs() {
  const [section, setSection] = useState('upload');
  const [provider, setProvider] = useState('');
  const [uploadMode, setUploadMode] = useState('pdf');
  const [urlInput, setUrlInput] = useState('');
  const [textInput, setTextInput] = useState('');
  const [textTitle, setTextTitle] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [selectedUrls, setSelectedUrls] = useState([]);
  const [ingestStatus, setIngestStatus] = useState({});
  const [searchInfo, setSearchInfo] = useState('');
  const [summaries, setSummaries] = useState({});   // url → {summary, metrics}
  const [parsingSummary, setParsingSummary] = useState({}); // url → bool
  const fileRef = useRef();
  const qc = useQueryClient();

  const { data: ingested = [], isLoading: loadingProviders } = useQuery({
    queryKey: ['ingested'],
    queryFn: api.ingestedProviders,
  });

  const uploadPDF = useMutation({
    mutationFn: ({ prov, file }) => api.uploadPDF(prov, file),
    onSuccess: () => { toast.success('PDF ingested successfully'); qc.invalidateQueries(['ingested']); },
    onError: (e) => toast.error(e.message),
  });
  const ingestURL = useMutation({
    mutationFn: ({ prov, url }) => api.ingestURL(prov, url),
    onSuccess: () => { toast.success('URL ingested'); qc.invalidateQueries(['ingested']); setUrlInput(''); },
    onError: (e) => toast.error(e.message),
  });
  const ingestText = useMutation({
    mutationFn: ({ prov, text, title }) => api.ingestText(prov, text, title),
    onSuccess: () => { toast.success('Text ingested'); qc.invalidateQueries(['ingested']); setTextInput(''); setTextTitle(''); },
    onError: (e) => toast.error(e.message),
  });
  const deleteProv = useMutation({
    mutationFn: (id) => api.deleteProvider(id),
    onSuccess: () => { toast.success('Provider removed'); qc.invalidateQueries(['ingested']); },
    onError: (e) => toast.error(e.message),
  });

  const searchMut = useMutation({
    mutationFn: ({ prov, query }) => {
      const q = query.trim() || (prov ? `${prov} service level agreement SLA` : 'cloud SLA');
      return api.searchSLA(q, 10);
    },
    onSuccess: (data) => {
      setSearchResults(data.results || []);
      setSearchInfo(data.info || '');
      setSelectedUrls([]);
      setIngestStatus({});
      setSummaries({});
    },
    onError: (e) => toast.error(e.message),
  });

  const autoFetch = useMutation({
    mutationFn: ({ prov, query }) => api.autoFetch(query.trim() || `${prov} SLA`, prov),
    onSuccess: () => { toast.success('Auto-fetch complete'); qc.invalidateQueries(['ingested']); },
    onError: (e) => toast.error(e.message),
  });

  async function handleIngestSelected() {
    if (!provider || selectedUrls.length === 0) return;
    const statuses = {};
    for (const url of selectedUrls) {
      // Defensive: skip empty/whitespace entries instead of sending them and
      // collecting a 422 — backend requires a non-empty URL.
      if (!url || !url.trim()) {
        statuses[url || '(empty)'] = 'skipped — empty URL';
        continue;
      }
      try {
        await api.ingestURL(provider, url.trim());
        statuses[url] = 'ok';
      } catch (e) {
        statuses[url] = e.message;
      }
    }
    setIngestStatus(statuses);
    qc.invalidateQueries(['ingested']);
    const failed = Object.values(statuses).filter(v => v !== 'ok').length;
    if (failed === 0) toast.success('All URLs ingested');
    else toast.error(`${failed} URL(s) failed`);
  }

  async function handleParseWeb(url) {
    if (!provider) { toast.error('Select a provider first'); return; }
    setParsingSummary(p => ({ ...p, [url]: true }));
    try {
      const data = await api.parseWebSLA(url, provider);
      if (data.error) {
        toast.error(data.error);
      } else {
        setSummaries(s => ({ ...s, [url]: { summary: data.summary, metrics: data.metrics } }));
        if (data.ingested) {
          qc.invalidateQueries(['ingested']);
          setIngestStatus(s => ({ ...s, [url]: 'ok' }));
          toast.success(`Parsed & ingested ${data.chunks_created} chunks`);
        }
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setParsingSummary(p => ({ ...p, [url]: false }));
    }
  }

  function tryUploadPDF(file) {
    if (!provider) { toast.error('Select a provider first'); return; }
    if (!file) return;
    if (file.size > MAX_PDF_BYTES) {
      const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
      toast.error(`PDF is ${sizeMB} MB — max allowed is ${MAX_PDF_MB} MB.`);
      return;
    }
    uploadPDF.mutate({ prov: provider, file });
  }

  function handleDrop(e) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    tryUploadPDF(file);
  }

  const canSearch = provider || searchQuery.trim();

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white mb-1">Add SLA Docs</h1>
        <p className="text-slate-500 text-sm">Upload documents or search official cloud provider SLA sites.</p>
      </div>

      {/* Section toggle */}
      <div className="flex gap-1 p-1 bg-surface-card border border-surface-border rounded-xl w-fit">
        {[
          { id: 'upload', icon: Upload, label: 'Upload / Paste' },
          { id: 'search', icon: Globe, label: 'Search Web' },
        ].map(({ id, icon: Icon, label }) => (
          <button
            key={id}
            onClick={() => setSection(id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              section === id ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Icon className="w-4 h-4" /> {label}
          </button>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <AnimatePresence mode="wait">
            {section === 'upload' ? (
              <motion.div key="upload" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }} className="space-y-4">
                {/* Provider selector */}
                <Card>
                  <p className="text-xs text-slate-500 mb-3 font-medium uppercase tracking-wider">Select Provider</p>
                  <div className="flex flex-wrap gap-2">
                    {PROVIDERS.map(p => (
                      <button key={p} onClick={() => setProvider(p)}
                        className={`px-3 py-1.5 rounded-lg text-sm border transition-all ${
                          provider === p ? 'bg-blue-600/20 border-blue-500/50 text-blue-300' : 'border-surface-border text-slate-400 hover:text-white hover:border-slate-600'
                        }`}>
                        {p}
                      </button>
                    ))}
                    <input placeholder="Other provider…"
                      value={PROVIDERS.includes(provider) ? '' : provider}
                      onChange={e => setProvider(e.target.value)}
                      className="px-3 py-1.5 rounded-lg text-sm border border-surface-border bg-transparent text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50 w-32" />
                  </div>
                </Card>

                {/* Mode tabs */}
                <div className="flex gap-1 p-1 bg-surface-card border border-surface-border rounded-lg w-fit">
                  {UPLOAD_MODES.map(({ id, icon: Icon, label }) => (
                    <button key={id} onClick={() => setUploadMode(id)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-all ${uploadMode === id ? 'bg-white/10 text-white' : 'text-slate-500 hover:text-white'}`}>
                      <Icon className="w-3.5 h-3.5" />{label}
                    </button>
                  ))}
                </div>

                {uploadMode === 'pdf' && (
                  <div onDrop={handleDrop} onDragOver={e => e.preventDefault()}
                    onClick={() => fileRef.current?.click()}
                    className="border-2 border-dashed border-surface-border rounded-xl p-12 text-center cursor-pointer hover:border-blue-500/40 transition-colors group">
                    <Upload className="w-8 h-8 text-slate-600 mx-auto mb-3 group-hover:text-blue-400 transition-colors" />
                    <p className="text-slate-400 text-sm">Drag & drop PDF here, or <span className="text-blue-400">click to browse</span></p>
                    <p className="text-slate-600 text-xs mt-1">PDF files only · Max {MAX_PDF_MB} MB</p>
                    <input ref={fileRef} type="file" accept=".pdf" hidden
                      onChange={e => { const f = e.target.files?.[0]; tryUploadPDF(f); e.target.value = ''; }} />
                    {uploadPDF.isPending && <Spinner className="mx-auto mt-3" />}
                  </div>
                )}

                {uploadMode === 'url' && (
                  <div className="space-y-2">
                    {!provider && (
                      <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs w-fit">
                        <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                        Select a provider above before ingesting a URL.
                      </div>
                    )}
                    <div className="flex gap-2">
                      <input value={urlInput} onChange={e => setUrlInput(e.target.value)}
                        placeholder="https://docs.provider.com/sla.html"
                        className="flex-1 px-4 py-2.5 rounded-lg bg-surface-card border border-surface-border text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50 text-sm" />
                      <Button
                        onClick={() => {
                          const trimmed = urlInput.trim();
                          if (!provider) { toast.error('Select a provider first'); return; }
                          if (!trimmed)  { toast.error('Paste a URL first'); return; }
                          ingestURL.mutate({ prov: provider, url: trimmed });
                        }}
                        disabled={ingestURL.isPending}>
                        {ingestURL.isPending ? <Spinner size="sm" /> : 'Ingest'}
                      </Button>
                    </div>
                  </div>
                )}

                {uploadMode === 'text' && (
                  <div className="space-y-3">
                    <input value={textTitle} onChange={e => setTextTitle(e.target.value)}
                      placeholder="Document title…"
                      className="w-full px-4 py-2.5 rounded-lg bg-surface-card border border-surface-border text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50 text-sm" />
                    <textarea value={textInput} onChange={e => setTextInput(e.target.value)}
                      rows={8} placeholder="Paste SLA text here…"
                      className="w-full px-4 py-2.5 rounded-lg bg-surface-card border border-surface-border text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50 text-sm resize-none" />
                    <Button onClick={() => provider && textInput && ingestText.mutate({ prov: provider, text: textInput, title: textTitle })}
                      disabled={!provider || !textInput || ingestText.isPending}>
                      {ingestText.isPending ? <Spinner size="sm" /> : 'Ingest Text'}
                    </Button>
                  </div>
                )}
              </motion.div>

            ) : (
              <motion.div key="search" initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -10 }} className="space-y-4">
                <Card className="space-y-3">
                  <p className="text-xs text-slate-500 font-medium uppercase tracking-wider">Search for SLA Documents</p>

                  {/* Requirement input */}
                  <input
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && canSearch && searchMut.mutate({ prov: provider, query: searchQuery })}
                    placeholder="Describe your requirement or just pick a provider below… (e.g. GCP 99.99% uptime GDPR)"
                    className="w-full px-4 py-2.5 rounded-lg bg-surface border border-surface-border text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50 text-sm"
                  />

                  {/* Provider chips + actions */}
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="flex flex-wrap gap-1.5 flex-1">
                      {PROVIDERS.map(p => (
                        <button key={p} onClick={() => setProvider(prev => prev === p ? '' : p)}
                          className={`px-2.5 py-1 rounded-md text-xs border transition-all ${
                            provider === p ? 'bg-blue-600/20 border-blue-500/50 text-blue-300' : 'border-surface-border text-slate-500 hover:text-white hover:border-slate-600'
                          }`}>
                          {p}
                        </button>
                      ))}
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <Button onClick={() => canSearch && searchMut.mutate({ prov: provider, query: searchQuery })}
                        disabled={!canSearch || searchMut.isPending}>
                        {searchMut.isPending ? <Spinner size="sm" /> : <><Search className="w-4 h-4" /> Search</>}
                      </Button>
                      <Button variant="secondary"
                        onClick={() => canSearch && autoFetch.mutate({ prov: provider, query: searchQuery })}
                        disabled={!canSearch || autoFetch.isPending}
                        title="Auto-fetch and ingest top results">
                        {autoFetch.isPending ? <Spinner size="sm" /> : <><CloudDownload className="w-4 h-4" /> Auto</>}
                      </Button>
                    </div>
                  </div>

                  {searchInfo && (
                    <p className="text-xs text-amber-400 flex items-center gap-1.5">
                      <AlertCircle className="w-3.5 h-3.5 shrink-0" /> {searchInfo}
                    </p>
                  )}

                  {/* Tip shown whenever any HTML/WEB result exists */}
                  {searchResults.some(r => !r.is_pdf) && (
                    <p className="text-xs text-blue-400/70 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 shrink-0" />
                      Some results are web pages, not downloadable PDFs. Use <strong className="text-blue-400 mx-0.5">Parse & Summarise</strong> on any <span className="text-blue-400 font-medium">WEB</span> result to extract and ingest the SLA content automatically.
                    </p>
                  )}
                </Card>

                {/* Results */}
                {searchResults.length > 0 && (
                  <Card className="space-y-3">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium text-white">{searchResults.length} results found</p>
                      {selectedUrls.length > 0 && (
                        <Button size="sm" onClick={handleIngestSelected}>
                          Ingest Selected ({selectedUrls.length})
                        </Button>
                      )}
                    </div>

                    <div className="space-y-2 max-h-[32rem] overflow-y-auto pr-1">
                      {searchResults.map((r) => {
                        const url = r.url || r.href || r.link;
                        const checked = selectedUrls.includes(url);
                        const status = ingestStatus[url];
                        const isPdf = r.is_pdf;
                        const summary = summaries[url];
                        const parsing = parsingSummary[url];

                        return (
                          <div key={url} className={`rounded-xl border transition-colors ${checked ? 'border-blue-500/30 bg-blue-600/5' : 'border-surface-border'}`}>
                            <div className="flex items-start gap-3 p-3">
                              <input type="checkbox" checked={checked}
                                onChange={e => setSelectedUrls(prev => e.target.checked ? [...prev, url] : prev.filter(u => u !== url))}
                                className="mt-1 accent-blue-500 shrink-0" />

                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                                  {/* PDF or WEB badge */}
                                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium border ${
                                    isPdf
                                      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                                      : 'bg-blue-500/10 border-blue-500/30 text-blue-400'
                                  }`}>
                                    {isPdf ? <span className="flex items-center gap-0.5"><FileDown className="w-2.5 h-2.5" /> PDF</span> : <span className="flex items-center gap-0.5"><Globe className="w-2.5 h-2.5" /> WEB</span>}
                                  </span>
                                  {r.relevance_score != null && (
                                    <span className="text-[10px] text-slate-600">score {r.relevance_score}</span>
                                  )}
                                </div>
                                <p className="text-sm text-slate-200 truncate">{r.title || url}</p>
                                <p className="text-xs text-slate-500 truncate">{url}</p>
                                {r.snippet && (
                                  <p className="text-xs text-slate-600 mt-1 line-clamp-2">{r.snippet}</p>
                                )}
                              </div>

                              <div className="flex items-center gap-1.5 shrink-0">
                                {status === 'ok' && <Check className="w-4 h-4 text-emerald-400" />}
                                {status && status !== 'ok' && (
                                  <span className="text-xs text-red-400 flex items-center gap-1">
                                    <X className="w-3 h-3" /> Failed
                                  </span>
                                )}
                                {/* Parse & Summarise button — shown for all results */}
                                <button
                                  onClick={() => summary ? setSummaries(s => { const n = { ...s }; delete n[url]; return n; }) : handleParseWeb(url)}
                                  disabled={parsing}
                                  className="flex items-center gap-1 px-2 py-1 rounded-md text-xs border border-blue-500/30 text-blue-400 hover:bg-blue-500/10 transition-colors disabled:opacity-50"
                                  title={isPdf ? 'Parse & summarise PDF' : 'Fetch page, extract SLA, and summarise'}
                                >
                                  {parsing ? <Spinner size="sm" /> : <Sparkles className="w-3 h-3" />}
                                  {parsing ? 'Parsing…' : summary ? 'Hide' : 'Parse & Summarise'}
                                </button>
                              </div>
                            </div>

                            {/* Inline summary panel */}
                            <AnimatePresence>
                              {summary && (
                                <div className="px-3 pb-3">
                                  <SummaryPanel
                                    summary={summary.summary}
                                    metrics={summary.metrics}
                                    onClose={() => setSummaries(s => { const n = { ...s }; delete n[url]; return n; })}
                                  />
                                </div>
                              )}
                            </AnimatePresence>
                          </div>
                        );
                      })}
                    </div>
                  </Card>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Right: ingested providers */}
        <div>
          <Card className="sticky top-0">
            <p className="text-sm font-semibold text-white mb-3">Ingested Providers</p>
            {loadingProviders ? (
              <Spinner className="mx-auto" />
            ) : ingested.length === 0 ? (
              <p className="text-slate-500 text-sm text-center py-4">No documents yet.</p>
            ) : (
              <div className="space-y-2">
                {ingested.map((p) => (
                  <div key={p.id} className="flex items-center justify-between p-2.5 rounded-lg bg-surface border border-surface-border">
                    <div>
                      <p className="text-sm text-white font-medium">{p.name}</p>
                      <p className="text-xs text-slate-500">{p.document_count ?? 0} docs</p>
                    </div>
                    <button onClick={() => deleteProv.mutate(p.id)}
                      className="p-1.5 rounded-md text-slate-600 hover:text-red-400 hover:bg-red-400/10 transition-colors">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
