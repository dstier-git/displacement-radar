import express from 'express';
import cors from 'cors';
import { GoogleGenerativeAI } from '@google/generative-ai';
import 'dotenv/config';

const app = express();
app.use(cors({ origin: ['http://localhost:5173', 'http://localhost:3000', 'http://127.0.0.1:5173'] }));
app.use(express.json());

const genAI = new GoogleGenerativeAI(process.env.GOOGLE_API_KEY);
const APOLLO_API_KEY = process.env.APOLLO_API_KEY;

// 10-minute in-memory cache per competitor
const signalCache = new Map();

// Call Gemini — optionally with Google Search grounding
async function callGemini(prompt, { useSearch = false, model = 'gemini-2.0-flash' } = {}) {
  const tools = useSearch ? [{ googleSearch: {} }] : undefined;
  const genModel = genAI.getGenerativeModel({ model, ...(tools ? { tools } : {}) });
  const result = await genModel.generateContent(prompt);
  return result.response.text();
}

// Parse JSON from model output (handles code blocks and raw JSON)
function parseJSON(text, isArray = true) {
  const pattern = isArray ? /\[[\s\S]*\]/s : /\{[\s\S]*\}/s;
  const codeBlock = text.match(/```(?:json)?\s*([\s\S]*?)```/s);
  if (codeBlock) {
    const m = codeBlock[1].match(pattern);
    if (m) { try { return JSON.parse(m[0]); } catch (_) {} }
  }
  const m = text.match(pattern);
  if (m) { try { return JSON.parse(m[0]); } catch (_) {} }
  return isArray ? [] : {};
}

// ─── POST /api/scan ──────────────────────────────────────────────────────────
app.post('/api/scan', async (req, res) => {
  const { competitor, yourProduct, yourCompany } = req.body;
  if (!competitor) return res.status(400).json({ error: 'competitor is required' });

  const cached = signalCache.get(competitor);
  if (cached && Date.now() - cached.ts < 10 * 60 * 1000) {
    console.log(`Cache hit: ${competitor}`);
    return res.json(cached.signals);
  }

  const prompt = `You are a competitive intelligence analyst for B2B SaaS. Research "${competitor}" and find up to 5 recent signals (last 6 months) that create customer switching opportunities.

Signal types to find:
- PRICE: price increases, tier changes, feature paywalling
- OUTAGE: service outages, reliability incidents, SLA breaches
- LEADERSHIP: C-suite departures (CEO/CTO/CPO/CRO)
- ACQUISITION: company acquired or making major acquisition
- REVIEWS: negative review waves on G2, Reddit, Hacker News, Gartner
- FEATURE: features deprecated, removed, or restricted
- SECURITY: data breaches, compliance failures, CVEs

Return ONLY a valid JSON array, no markdown:
[{
  "type": "PRICE|OUTAGE|LEADERSHIP|ACQUISITION|REVIEWS|FEATURE|SECURITY",
  "title": "Concise descriptive title",
  "description": "2-3 sentences: what happened, why customers are upset, scale of impact",
  "severity": "high|medium|low",
  "date": "Month YYYY or Recent",
  "source": "Publication or site name",
  "opportunity_score": <integer 1-10>,
  "displacement_angle": "One sentence: how ${yourProduct} by ${yourCompany} directly solves this specific pain"
}]`;

  try {
    // Try with Google Search grounding first (live web results)
    const text = await callGemini(prompt, { useSearch: true });
    const signals = parseJSON(text, true);
    if (signals.length === 0) throw new Error('Empty result from search path');
    signalCache.set(competitor, { signals, ts: Date.now() });
    console.log(`Scanned ${competitor}: ${signals.length} signals (Google Search)`);
    return res.json(signals);
  } catch (err) {
    console.warn(`Search path failed for ${competitor}: ${err.message}, using training fallback`);
  }

  // Fallback: Gemini's training knowledge
  try {
    const fallbackPrompt = prompt.replace(
      `Research "${competitor}" and find`,
      `Based on your training knowledge, identify`
    );
    const text = await callGemini(fallbackPrompt, { useSearch: false });
    const signals = parseJSON(text, true);
    signalCache.set(competitor, { signals, ts: Date.now() });
    console.log(`Scanned ${competitor}: ${signals.length} signals (training knowledge)`);
    return res.json(signals);
  } catch (fallbackErr) {
    console.error('Both scan paths failed:', fallbackErr.message);
    return res.status(500).json({ error: fallbackErr.message });
  }
});

// ─── POST /api/prospects ─────────────────────────────────────────────────────
app.post('/api/prospects', async (req, res) => {
  const { signal, competitor, yourProduct } = req.body;

  const titlesByType = {
    PRICE:       ['VP of Sales', 'Chief Revenue Officer', 'VP Revenue Operations', 'Head of Sales Operations'],
    OUTAGE:      ['CTO', 'VP of Engineering', 'VP Infrastructure', 'Head of Platform Engineering'],
    LEADERSHIP:  ['CEO', 'Chief Executive Officer', 'VP of Sales', 'Chief Revenue Officer'],
    ACQUISITION: ['CEO', 'VP Sales', 'Chief Revenue Officer', 'Head of Corporate Strategy'],
    REVIEWS:     ['VP of Sales', 'Revenue Operations Director', 'Head of Sales Enablement', 'CRO'],
    FEATURE:     ['VP of Product', 'Chief Product Officer', 'VP Sales', 'Head of Operations'],
    SECURITY:    ['CISO', 'CTO', 'Chief Information Officer', 'VP Information Security'],
  };

  const titles = titlesByType[signal?.type] || ['VP Sales', 'CTO', 'Chief Revenue Officer'];

  // Try Apollo REST API
  if (APOLLO_API_KEY) {
    try {
      const apolloRes = await fetch('https://api.apollo.io/api/v1/mixed_people/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_key: APOLLO_API_KEY,
          person_titles: titles,
          per_page: 8,
          page: 1,
          sort_by_field: 'recommendations',
          sort_ascending: false,
        }),
      });

      if (apolloRes.ok) {
        const data = await apolloRes.json();
        const people = (data.people || []).slice(0, 8);
        if (people.length > 0) {
          return res.json(people.map(p => ({
            id: p.id || `ap-${Math.random().toString(36).slice(2)}`,
            name: p.name,
            title: p.title,
            company: p.organization?.name || 'Unknown',
            industry: p.organization?.industry || '',
            employees: p.organization?.estimated_num_employees || null,
            email: p.email || null,
            linkedin: p.linkedin_url || null,
          })));
        }
      }
    } catch (apolloErr) {
      console.warn('Apollo API error:', apolloErr.message);
    }
  }

  // Fallback: Gemini generates realistic fictional prospects
  const prompt = `Generate 8 realistic fictional B2B decision-makers who use ${competitor} and would be highly interested in ${yourProduct} given this issue: "${signal?.title || 'competitor pain point'}".

Target roles: ${titles.slice(0, 4).join(', ')}
Mix of company sizes: 150–5000 employees. Use real-sounding US company names across different industries.

Return ONLY valid JSON array:
[{
  "id": "p<n>",
  "name": "First Last",
  "title": "Job Title",
  "company": "Company Name",
  "industry": "Industry",
  "employees": <number>,
  "email": "firstname@company.com",
  "linkedin": "https://linkedin.com/in/firstname-lastname"
}]`;

  try {
    const text = await callGemini(prompt);
    const prospects = parseJSON(text, true);
    return res.json(prospects);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
});

// ─── POST /api/email ──────────────────────────────────────────────────────────
app.post('/api/email', async (req, res) => {
  const { prospect, signal, yourProduct, yourCompany } = req.body;

  const prompt = `Write a cold outreach email from ${yourCompany} (selling ${yourProduct}) to ${prospect.name}, ${prospect.title} at ${prospect.company}.

Signal context: ${signal.title}
Details: ${signal.description}

HARD RULES — violating any fails the task:
1. First sentence MUST directly reference this specific event: "${signal.title}"
2. Under 100 words total. Count them.
3. Peer-to-peer tone. No corporate speak, no "I hope this email finds you well"
4. ONE soft CTA: offer a 15-minute call or quick chat
5. Last sentence mentions ${yourProduct} by name and its specific value for this situation
6. No generic placeholders

Return ONLY valid JSON, no markdown:
{
  "subject": "subject line (under 60 chars)",
  "preview": "preview text (under 50 chars)",
  "body": "full email body text"
}`;

  try {
    const text = await callGemini(prompt);
    const email = parseJSON(text, false);
    return res.json(email);
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
});

// ─── Health check ─────────────────────────────────────────────────────────────
app.get('/api/health', (_, res) => res.json({ status: 'ok', ts: new Date().toISOString() }));

const PORT = process.env.PORT || 3001;
app.listen(PORT, () => {
  console.log(`\n🚀 Displacement API running on http://localhost:${PORT}`);
  console.log(`   Google AI key: ${process.env.GOOGLE_API_KEY ? '✓ set' : '✗ missing'}`);
  console.log(`   Apollo key:    ${process.env.APOLLO_API_KEY ? '✓ set' : '○ not set (will use AI fallback)'}\n`);
});
