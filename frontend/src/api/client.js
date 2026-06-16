const BASE = '/api';
const ADMIN_KEY = import.meta.env.VITE_ADMIN_KEY || 'dev-admin-key';

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

const get = (path) => request(path);
const post = (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) });
const del = (path) => request(path, { method: 'DELETE' });
const adminPost = (path, body) => request(path, { method: 'POST', body: JSON.stringify(body), headers: { 'X-Admin-Key': ADMIN_KEY } });
const adminDel = (path) => request(path, { method: 'DELETE', headers: { 'X-Admin-Key': ADMIN_KEY } });
const adminGet = (path) => request(path, { headers: { 'X-Admin-Key': ADMIN_KEY } });

export const api = {
  // Health
  health: () => get('/health'),

  // Providers
  providers: () => get(`${BASE}/providers`),
  ingestedProviders: () => get(`${BASE}/providers/ingested`),
  providerSLA: (id) => get(`${BASE}/providers/${id}/sla`),
  providerCost: (id) => get(`${BASE}/providers/${id}/cost`),
  deleteProvider: (id) => adminDel(`${BASE}/admin/provider/${id}`),

  // Query / Recommend
  query: (text, weights, lang = 'English') => post(`${BASE}/query`, { text, weights, lang }),
  compare: (providers, metrics) =>
    get(`${BASE}/compare?providers=${encodeURIComponent(providers)}${metrics ? `&metrics=${encodeURIComponent(metrics)}` : ''}`),

  // Upload / Ingest
  uploadPDF: (provider, file) => {
    const fd = new FormData();
    fd.append('provider', provider);
    fd.append('file', file);
    return request(`${BASE}/admin/upload`, { method: 'POST', headers: { 'X-Admin-Key': ADMIN_KEY }, body: fd });
  },
  ingestURL: (provider, url) => adminPost(`${BASE}/admin/ingest-url`, { provider, url }),
  ingestText: (provider, text, title) => adminPost(`${BASE}/admin/ingest-text`, { provider, text, title }),

  // Web Search
  searchSLA: (query, maxResults = 10) => post(`${BASE}/search/sla`, { query, max_results: maxResults }),
  ingestSelected: (provider, urls) => post(`${BASE}/search/ingest-selected`, { provider, urls }),
  autoFetch: (query, provider) => post(`${BASE}/search/auto-fetch`, { query, provider }),
  parseWebSLA: (url, provider) => post(`${BASE}/search/parse-web`, { url, provider }),

  // Chat / RAG
  ask: (question, provider = null, lang = 'English') => post(`${BASE}/ask`, { question, provider, lang }),

  // Feedback
  feedback: (queryId, providerId, signal) =>
    post(`${BASE}/feedback`, { query_id: queryId, provider_id: providerId, signal }),

  // Alerts
  alerts: () => get(`${BASE}/alerts`),
  thresholds: () => get(`${BASE}/alerts/thresholds`),
  createThreshold: (data) => post(`${BASE}/alerts/thresholds`, data),
  deleteThreshold: (id) => del(`${BASE}/alerts/thresholds/${id}`),
  toggleThreshold: (id) => request(`${BASE}/alerts/thresholds/${id}`, { method: 'PATCH' }),
  checkThresholds: () => post(`${BASE}/alerts/thresholds/check`, {}),

  // Pricing
  pricingLive: () => get(`${BASE}/pricing/live`),
  pricingServices: () => get(`${BASE}/pricing/services`),
  pricingCompare: (providers, service, region) =>
    get(`${BASE}/pricing/compare?providers=${encodeURIComponent(providers)}${service ? `&service=${service}` : ''}${region ? `&region=${region}` : ''}`),
  refreshPricing: () => post(`${BASE}/pricing/refresh`, {}),

  // Model Training
  feedbackStats: () => adminGet(`${BASE}/admin/feedback/stats`),
  retrainNow: () => adminPost(`${BASE}/admin/retrain-now`, {}),
};
