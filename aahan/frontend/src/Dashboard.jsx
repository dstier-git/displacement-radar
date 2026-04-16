import { useState } from 'react';

// ── Helpers ──────────────────────────────────────────────────────
const TYPE_COLORS = {
  PRICE: 'type-PRICE', OUTAGE: 'type-OUTAGE', LEADERSHIP: 'type-LEADERSHIP',
  ACQUISITION: 'type-ACQUISITION', REVIEWS: 'type-REVIEWS', FEATURE: 'type-FEATURE',
  SECURITY: 'type-SECURITY',
};
const SEV_COLORS = { high: 'var(--red)', medium: 'var(--yellow)', low: 'var(--green)' };

function scoreClass(n) {
  if (n >= 8) return 'score-high';
  if (n >= 5) return 'score-med';
  return 'score-low';
}

function initials(name = '') {
  return name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase() || '?';
}

// ── Signal Panel ─────────────────────────────────────────────────
function SignalPanel({ signals, selectedSignal, onSelectSignal }) {
  return (
    <div className="panel panel-signals">
      <div className="panel-header">
        <span className="panel-title">Signals</span>
        <span className="panel-count">{signals.length} found</span>
      </div>
      <div className="panel-body">
        {signals.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📡</div>
            <span>No signals detected</span>
          </div>
        ) : (
          signals.map(signal => (
            <div
              key={signal.id}
              className={`signal-card ${selectedSignal?.id === signal.id ? 'selected' : ''}`}
              onClick={() => onSelectSignal(signal)}
            >
              <div className="signal-top">
                <span className={`signal-type-badge ${TYPE_COLORS[signal.type] || ''}`}>
                  {signal.type}
                </span>
                <div className="signal-severity">
                  <div className="sev-dot" style={{ background: SEV_COLORS[signal.severity] || 'var(--text-muted)' }} />
                  {signal.severity}
                </div>
              </div>
              <div className="signal-title">{signal.title}</div>
              <div className="signal-meta">
                <span className="signal-date">{signal.date}</span>
                <span className={`signal-score ${scoreClass(signal.opportunity_score)}`}>
                  {signal.opportunity_score}/10
                </span>
              </div>
              <span className="signal-competitor-tag">{signal.competitor}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ── Prospect Panel ────────────────────────────────────────────────
function ProspectPanel({ selectedSignal, prospects, loading, selectedProspects, onToggle, onSelectAll, onClearSelection, onGenerate, emails, generatingEmails }) {
  const selectedCount = selectedProspects.size;

  return (
    <div className="panel panel-prospects">
      <div className="panel-header">
        <span className="panel-title">Prospects</span>
        <span className="panel-count">{prospects.length} loaded</span>
      </div>

      {!selectedSignal ? null : (
        <div className="prospect-toolbar">
          <div className="prospect-toolbar-left">
            <button className="btn-sm" onClick={onSelectAll} disabled={prospects.length === 0}>
              Select All
            </button>
            <button className="btn-sm" onClick={onClearSelection} disabled={selectedCount === 0}>
              Clear
            </button>
          </div>
          {selectedCount > 0 && (
            <span className="selection-count">{selectedCount} selected</span>
          )}
          <button
            className="btn-generate"
            disabled={selectedCount === 0}
            onClick={onGenerate}
          >
            Generate Emails →
          </button>
        </div>
      )}

      <div className="prospect-grid">
        {!selectedSignal ? (
          <div className="loading-prospects" style={{ gridColumn: '1/-1' }}>
            <div className="empty-icon">👈</div>
            <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>
              Select a signal to load prospects
            </span>
          </div>
        ) : loading ? (
          <div className="loading-prospects">
            <div className="spinner-lg" />
            <span>Loading prospects from Apollo...</span>
          </div>
        ) : prospects.length === 0 ? (
          <div className="loading-prospects">
            <div className="empty-icon" style={{ fontSize: 28 }}>🔍</div>
            <span style={{ color: 'var(--text-muted)' }}>No prospects found</span>
          </div>
        ) : (
          prospects.map(p => {
            const isSelected = selectedProspects.has(p.id);
            const isGenerating = generatingEmails.has(p.id);
            const hasEmail = !!emails[p.id];
            return (
              <div
                key={p.id}
                className={`prospect-card ${isSelected ? 'selected' : ''} ${hasEmail ? 'has-email' : ''}`}
                onClick={() => onToggle(p.id)}
              >
                {isGenerating && (
                  <div className="prospect-generating">
                    <div className="spinner" />
                    <span>Writing...</span>
                  </div>
                )}
                <div className="prospect-checkbox">
                  {hasEmail ? '✓' : isSelected ? '✓' : ''}
                </div>
                <div className="prospect-avatar">{initials(p.name)}</div>
                <div className="prospect-name">{p.name}</div>
                <div className="prospect-title">{p.title}</div>
                <div className="prospect-company">
                  🏢 {p.company}
                  {p.employees && (
                    <span style={{ marginLeft: 4, color: 'var(--text-muted)' }}>
                      · {p.employees.toLocaleString()}
                    </span>
                  )}
                </div>
                {p.industry && (
                  <div className="prospect-badges">
                    <span className="badge badge-industry">{p.industry}</span>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ── Campaign Panel ────────────────────────────────────────────────
function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  function handleCopy() {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }
  return (
    <button className={`btn-copy ${copied ? 'copied' : ''}`} onClick={handleCopy}>
      {copied ? '✓ Copied' : '📋 Copy'}
    </button>
  );
}

function CampaignPanel({ prospects, selectedProspects, emails, generatingEmails, onCopyAll }) {
  const selected = prospects.filter(p => selectedProspects.has(p.id));
  const readyCount = selected.filter(p => emails[p.id]).length;

  return (
    <div className="panel panel-campaign">
      <div className="campaign-toolbar">
        <span className="panel-title">Campaign</span>
        {readyCount > 1 && (
          <button className="btn-copy-all" onClick={onCopyAll}>
            📤 Copy All ({readyCount})
          </button>
        )}
      </div>

      <div className="campaign-body">
        {selected.length === 0 ? (
          <div className="campaign-placeholder">
            <div className="campaign-placeholder-icon">✉️</div>
            <h3>No prospects selected</h3>
            <p>Select prospects in the center panel and click Generate Emails to create personalized outreach.</p>
          </div>
        ) : (
          selected.map(p => {
            const email = emails[p.id];
            const isGenerating = generatingEmails.has(p.id);

            return (
              <div key={p.id} className="email-card">
                <div className="email-card-header">
                  <div>
                    <div className="email-card-name">{p.name}</div>
                    <div className="email-card-company">{p.title} · {p.company}</div>
                  </div>
                </div>

                {isGenerating ? (
                  <div className="email-generating">
                    <div className="spinner" />
                    <span>Writing personalized email...</span>
                  </div>
                ) : email ? (
                  <>
                    <div className="email-subject">Subject: {email.subject}</div>
                    <div className="email-preview">{email.preview}</div>
                    <div className="email-body">{email.body}</div>
                    <div className="email-card-footer">
                      <CopyButton text={`Subject: ${email.subject}\n\n${email.body}`} />
                    </div>
                  </>
                ) : (
                  <div className="email-generating" style={{ color: 'var(--text-muted)' }}>
                    <span>Waiting to generate...</span>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ── Dashboard Root ────────────────────────────────────────────────
export default function Dashboard({
  config, signals, selectedSignal, onSelectSignal,
  prospects, loadingProspects, selectedProspects, onToggleProspect,
  onSelectAll, onClearSelection, onGenerateSelected,
  emails, generatingEmails, onCopyAll, onReset,
}) {
  return (
    <div className="dashboard">
      <header className="dash-header">
        <div className="dash-logo">
          <div className="dash-logo-icon">⬡</div>
          DISPLACEMENT
        </div>
        <div className="live-badge">LIVE</div>
        <span className="dash-sep">|</span>
        <div className="dash-route">
          <span className="route-product">{config.yourProduct}</span>
          <span className="route-arrow">→</span>
          <span className="route-competitors">{config.competitors.join(', ')}</span>
        </div>
        <div className="dash-header-right">
          <span className="dash-stat">{signals.length} signals detected</span>
          <button className="btn-ghost" onClick={onReset}>↩ Reset</button>
        </div>
      </header>

      <div className="dash-panels">
        <SignalPanel
          signals={signals}
          selectedSignal={selectedSignal}
          onSelectSignal={onSelectSignal}
        />
        <ProspectPanel
          selectedSignal={selectedSignal}
          prospects={prospects}
          loading={loadingProspects}
          selectedProspects={selectedProspects}
          onToggle={onToggleProspect}
          onSelectAll={onSelectAll}
          onClearSelection={onClearSelection}
          onGenerate={onGenerateSelected}
          emails={emails}
          generatingEmails={generatingEmails}
        />
        <CampaignPanel
          prospects={prospects}
          selectedProspects={selectedProspects}
          emails={emails}
          generatingEmails={generatingEmails}
          onCopyAll={onCopyAll}
        />
      </div>
    </div>
  );
}
