import { useState, useRef, useEffect } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Bot, User, ChevronDown, ChevronUp, ExternalLink, Globe, SlidersHorizontal, AlertCircle } from 'lucide-react';
import Spinner from '../../components/ui/Spinner';
import Card from '../../components/ui/Card';
import { api } from '../../api/client';

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

function Message({ msg }) {
  const [showSources, setShowSources] = useState(false);
  const isUser = msg.role === 'user';
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${isUser ? 'bg-blue-600' : 'bg-surface-card border border-surface-border'}`}>
        {isUser ? <User className="w-4 h-4 text-white" /> : <Bot className="w-4 h-4 text-blue-400" />}
      </div>
      <div className={`max-w-[75%] space-y-1 ${isUser ? 'items-end' : ''}`}>
        {/* Heads-up banner from /api/ask — for example "no storage-specific
            SLA found for AWS, showing general AWS SLA". Lets the user know
            the answer used a broader scope than they requested. */}
        {!isUser && msg.info && (
          <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs">
            <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            <span>{msg.info}</span>
          </div>
        )}
        <div className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
          isUser ? 'bg-blue-600 text-white rounded-tr-sm' : 'bg-surface-card border border-surface-border text-slate-200 rounded-tl-sm'
        }`}>
          {msg.content}
        </div>
        {msg.lang && msg.lang !== 'English' && (
          <div className="flex items-center gap-1 text-[10px] text-blue-400/60 mt-0.5 pl-1">
            <Globe className="w-3 h-3" /> Answered in {msg.lang}
          </div>
        )}
        {msg.sources?.length > 0 && (
          <div>
            <button onClick={() => setShowSources(s => !s)}
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors mt-1">
              {showSources ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              {msg.sources.length} source{msg.sources.length > 1 ? 's' : ''}
            </button>
            <AnimatePresence>
              {showSources && (
                <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden mt-1 space-y-1">
                  {msg.sources.map((s, i) => {
                    // Pretty label: shorten long URLs so the pill doesn't
                    // overflow the chat bubble, but keep enough context to
                    // identify the document.
                    const label = (() => {
                      if (s.title) return s.title.length > 70 ? s.title.slice(0, 67) + '…' : s.title;
                      if (s.url)   return s.url.length   > 70 ? s.url.slice(0, 67)   + '…' : s.url;
                      return `${s.provider ?? 'Source'} — page ${s.page ?? '?'}`;
                    })();
                    // If we have a real URL → external anchor that opens in
                    // a new tab. Otherwise → a non-interactive div so a
                    // dead `href="#"` can't scroll the user back to the top
                    // of the page (which previously looked like a "redirect
                    // to fresh chat").
                    return s.url ? (
                      <a key={i} href={s.url} target="_blank" rel="noopener noreferrer"
                        className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors break-all">
                        <ExternalLink className="w-3 h-3 shrink-0" />
                        {label}
                      </a>
                    ) : (
                      <div key={i}
                        className="flex items-center gap-1.5 text-xs text-slate-500"
                        title="No public URL available for this source"
                      >
                        <ExternalLink className="w-3 h-3 shrink-0 opacity-40" />
                        {label}
                      </div>
                    );
                  })}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
    </motion.div>
  );
}

export default function Chat() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: "Hi! Ask me anything about your ingested cloud provider SLA documents. I can compare terms, explain penalties, or help you understand uptime commitments." }
  ]);
  const [input, setInput] = useState('');
  const [providerFilter, setProviderFilter] = useState('');
  // Service-category filter. Only meaningful when a provider is also chosen
  // — backend will narrow the RAG search to chunks tagged with this category
  // and fall back to provider-only with a heads-up note if none exist.
  const [serviceCategory, setServiceCategory] = useState('');
  const [selectedLang, setSelectedLang] = useState('English');
  const [typing, setTyping] = useState(false);
  const bottomRef = useRef();

  const { data: providers = [] } = useQuery({ queryKey: ['ingested'], queryFn: api.ingestedProviders });
  // Service catalog drives the category dropdown — cached aggressively
  // because it's static curated data, not per-tenant.
  const { data: catalogData } = useQuery({
    queryKey: ['serviceCategories'],
    queryFn: api.serviceCategories,
    staleTime: 60 * 60 * 1000,
  });
  const serviceCategoryList = catalogData?.categories || [];

  // Reset the category selector whenever the provider changes — a
  // pairing like (Oracle, serverless) might not exist while (AWS,
  // serverless) does, so don't carry a stale value across providers.
  useEffect(() => { setServiceCategory(''); }, [providerFilter]);

  const askMut = useMutation({
    mutationFn: ({ question, provider, lang, category }) =>
      api.ask(question, provider || null, lang, category || null),
    onMutate: ({ question }) => {
      setMessages(m => [...m, { role: 'user', content: question }]);
      setTyping(true);
    },
    onSuccess: (data, variables) => {
      setTyping(false);
      setMessages(m => [
        ...m,
        {
          role: 'assistant',
          content: data.answer || data.response || 'No answer returned.',
          sources: data.sources || [],
          info:    data.info || null,
          lang: variables.lang,
        },
      ]);
    },
    onError: (e) => {
      setTyping(false);
      setMessages(m => [...m, { role: 'assistant', content: `Error: ${e.message}` }]);
    },
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, typing]);

  function send() {
    const q = input.trim();
    if (!q || askMut.isPending) return;
    setInput('');
    askMut.mutate({ question: q, provider: providerFilter, lang: selectedLang, category: serviceCategory });
  }

  return (
    <div className="max-w-3xl mx-auto flex flex-col h-[calc(100vh-8rem)]">
      {/* Header */}
      <div className="mb-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold text-white">Chat with SLA</h1>
            <p className="text-slate-500 text-sm">Ask questions about ingested SLA documents using RAG.</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Language selector */}
            <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20">
              <Globe className="w-3.5 h-3.5 text-blue-400 shrink-0" />
              <select
                value={selectedLang}
                onChange={e => setSelectedLang(e.target.value)}
                className="bg-transparent text-blue-300 text-xs font-medium focus:outline-none cursor-pointer"
                title="Response language"
              >
                {LANGUAGES.map(l => (
                  <option key={l.code} value={l.code} className="bg-slate-900 text-slate-200">
                    {l.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Provider filter */}
            <select value={providerFilter} onChange={e => setProviderFilter(e.target.value)}
              className="px-3 py-2 rounded-lg bg-surface-card border border-surface-border text-slate-300 text-sm focus:outline-none focus:border-blue-500/50">
              <option value="">All providers</option>
              {providers.map(p => <option key={p.id} value={p.name}>{p.name}</option>)}
            </select>

            {/* Service-category filter — cascade. Only meaningful once a
                provider is chosen; before that, the dropdown stays hidden
                so users aren't presented with a useless control. */}
            {providerFilter && serviceCategoryList.length > 0 && (
              <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
                <SlidersHorizontal className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                <select
                  value={serviceCategory}
                  onChange={e => setServiceCategory(e.target.value)}
                  className="bg-transparent text-indigo-300 text-xs font-medium focus:outline-none cursor-pointer"
                  title={`Narrow Q&A to a specific ${providerFilter} service category`}
                >
                  <option value="" className="bg-slate-900 text-slate-200">Any category</option>
                  {serviceCategoryList.map(cat => (
                    <option key={cat} value={cat} className="bg-slate-900 text-slate-200">
                      {cat.charAt(0).toUpperCase() + cat.slice(1)}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>

        {/* Active language badge */}
        {selectedLang !== 'English' && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-2 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs w-fit"
          >
            <Globe className="w-3.5 h-3.5 shrink-0" />
            Responses will be in&nbsp;<span className="font-semibold">{selectedLang}</span>
          </motion.div>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 py-2 pr-1">
        {messages.map((msg, i) => <Message key={i} msg={msg} />)}
        {typing && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-surface-card border border-surface-border flex items-center justify-center">
              <Bot className="w-4 h-4 text-blue-400" />
            </div>
            <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-surface-card border border-surface-border flex items-center gap-2">
              <div className="flex items-center gap-1">
                {[0, 1, 2].map(i => (
                  <div key={i} className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
                ))}
              </div>
              {selectedLang !== 'English' && (
                <span className="text-[10px] text-slate-600 italic">translating to {selectedLang}…</span>
              )}
            </div>
          </motion.div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="pt-4 border-t border-surface-border">
        <div className="flex gap-3">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
            placeholder={`Ask about SLA terms, uptime, penalties…`}
            className="flex-1 px-4 py-3 rounded-xl bg-surface-card border border-surface-border text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500/50 text-sm"
          />
          <button onClick={send} disabled={!input.trim() || askMut.isPending}
            className="px-4 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white transition-colors">
            {askMut.isPending ? <Spinner size="sm" /> : <Send className="w-4 h-4" />}
          </button>
        </div>
        <p className="text-[10px] text-slate-600 mt-1.5 text-center">
          Answering in <span className="text-blue-400/70">{selectedLang}</span> · powered by Groq llama-3.1-8b
        </p>
      </div>
    </div>
  );
}
