"""
core/models.py — SQLAlchemy ORM Models (Database Schema)

This file defines ALL tables in our PostgreSQL database as Python classes.
Each class = one table. Each class attribute = one column.

SQLAlchemy reads these classes and creates the real SQL tables for us.
We never have to write CREATE TABLE SQL manually.

Relationship summary:
  suppliers → purchase_orders → shipments
  parts     → bill_of_materials (parent/child parts)
  parts     → inventory → warehouses
  parts     → production_orders → customer_orders
  disruption_events (links to any entity above)
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, DateTime,
    ForeignKey, Enum, Text, Boolean
)
from sqlalchemy.orm import declarative_base, relationship

# Base is the "parent class" all our models inherit from.
# SQLAlchemy uses it to track which classes are database tables.
Base = declarative_base()


# ---------------------------------------------------------------------------
# ENUMS — fixed list of allowed values for certain columns
# Using Python enums means the database enforces valid values automatically.
# ---------------------------------------------------------------------------

class SupplierStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ON_HOLD = "on_hold"          # e.g. quality issues being investigated


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    DELAYED = "delayed"


class ProductionStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"


class DisruptionType(str, enum.Enum):
    SUPPLIER_DELAY = "supplier_delay"       # Shipment arrives later than planned
    QUALITY_HOLD = "quality_hold"           # Batch failed quality check
    DEMAND_SPIKE = "demand_spike"           # Sudden increase in customer orders
    INVENTORY_SHORTAGE = "inventory_shortage"
    PRODUCTION_STOPPAGE = "production_stoppage"
    LOGISTICS_ISSUE = "logistics_issue"     # Carrier/port/customs problem


class DisruptionSeverity(str, enum.Enum):
    LOW = "low"           # Covered by buffer stock, no immediate action
    MEDIUM = "medium"     # Some orders at risk, monitor closely
    HIGH = "high"         # Active shortage, recovery action needed
    CRITICAL = "critical" # Customer deliveries will miss deadline


class DisruptionStatus(str, enum.Enum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    CLOSED = "closed"


# ---------------------------------------------------------------------------
# TABLE 1: suppliers
# Who supplies our parts? This table stores one row per supplier company.
# ---------------------------------------------------------------------------

class Supplier(Base):
    __tablename__ = "suppliers"

    # Primary key — stable ID we assign (e.g. "SUP-001")
    # Why string IDs? Easier to read in logs and test data than auto-increment integers.
    id = Column(String(20), primary_key=True)

    name = Column(String(200), nullable=False)
    country = Column(String(100), nullable=False)
    city = Column(String(100))
    contact_email = Column(String(200))
    contact_phone = Column(String(50))

    # How many days on average between placing an order and receiving it
    lead_time_days = Column(Integer, nullable=False, default=14)

    # Score 0.0–1.0 based on historical on-time delivery rate
    # e.g. 0.92 means 92% of past shipments arrived on time
    reliability_score = Column(Float, default=1.0)

    status = Column(Enum(SupplierStatus), default=SupplierStatus.ACTIVE)
    created_at = Column(DateTime, default=datetime.utcnow)

    # SQLAlchemy "relationship" — lets us do supplier.purchase_orders in Python
    # without writing any JOIN SQL. It's a convenience, not a real column.
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")


# ---------------------------------------------------------------------------
# TABLE 2: parts
# Every component, raw material, or finished product in the system.
# "Parts" covers both raw inputs (C-104 hydraulic valve) and
# finished goods (Product P-22 assembly).
# ---------------------------------------------------------------------------

class Part(Base):
    __tablename__ = "parts"

    id = Column(String(20), primary_key=True)   # e.g. "PRT-104"
    name = Column(String(200), nullable=False)
    description = Column(Text)

    # "component" = raw material / sub-assembly bought from suppliers
    # "finished_good" = final product sold to customers
    category = Column(String(50), default="component")

    unit_cost = Column(Float, default=0.0)       # Cost per unit in USD
    unit_of_measure = Column(String(20), default="each")  # each, kg, litre, etc.

    # Is this part currently being actively used?
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    inventory_records = relationship("Inventory", back_populates="part")
    # BOM as parent: this part is built FROM the child parts below
    bom_as_parent = relationship("BillOfMaterials",
                                  foreign_keys="BillOfMaterials.parent_part_id",
                                  back_populates="parent_part")
    # BOM as child: this part is used IN other assemblies
    bom_as_child = relationship("BillOfMaterials",
                                 foreign_keys="BillOfMaterials.child_part_id",
                                 back_populates="child_part")
    purchase_orders = relationship("PurchaseOrder", back_populates="part")
    production_orders = relationship("ProductionOrder", back_populates="product")


# ---------------------------------------------------------------------------
# TABLE 3: warehouses
# Physical locations where inventory is stored.
# A company may have multiple warehouses in different cities.
# ---------------------------------------------------------------------------

class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(String(20), primary_key=True)    # e.g. "WH-01"
    name = Column(String(200), nullable=False)
    location = Column(String(200))               # City, State
    country = Column(String(100), default="USA")
    capacity = Column(Integer)                   # Max storage units

    inventory_records = relationship("Inventory", back_populates="warehouse")
    production_orders = relationship("ProductionOrder", back_populates="warehouse")


# ---------------------------------------------------------------------------
# TABLE 4: inventory
# How much of each part is physically in each warehouse RIGHT NOW.
# This is the most critical table for shortage calculations.
#
# Key formula used in Stage 3:
#   usable_stock = quantity_on_hand - quantity_reserved
#   coverage_days = usable_stock / daily_consumption_rate
# ---------------------------------------------------------------------------

class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(String(20), primary_key=True)

    # Foreign keys — link this row to its part and warehouse
    part_id = Column(String(20), ForeignKey("parts.id"), nullable=False)
    warehouse_id = Column(String(20), ForeignKey("warehouses.id"), nullable=False)

    # Total physical units in the warehouse
    quantity_on_hand = Column(Float, nullable=False, default=0.0)

    # Units already committed/reserved for existing production orders
    # Cannot be used for new orders without un-reserving first
    quantity_reserved = Column(Float, nullable=False, default=0.0)

    # Computed property — available for new use
    # Not stored in DB (calculated on the fly): on_hand - reserved
    @property
    def quantity_available(self):
        return max(0.0, self.quantity_on_hand - self.quantity_reserved)

    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    part = relationship("Part", back_populates="inventory_records")
    warehouse = relationship("Warehouse", back_populates="inventory_records")


# ---------------------------------------------------------------------------
# TABLE 5: bill_of_materials (BOM)
# Defines what parts are needed to build other parts/products.
# This is the key to tracing impact: if C-104 is short,
# find all parent_parts that require C-104, then find their production orders.
# ---------------------------------------------------------------------------

class BillOfMaterials(Base):
    __tablename__ = "bill_of_materials"

    id = Column(String(20), primary_key=True)

    # The assembly/product being built (e.g. "Product P-22")
    parent_part_id = Column(String(20), ForeignKey("parts.id"), nullable=False)

    # The component needed to build it (e.g. "C-104 Hydraulic Valve")
    child_part_id = Column(String(20), ForeignKey("parts.id"), nullable=False)

    # How many units of the child are needed per one unit of the parent
    quantity_required = Column(Float, nullable=False, default=1.0)

    # Relationships
    parent_part = relationship("Part", foreign_keys=[parent_part_id],
                                back_populates="bom_as_parent")
    child_part = relationship("Part", foreign_keys=[child_part_id],
                               back_populates="bom_as_child")


# ---------------------------------------------------------------------------
# TABLE 6: purchase_orders
# Orders we placed with suppliers to buy parts.
# One supplier delay event = one purchase_order's ETA changes.
# ---------------------------------------------------------------------------

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(String(20), primary_key=True)    # e.g. "PO-441"

    supplier_id = Column(String(20), ForeignKey("suppliers.id"), nullable=False)
    part_id = Column(String(20), ForeignKey("parts.id"), nullable=False)

    quantity = Column(Float, nullable=False)
    unit_cost = Column(Float)                    # Price agreed in this PO

    order_date = Column(DateTime, nullable=False)
    expected_arrival = Column(DateTime, nullable=False)  # Original planned date

    status = Column(Enum(OrderStatus), default=OrderStatus.CONFIRMED)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    supplier = relationship("Supplier", back_populates="purchase_orders")
    part = relationship("Part", back_populates="purchase_orders")
    shipments = relationship("Shipment", back_populates="purchase_order")


# ---------------------------------------------------------------------------
# TABLE 7: shipments
# Tracks the physical delivery status of a purchase order.
# THIS is where supplier delay events land — we update revised_eta here.
# One purchase order can have one active shipment record.
# ---------------------------------------------------------------------------

class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(String(20), primary_key=True)    # e.g. "SHP-201"

    purchase_order_id = Column(String(20), ForeignKey("purchase_orders.id"), nullable=False)

    # Original promised delivery date (from the purchase order)
    scheduled_date = Column(DateTime, nullable=False)

    # Updated date after a delay notification — NULL if no delay yet
    revised_eta = Column(DateTime, nullable=True)

    # How many days late (positive = delayed, 0 = on time, negative = early)
    delay_days = Column(Integer, default=0)

    status = Column(Enum(OrderStatus), default=OrderStatus.IN_TRANSIT)

    # Free text field for the supplier's reason for delay
    delay_reason = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    purchase_order = relationship("PurchaseOrder", back_populates="shipments")


# ---------------------------------------------------------------------------
# TABLE 8: production_orders
# Manufacturing jobs — "produce X units of Product P-22 by date Y".
# These are affected when the parts they need run short.
# ---------------------------------------------------------------------------

class ProductionOrder(Base):
    __tablename__ = "production_orders"

    id = Column(String(20), primary_key=True)   # e.g. "PRD-101"

    # What product are we building?
    product_part_id = Column(String(20), ForeignKey("parts.id"), nullable=False)

    quantity = Column(Float, nullable=False)
    planned_start = Column(DateTime, nullable=False)
    planned_end = Column(DateTime, nullable=False)

    status = Column(Enum(ProductionStatus), default=ProductionStatus.PLANNED)

    # Which warehouse will the finished goods go to?
    warehouse_id = Column(String(20), ForeignKey("warehouses.id"))

    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    product = relationship("Part", back_populates="production_orders")
    warehouse = relationship("Warehouse", back_populates="production_orders")
    customer_orders = relationship("CustomerOrder", back_populates="production_order")


# ---------------------------------------------------------------------------
# TABLE 9: customer_orders
# Orders from our customers. Linked to the production order that will fulfil them.
# If a production order is delayed, all its customer orders are at risk.
# ---------------------------------------------------------------------------

class CustomerOrder(Base):
    __tablename__ = "customer_orders"

    id = Column(String(20), primary_key=True)    # e.g. "CO-501"

    customer_name = Column(String(200), nullable=False)
    customer_ref = Column(String(100))           # Customer's own order reference

    # What product did they order?
    part_id = Column(String(20), ForeignKey("parts.id"), nullable=False)
    quantity = Column(Float, nullable=False)

    # The date we promised to deliver by
    promised_delivery_date = Column(DateTime, nullable=False)

    # Which production order will make the goods for this customer?
    production_order_id = Column(String(20), ForeignKey("production_orders.id"))

    status = Column(Enum(OrderStatus), default=OrderStatus.CONFIRMED)

    # Financial impact — useful for prioritisation
    order_value = Column(Float, default=0.0)

    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    production_order = relationship("ProductionOrder", back_populates="customer_orders")


# ---------------------------------------------------------------------------
# TABLE 10: disruption_events
# Every disruption that enters the system gets logged here.
# This is the "inbox" — supplier delay notifications land here first.
# The AI agent reads from here and starts its analysis workflow.
# ---------------------------------------------------------------------------

class DisruptionEvent(Base):
    __tablename__ = "disruption_events"

    id = Column(String(20), primary_key=True)    # e.g. "EVT-001"

    event_type = Column(Enum(DisruptionType), nullable=False)
    severity = Column(Enum(DisruptionSeverity), default=DisruptionSeverity.MEDIUM)
    status = Column(Enum(DisruptionStatus), default=DisruptionStatus.OPEN)

    # Which entity triggered this? (e.g. supplier ID, shipment ID, part ID)
    source_entity_type = Column(String(50))      # "supplier", "shipment", "part", etc.
    source_entity_id = Column(String(20))        # The actual ID of that entity

    # Human-readable description of what happened
    description = Column(Text, nullable=False)

    # When was this detected/reported?
    detected_at = Column(DateTime, default=datetime.utcnow)

    # Who reviewed/resolved it?
    reviewed_by = Column(String(100))
    resolved_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# TABLE 11: decision_log
# Every human approval / rejection decision is recorded here permanently.
# This is the audit trail — who decided what, when, and why.
# Added in Stage 6 (Agent layer).
# ---------------------------------------------------------------------------

class DecisionLog(Base):
    __tablename__ = "decision_log"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Which disruption event triggered this decision?
    event_id = Column(String(20), nullable=False)

    # What did the system recommend vs what the human actually chose?
    recommended_option_id = Column(String(20))   # e.g. "OPT-A"
    chosen_option_id      = Column(String(20))   # may differ from recommended

    # The decision outcome
    approved       = Column(Boolean, nullable=False)   # True = approved, False = rejected
    reviewer_name  = Column(String(200), nullable=False)
    rationale      = Column(Text, nullable=False)       # Why this decision was made

    # Financial context at time of decision
    financial_exposure = Column(Float, default=0.0)    # Total at-risk value
    estimated_cost     = Column(Float, default=0.0)    # Cost of chosen option

    # When was the decision made?
    decided_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
