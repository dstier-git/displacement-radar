import { useState, useCallback } from 'react';
import { scanCompetitor, fetchProspects, generateEmail } from './api';
import SetupScreen from './SetupScreen';
import ScanningScreen from './ScanningScreen';
import Dashboard from './Dashboard';

export default function App() {
  const [screen, setScreen] = useState('setup');
  const [config, setConfig] = useState({ yourProduct: '', yourCompany: '', competitors: [] });
  const [scanStatus, setScanStatus] = useState({ current: '', progress: 0, total: 0 });
  const [signals, setSignals] = useState([]);
  const [selectedSignal, setSelectedSignal] = useState(null);
  const [prospects, setProspects] = useState([]);
  const [loadingProspects, setLoadingProspects] = useState(false);
  const [selectedProspects, setSelectedProspects] = useState(new Set());
  const [emails, setEmails] = useState({});
  const [generatingEmails, setGeneratingEmails] = useState(new Set());

  const handleInitialize = useCallback(async (formConfig) => {
    setConfig(formConfig);
    setScreen('scanning');
    setSignals([]);
    setSelectedSignal(null);
    setProspects([]);
    setEmails({});

    const allSignals = [];
    for (let i = 0; i < formConfig.competitors.length; i++) {
      const competitor = formConfig.competitors[i];
      setScanStatus({ current: competitor, progress: i, total: formConfig.competitors.length });
      try {
        const found = await scanCompetitor(competitor, formConfig.yourProduct, formConfig.yourCompany);
        const tagged = (Array.isArray(found) ? found : []).map(s => ({
          ...s,
          id: `${competitor}-${Math.random().toString(36).slice(2)}`,
          competitor,
        }));
        allSignals.push(...tagged);
      } catch (e) {
        console.error(`Scan failed for ${competitor}:`, e.message);
      }
    }

    setScanStatus(s => ({ ...s, progress: s.total }));
    setSignals(allSignals);
    setTimeout(() => setScreen('dashboard'), 700);
  }, []);

  const handleSelectSignal = useCallback(async (signal) => {
    setSelectedSignal(signal);
    setProspects([]);
    setSelectedProspects(new Set());
    setEmails({});
    setLoadingProspects(true);
    try {
      const found = await fetchProspects(signal, signal.competitor, config.yourProduct);
      setProspects(Array.isArray(found) ? found : []);
    } catch (e) {
      console.error('Prospects failed:', e.message);
    } finally {
      setLoadingProspects(false);
    }
  }, [config.yourProduct]);

  const toggleProspect = useCallback((id) => {
    setSelectedProspects(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const selectAllProspects = useCallback(() => {
    setSelectedProspects(new Set(prospects.map(p => p.id)));
  }, [prospects]);

  const clearSelection = useCallback(() => setSelectedProspects(new Set()), []);

  const generateSelected = useCallback(async () => {
    const toGenerate = prospects.filter(p => selectedProspects.has(p.id) && !emails[p.id]);
    if (toGenerate.length === 0) return;

    setGeneratingEmails(prev => {
      const next = new Set(prev);
      toGenerate.forEach(p => next.add(p.id));
      return next;
    });

    await Promise.all(toGenerate.map(async (prospect) => {
      try {
        const email = await generateEmail(prospect, selectedSignal, config.yourProduct, config.yourCompany);
        setEmails(prev => ({ ...prev, [prospect.id]: email }));
      } catch (e) {
        console.error(`Email failed for ${prospect.name}:`, e.message);
        setEmails(prev => ({
          ...prev,
          [prospect.id]: {
            subject: 'Generation failed — please retry',
            preview: '',
            body: `Could not generate email for ${prospect.name}. Please try again.`,
          },
        }));
      } finally {
        setGeneratingEmails(prev => {
          const next = new Set(prev);
          next.delete(prospect.id);
          return next;
        });
      }
    }));
  }, [prospects, selectedProspects, emails, selectedSignal, config]);

  const copyAllEmails = useCallback(() => {
    const text = prospects
      .filter(p => selectedProspects.has(p.id) && emails[p.id])
      .map(p => {
        const e = emails[p.id];
        return `${'─'.repeat(60)}\nTo: ${p.name} — ${p.title} @ ${p.company}\nSubject: ${e.subject}\n\n${e.body}`;
      })
      .join('\n\n');
    navigator.clipboard.writeText(text);
  }, [prospects, selectedProspects, emails]);

  const handleReset = useCallback(() => {
    setScreen('setup');
    setSignals([]);
    setSelectedSignal(null);
    setProspects([]);
    setSelectedProspects(new Set());
    setEmails({});
    setGeneratingEmails(new Set());
  }, []);

  if (screen === 'setup') return <SetupScreen onInitialize={handleInitialize} />;
  if (screen === 'scanning') return <ScanningScreen status={scanStatus} />;

  return (
    <Dashboard
      config={config}
      signals={signals}
      selectedSignal={selectedSignal}
      onSelectSignal={handleSelectSignal}
      prospects={prospects}
      loadingProspects={loadingProspects}
      selectedProspects={selectedProspects}
      onToggleProspect={toggleProspect}
      onSelectAll={selectAllProspects}
      onClearSelection={clearSelection}
      onGenerateSelected={generateSelected}
      emails={emails}
      generatingEmails={generatingEmails}
      onCopyAll={copyAllEmails}
      onReset={handleReset}
    />
  );
}
