---- MODULE Vault ----
\* Reviewed system spec S for the PC-12 spec-freshness demo's covered Solidity module
\* (requirements/spec-freshness/foundry/src/Vault.sol). Hand-written and reviewed per the PB-5
\* pattern — a human's TLA model of the vault's redemption guarantee, NOT machine-extracted. Its
\* trace-observable projection lives in ../contract.json (a declared SpecTraceContract) and is
\* what spec-revalidate replays against the module's REAL Foundry traces: the spec stays `fresh`
\* only while that replay reproduces the contract's behavior over the current source.
EXTENDS Naturals

\* @type: Int;
VARIABLE total

\* The vault only accumulates redemptions: total never decreases and starts at zero.
TotalNonNegative == total >= 0
Init == total = 0
Next == \E amount \in 1..16 : total' = total + amount
====
