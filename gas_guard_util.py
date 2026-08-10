"""On-chain gas pre-check for the AutoClaimer (2026-06-18).

When the gas-paying account runs low on native token, every claim/wrap broadcast fails
with `insufficient funds for gas * price + value` — on 2026-06-18 that produced
108 failed broadcasts in 3 days (pure log spam + wasted RPC round-trips), because
the claimer re-attempted the send every cycle regardless of balance.

`sufficient_gas` reproduces the exact check the RPC node enforces
(balance >= gas_price * gas_limit) so the claimer can SKIP a doomed broadcast
instead of issuing it and logging the failure. Funds in transit / value=0 here
(redeem + wrap carry no native value), so gas cost is the whole tx cost.
"""


def sufficient_gas(gas_balance_pol, gas_price_wei, gas_limit):
    """True if the EOA POL balance can cover gas_price_wei * gas_limit."""
    cost_pol = (gas_price_wei * gas_limit) / 1e18
    return gas_balance_pol >= cost_pol
