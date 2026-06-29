#!/usr/bin/env node
/**
 * Deploy SubBot contracts to Celo Mainnet
 * Run: node deploy-contract.js [SubBotCredits|SubBotLog]
 * Requires: .env with AGENT_PRIVATE_KEY, wallet funded with CELO for gas
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

  const target = process.argv[2] || 'SubBotCredits';

  // ── Deploy SubBotLog (skip if already deployed) ──────────────────────────
  let logAddress = process.env.LOG_CONTRACT_ADDRESS;
  if (target === 'SubBotLog' || !logAddress) {
    const logABI      = JSON.parse(fs.readFileSync('build/SubBotLog.abi.json', 'utf8'));
    const logBytecode = fs.readFileSync('build/SubBotLog.bytecode.txt', 'utf8').trim();
    const { address } = await deployContract('SubBotLog', logABI, logBytecode, wallet);
    logAddress = address;
  } else {
    console.log(`\nSubBotLog already deployed → ${logAddress} (skipping)`);
  }

  // ── Deploy SubBotCredits ─────────────────────────────────────────────────
  if (target === 'SubBotCredits') {
    const creditsABI      = JSON.parse(fs.readFileSync('build/SubBotCredits.abi.json', 'utf8'));
    const creditsBytecode = fs.readFileSync('build/SubBotCredits.bytecode.txt', 'utf8').trim();

    // constructor(address _agent) — agent = deployer wallet
    const { address: creditsAddress } = await deployContract(
      'SubBotCredits', creditsABI, creditsBytecode, wallet, wallet.address
    );

    // Save address to .env
    const envFile = path.join(__dirname, '.env');
    let env = fs.readFileSync(envFile, 'utf8');
    env = env.replace(/LOG_CONTRACT_ADDRESS=.*/, `LOG_CONTRACT_ADDRESS=${logAddress}`);
    if (env.includes('CREDITS_CONTRACT_ADDRESS=')) {
      env = env.replace(/CREDITS_CONTRACT_ADDRESS=.*/, `CREDITS_CONTRACT_ADDRESS=${creditsAddress}`);
    } else {
      env += `\nCREDITS_CONTRACT_ADDRESS=${creditsAddress}\n`;
    }
    fs.writeFileSync(envFile, env);

    console.log(`\n✅ SubBotCredits deployed. Address saved to .env`);
    console.log(`G$ token: 0x62B8B11039FcfE5aB0C56E502b1C372A3d2a9c7A`);
    console.log(`\nRestart api-bridge.js to activate credits endpoints:`);
    console.log(`   node api-bridge.js`);
  }
}

main().catch(e => { console.error(e.message); process.exit(1); });
