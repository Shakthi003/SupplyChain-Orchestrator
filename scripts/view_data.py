"""
scripts/view_data.py -- Quick viewer for all PostgreSQL tables.
Run: uv run python scripts/view_data.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from core.config import DATABASE_URL
from core.models import (Supplier, Part, Warehouse, Inventory,
                          BillOfMaterials, PurchaseOrder, Shipment,
                          ProductionOrder, CustomerOrder, DisruptionEvent)

engine = create_engine(DATABASE_URL)

with Session(engine) as s:
    sep = "-" * 70

    print("\n== SUPPLIERS ==")
    print(f"{'ID':<12} {'NAME':<25} {'COUNTRY':<10} {'LEAD':>5} {'RELIABILITY':>12}")
    print(sep)
    for r in s.query(Supplier).all():
        print(f"{r.id:<12} {r.name:<25} {r.country:<10} {r.lead_time_days:>5} {r.reliability_score:>12.2f}")

    print("\n== PARTS ==")
    print(f"{'ID':<12} {'NAME':<35} {'CATEGORY':<15} {'COST':>8}")
    print(sep)
    for r in s.query(Part).all():
        print(f"{r.id:<12} {r.name:<35} {r.category:<15} ${r.unit_cost:>7.2f}")

    print("\n== INVENTORY (PRT-104 focus) ==")
    print(f"{'ID':<12} {'PART':<10} {'WH':<8} {'ON HAND':>9} {'RESERVED':>9} {'AVAILABLE':>10}")
    print(sep)
    for r in s.query(Inventory).filter(Inventory.part_id == "PRT-104").all():
        avail = r.quantity_on_hand - r.quantity_reserved
        print(f"{r.id:<12} {r.part_id:<10} {r.warehouse_id:<8} {r.quantity_on_hand:>9.0f} {r.quantity_reserved:>9.0f} {avail:>10.0f}")

    print("\n== PURCHASE ORDERS ==")
    print(f"{'ID':<10} {'SUPPLIER':<10} {'PART':<10} {'QTY':>6} {'STATUS':<12}")
    print(sep)
    for r in s.query(PurchaseOrder).all():
        print(f"{r.id:<10} {r.supplier_id:<10} {r.part_id:<10} {r.quantity:>6.0f} {r.status.value:<12}")

    print("\n== SHIPMENTS ==")
    print(f"{'ID':<12} {'PO':<10} {'SCHED DATE':<14} {'REVISED ETA':<14} {'DELAY':>6}")
    print(sep)
    for r in s.query(Shipment).all():
        revised = r.revised_eta.strftime('%Y-%m-%d') if r.revised_eta else "None"
        print(f"{r.id:<12} {r.purchase_order_id:<10} {r.scheduled_date.strftime('%Y-%m-%d'):<14} {revised:<14} {r.delay_days:>6}")

    print("\n== PRODUCTION ORDERS ==")
    print(f"{'ID':<10} {'PRODUCT':<10} {'QTY':>5} {'START':<12} {'STATUS':<15}")
    print(sep)
    for r in s.query(ProductionOrder).all():
        print(f"{r.id:<10} {r.product_part_id:<10} {r.quantity:>5.0f} {r.planned_start.strftime('%Y-%m-%d'):<12} {r.status.value:<15}")

    print("\n== CUSTOMER ORDERS ==")
    print(f"{'ID':<10} {'CUSTOMER':<30} {'PART':<10} {'QTY':>5} {'VALUE':>10} {'PROD ORDER':<12}")
    print(sep)
    for r in s.query(CustomerOrder).all():
        print(f"{r.id:<10} {r.customer_name:<30} {r.part_id:<10} {r.quantity:>5.0f} ${r.order_value:>9,.0f} {r.production_order_id or 'None':<12}")

    print("\n== DISRUPTION EVENTS ==")
    print(f"{'ID':<10} {'TYPE':<20} {'SEVERITY':<10} {'SOURCE':<15} {'STATUS':<12}")
    print(sep)
    for r in s.query(DisruptionEvent).all():
        print(f"{r.id:<10} {r.event_type.value:<20} {r.severity.value:<10} {r.source_entity_id:<15} {r.status.value:<12}")

    print("\n== BILL OF MATERIALS (products using PRT-104) ==")
    print(f"{'BOM ID':<10} {'PARENT (finished good)':<12} {'CHILD (component)':<12} {'QTY NEEDED':>12}")
    print(sep)
    for r in s.query(BillOfMaterials).filter(BillOfMaterials.child_part_id == "PRT-104").all():
        print(f"{r.id:<10} {r.parent_part_id:<12} {r.child_part_id:<12} {r.quantity_required:>12.1f}")
