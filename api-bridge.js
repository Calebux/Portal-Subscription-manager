#!/usr/bin/env node
/**
 * SubBot API Bridge — localhost:3747
 * Connects the browser extension to the Hermes agent Python scripts.
 * Run: node ~/.hermes/api-bridge.js
 */

const express = require('express');
const cors    = require('cors');
const { exec } = require('child_process');
const fs      = require('fs');
const path    = require('path');
const https   = require('https');

const app  = express();
const PORT = process.env.PORT || 3747;
const HERMES_HOME = process.env.DATA_DIR || path.join(process.env.HOME || '/tmp', '.hermes');
const USER_DATA   = path.join(HERMES_HOME, 'user-data');
const CELO_RPC    = 'https://rpc.ankr.com/celo';
const CUSD_ADDR   = '0x765DE816845861e75A25fCA122bb6898B8B1282a'; // cUSD mainnet

const DEMO_DATA = {
  subscriptions: [
    { id: 'claude-pro', name: 'Claude Pro', provider: 'Anthropic', category: 'ai', monthly_cost: 20, monthly_cost_usd: 20, currency: 'USD', billing_cycle: 'monthly', next_renewal: new Date(Date.now() + 12 * 86400000).toISOString().slice(0,10), status: 'active', health_score: 85 },
    { id: 'chatgpt-plus', name: 'ChatGPT Plus', provider: 'OpenAI', category: 'ai', monthly_cost: 20, monthly_cost_usd: 20, currency: 'USD', billing_cycle: 'monthly', next_renewal: new Date(Date.now() + 9 * 86400000).toISOString().slice(0,10), status: 'active', health_score: 65 },
    { id: 'github-copilot', name: 'GitHub Copilot', provider: 'GitHub', category: 'ai', monthly_cost: 10, monthly_cost_usd: 10, currency: 'USD', billing_cycle: 'monthly', next_renewal: new Date(Date.now() + 16 * 86400000).toISOString().slice(0,10), status: 'active', health_score: 78 },
    { id: 'cursor', name: 'Cursor', provider: 'Cursor', category: 'ai', monthly_cost: 20, monthly_cost_usd: 20, currency: 'USD', billing_cycle: 'monthly', next_renewal: new Date(Date.now() + 21 * 86400000).toISOString().slice(0,10), status: 'active', health_score: 90 },
    { id: 'starlink', name: 'Starlink', provider: 'SpaceX', category: 'other', monthly_cost: 41.55, monthly_cost_usd: 41.55, currency: 'USD', billing_cycle: 'monthly', next_renewal: new Date(Date.now() + 20 * 86400000).toISOString().slice(0,10), status: 'active', health_score: 70 },
  ],
  cancellation_history: [],
  monthly_budget: 120,
};

app.use(cors({ origin: '*' }));
app.use(express.json());

// ── Helpers ────────────────────────────────────────────────────────────────

function userDir(userId = 'local') {
  const d = path.join(USER_DATA, userId);
  if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
  return d;
}

function readJSON(file) {
  if (!fs.existsSync(file)) return null;
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch(e) { return null; }
}

function writeJSON(file, data) {
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
}

function runPy(cmd) {
  return new Promise((resolve, reject) => {
    exec(`python3 ${HERMES_HOME}/${cmd}`, { timeout: 60000 }, (err, stdout, stderr) => {
      if (err) reject({ error: err.message, stderr });
      else resolve(stdout);
    });
  });
}

// cUSD balance via Celo JSON-RPC (eth_call for ERC-20 balanceOf)
function celoRPC(method, params) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ jsonrpc:'2.0', id:1, method, params });
    const req = https.request(CELO_RPC, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }
    }, res => {
      let data = '';
      res.on('data', d => data += d);
      res.on('end', () => { try { resolve(JSON.parse(data)); } catch(e) { reject(e); } });
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

async function getCUSDBalance(address) {
  // ERC-20 balanceOf(address) selector = 0x70a08231
  const padded = address.slice(2).padStart(64, '0');
  const data   = '0x70a08231' + padded;
  const result = await celoRPC('eth_call', [{ to: CUSD_ADDR, data }, 'latest']);
  if (!result.result || result.result === '0x') return '0';
  const wei = BigInt(result.result);
  const cusd = Number(wei) / 1e18;
  return cusd.toFixed(4);
}

// ── Routes ─────────────────────────────────────────────────────────────────

// Health check
app.get('/health', (req, res) => res.json({ ok: true, version: '1.0' }));

// Get subscriptions
app.get('/subs', (req, res) => {
  const userId = req.query.userId || 'local';
  const file   = path.join(userDir(userId), 'scanned-subscriptions.json');
  const data   = readJSON(file);
  res.json(data || DEMO_DATA);
});

// Scan Gmail inbox
app.post('/scan', async (req, res) => {
  const { email, password, userId = 'local' } = req.body;
  if (!email || !password) return res.status(400).json({ error: 'email and password required' });
  try {
    const out = await runPy(`gmail-scanner.py --email "${email}" --password "${password}" --user-id ${userId}`);
    const file = path.join(userDir(userId), 'scanned-subscriptions.json');
    const data = readJSON(file);
    res.json(data || { subscriptions: [] });
  } catch(e) {
    res.status(500).json({ error: e.error || 'Scan failed', detail: e.stderr });
  }
});

// Run audit (reads existing subs, returns summary)
app.post('/audit', (req, res) => {
  const { userId = 'local' } = req.body;
  const file  = path.join(userDir(userId), 'scanned-subscriptions.json');
  const data  = readJSON(file);
  if (!data) return res.json({ monthly: 0, annual: 0, overlaps: [], subs: [] });

  const subs    = (data.subscriptions || []).filter(s => s.status === 'active');
  const monthly = subs.reduce((sum, s) => sum + (s.monthly_cost || 0), 0);
  const cats    = {};
  subs.forEach(s => { const c = s.category || 'other'; cats[c] = (cats[c] || []).concat(s.name); });
  const overlaps = Object.entries(cats).filter(([,n]) => n.length > 1).map(([cat, names]) => ({ cat, names }));

  res.json({ monthly, annual: monthly * 12, overlaps, subs, budget: data.monthly_budget });
});

// Export CSV (calls export.py which sends to Telegram)
app.post('/export', async (req, res) => {
  const { userId = 'local' } = req.body;
  try {
    await runPy(`export.py --user-id ${userId} --notify`);
    res.json({ ok: true, message: 'CSV sent to Telegram' });
  } catch(e) {
    // Fallback — return CSV data for browser download
    const file = path.join(userDir(userId), 'scanned-subscriptions.json');
    const data = readJSON(file);
    if (!data) return res.status(500).json({ error: 'No data to export' });
    const subs = data.subscriptions || [];
    const csv  = ['Name,Provider,Category,Monthly Cost,Currency,Renewal,Status,Health']
      .concat(subs.map(s => `${s.name},${s.provider},${s.category},${s.monthly_cost},${s.currency},${s.next_renewal},${s.status},${s.health_score}`))
      .join('\n');
    res.setHeader('Content-Type', 'text/csv');
    res.setHeader('Content-Disposition', 'attachment; filename=subbot-subscriptions.csv');
    res.send(csv);
  }
});

// Draft negotiation email
app.post('/negotiate', (req, res) => {
  const { serviceName, userId = 'local' } = req.body;
  const email = {
    to:      `support@${(serviceName || 'service').toLowerCase().replace(/\s+/g,'')}.com`,
    subject: `Cancellation / Retention Request — ${serviceName}`,
    body:    `Hi team,\n\nI've been a loyal ${serviceName} subscriber for a while but I'm currently reviewing my AI/SaaS spending. Before I cancel, I wanted to check — do you have any retention offers, annual discounts, or reduced-feature plans available?\n\nIf there's something that works for my budget, I'd love to continue. Please let me know.\n\nThank you,\n[Your Name]`
  };
  res.json(email);
});

// Celo cUSD balance
app.get('/balance', async (req, res) => {
  const { address } = req.query;
  if (!address) return res.status(400).json({ error: 'address required' });
  try {
    const balance = await getCUSDBalance(address);
    res.json({ address, balance, currency: 'cUSD' });
  } catch(e) {
    res.status(500).json({ error: 'RPC error', detail: e.message, balance: '0' });
  }
});

// Record credit deduction
app.post('/deduct', (req, res) => {
  const { action, cost, walletAddress, userId = 'local' } = req.body;
  const file   = path.join(userDir(userId), 'credits.json');
  const ledger = readJSON(file) || { walletAddress, transactions: [] };
  ledger.walletAddress = walletAddress || ledger.walletAddress;
  ledger.transactions  = [{ type:'deduct', action, amount: cost, ts: new Date().toISOString() }, ...ledger.transactions].slice(0, 200);
  writeJSON(file, ledger);
  res.json({ ok: true });
});

// Get credit history
app.get('/history', (req, res) => {
  const userId = req.query.userId || 'local';
  const file   = path.join(userDir(userId), 'credits.json');
  res.json(readJSON(file) || { transactions: [] });
});

// Save budget
app.post('/budget', (req, res) => {
  const { budget, userId = 'local' } = req.body;
  const file = path.join(userDir(userId), 'scanned-subscriptions.json');
  const data = readJSON(file) || { subscriptions: [], cancellation_history: [] };
  data.monthly_budget = budget;
  writeJSON(file, data);
  res.json({ ok: true, budget });
});

// ── Start ──────────────────────────────────────────────────────────────────
app.listen(PORT, '0.0.0.0', () => {
  console.log(`[SubBot Bridge] Running at http://0.0.0.0:${PORT}`);
  console.log(`[SubBot Bridge] HERMES_HOME: ${HERMES_HOME}`);
});
