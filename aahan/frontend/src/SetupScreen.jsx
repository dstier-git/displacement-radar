import { useState } from 'react';

export default function SetupScreen({ onInitialize }) {
  const [yourProduct, setYourProduct] = useState('');
  const [yourCompany, setYourCompany] = useState('');
  const [competitorInput, setCompetitorInput] = useState('');
  const [competitors, setCompetitors] = useState([]);

  function addCompetitor() {
    const val = competitorInput.trim();
    if (val && !competitors.includes(val)) {
      setCompetitors([...competitors, val]);
    }
    setCompetitorInput('');
  }

  function removeCompetitor(c) {
    setCompetitors(competitors.filter(x => x !== c));
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addCompetitor();
    }
  }

  const canSubmit = yourProduct.trim() && yourCompany.trim() && competitors.length > 0;

  return (
    <div className="setup-screen">
      <div className="setup-logo">
        <div className="setup-logo-icon">⬡</div>
        <span className="setup-logo-text">DISPLACEMENT</span>
      </div>
      <p className="setup-tagline">
        Turn your competitors' worst moments into your best pipeline opportunities
      </p>

      <div className="setup-card">
        <h2>Initialize Intelligence Agent</h2>

        <div className="form-row">
          <div className="form-group">
            <label>Your Product</label>
            <input
              placeholder="e.g. Rippling"
              value={yourProduct}
              onChange={e => setYourProduct(e.target.value)}
            />
          </div>
          <div className="form-group">
            <label>Your Company</label>
            <input
              placeholder="e.g. Rippling Inc"
              value={yourCompany}
              onChange={e => setYourCompany(e.target.value)}
            />
          </div>
        </div>

        <div className="form-group">
          <label>Add Competitors to Monitor</label>
          <input
            placeholder="Type a competitor name and press Enter"
            value={competitorInput}
            onChange={e => setCompetitorInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={addCompetitor}
          />
        </div>
        <p className="form-hint">Press Enter after each competitor. Try: Salesforce, HubSpot, Workday, Rippling...</p>

        {competitors.length > 0 && (
          <div className="competitor-tags">
            {competitors.map(c => (
              <span key={c} className="competitor-tag">
                {c}
                <button onClick={() => removeCompetitor(c)}>×</button>
              </span>
            ))}
          </div>
        )}

        <button
          className="btn-primary"
          disabled={!canSubmit}
          onClick={() => onInitialize({ yourProduct: yourProduct.trim(), yourCompany: yourCompany.trim(), competitors })}
        >
          Initialize Monitoring →
        </button>
      </div>
    </div>
  );
}
