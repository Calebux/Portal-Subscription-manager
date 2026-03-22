#!/usr/bin/env node
/**
 * Deploy SubBotLog + SubBotVault to Celo Mainnet
 * Run: node deploy-contract.js
 * Requires: .env with AGENT_PRIVATE_KEY, wallet funded with CELO for gas
 *
 * SubBotVault earns real yield via Aave v3 on Celo — no reserve seeding needed.
 * User deposits go directly into Aave. Yield comes from real borrowers paying interest.
 */

require('./load-env');
const { ethers } = require('ethers');
const fs   = require('fs');
const path = require('path');

async function deployContract(name, abi, bytecode, wallet, ...args) {
  console.log(`\nDeploying ${name}...`);
  const factory  = new ethers.ContractFactory(abi, bytecode, wallet);
  const contract = await factory.deploy(...args);
  console.log(`  Tx: ${contract.deploymentTransaction().hash}`);
  await contract.waitForDeployment();
  const address = await contract.getAddress();
  console.log(`  ✅ ${name} → ${address}`);
  console.log(`     CeloScan: https://celoscan.io/address/${address}`);
  return { contract, address };
}

const CELO_RPC = 'https://forno.celo.org';

async function main() {
  const privateKey = process.env.AGENT_PRIVATE_KEY;
  if (!privateKey) { console.error('AGENT_PRIVATE_KEY not set in .env'); process.exit(1); }

  const provider = new ethers.JsonRpcProvider(CELO_RPC);
  const wallet   = new ethers.Wallet(privateKey, provider);
  const network  = await provider.getNetwork();
  const balance  = await provider.getBalance(wallet.address);

  console.log(`Network:  Celo (chainId ${network.chainId})`);
  console.log(`Deployer: ${wallet.address}`);
  console.log(`Balance:  ${ethers.formatEther(balance)} CELO`);
  console.log(`\nYield source: Aave v3 on Celo (0x3E59A31363E2ad014dcbc521c4a0d5757d9f3402)`);
  console.log(`Asset:        cUSD / USDm (0x765DE816845861e75A25fCA122bb6898B8B1282a)`);

  // ── Deploy SubBotLog (skip if already deployed) ──────────────────────────
  let logAddress = process.env.LOG_CONTRACT_ADDRESS;
  if (!logAddress) {
    const logABI      = JSON.parse(fs.readFileSync('build/SubBotLog.abi.json', 'utf8'));
    const logBytecode = fs.readFileSync('build/SubBotLog.bytecode.txt', 'utf8').trim();
    const { address } = await deployContract('SubBotLog', logABI, logBytecode, wallet);
    logAddress = address;
  } else {
    console.log(`\nSubBotLog already deployed → ${logAddress} (skipping)`);
  }

  // ── Deploy SubBotVault ───────────────────────────────────────────────────
  const vaultABI      = JSON.parse(fs.readFileSync('build/SubBotVault.abi.json', 'utf8'));
  const vaultBytecode = fs.readFileSync('build/SubBotVault.bytecode.txt', 'utf8').trim();

  // agent = deployer wallet (will sign vault transactions)
  const { address: vaultAddress } = await deployContract(
    'SubBotVault', vaultABI, vaultBytecode, wallet, wallet.address
  );

  console.log(`\nNo reserve seeding needed — yield comes from Aave v3 borrowers.`);
  console.log(`Users deposit cUSD → vault supplies to Aave → real yield accrues automatically.`);

  // ── Save addresses to .env ───────────────────────────────────────────────
  const envFile = path.join(__dirname, '.env');
  let env = fs.readFileSync(envFile, 'utf8');
  env = env.replace(/LOG_CONTRACT_ADDRESS=.*/, `LOG_CONTRACT_ADDRESS=${logAddress}`);
  if (env.includes('VAULT_CONTRACT_ADDRESS=')) {
    env = env.replace(/VAULT_CONTRACT_ADDRESS=.*/, `VAULT_CONTRACT_ADDRESS=${vaultAddress}`);
  } else {
    env += `\nVAULT_CONTRACT_ADDRESS=${vaultAddress}\n`;
  }
  fs.writeFileSync(envFile, env);

  console.log(`\n✅ All done. Addresses saved to .env`);
  console.log(`\nRestart api-bridge.js to activate vault endpoints:`);
  console.log(`   node api-bridge.js`);
}

main().catch(e => { console.error(e.message); process.exit(1); });
