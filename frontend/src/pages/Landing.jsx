import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence, useScroll, useTransform } from 'framer-motion';
import {
  Cloud, Brain, BarChart3, MessageSquare, Bell, DollarSign,
  ArrowRight, ChevronLeft, ChevronRight, Search, Zap,
  Upload, Lightbulb, Shield, Activity, Database, Check,
  Trophy, Send, Bot, User, TrendingUp, FilePlus, Menu, X,
  Star, FileText, Globe,
} from 'lucide-react';

// ─── Mini UI Previews ─────────────────────────────────────────────────────────

function RecommendPreview() {
  const items = [
    { name: 'AWS', score: 9.2, color: '#FF9900', uptime: '99.99%', badge: 'Best Match' },
    { name: 'Azure', score: 8.7, color: '#0078D4', uptime: '99.95%' },
    { name: 'GCP', score: 8.1, color: '#4285F4', uptime: '99.95%' },
  ];
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5 border border-white/8 mb-3">
        <Search className="w-3 h-3 text-blue-400 shrink-0" />
        <span className="text-[10px] text-slate-400 truncate">99.99% uptime, EU region, fintech compliance…</span>
      </div>
      {items.map((p, i) => (
        <div key={p.name}
          className={`flex items-center gap-2.5 p-2.5 rounded-xl border transition-all ${
            i === 0 ? 'border-blue-500/40 bg-blue-600/10' : 'border-white/6 bg-white/3'
          }`}>
          <div className="w-7 h-7 rounded-lg flex items-center justify-center text-[9px] font-bold shrink-0"
            style={{ backgroundColor: p.color + '25', border: `1px solid ${p.color}50`, color: p.color }}>
            {p.name.slice(0, 2)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[11px] text-white font-semibold">{p.name}</span>
              <span className="text-[11px] font-bold" style={{ color: p.color }}>{p.score}</span>
            </div>
            <div className="h-1 rounded-full bg-white/10 overflow-hidden">
              <motion.div className="h-full rounded-full"
                initial={{ width: 0 }} animate={{ width: `${(p.score / 10) * 100}%` }}
                transition={{ delay: i * 0.15 + 0.3, duration: 0.8 }}
                style={{ backgroundColor: p.color }} />
            </div>
          </div>
          {p.badge && (
            <span className="text-[8px] px-1.5 py-0.5 rounded-full bg-blue-600/30 text-blue-300 border border-blue-500/30 shrink-0">
              {p.badge}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

function ComparePreview() {
  const headers = ['Metric', 'AWS', 'Azure', 'GCP'];
  const rows = [
    { label: 'Uptime SLA', vals: ['99.99%', '99.95%', '99.95%'], winner: 0 },
    { label: 'Support', vals: ['24/7', '24/7', 'Business'], winner: 0 },
    { label: 'Credits', vals: '10-30%', winner: -1 },
    { label: 'Regions', vals: ['33', '60+', '35+'], winner: 1 },
  ];
  return (
    <div className="overflow-hidden rounded-lg border border-white/8">
      <table className="w-full text-[10px]">
        <thead>
          <tr className="border-b border-white/8 bg-white/5">
            {headers.map(h => (
              <th key={h} className="px-2 py-2 text-left text-slate-400 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} className="border-b border-white/5 hover:bg-white/3 transition-colors">
              <td className="px-2 py-1.5 text-slate-500">{row.label}</td>
              {Array.isArray(row.vals) ? row.vals.map((v, ci) => (
                <td key={ci} className={`px-2 py-1.5 font-medium ${
                  row.winner === ci ? 'text-emerald-400' : 'text-slate-300'
                }`}>
                  {row.winner === ci && <Trophy className="w-2.5 h-2.5 inline mr-0.5 text-amber-400" />}
                  {v}
                </td>
              )) : (
                <td colSpan={3} className="px-2 py-1.5 text-slate-400 text-center">{row.vals}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChatPreview() {
  const msgs = [
    { role: 'user', text: "What's AWS's SLA for EC2?" },
    { role: 'bot', text: 'AWS guarantees 99.99% monthly uptime for EC2. Service credits: 10% for <99.99%, 30% for <99.0%.' },
    { role: 'user', text: 'How does Azure compare?' },
  ];
  return (
    <div className="space-y-2.5">
      {msgs.map((m, i) => (
        <motion.div key={i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.2 }}
          className={`flex items-end gap-1.5 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
          <div className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 ${
            m.role === 'user' ? 'bg-blue-600' : 'bg-surface-card border border-white/10'
          }`}>
            {m.role === 'user' ? <User className="w-2.5 h-2.5 text-white" /> : <Bot className="w-2.5 h-2.5 text-blue-400" />}
          </div>
          <div className={`max-w-[80%] px-2.5 py-1.5 rounded-xl text-[10px] leading-relaxed ${
            m.role === 'user'
              ? 'bg-blue-600 text-white rounded-br-sm'
              : 'bg-white/8 border border-white/10 text-slate-200 rounded-bl-sm'
          }`}>
            {m.text}
          </div>
        </motion.div>
      ))}
      <div className="flex items-center gap-1 ml-6">
        {[0, 1, 2].map(i => (
          <motion.div key={i} className="w-1.5 h-1.5 rounded-full bg-slate-600"
            animate={{ y: [-2, 2, -2] }}
            transition={{ delay: i * 0.15, duration: 0.8, repeat: Infinity }} />
        ))}
      </div>
    </div>
  );
}

function AlertsPreview() {
  const alerts = [
    { icon: TrendingUp, color: '#3b82f6', provider: 'AWS', msg: 'EC2 uptime SLA increased to 99.99%', tag: 'UPTIME_CHANGE', time: '2m ago' },
    { icon: FilePlus, color: '#10b981', provider: 'Azure', msg: 'New Blob Storage SLA document ingested', tag: 'NEW_DOCUMENT', time: '1h ago' },
    { icon: FileText, color: '#f59e0b', provider: 'GCP', msg: 'Compute Engine terms updated', tag: 'SLA_CHANGE', time: '3h ago' },
  ];
  return (
    <div className="space-y-2">
      {alerts.map((a, i) => (
        <motion.div key={i} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}
          transition={{ delay: i * 0.15 }}
          className="flex items-start gap-2.5 p-2.5 rounded-xl bg-white/4 border border-white/6">
          <div className="w-6 h-6 rounded-lg flex items-center justify-center shrink-0"
            style={{ backgroundColor: a.color + '20', border: `1px solid ${a.color}40` }}>
            <a.icon className="w-3 h-3" style={{ color: a.color }} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 mb-0.5">
              <span className="text-[10px] text-white font-medium">{a.provider}</span>
              <span className="text-[8px] px-1 py-0.5 rounded-full border"
                style={{ backgroundColor: a.color + '15', borderColor: a.color + '40', color: a.color }}>
                {a.tag.replace(/_/g, ' ')}
              </span>
            </div>
            <p className="text-[10px] text-slate-400 truncate">{a.msg}</p>
          </div>
          <span className="text-[9px] text-slate-600 shrink-0">{a.time}</span>
        </motion.div>
      ))}
    </div>
  );
}

function PricingPreview() {
  const services = [
    { provider: 'AWS', color: '#FF9900', service: 'EC2 t3.medium', price: '$0.0416', unit: '/hr', region: 'us-east-1' },
    { provider: 'Azure', color: '#0078D4', service: 'D2s v3', price: '$0.0480', unit: '/hr', region: 'eastus' },
    { provider: 'GCP', color: '#4285F4', service: 'e2-standard-2', price: '$0.0385', unit: '/hr', region: 'us-central1' },
  ];
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 gap-1 text-[9px] text-slate-500 font-medium pb-1 border-b border-white/6 px-1">
        <span>Provider</span><span>Service</span><span className="text-right">Price</span>
      </div>
      {services.map((s, i) => (
        <motion.div key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.1 }}
          className="flex items-center gap-2 p-2 rounded-lg bg-white/4 border border-white/6">
          <div className="w-6 h-6 rounded-md flex items-center justify-center text-[9px] font-bold shrink-0"
            style={{ backgroundColor: s.color + '25', border: `1px solid ${s.color}40`, color: s.color }}>
            {s.provider.slice(0, 2)}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-[10px] text-slate-300 font-medium truncate">{s.service}</p>
            <p className="text-[9px] text-slate-600">{s.region}</p>
          </div>
          <div className="text-right shrink-0">
            <span className="text-[11px] font-bold text-emerald-400">{s.price}</span>
            <span className="text-[9px] text-slate-600">{s.unit}</span>
          </div>
        </motion.div>
      ))}
    </div>
  );
}

// ─── Carousel Config ──────────────────────────────────────────────────────────

const SLIDES = [
  { id: 'recommend', icon: Brain, title: 'AI Recommendations', subtitle: 'Rank providers against your real requirements', color: '#3b82f6', Preview: RecommendPreview },
  { id: 'compare', icon: BarChart3, title: 'SLA Comparison', subtitle: 'Side-by-side terms with winner highlighting', color: '#a855f7', Preview: ComparePreview },
  { id: 'chat', icon: MessageSquare, title: 'AI Chat Interface', subtitle: 'Ask anything in natural language', color: '#10b981', Preview: ChatPreview },
  { id: 'alerts', icon: Bell, title: 'Change Alerts', subtitle: 'Real-time SLA change notifications', color: '#f59e0b', Preview: AlertsPreview },
  { id: 'pricing', icon: DollarSign, title: 'Pricing Intelligence', subtitle: 'Compare costs alongside SLA commitments', color: '#06b6d4', Preview: PricingPreview },
];

// ─── Feature Carousel Component ───────────────────────────────────────────────

function FeatureCarousel() {
  const [active, setActive] = useState(0);
  const [dir, setDir] = useState(1);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused) return;
    const id = setInterval(() => {
      setDir(1);
      setActive(a => (a + 1) % SLIDES.length);
    }, 3500);
    return () => clearInterval(id);
  }, [paused]);

  function go(i) {
    setDir(i > active ? 1 : -1);
    setActive(i);
  }
  function prev() { setDir(-1); setActive(a => (a - 1 + SLIDES.length) % SLIDES.length); }
  function next() { setDir(1); setActive(a => (a + 1) % SLIDES.length); }

  const slide = SLIDES[active];

  return (
    <div
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      className="relative w-full max-w-[420px] mx-auto select-none"
    >
      {/* Glow behind card */}
      <div
        className="absolute inset-0 blur-3xl opacity-20 rounded-3xl transition-all duration-700 pointer-events-none"
        style={{ backgroundColor: slide.color }}
      />

      {/* Card */}
      <div className="relative rounded-2xl border border-surface-border bg-surface-card overflow-hidden shadow-2xl">
        {/* Window bar */}
        <div className="flex items-center gap-1.5 px-4 py-3 border-b border-surface-border bg-white/[0.02]">
          <div className="w-3 h-3 rounded-full bg-red-500/70" />
          <div className="w-3 h-3 rounded-full bg-amber-500/70" />
          <div className="w-3 h-3 rounded-full bg-emerald-500/70" />
          <div className="flex-1 mx-3 h-5 rounded-md bg-white/5 border border-white/5 flex items-center px-2">
            <span className="text-[9px] text-slate-600">slawise.app / {slide.id}</span>
          </div>
        </div>

        {/* Top color accent */}
        <div className="h-0.5 w-full transition-all duration-700"
          style={{ background: `linear-gradient(90deg, ${slide.color}, ${slide.color}60, transparent)` }} />

        {/* Section header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-surface-border/60">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-all duration-500"
            style={{ backgroundColor: slide.color + '20', border: `1px solid ${slide.color}40` }}>
            <slide.icon className="w-4 h-4 transition-all" style={{ color: slide.color }} />
          </div>
          <div>
            <p className="text-sm font-semibold text-white">{slide.title}</p>
            <p className="text-[11px] text-slate-500">{slide.subtitle}</p>
          </div>
        </div>

        {/* Content */}
        <div className="relative overflow-hidden" style={{ minHeight: 220 }}>
          <AnimatePresence mode="wait" custom={dir}>
            <motion.div
              key={active}
              custom={dir}
              variants={{
                enter: d => ({ x: d * 50, opacity: 0 }),
                center: { x: 0, opacity: 1 },
                exit: d => ({ x: d * -50, opacity: 0 }),
              }}
              initial="enter" animate="center" exit="exit"
              transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
              className="p-4"
            >
              <slide.Preview />
            </motion.div>
          </AnimatePresence>
        </div>
      </div>

      {/* Arrow buttons */}
      <button onClick={prev}
        className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-5 w-9 h-9 rounded-full bg-surface-card border border-surface-border flex items-center justify-center text-slate-500 hover:text-white hover:border-blue-500/40 transition-all shadow-lg z-10">
        <ChevronLeft className="w-4 h-4" />
      </button>
      <button onClick={next}
        className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-5 w-9 h-9 rounded-full bg-surface-card border border-surface-border flex items-center justify-center text-slate-500 hover:text-white hover:border-blue-500/40 transition-all shadow-lg z-10">
        <ChevronRight className="w-4 h-4" />
      </button>

      {/* Dot + label nav */}
      <div className="mt-5 flex flex-col items-center gap-3">
        <div className="flex items-center gap-2">
          {SLIDES.map((s, i) => (
            <button key={i} onClick={() => go(i)}
              className="transition-all duration-400 rounded-full"
              style={{
                width: i === active ? 28 : 8,
                height: 8,
                backgroundColor: i === active ? slide.color : '#1e2a42',
              }} />
          ))}
        </div>
        <div className="flex flex-wrap justify-center gap-1.5">
          {SLIDES.map((s, i) => (
            <button key={i} onClick={() => go(i)}
              className="text-[11px] px-2.5 py-1 rounded-lg transition-all duration-200"
              style={i === active
                ? { backgroundColor: s.color + '18', border: `1px solid ${s.color}40`, color: s.color }
                : { color: '#475569', border: '1px solid transparent' }
              }>
              {s.title.split(' ')[0]}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Animated Background Orbs ─────────────────────────────────────────────────

function BackgroundOrbs() {
  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
      <motion.div
        className="absolute top-[-20%] left-[-10%] w-[600px] h-[600px] rounded-full"
        style={{ background: 'radial-gradient(circle, rgba(59,130,246,0.07) 0%, transparent 70%)' }}
        animate={{ x: [0, 40, 0], y: [0, 30, 0] }}
        transition={{ duration: 18, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.div
        className="absolute top-[30%] right-[-15%] w-[500px] h-[500px] rounded-full"
        style={{ background: 'radial-gradient(circle, rgba(168,85,247,0.06) 0%, transparent 70%)' }}
        animate={{ x: [0, -30, 0], y: [0, -40, 0] }}
        transition={{ duration: 22, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.div
        className="absolute bottom-[-10%] left-[30%] w-[400px] h-[400px] rounded-full"
        style={{ background: 'radial-gradient(circle, rgba(16,185,129,0.05) 0%, transparent 70%)' }}
        animate={{ x: [0, 20, 0], y: [0, -20, 0] }}
        transition={{ duration: 15, repeat: Infinity, ease: 'easeInOut' }}
      />
      {/* Grid overlay */}
      <div className="absolute inset-0 opacity-[0.025]"
        style={{
          backgroundImage: 'linear-gradient(rgba(148,163,184,1) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,1) 1px, transparent 1px)',
          backgroundSize: '60px 60px',
        }} />
    </div>
  );
}

// ─── Top Navbar ───────────────────────────────────────────────────────────────

const NAV_LINKS = [
  { label: 'Features', href: '#features' },
  { label: 'How it Works', href: '#how-it-works' },
  { label: 'Providers', href: '#providers' },
];

function LandingNav() {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 24);
    window.addEventListener('scroll', handler);
    return () => window.removeEventListener('scroll', handler);
  }, []);

  function scrollTo(href) {
    setMenuOpen(false);
    document.querySelector(href)?.scrollIntoView({ behavior: 'smooth' });
  }

  return (
    <nav className={`fixed top-0 inset-x-0 z-50 transition-all duration-300 ${scrolled ? 'glass border-b border-surface-border shadow-xl' : 'bg-transparent'}`}>
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center shadow-lg shadow-blue-600/30">
            <Cloud className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-white tracking-tight">SLAwise</span>
          <span className="hidden sm:inline text-slate-500 font-light text-sm">by CloudSLA</span>
        </Link>

        {/* Desktop nav */}
        <div className="hidden md:flex items-center gap-1">
          {NAV_LINKS.map(({ label, href }) => (
            <button key={href} onClick={() => scrollTo(href)}
              className="px-4 py-2 text-sm text-slate-400 hover:text-white rounded-lg hover:bg-white/5 transition-all">
              {label}
            </button>
          ))}
        </div>

        {/* CTA */}
        <div className="flex items-center gap-3">
          <Link to="/app"
            className="hidden sm:inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition-all shadow-lg shadow-blue-600/25 hover:shadow-blue-500/35">
            Launch App <ArrowRight className="w-3.5 h-3.5" />
          </Link>
          <button className="md:hidden p-2 text-slate-400 hover:text-white" onClick={() => setMenuOpen(o => !o)}>
            {menuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      <AnimatePresence>
        {menuOpen && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            className="md:hidden border-t border-surface-border bg-surface-card/95 backdrop-blur overflow-hidden">
            <div className="px-6 py-4 space-y-1">
              {NAV_LINKS.map(({ label, href }) => (
                <button key={href} onClick={() => scrollTo(href)}
                  className="block w-full text-left px-4 py-2.5 text-slate-300 hover:text-white rounded-lg hover:bg-white/5 transition-all text-sm">
                  {label}
                </button>
              ))}
              <Link to="/app" className="flex items-center gap-2 px-4 py-2.5 mt-2 rounded-xl bg-blue-600 text-white text-sm font-semibold">
                Launch App <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
}

// ─── Main Landing Page ────────────────────────────────────────────────────────

const fadeUp = {
  hidden: { opacity: 0, y: 28 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { delay: i * 0.1, duration: 0.55, ease: [0.4, 0, 0.2, 1] } }),
};

const FEATURES = [
  {
    icon: Brain,
    title: 'Smart Recommendations',
    desc: 'Describe your workload in plain English. Our AI pipeline scores each provider against actual SLA documents using semantic search and multi-factor weighting.',
    color: '#3b82f6',
    points: ['Semantic vector search', 'Customizable weight factors', 'Explainable scoring'],
  },
  {
    icon: Bell,
    title: 'Real-Time Alerts',
    desc: 'Automatic detection of SLA changes across all ingested providers. Never miss an uptime commitment downgrade or penalty clause update.',
    color: '#f59e0b',
    points: ['Uptime change detection', 'New document tracking', 'Severity classification'],
  },
  {
    icon: BarChart3,
    title: 'Side-by-Side Compare',
    desc: 'Select multiple providers and get a structured comparison with winner badges, percentage advantages, and color-coded cell highlighting.',
    color: '#a855f7',
    points: ['Winner highlighting', 'Advantage summaries', 'Pricing integration'],
  },
  {
    icon: MessageSquare,
    title: 'RAG-Powered Chat',
    desc: 'Ask questions about any ingested SLA document in natural language. Get answers grounded in the actual source with citation links.',
    color: '#10b981',
    points: ['Source-cited answers', 'Provider-filtered queries', 'Context-aware dialogue'],
  },
  {
    icon: Globe,
    title: 'Auto Web Ingestion',
    desc: 'Search official provider SLA pages directly from the app. Auto-fetch, select, and ingest in one click — no manual copy-paste.',
    color: '#06b6d4',
    points: ['Curated official URLs', 'Batch ingest', 'PDF & HTML support'],
  },
  {
    icon: DollarSign,
    title: 'Pricing Intelligence',
    desc: 'Cross-reference SLA commitments with real service pricing. Make cost-aware decisions without leaving the platform.',
    color: '#f472b6',
    points: ['Per-service pricing', 'Region comparison', 'Refresh on demand'],
  },
];

const STEPS = [
  { icon: Upload, title: 'Ingest SLA Documents', desc: 'Upload PDFs, paste URLs, or auto-fetch from official provider pages. The system chunkes and embeds everything into a semantic vector store.' },
  { icon: Brain, title: 'AI Processes & Indexes', desc: 'A 6-stage pipeline embeds documents using multilingual-e5-base, stores vectors in ChromaDB, and extracts key SLA metrics automatically.' },
  { icon: Lightbulb, title: 'Get Recommendations', desc: 'Describe your workload in natural language. Receive ranked, explainable recommendations with score breakdowns and direct source links.' },
];

const PROVIDERS = [
  { name: 'Amazon Web Services', short: 'AWS', color: '#FF9900', desc: '200+ services, global CDN' },
  { name: 'Microsoft Azure', short: 'AZ', color: '#0078D4', desc: '60+ regions worldwide' },
  { name: 'Google Cloud', short: 'GCP', color: '#4285F4', desc: 'Kubernetes & AI-native' },
  { name: 'Oracle Cloud', short: 'OCI', color: '#F80000', desc: 'Enterprise & ERP focus' },
  { name: 'IBM Cloud', short: 'IBM', color: '#1261FE', desc: 'Hybrid & regulated industries' },
];

const STATS = [
  { value: '5', label: 'Cloud Providers', sub: 'AWS · Azure · GCP · Oracle · IBM', icon: Cloud, color: '#3b82f6' },
  { value: '32', label: 'API Endpoints', sub: 'Fully documented REST API', icon: Activity, color: '#a855f7' },
  { value: '6', label: 'Pipeline Stages', sub: 'Ingest → Embed → Retrieve → Rank', icon: Database, color: '#10b981' },
];

export default function Landing() {
  return (
    <div className="relative min-h-screen bg-surface overflow-x-hidden" style={{ scrollBehavior: 'smooth' }}>
      <BackgroundOrbs />
      <LandingNav />

      {/* ── Hero ── */}
      <section className="relative z-10 min-h-screen flex items-center pt-20 pb-16 px-6">
        <div className="max-w-7xl mx-auto w-full">
          <div className="grid lg:grid-cols-2 gap-16 items-center">

            {/* Left: text */}
            <div>
              <motion.div variants={fadeUp} initial="hidden" animate="show" custom={0}>
                <span className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-medium mb-6">
                  <Zap className="w-3.5 h-3.5" /> AI-Powered Cloud SLA Intelligence
                </span>
              </motion.div>

              <motion.h1 variants={fadeUp} initial="hidden" animate="show" custom={1}
                className="text-5xl sm:text-6xl font-extrabold text-white leading-[1.1] tracking-tight mb-6">
                Pick the Right{' '}
                <span className="relative inline-block">
                  <span style={{ background: 'linear-gradient(135deg, #60a5fa, #a78bfa)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text' }}>
                    Cloud Provider
                  </span>
                </span>
                <br />With Confidence
              </motion.h1>

              <motion.p variants={fadeUp} initial="hidden" animate="show" custom={2}
                className="text-lg text-slate-400 leading-relaxed mb-8 max-w-lg">
                Stop manually reading hundreds of SLA pages. Describe your workload once — our AI
                compares AWS, Azure, GCP, Oracle, and IBM Cloud against real SLA commitments and
                returns ranked, explainable recommendations.
              </motion.p>

              <motion.div variants={fadeUp} initial="hidden" animate="show" custom={3} className="flex flex-wrap gap-3 mb-10">
                <Link to="/app"
                  className="group inline-flex items-center gap-2 px-7 py-3.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold transition-all shadow-xl shadow-blue-600/25 hover:shadow-blue-500/35 hover:-translate-y-0.5">
                  Get Started Free
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                </Link>
                <Link to="/app/compare"
                  className="inline-flex items-center gap-2 px-7 py-3.5 rounded-xl border border-surface-border bg-white/3 hover:bg-white/6 hover:border-slate-600 text-white font-medium transition-all hover:-translate-y-0.5">
                  Compare Providers
                  <ChevronRight className="w-4 h-4" />
                </Link>
              </motion.div>

              <motion.div variants={fadeUp} initial="hidden" animate="show" custom={4}
                className="flex items-center gap-6 flex-wrap">
                {[
                  { icon: Check, text: 'No sign-up required' },
                  { icon: Check, text: 'Works with any SLA PDF' },
                  { icon: Check, text: 'Open source backend' },
                ].map(({ icon: Icon, text }) => (
                  <div key={text} className="flex items-center gap-1.5 text-sm text-slate-500">
                    <Icon className="w-3.5 h-3.5 text-emerald-500" /> {text}
                  </div>
                ))}
              </motion.div>
            </div>

            {/* Right: carousel */}
            <motion.div variants={fadeUp} initial="hidden" animate="show" custom={2}
              className="hidden lg:block">
              <FeatureCarousel />
            </motion.div>
          </div>

          {/* Mobile carousel */}
          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={3} className="lg:hidden mt-12">
            <FeatureCarousel />
          </motion.div>
        </div>
      </section>

      {/* ── Stats ── */}
      <section className="relative z-10 py-14 border-y border-surface-border bg-surface-card/30 backdrop-blur-sm">
        <div className="max-w-4xl mx-auto px-6 grid sm:grid-cols-3 gap-8">
          {STATS.map(({ value, label, sub, icon: Icon, color }, i) => (
            <motion.div key={label}
              variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true }} custom={i * 0.1}
              className="flex flex-col items-center text-center gap-2">
              <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-1"
                style={{ backgroundColor: color + '15', border: `1px solid ${color}30` }}>
                <Icon className="w-5 h-5" style={{ color }} />
              </div>
              <div className="text-4xl font-black text-white">{value}</div>
              <div className="font-semibold text-slate-200 text-sm">{label}</div>
              <div className="text-xs text-slate-600">{sub}</div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── Features ── */}
      <section id="features" className="relative z-10 py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <motion.div variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true }}
            className="text-center mb-16">
            <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-400 text-xs mb-4">
              <Star className="w-3 h-3" /> Platform Features
            </span>
            <h2 className="text-4xl font-bold text-white mb-4">Everything for cloud SLA decisions</h2>
            <p className="text-slate-500 max-w-xl mx-auto">
              From raw SLA document ingestion to AI-ranked recommendations — the entire decision pipeline in one platform.
            </p>
          </motion.div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {FEATURES.map(({ icon: Icon, title, desc, color, points }, i) => (
              <motion.div key={title}
                variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true }} custom={i * 0.07}
                className="group p-6 rounded-2xl bg-surface-card border border-surface-border hover:border-opacity-60 transition-all duration-300 hover:-translate-y-1 cursor-default"
                style={{ '--hover-color': color }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = color + '50')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = '')}>
                <div className="w-11 h-11 rounded-xl flex items-center justify-center mb-5 transition-transform group-hover:scale-110"
                  style={{ backgroundColor: color + '15', border: `1px solid ${color}30` }}>
                  <Icon className="w-5 h-5" style={{ color }} />
                </div>
                <h3 className="text-white font-semibold mb-2">{title}</h3>
                <p className="text-slate-500 text-sm leading-relaxed mb-4">{desc}</p>
                <ul className="space-y-1.5">
                  {points.map(p => (
                    <li key={p} className="flex items-center gap-2 text-xs text-slate-500">
                      <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
                      {p}
                    </li>
                  ))}
                </ul>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it Works ── */}
      <section id="how-it-works" className="relative z-10 py-24 px-6">
        <div className="max-w-5xl mx-auto">
          <motion.div variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true }}
            className="text-center mb-16">
            <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs mb-4">
              <Zap className="w-3 h-3" /> Simple Setup
            </span>
            <h2 className="text-4xl font-bold text-white mb-4">From zero to recommendation in 3 steps</h2>
            <p className="text-slate-500 max-w-lg mx-auto">No configuration required. Run the Docker stack and start getting AI-powered SLA recommendations immediately.</p>
          </motion.div>

          <div className="grid md:grid-cols-3 gap-10 relative">
            {/* Connector */}
            <div className="hidden md:block absolute top-10 left-[20%] right-[20%] h-px"
              style={{ background: 'linear-gradient(90deg, #1e2a42, #3b82f6, #1e2a42)' }} />

            {STEPS.map(({ icon: Icon, title, desc }, i) => (
              <motion.div key={title}
                variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true }} custom={i * 0.15}
                className="flex flex-col items-center text-center">
                <div className="relative mb-6">
                  <div className="w-20 h-20 rounded-2xl bg-surface-card border border-surface-border flex items-center justify-center z-10 relative shadow-xl">
                    <Icon className="w-8 h-8 text-blue-400" />
                  </div>
                  <div className="absolute -top-2 -right-2 w-7 h-7 rounded-full bg-blue-600 border-2 border-surface text-white text-xs font-black flex items-center justify-center z-20 shadow-lg shadow-blue-600/40">
                    {i + 1}
                  </div>
                </div>
                <h3 className="text-white font-bold text-lg mb-3">{title}</h3>
                <p className="text-slate-500 text-sm leading-relaxed">{desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Providers ── */}
      <section id="providers" className="relative z-10 py-20 px-6 bg-surface-card/20">
        <div className="max-w-4xl mx-auto">
          <motion.div variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true }}
            className="text-center mb-10">
            <h2 className="text-3xl font-bold text-white mb-3">Supported Providers</h2>
            <p className="text-slate-500">Ingest and compare SLA documents from any of these providers — or any custom provider you add.</p>
          </motion.div>

          <div className="grid sm:grid-cols-5 gap-4">
            {PROVIDERS.map(({ name, short, color, desc }, i) => (
              <motion.div key={name}
                variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true }} custom={i * 0.08}
                className="flex flex-col items-center text-center p-4 rounded-2xl bg-surface-card border border-surface-border hover:border-opacity-50 transition-all hover:-translate-y-1 group"
                onMouseEnter={e => (e.currentTarget.style.borderColor = color + '50')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = '')}>
                <div className="w-12 h-12 rounded-xl flex items-center justify-center text-sm font-black mb-3 transition-transform group-hover:scale-110"
                  style={{ backgroundColor: color + '20', border: `1px solid ${color}40`, color }}>
                  {short}
                </div>
                <p className="text-white text-xs font-semibold mb-1">{name.split(' ')[0]}</p>
                <p className="text-slate-600 text-[10px]">{desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="relative z-10 py-24 px-6">
        <motion.div
          variants={fadeUp} initial="hidden" whileInView="show" viewport={{ once: true }}
          className="max-w-3xl mx-auto text-center"
        >
          <div className="relative p-12 rounded-3xl overflow-hidden border border-blue-500/20"
            style={{ background: 'linear-gradient(135deg, rgba(59,130,246,0.08), rgba(168,85,247,0.06))' }}>
            <div className="absolute inset-0 pointer-events-none">
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-64 h-px bg-gradient-to-r from-transparent via-blue-500/40 to-transparent" />
              <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-48 h-px bg-gradient-to-r from-transparent via-purple-500/30 to-transparent" />
            </div>

            <Shield className="w-12 h-12 text-blue-400 mx-auto mb-6" />
            <h2 className="text-4xl font-extrabold text-white mb-4 leading-tight">
              Ready to make smarter<br />cloud decisions?
            </h2>
            <p className="text-slate-400 mb-8 max-w-lg mx-auto leading-relaxed">
              Start comparing cloud SLAs in minutes. No account, no API key, no credit card —
              just run Docker and go.
            </p>

            <div className="flex flex-wrap justify-center gap-4">
              <Link to="/app"
                className="group inline-flex items-center gap-2 px-8 py-4 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold transition-all shadow-xl shadow-blue-600/30 hover:shadow-blue-500/40 hover:-translate-y-0.5 text-lg">
                Open the App
                <ArrowRight className="w-5 h-5 group-hover:translate-x-0.5 transition-transform" />
              </Link>
              <Link to="/app/recommend"
                className="inline-flex items-center gap-2 px-8 py-4 rounded-xl border border-surface-border hover:border-slate-600 bg-white/3 hover:bg-white/5 text-white font-medium transition-all hover:-translate-y-0.5 text-lg">
                Try Recommender
              </Link>
            </div>
          </div>
        </motion.div>
      </section>

      {/* ── Footer ── */}
      <footer className="relative z-10 border-t border-surface-border py-10 px-6">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-blue-600/70 flex items-center justify-center">
              <Cloud className="w-4 h-4 text-white" />
            </div>
            <span className="text-slate-400 font-medium text-sm">SLAwise</span>
          </div>

          <div className="flex items-center gap-6 text-xs text-slate-600">
            {NAV_LINKS.map(({ label, href }) => (
              <button key={href} onClick={() => document.querySelector(href)?.scrollIntoView({ behavior: 'smooth' })}
                className="hover:text-slate-400 transition-colors">
                {label}
              </button>
            ))}
            <Link to="/app" className="hover:text-slate-400 transition-colors">Launch App</Link>
          </div>

          <p className="text-xs text-slate-700">AI-powered SLA intelligence platform</p>
        </div>
      </footer>
    </div>
  );
}
