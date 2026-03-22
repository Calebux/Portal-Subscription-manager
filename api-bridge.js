#!/usr/bin/env node
/**
 * SubBot API Bridge — localhost:3747
 * Connects the browser extension to the Hermes agent Python scripts.
 * Run: node ~/.hermes/api-bridge.js
 */

require('./load-env');
const express = require('express');
const cors    = require('cors');
const { exec } = require('child_process');
const fs      = require('fs');
const path    = require('path');
const https   = require('https');

// On-chain contracts (SubBotLog + SubBotVault)
let logContract   = null;
let vaultContract = null;

(async () => {
  const privateKey = process.env.AGENT_PRIVATE_KEY;
  if (!privateKey) return;
  try {
    const { ethers } = require('ethers');
    const CELO_RPC   = 'https://forno.celo.org';
    const provider   = new ethers.JsonRpcProvider(CELO_RPC);
    const wallet     = new ethers.Wallet(privateKey, provider);

    if (process.env.LOG_CONTRACT_ADDRESS) {
      const LOG_ABI = [
        "function logDecision(string calldata userId, string calldata action, uint256 amountSavedUSD) external",
        "function getDecisionCount() external view returns (uint256)",
        "function getTotalSavingsUSD() external view returns (uint256)",
        "event DecisionLogged(address indexed agent, bytes32 indexed userHash, string action, uint256 amountSavedUSD, uint256 timestamp)"
      ];
      logContract = new ethers.Contract(process.env.LOG_CONTRACT_ADDRESS, LOG_ABI, wallet);
      console.log(`[SubBot] Decision log active → ${process.env.LOG_CONTRACT_ADDRESS}`);
    }

    if (process.env.VAULT_CONTRACT_ADDRESS) {
      const vaultABI = require('./build/SubBotVault.abi.json');
      vaultContract  = new ethers.Contract(process.env.VAULT_CONTRACT_ADDRESS, vaultABI, wallet);
      console.log(`[SubBot] Vault active         → ${process.env.VAULT_CONTRACT_ADDRESS}`);
    }
  } catch (e) {
    console.warn('[SubBot] Contract init failed:', e.message);
  }
})();

const app  = express();
const PORT = process.env.PORT || 3747;
const HERMES_HOME = process.env.DATA_DIR || path.join(process.env.HOME || '/tmp', '.hermes');
const USER_DATA   = path.join(HERMES_HOME, 'user-data');
const CELO_RPC    = 'https://rpc.ankr.com/celo';
const CUSD_ADDR   = '0x765DE816845861e75A25fCA122bb6898B8B1282a'; // cUSD mainnet


app.use(cors({ origin: '*' }));
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

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

// Bulk sync — bot pushes full data file to Railway after every update
app.post('/sync', (req, res) => {
  const { userId = 'local', data } = req.body;
  if (!data) return res.status(400).json({ error: 'data required' });
  const file = path.join(userDir(userId), 'scanned-subscriptions.json');
  writeJSON(file, data);
  res.json({ ok: true, count: (data.subscriptions || []).length });
});

// Get subscriptions
app.get('/subs', (req, res) => {
  const userId = req.query.userId || 'local';
  const file   = path.join(userDir(userId), 'scanned-subscriptions.json');
  const data   = readJSON(file);
  res.json(data || { subscriptions: [], cancellation_history: [], monthly_budget: null });
});

// Add a single subscription (from extension manual add)
app.post('/add-sub', (req, res) => {
  const { sub, userId = 'local' } = req.body;
  if (!sub || !sub.name) return res.status(400).json({ error: 'sub.name required' });
  const file = path.join(userDir(userId), 'scanned-subscriptions.json');
  const data = readJSON(file) || { subscriptions: [], cancellation_history: [], monthly_budget: null };
  // Avoid duplicates by id
  data.subscriptions = data.subscriptions.filter(s => s.id !== sub.id);
  data.subscriptions.push(sub);
  writeJSON(file, data);
  res.json({ ok: true, count: data.subscriptions.length });
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

// Run LLM-powered audit (delegates to llm-analyze.py for contextual reasoning)
app.post('/audit', async (req, res) => {
  const { userId = 'local' } = req.body;
  const file = path.join(userDir(userId), 'scanned-subscriptions.json');
  const data = readJSON(file);
  if (!data) return res.json({ monthly: 0, annual: 0, overlaps: [], subs: [] });

  // Return cached LLM analysis if it's fresh (< 1 hour old)
  const analysisFile = path.join(userDir(userId), 'llm-analysis.json');
  const cached = readJSON(analysisFile);
  if (cached && cached.generated_at) {
    const ageMs = Date.now() - new Date(cached.generated_at).getTime();
    if (ageMs < 60 * 60 * 1000) {
      return res.json({ ...cached, source: 'cache' });
    }
  }

  // Run LLM analysis in background — return basic summary immediately,
  // full results available via GET /analysis once complete
  const subs    = (data.subscriptions || []).filter(s => s.status === 'active');
  const monthly = subs.reduce((sum, s) => sum + (s.monthly_cost_usd || s.monthly_cost || 0), 0);

  // Fire off LLM analysis asynchronously
  runPy(`llm-analyze.py --user-id ${userId}`)
    .then(() => console.log(`[audit] LLM analysis complete for ${userId}`))
    .catch(e  => console.warn(`[audit] LLM analysis failed: ${e.error}`));

  res.json({
    monthly,
    annual:   monthly * 12,
    subs,
    budget:   data.monthly_budget,
    source:   'basic',
    message:  'Full LLM analysis running — check GET /analysis in a few seconds',
  });
});

// Get latest LLM analysis result
app.get('/analysis', (req, res) => {
  const userId       = req.query.userId || 'local';
  const analysisFile = path.join(userDir(userId), 'llm-analysis.json');
  const analysis     = readJSON(analysisFile);
  if (!analysis) return res.status(404).json({ error: 'No analysis yet — run /audit first' });
  res.json(analysis);
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

// Draft LLM-personalized negotiation email
app.post('/negotiate', async (req, res) => {
  const { serviceName, userId = 'local' } = req.body;
  if (!serviceName) return res.status(400).json({ error: 'serviceName required' });

  // Load subscription context for this service
  const file = path.join(userDir(userId), 'scanned-subscriptions.json');
  const data = readJSON(file) || {};
  const subs = data.subscriptions || [];
  const sub  = subs.find(s => s.name.toLowerCase() === serviceName.toLowerCase());

  // Check if LLM analysis has a strategy for this service
  const analysisFile = path.join(userDir(userId), 'llm-analysis.json');
  const analysis     = readJSON(analysisFile);
  const candidate    = analysis?.negotiation_candidates?.find(
    c => c.service.toLowerCase() === serviceName.toLowerCase()
  );

  // If we have full context, run LLM negotiation script
  if (sub && process.env.OPENAI_API_KEY) {
    try {
      const out = await runPy(
        `negotiate.py --user-id ${userId} --service "${serviceName}"`
      );
      const result = JSON.parse(out.trim());
      return res.json(result);
    } catch (_) {
      // Fall through to contextual fallback below
    }
  }

  // Contextual fallback: better than generic template, uses whatever data we have
  const healthScore  = sub?.health_score;
  const monthlyCost  = sub?.monthly_cost_usd || sub?.monthly_cost || 0;
  const renewalDate  = sub?.next_renewal || '';
  const strategy     = candidate?.strategy || '';
  const expectedDisc = candidate?.expected_discount_pct || 20;

  // Find overlapping services as leverage
  const overlaps = analysis?.overlaps?.find(o =>
    o.services.some(s => s.toLowerCase() === serviceName.toLowerCase())
  );
  const competitor = overlaps?.services?.find(
    s => s.toLowerCase() !== serviceName.toLowerCase()
  ) || '';

  const competitorLine = competitor
    ? `\n\nI'm currently also evaluating ${competitor} as an alternative.`
    : '';

  const email = {
    to:       `support@${serviceName.toLowerCase().replace(/\s+/g, '').replace(/[^a-z0-9]/g, '')}.com`,
    subject:  `Subscription Review — ${serviceName}`,
    body:     `Hi team,\n\nI've been a ${serviceName} subscriber and I'm currently doing a full review of my AI/SaaS spending.${competitorLine}\n\nBefore I make any changes, I wanted to check — do you have any retention offers, annual plan discounts, or paused-subscription options? I've seen ${expectedDisc}% discounts mentioned in the community.\n\nIf there's a plan that works better for my budget, I'd love to stay. Please let me know what's available.\n\nThank you,\n[Your Name]`,
    context:  {
      healthScore,
      monthlyCost,
      renewalDate,
      strategy,
      competitor,
    },
  };

  res.json(email);
});

// Log agent decision on Celo blockchain
// Called by the LLM (via Python scripts) after every significant recommendation.
// Creates an immutable on-chain audit trail of the agent's decisions.
app.post('/log-decision', async (req, res) => {
  const { userId = 'local', action, amountSavedUSD = 0 } = req.body;
  if (!action) return res.status(400).json({ error: 'action required' });

  // Always save locally regardless of on-chain status
  const file   = path.join(userDir(userId), 'decision-log.json');
  const log    = readJSON(file) || { decisions: [], totalSavedUSD: 0 };
  const entry  = {
    action,
    amountSavedUSD,
    timestamp: new Date().toISOString(),
    onChain:   false,
    txHash:    null,
  };

  if (logContract) {
    try {
      // Convert USD to cents for the contract (avoids decimals)
      const cents = Math.round(amountSavedUSD * 100);
      const tx    = await logContract.logDecision(userId, action, cents);
      await tx.wait();
      entry.onChain = true;
      entry.txHash  = tx.hash;
      console.log(`[chain] ${action} for ${userId} → ${tx.hash}`);
    } catch (e) {
      console.warn(`[chain] logDecision failed: ${e.message}`);
    }
  }

  log.decisions  = [entry, ...log.decisions].slice(0, 500);
  log.totalSavedUSD = (log.totalSavedUSD || 0) + amountSavedUSD;
  writeJSON(file, log);

  res.json({
    ok:      true,
    onChain: entry.onChain,
    txHash:  entry.txHash,
    action,
    amountSavedUSD,
  });
});

// Get agent decision history (local + on-chain status)
app.get('/decisions', (req, res) => {
  const userId = req.query.userId || 'local';
  const file   = path.join(userDir(userId), 'decision-log.json');
  res.json(readJSON(file) || { decisions: [], totalSavedUSD: 0 });
});

// ── Vault routes ────────────────────────────────────────────────────────────

// GET /vault/:userId — full vault state
app.get('/vault/:userId', async (req, res) => {
  if (!vaultContract) return res.status(503).json({ error: 'Vault not configured', configured: false });
  const { ethers } = require('ethers');
  try {
    const r = await vaultContract.getVault(req.params.userId);
    res.json({
      principal:        ethers.formatEther(r.principal),
      credits:          ethers.formatEther(r.credits),
      pending:          ethers.formatEther(r.pending),
      totalYieldEarned: ethers.formatEther(r.totalYieldEarned),
      totalSpent:       ethers.formatEther(r.totalSpent),
      selfSustaining:   r.selfSustaining,
      vaultAddress:     process.env.VAULT_CONTRACT_ADDRESS,
      apy:              '10%',
    });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// POST /vault/harvest — agent harvests pending yield into credits
app.post('/vault/harvest', async (req, res) => {
  if (!vaultContract) return res.status(503).json({ error: 'Vault not configured' });
  const { userId } = req.body;
  if (!userId) return res.status(400).json({ error: 'userId required' });
  try {
    const tx    = await vaultContract.harvestYield(userId);
    const rcpt  = await tx.wait();
    const { ethers } = require('ethers');
    const r     = await vaultContract.getVault(userId);
    res.json({ ok: true, txHash: tx.hash, credits: ethers.formatEther(r.credits) });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// POST /vault/spend — agent spends credits for an operation
app.post('/vault/spend', async (req, res) => {
  if (!vaultContract) return res.status(503).json({ error: 'Vault not configured' });
  const { userId, action } = req.body;
  if (!userId || !action) return res.status(400).json({ error: 'userId and action required' });

  const COSTS = { scan: '2000000000000000', audit: '2000000000000000',
                  negotiate: '5000000000000000', export: '1000000000000000' };
  const cost = COSTS[action];
  if (!cost) return res.status(400).json({ error: `Unknown action: ${action}` });

  try {
    const tx = await vaultContract.spendCredits(userId, cost, action);
    await tx.wait();
    const { ethers } = require('ethers');
    const r  = await vaultContract.getVault(userId);
    res.json({ ok: true, txHash: tx.hash, action, costCUSD: ethers.formatEther(cost),
               creditsRemaining: ethers.formatEther(r.credits) });
  } catch (e) {
    // If vault credits are insufficient, fall back to wallet balance (old pay-per-run)
    res.status(402).json({ error: e.message, fallback: 'wallet_balance' });
  }
});

// POST /vault/withdraw — return principal to user's wallet
app.post('/vault/withdraw', async (req, res) => {
  if (!vaultContract) return res.status(503).json({ error: 'Vault not configured' });
  const { userId, amount, toAddress } = req.body;
  if (!userId || !amount || !toAddress) return res.status(400).json({ error: 'userId, amount, toAddress required' });
  try {
    const { ethers } = require('ethers');
    const tx = await vaultContract.withdrawPrincipal(userId, ethers.parseEther(String(amount)), toAddress);
    await tx.wait();
    res.json({ ok: true, txHash: tx.hash, amount, toAddress });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// POST /vault/fund-reserve — fund yield reserve (admin)
app.post('/vault/fund-reserve', async (req, res) => {
  res.json({ vaultAddress: process.env.VAULT_CONTRACT_ADDRESS,
             instructions: 'Call fundReserve(amount) on the vault contract with cUSD approved first.' });
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
