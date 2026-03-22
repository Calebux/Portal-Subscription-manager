#!/usr/bin/env node
/**
 * Fund the SubBotVault reserve with cUSD
 * Run: node fund-reserve.js [amount]
 * Default: 5 cUSD
 *
 * The reserve backs yield payouts. 5 cUSD @ 10% APY supports
 * ~50 cUSD in user deposits for 1 year.
 *
 * If you don't have cUSD, run: node swap-celo-for-cusd.js first
 */

require('./load-env');
const { ethers } = require('ethers');
const fs = require('fs');

const CELO_RPC  = 'https://forno.celo.org';
const CUSD_ADDR = '0x765DE816845861e75A25fCA122bb6898B8B1282a';

async function main() {
  const amountArg = process.argv[2] || '5';
  const amount = ethers.parseEther(amountArg);

  const vaultAddress = process.env.VAULT_CONTRACT_ADDRESS;
  if (!vaultAddress) { console.error('VAULT_CONTRACT_ADDRESS not set in .env'); process.exit(1); }

  const provider = new ethers.JsonRpcProvider(CELO_RPC);
  const wallet   = new ethers.Wallet(process.env.AGENT_PRIVATE_KEY, provider);

  const cusd = new ethers.Contract(CUSD_ADDR, [
    'function approve(address spender, uint256 amount) external returns (bool)',
    'function balanceOf(address account) external view returns (uint256)',
  ], wallet);

  const balance = await cusd.balanceOf(wallet.address);
  console.log(`Wallet:  ${wallet.address}`);
  console.log(`cUSD:    ${ethers.formatEther(balance)} cUSD`);
  console.log(`Funding: ${amountArg} cUSD → ${vaultAddress}`);

  if (balance < amount) {
    console.error(`\nNot enough cUSD. Have ${ethers.formatEther(balance)}, need ${amountArg}`);
    console.error('Get cUSD by running: node swap-celo-for-cusd.js');
    process.exit(1);
  }

  const vaultABI = JSON.parse(fs.readFileSync('build/SubBotVault.abi.json', 'utf8'));
  const vault    = new ethers.Contract(vaultAddress, vaultABI, wallet);

  console.log('\nApproving cUSD transfer...');
  const approveTx = await cusd.approve(vaultAddress, amount);
  await approveTx.wait();
  console.log('  Approved');

  console.log('Calling fundReserve...');
  const fundTx = await vault.fundReserve(amount);
  const receipt = await fundTx.wait();
  console.log(`  Tx: ${receipt.hash}`);
  console.log(`\n✅ Vault reserve funded with ${amountArg} cUSD`);
  console.log(`   This backs yield for ~${parseFloat(amountArg) * 10} cUSD in deposits for 1 year`);
  console.log(`\nVerify: https://celoscan.io/address/${vaultAddress}`);
}

main().catch(e => { console.error(e.message); process.exit(1); });
