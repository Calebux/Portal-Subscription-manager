#!/usr/bin/env node
/**
 * Swap CELO → cUSD via Mento on Celo mainnet
 * Run: node swap-celo-for-cusd.js [celo_amount]
 * Default: swaps 0.5 CELO
 *
 * After this, run: node fund-reserve.js
 */

require('./load-env');
const { ethers } = require('ethers');

const CELO_RPC      = 'https://forno.celo.org';
const CUSD_ADDR     = '0x765DE816845861e75A25fCA122bb6898B8B1282a';
const GOLD_TOKEN    = '0x471EcE3750Da237f93B8E339c536989b8978a438'; // ERC-20 CELO
const MENTO_EXCHANGE = '0x67316300f17f063085Ca8bCa4bd3f7a5a3C66275';

const EXCHANGE_ABI = [
  'function sell(uint256 sellAmount, uint256 minBuyAmount, bool sellGold) external returns (uint256)',
  'function getBuyTokenAmount(uint256 sellAmount, bool sellGold) external view returns (uint256)',
];

const GOLD_ABI = [
  'function approve(address spender, uint256 amount) external returns (bool)',
  'function balanceOf(address account) external view returns (uint256)',
];

const CUSD_ABI = [
  'function balanceOf(address account) external view returns (uint256)',
];

async function main() {
  const sellArg = process.argv[2] || '0.5';
  const sellAmount = ethers.parseEther(sellArg);

  const provider = new ethers.JsonRpcProvider(CELO_RPC);
  const wallet   = new ethers.Wallet(process.env.AGENT_PRIVATE_KEY, provider);

  const gold = new ethers.Contract(GOLD_TOKEN,     GOLD_ABI,     wallet);
  const cusd = new ethers.Contract(CUSD_ADDR,      CUSD_ABI,     provider);
  const exch = new ethers.Contract(MENTO_EXCHANGE, EXCHANGE_ABI, wallet);

  const goldBalance = await gold.balanceOf(wallet.address);
  const cusdBefore  = await cusd.balanceOf(wallet.address);

  console.log(`Wallet:      ${wallet.address}`);
  console.log(`CELO (ERC20):${ethers.formatEther(goldBalance)} CELO`);
  console.log(`cUSD before: ${ethers.formatEther(cusdBefore)} cUSD`);

  if (goldBalance < sellAmount) {
    console.error(`\nNot enough ERC-20 CELO. Have ${ethers.formatEther(goldBalance)}, need ${sellArg}`);
    console.error('Note: You need GoldToken (ERC-20 CELO), not native CELO gas token.');
    process.exit(1);
  }

  // Get quote
  const expected = await exch.getBuyTokenAmount(sellAmount, true);
  const minBuy   = expected * 95n / 100n; // 5% slippage
  console.log(`\nExpected:    ${ethers.formatEther(expected)} cUSD`);
  console.log(`Min (5% slip):${ethers.formatEther(minBuy)} cUSD`);

  // Approve
  console.log('\nApproving GoldToken...');
  const approveTx = await gold.approve(MENTO_EXCHANGE, sellAmount);
  await approveTx.wait();

  // Swap
  console.log(`Swapping ${sellArg} CELO → cUSD...`);
  const swapTx = await exch.sell(sellAmount, minBuy, true);
  const receipt = await swapTx.wait();

  const cusdAfter = await cusd.balanceOf(wallet.address);
  const received  = cusdAfter - cusdBefore;

  console.log(`  Tx: ${receipt.hash}`);
  console.log(`\n✅ Received: ${ethers.formatEther(received)} cUSD`);
  console.log(`   cUSD balance: ${ethers.formatEther(cusdAfter)} cUSD`);
  console.log('\nNow run: node fund-reserve.js');
}

main().catch(e => { console.error(e.message); process.exit(1); });
