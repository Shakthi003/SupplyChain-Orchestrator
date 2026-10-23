"""
Late alternate suppliers: feasible but PARTIAL, only when a real shortage exists.
Pure logic, no database.
"""

from datetime import datetime, timedelta

from core.optimization.constraints import check_alt_supplier
from core.optimization.options import OptionType, RecoveryOption

TODAY = datetime(2026, 10, 23)


def _alt(lead_days: int, reliability: float = 0.96) -> RecoveryOption:
    return RecoveryOption(
        option_id="OPT-D1", option_type=OptionType.ALT_SUPPLIER, title="Buy", description="",
        alt_supplier_name="Bosch", alt_supplier_lead_time=lead_days, alt_supplier_reliability=reliability,
    )


def test_arrives_after_stockout_is_partial_with_residual_days():
    opt = _alt(14)                                   # lands Nov 6
    shortage = TODAY + timedelta(days=11)            # stock out Nov 3
    ok, note = check_alt_supplier(opt, shortage, TODAY, nearest_shipment_eta=TODAY + timedelta(days=26))
    assert ok                                        # still useful, so still feasible
    assert not opt.fully_closes_gap
    assert opt.residual_gap_days == 3.0
    assert "PARTIAL" in note and "NOT fully prevent" in note


def test_arrives_before_stockout_closes_gap():
    opt = _alt(5)
    ok, _ = check_alt_supplier(opt, TODAY + timedelta(days=11), TODAY,
                               nearest_shipment_eta=TODAY + timedelta(days=26))
    assert ok and opt.fully_closes_gap and opt.residual_gap_days == 0.0


def test_no_real_shortage_is_never_partial():
    # Inbound shipment lands before stock runs out, so nothing can be "late".
    opt = _alt(14)
    ok, _ = check_alt_supplier(opt, TODAY + timedelta(days=11), TODAY,
                               nearest_shipment_eta=TODAY + timedelta(days=7))
    assert ok and opt.fully_closes_gap


def test_low_reliability_is_still_infeasible():
    opt = _alt(5, reliability=0.5)
    ok, _ = check_alt_supplier(opt, TODAY + timedelta(days=11), TODAY)
    assert not ok
