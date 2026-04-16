const STEPS = [
  { id: 'web', label: 'Scanning live web signals' },
  { id: 'cross', label: 'Cross-referencing Apollo database' },
  { id: 'score', label: 'Scoring displacement opportunities' },
  { id: 'build', label: 'Building prospect profiles' },
];

export default function ScanningScreen({ status }) {
  const { current, progress, total } = status;
  const pct = total > 0 ? Math.round((progress / total) * 100) : 0;

  // Map progress into step index for animation
  const activeStep = progress < total ? Math.floor((progress / total) * STEPS.length) : STEPS.length;

  return (
    <div className="scanning-screen">
      <div className="scanning-logo">⬡ DISPLACEMENT</div>

      <div className="scanning-orbit">
        <div className="scanning-orbit-ring" />
        <div className="scanning-orbit-core">⬡</div>
      </div>

      <div className="scanning-status">
        <h3>{current ? `Scanning ${current}...` : 'Finalizing intelligence report...'}</h3>
        <p>
          {total > 0
            ? `${progress} of ${total} competitor${total !== 1 ? 's' : ''} processed — ${pct}%`
            : 'Initializing agent...'}
        </p>
      </div>

      <div className="scanning-steps">
        {STEPS.map((step, i) => {
          const isDone = i < activeStep;
          const isActive = i === activeStep;
          return (
            <div
              key={step.id}
              className={`scanning-step ${isDone ? 'done' : ''} ${isActive ? 'active' : ''}`}
            >
              <div className="step-dot" />
              {isDone ? '✓' : isActive ? '▶' : '○'}&nbsp;{step.label}
            </div>
          );
        })}
      </div>
    </div>
  );
}
