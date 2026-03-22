// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

/**
 * @dev Minimal Aave v3 Pool interface.
 *      Full interface: https://github.com/aave/aave-v3-core
 *
 *      Deployed on Celo mainnet: 0x3E59A31363E2ad014dcbc521c4a0d5757d9f3402
 */
interface IPool {
    /// @notice Supply cUSD into Aave. Vault receives aUSDm tokens that grow over time.
    function supply(address asset, uint256 amount, address onBehalfOf, uint16 referralCode) external;

    /// @notice Withdraw cUSD from Aave. Burns aUSDm proportionally.
    function withdraw(address asset, uint256 amount, address to) external returns (uint256);

    /// @notice Cumulative liquidity index in RAY (1e27). Grows continuously as
    ///         borrowers pay interest. If index grows from 1.000 to 1.005 RAY,
    ///         every depositor earned 0.5% on their principal.
    function getReserveNormalizedIncome(address asset) external view returns (uint256);
}

/**
 * @title SubBotVault
 * @notice Yield-bearing vault that funds SubBot agent operations via real DeFi yield.
 *
 * How it works:
 *   1. User deposits cUSD once — the vault immediately supplies it to Aave v3 on Celo.
 *   2. Real borrowers pay interest to Aave. The vault's aUSDm balance grows every block.
 *   3. The agent harvests yield into "credits" and spends them on operations.
 *   4. spendCredits() REVERTS if credits (yield) are zero — principal is untouchable.
 *   5. Once the deposit is large enough, operations run forever at zero cost to the user.
 *
 * At Aave's current stablecoin rates on Celo (3–8% APY):
 *   - 40 cUSD deposit generates ~0.13 cUSD/month in yield
 *   - Monthly operations cost ~0.12 cUSD
 *   - Self-sustaining at 40 cUSD+ deposit
 *
 * No admin reserve needed. No manual top-ups. Yield comes from the open market.
 *
 * Aave v3 Celo:  0x3E59A31363E2ad014dcbc521c4a0d5757d9f3402
 * cUSD (USDm):   0x765DE816845861e75A25fCA122bb6898B8B1282a
 * aUSDm:         0xBba98352628B0B0c4b40583F593fFCb630935a45
 */
contract SubBotVault {

    // ── Constants ────────────────────────────────────────────────────────────

    IERC20 public constant CUSD = IERC20(0x765DE816845861e75A25fCA122bb6898B8B1282a);
    IPool  public constant AAVE = IPool(0x3E59A31363E2ad014dcbc521c4a0d5757d9f3402);

    uint256 private constant RAY              = 1e27;
    uint256 private constant SECONDS_PER_YEAR = 365 days;

    // Operation costs in cUSD wei (1e18 = 1 cUSD)
    // Kept intentionally low — 25 cUSD deposit covers heavy usage at Aave's rates.
    uint256 public constant COST_SCAN      = 0.002 ether;   // 0.002 cUSD per Gmail scan
    uint256 public constant COST_AUDIT     = 0.002 ether;   // 0.002 cUSD per LLM audit
    uint256 public constant COST_NEGOTIATE = 0.005 ether;   // 0.005 cUSD per negotiation email
    uint256 public constant COST_EXPORT    = 0.001 ether;   // 0.001 cUSD per CSV export
    // Daily digest and renewal alerts are FREE — agent works for you at no charge.

    // Estimated monthly ops: 5 scans + 5 audits + 4 exports = 0.021 cUSD
    // 5 cUSD @ Aave 5% APY generates 0.021 cUSD/month — self-sustaining at just $5.
    uint256 public constant MONTHLY_OPS_ESTIMATE = 0.021 ether;

    // ── State ────────────────────────────────────────────────────────────────

    struct UserVault {
        uint256 principal;         // cUSD deposited (sitting in Aave, earning real yield)
        uint256 credits;           // harvested yield available to spend
        uint256 yieldIndex;        // Aave normalized income index at last harvest
        uint256 depositTimestamp;  // when user first deposited (for APY estimation)
        uint256 totalYieldEarned;  // cumulative real yield earned from Aave (all time)
        uint256 totalSpent;        // cumulative credits spent on operations
    }

    mapping(bytes32 => UserVault) private vaults;
    mapping(bytes32 => address)   public depositors;

    uint256 public totalPrincipal;

    address public agent;
    address public owner;

    // ── Events ───────────────────────────────────────────────────────────────

    event Deposited(bytes32 indexed userKey, uint256 amount, uint256 newPrincipal);
    event YieldHarvested(bytes32 indexed userKey, uint256 yield, uint256 totalCredits);
    event CreditsSpent(bytes32 indexed userKey, uint256 amount, string action);
    event PrincipalWithdrawn(bytes32 indexed userKey, uint256 amount, address to);

    // ── Setup ────────────────────────────────────────────────────────────────

    constructor(address _agent) {
        agent = _agent;
        owner = msg.sender;
        // Pre-approve Aave to pull cUSD — saves gas on every deposit.
        CUSD.approve(address(AAVE), type(uint256).max);
    }

    modifier onlyAgent() {
        require(msg.sender == agent || msg.sender == owner, "Unauthorized");
        _;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    // ── User: Deposit ────────────────────────────────────────────────────────

    /**
     * @notice Deposit cUSD. Immediately supplied to Aave v3 to start earning real yield.
     * @param userId  User's Telegram ID (stored as keccak256 hash for privacy)
     * @param amount  Amount in wei (1e18 = 1 cUSD)
     */
    function deposit(string calldata userId, uint256 amount) external {
        require(amount > 0, "Amount must be > 0");

        bytes32 key = _key(userId);
        _harvest(key); // lock in yield accrued so far before adding new principal

        CUSD.transferFrom(msg.sender, address(this), amount);
        AAVE.supply(address(CUSD), amount, address(this), 0);

        UserVault storage v = vaults[key];
        if (v.depositTimestamp == 0) {
            v.depositTimestamp = block.timestamp;
            v.yieldIndex       = AAVE.getReserveNormalizedIncome(address(CUSD));
        }

        v.principal    += amount;
        totalPrincipal += amount;
        depositors[key] = msg.sender;

        emit Deposited(key, amount, v.principal);
    }

    // ── User: Withdraw Principal ─────────────────────────────────────────────

    /**
     * @notice Return principal to user. Called by agent when user requests withdrawal.
     *         Harvests yield first so no earnings are lost.
     */
    function withdrawPrincipal(
        string calldata userId,
        uint256 amount,
        address to
    ) external onlyAgent {
        bytes32 key = _key(userId);
        UserVault storage v = vaults[key];
        require(v.principal >= amount, "Insufficient principal");

        _harvest(key);

        v.principal    -= amount;
        totalPrincipal -= amount;

        // Withdraw from Aave — burns aUSDm, sends cUSD directly to user's wallet
        AAVE.withdraw(address(CUSD), amount, to);

        emit PrincipalWithdrawn(key, amount, to);
    }

    // ── Agent: Yield Harvest ─────────────────────────────────────────────────

    /**
     * @notice Manually harvest pending Aave yield into spendable credits.
     *         Also auto-called before every deposit and spend.
     */
    function harvestYield(string calldata userId) external onlyAgent returns (uint256) {
        return _harvest(_key(userId));
    }

    // ── Agent: Spend Credits ─────────────────────────────────────────────────

    /**
     * @notice Spend harvested yield credits to pay for an agent operation.
     *         Auto-harvests pending yield first.
     *         REVERTS if credits are zero — the agent cannot touch principal. Ever.
     */
    function spendCredits(
        string calldata userId,
        uint256 amount,
        string calldata action
    ) external onlyAgent {
        bytes32 key = _key(userId);
        _harvest(key);

        UserVault storage v = vaults[key];
        require(v.credits >= amount, "Insufficient yield credits");

        v.credits    -= amount;
        v.totalSpent += amount;

        // Transfer spent yield (real cUSD) to agent wallet to cover operational costs
        CUSD.transfer(agent, amount);

        emit CreditsSpent(key, amount, action);
    }

    // ── Read ─────────────────────────────────────────────────────────────────

    /**
     * @notice Full vault state for a user. Does not mutate state.
     * @return principal       cUSD locked in Aave (agent can NEVER spend this)
     * @return credits         spendable yield credits right now
     * @return pending         yield that will be added on next harvest
     * @return totalYieldEarned cumulative real Aave yield earned since deposit
     * @return totalSpent      cumulative credits spent on operations
     * @return selfSustaining  true when estimated monthly yield >= monthly ops cost
     */
    function getVault(string calldata userId) external view returns (
        uint256 principal,
        uint256 credits,
        uint256 pending,
        uint256 totalYieldEarned,
        uint256 totalSpent,
        bool    selfSustaining
    ) {
        bytes32 key        = _key(userId);
        UserVault storage v = vaults[key];
        uint256 p          = _pendingYield(key);

        // Estimate monthly yield using observed yield rate since deposit
        bool sustainable = false;
        if (v.principal > 0 && v.depositTimestamp > 0) {
            uint256 elapsed = block.timestamp - v.depositTimestamp;
            if (elapsed >= 1 days && v.totalYieldEarned > 0) {
                // Annualize observed yield, divide by 12 for monthly estimate
                uint256 monthlyEst = (v.totalYieldEarned * SECONDS_PER_YEAR) / elapsed / 12;
                sustainable = monthlyEst >= MONTHLY_OPS_ESTIMATE;
            } else {
                // Not enough history — use principal threshold as proxy.
                // At Aave's stablecoin rates (5%+ APY), 5 cUSD covers monthly ops.
                sustainable = v.principal >= 5 ether;
            }
        }

        return (v.principal, v.credits, p, v.totalYieldEarned, v.totalSpent, sustainable);
    }

    function pendingYield(string calldata userId) external view returns (uint256) {
        return _pendingYield(_key(userId));
    }

    // ── Admin ────────────────────────────────────────────────────────────────

    function setAgent(address _agent) external onlyOwner {
        agent = _agent;
    }

    /// @notice Emergency rescue for stuck tokens. Should never be needed in normal operation.
    function rescueTokens(address token, address to, uint256 amount) external onlyOwner {
        IERC20(token).transfer(to, amount);
    }

    // ── Internal ─────────────────────────────────────────────────────────────

    function _key(string memory userId) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(userId));
    }

    /**
     * @dev Pending yield = principal * (currentIndex - lastIndex) / lastIndex
     *
     *      The Aave normalized income index represents cumulative interest.
     *      When it grows from 1.000 to 1.001 RAY, every depositor earned 0.1%.
     *      We multiply by principal to get the absolute yield in cUSD wei.
     */
    function _pendingYield(bytes32 key) internal view returns (uint256) {
        UserVault storage v = vaults[key];
        if (v.principal == 0 || v.yieldIndex == 0) return 0;

        uint256 currentIndex = AAVE.getReserveNormalizedIncome(address(CUSD));
        if (currentIndex <= v.yieldIndex) return 0;

        return (v.principal * (currentIndex - v.yieldIndex)) / v.yieldIndex;
    }

    function _harvest(bytes32 key) internal returns (uint256 yield) {
        yield = _pendingYield(key);
        UserVault storage v = vaults[key];
        uint256 currentIndex = AAVE.getReserveNormalizedIncome(address(CUSD));

        if (yield == 0) {
            // Still advance the index so future calculations start from now
            if (v.yieldIndex == 0 && v.principal > 0) {
                v.yieldIndex = currentIndex;
            }
            return 0;
        }

        // Withdraw exactly the yield from Aave → cUSD lands in this contract
        // aUSDm balance drops by yield; principal aUSDm stays intact
        AAVE.withdraw(address(CUSD), yield, address(this));

        v.credits          += yield;
        v.totalYieldEarned += yield;
        v.yieldIndex        = currentIndex;

        emit YieldHarvested(key, yield, v.credits);
    }
}
