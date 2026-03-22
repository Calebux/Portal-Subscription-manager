// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title SubBotLog
 * @notice On-chain audit trail for SubBot AI agent decisions.
 *         Every time the agent recommends a cancel, negotiation, or audit,
 *         it writes an immutable record here on Celo mainnet.
 *
 *         This creates a verifiable track record of the agent's reasoning
 *         and estimated savings — permanently tied to the agent's identity.
 *
 * Deploy on Celo mainnet: https://celoscan.io
 */
contract SubBotLog {

    // ── Events ──────────────────────────────────────────────────────────────

    event DecisionLogged(
        address indexed agent,
        bytes32 indexed userHash,   // keccak256 of userId — privacy-preserving
        string  action,             // "recommend_cancel" | "recommend_negotiate" | "audit_complete" | "daily_digest"
        uint256 amountSavedUSD,     // estimated monthly saving in cents (e.g. 2000 = $20.00)
        uint256 timestamp
    );

    // ── Storage ─────────────────────────────────────────────────────────────

    struct Decision {
        address agent;
        bytes32 userHash;
        string  action;
        uint256 amountSavedUSD;
        uint256 timestamp;
    }

    Decision[] public decisions;
    uint256    public totalSavingsUSD;  // cumulative across all users, in cents
    uint256    public decisionCount;

    // ── Write ────────────────────────────────────────────────────────────────

    /**
     * @notice Log an agent decision. Called by the SubBot API bridge.
     * @param userId         Raw user identifier (will be hashed for privacy)
     * @param action         Type of decision made
     * @param amountSavedUSD Estimated monthly saving in cents (0 if not applicable)
     */
    function logDecision(
        string calldata userId,
        string calldata action,
        uint256         amountSavedUSD
    ) external {
        bytes32 userHash = keccak256(abi.encodePacked(userId));

        decisions.push(Decision({
            agent:          msg.sender,
            userHash:       userHash,
            action:         action,
            amountSavedUSD: amountSavedUSD,
            timestamp:      block.timestamp
        }));

        totalSavingsUSD += amountSavedUSD;
        decisionCount   += 1;

        emit DecisionLogged(
            msg.sender,
            userHash,
            action,
            amountSavedUSD,
            block.timestamp
        );
    }

    // ── Read ─────────────────────────────────────────────────────────────────

    function getDecision(uint256 index) external view returns (Decision memory) {
        require(index < decisions.length, "Index out of bounds");
        return decisions[index];
    }

    function getDecisionCount() external view returns (uint256) {
        return decisions.length;
    }

    /**
     * @notice Total estimated savings the agent has identified, in cents.
     *         Divide by 100 to get USD.
     */
    function getTotalSavingsUSD() external view returns (uint256) {
        return totalSavingsUSD;
    }
}
