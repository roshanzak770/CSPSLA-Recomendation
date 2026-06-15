import { useState, useRef, useEffect } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Bot, User, ChevronDown, ChevronUp, ExternalLink, Globe } from 'lucide-react';
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
                  {msg.sources.map((s, i) => (
                    <a key={i} href={s.url || '#'} target="_blank" rel="noreferrer"
                      className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors">
                      <ExternalLink className="w-3 h-3" /> {s.title || s.url || `Source ${i+1}`}
                    </a>
                  ))}
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
  const [selectedLang, setSelectedLang] = useState('English');
  const [typing, setTyping] = useState(false);
  const bottomRef = useRef();

  const { data: providers = [] } = useQuery({ queryKey: ['ingested'], queryFn: api.ingestedProviders });

  const askMut = useMutation({
    mutationFn: ({ question, provider, lang }) => api.ask(question, provider || null, lang),
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
    askMut.mutate({ question: q, provider: providerFilter, lang: selectedLang });
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
