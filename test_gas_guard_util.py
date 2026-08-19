"""Tests for the on-chain gas pre-check (gas_guard_util).

Stops the AutoClaimer from broadcasting a claim/wrap tx it cannot pay for
(EOA POL balance < gas_price * gas_limit) — which on 2026-06-18 produced 108
failed `insufficient funds for gas` broadcasts in 3 days. The check mirrors
exactly what the RPC node enforces, so a True/False here predicts the outcome
without spending the round-trip.

Real values from the incident: gas wallet 0.0341 POL, Polygon gas ~281 gwei,
factory redeem gas_limit 300000 -> cost ~0.0843 POL (unaffordable).
"""
import unittest
from gas_guard_util import sufficient_gas, should_log_now

GWEI = 10 ** 9


class TestSufficientGas(unittest.TestCase):
    def test_dead_wallet_cannot_afford_factory_redeem(self):
        # 0.0341 POL, 281 gwei, 300k gas -> cost 0.0843 POL.
        self.assertFalse(sufficient_gas(0.0341, 281 * GWEI, 300_000))

    def test_dead_wallet_cannot_afford_wrap(self):
        # 0.0341 POL, 281 gwei, 250k gas -> cost 0.0703 POL.
        self.assertFalse(sufficient_gas(0.0341, 281 * GWEI, 250_000))

    def test_funded_wallet_can_afford(self):
        self.assertTrue(sufficient_gas(0.5, 281 * GWEI, 300_000))

    def test_balance_exactly_equal_to_cost_is_sufficient(self):
        cost_pol = (281 * GWEI * 300_000) / 1e18
        self.assertTrue(sufficient_gas(cost_pol, 281 * GWEI, 300_000))

    def test_balance_one_wei_below_cost_is_insufficient(self):
        cost_pol = (281 * GWEI * 300_000) / 1e18
        self.assertFalse(sufficient_gas(cost_pol - 1e-12, 281 * GWEI, 300_000))

    def test_low_gas_price_makes_small_balance_sufficient(self):
        # 35 gwei, 250k gas -> cost 0.00875 POL; 0.0341 POL covers it.
        self.assertTrue(sufficient_gas(0.0341, 35 * GWEI, 250_000))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestShouldLogNow(unittest.TestCase):
    """The throttle that stopped 97 identical low-gas warnings in 27 minutes."""

    def test_first_ever_call_logs(self):
        # last_ts 0 means never logged; silence on the FIRST warning would
        # hide the condition entirely.
        self.assertTrue(should_log_now(0, 1000.0, 600.0))

    def test_none_is_treated_as_never_logged(self):
        self.assertTrue(should_log_now(None, 1000.0, 600.0))

    def test_repeat_inside_the_window_is_suppressed(self):
        # claim loop runs every ~15s; the 2nd pass must stay quiet
        self.assertFalse(should_log_now(1000.0, 1015.0, 600.0))

    def test_logs_again_once_the_window_has_passed(self):
        self.assertTrue(should_log_now(1000.0, 1600.0, 600.0))

    def test_boundary_is_inclusive(self):
        self.assertTrue(should_log_now(1000.0, 1600.0, 600.0))
        self.assertFalse(should_log_now(1000.0, 1599.9, 600.0))

    def test_one_cycle_of_the_real_incident(self):
        # 27 minutes of 15s cycles at a 10-minute throttle: 108 passes should
        # yield 3 log lines, not 108.
        last, logged = 0.0, 0
        for i in range(108):
            now = 1000.0 + i * 15.0
            if should_log_now(last, now, 600.0):
                last, logged = now, logged + 1
        self.assertEqual(logged, 3)
