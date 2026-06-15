import { Routes, Route, Navigate, Link } from 'react-router-dom';
import { Home } from 'lucide-react';
import Landing from './pages/Landing';
import Dashboard from './pages/app/Dashboard';
import AddSLADocs from './pages/app/AddSLADocs';
import Recommend from './pages/app/Recommend';
import Compare from './pages/app/Compare';
import Chat from './pages/app/Chat';
import Pricing from './pages/app/Pricing';
import Alerts from './pages/app/Alerts';
import ErrorBoundary from './components/ErrorBoundary';

function NotFound() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-surface-bg">
      <div className="text-center space-y-4">
        <p className="text-8xl font-black text-white/5">404</p>
        <p className="text-white font-semibold text-xl -mt-6">Page not found</p>
        <p className="text-slate-500 text-sm">This route doesn't exist.</p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 text-sm hover:bg-blue-500/20 transition-colors"
        >
          <Home className="w-3.5 h-3.5" />
          Back to home
        </Link>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route
        path="/app"
        element={
          <ErrorBoundary>
            <Dashboard />
          </ErrorBoundary>
        }
      >
        <Route index element={<Navigate to="recommend" replace />} />
        <Route path="upload" element={<ErrorBoundary><AddSLADocs /></ErrorBoundary>} />
        <Route path="recommend" element={<ErrorBoundary><Recommend /></ErrorBoundary>} />
        <Route path="compare" element={<ErrorBoundary><Compare /></ErrorBoundary>} />
        <Route path="chat" element={<ErrorBoundary><Chat /></ErrorBoundary>} />
        <Route path="pricing" element={<ErrorBoundary><Pricing /></ErrorBoundary>} />
        <Route path="alerts" element={<ErrorBoundary><Alerts /></ErrorBoundary>} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
