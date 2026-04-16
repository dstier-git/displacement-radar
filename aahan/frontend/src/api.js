const BASE = '/api';

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || res.statusText);
  }
  return res.json();
}

export const scanCompetitor = (competitor, yourProduct, yourCompany) =>
  post('/scan', { competitor, yourProduct, yourCompany });

export const fetchProspects = (signal, competitor, yourProduct) =>
  post('/prospects', { signal, competitor, yourProduct });

export const generateEmail = (prospect, signal, yourProduct, yourCompany) =>
  post('/email', { prospect, signal, yourProduct, yourCompany });
