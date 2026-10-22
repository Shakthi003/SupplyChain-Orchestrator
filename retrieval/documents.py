"""
retrieval/documents.py -- Synthetic Document Library

Defines all documents that will be indexed into ChromaDB.
These are realistic-looking but completely synthetic documents.

In a real system these would be:
  - Actual PDF contracts uploaded by procurement
  - Word documents from the legal team
  - Scanned paper policies from the warehouse
  - Past decision records exported from an ERP system

For our prototype, we define them as Python strings here.
The embedder.py script reads this file and loads them into ChromaDB.

Document types:
  1. Supplier Contracts  -- one per supplier (SUP-001 to SUP-005)
  2. Internal Policies   -- procurement, inventory, logistics
  3. Past Decisions      -- how similar situations were handled before
  4. Risk Runbooks       -- step-by-step response procedures

Each document has:
  - doc_id    : unique identifier (e.g. "CONTRACT-SUP-005")
  - title     : short human-readable name
  - category  : contract / policy / past_decision / runbook
  - supplier_id: which supplier it relates to (None for general docs)
  - content   : the full document text
"""

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# DOCUMENT DATA CLASS
# ---------------------------------------------------------------------------

@dataclass
class Document:
    """One document to be indexed into ChromaDB."""
    doc_id: str
    title: str
    category: str          # contract | policy | past_decision | runbook
    supplier_id: Optional[str]
    content: str


# ---------------------------------------------------------------------------
# SECTION 1: SUPPLIER CONTRACTS
# One contract per supplier in our database (SUP-001 to SUP-005)
# ---------------------------------------------------------------------------

SUPPLIER_CONTRACTS = [

    Document(
        doc_id="CONTRACT-SUP-001",
        title="Supplier Contract — Bosch Industrial GmbH (SUP-001)",
        category="contract",
        supplier_id="SUP-001",
        content="""
SUPPLIER CONTRACT — Bosch Industrial GmbH (SUP-001)
Contract Reference: SC-2024-001
Effective Date: January 1, 2024
Review Date: December 31, 2025

APPROVED PARTS:
  SUP-001 is approved to supply: PRT-101, PRT-103, PRT-109
  Any other part requires written approval from Procurement Director.

LEAD TIME GUARANTEE:
  Standard lead time: 14 calendar days from purchase order confirmation.
  Maximum guaranteed lead time: 18 calendar days.
  Express delivery available: 7 calendar days at 30% freight surcharge.

DELAY NOTIFICATION:
  Supplier must notify buyer within 24 hours of any anticipated delay.
  Failure to notify within 24 hours results in automatic penalty escalation.

PENALTY CLAUSES:
  Delay 1-3 days: No penalty. Supplier must provide written explanation.
  Delay 4-7 days: 3% of purchase order value deducted from invoice.
  Delay 8-14 days: 7% of purchase order value deducted from invoice.
  Delay > 14 days: Buyer may cancel order without penalty. 10% of PO value as compensation.

QUALITY REQUIREMENTS:
  Defect rate must not exceed 0.5% per shipment.
  Failed quality inspection: full replacement at supplier cost within 5 days.

FORCE MAJEURE:
  Supplier not liable for delays caused by natural disasters, government actions,
  or labor strikes beyond supplier control. Buyer must be notified within 12 hours.
  Force majeure cannot be claimed for internal production issues.

PREFERRED SUPPLIER STATUS:
  Bosch Industrial GmbH holds Tier-1 Preferred Supplier status.
  Eligible for priority allocation during industry-wide shortages.
  Quarterly performance review required to maintain status.
        """.strip()
    ),

    Document(
        doc_id="CONTRACT-SUP-002",
        title="Supplier Contract — Yamaha Precision Parts (SUP-002)",
        category="contract",
        supplier_id="SUP-002",
        content="""
SUPPLIER CONTRACT — Yamaha Precision Parts (SUP-002)
Contract Reference: SC-2024-002
Effective Date: March 1, 2024
Review Date: February 28, 2026

APPROVED PARTS:
  SUP-002 is approved to supply: PRT-102, PRT-107
  Precision parts only. No substitution without engineering sign-off.

LEAD TIME GUARANTEE:
  Standard lead time: 21 calendar days (international shipping from Japan).
  Maximum guaranteed lead time: 26 calendar days.
  Express air freight: 10 calendar days at 45% surcharge.

DELAY NOTIFICATION:
  Supplier must notify buyer 72 hours before any confirmed delay.
  International suppliers given extended notification window due to time zones.

PENALTY CLAUSES:
  Delay 1-5 days: No penalty. Written explanation required.
  Delay 6-10 days: 4% of purchase order value deducted.
  Delay 11-21 days: 8% of purchase order value deducted.
  Delay > 21 days: Buyer may cancel. 12% compensation payable.

QUALITY REQUIREMENTS:
  Precision parts require Certificate of Conformance with each shipment.
  Dimensional tolerance: per drawing specification ±0.01mm.
  Hardness testing certification required for all metal parts.

IMPORT COMPLIANCE:
  All shipments must comply with US customs regulations.
  Harmonized tariff codes must be declared accurately.
  Supplier responsible for export licenses from Japan.

FORCE MAJEURE:
  Natural disasters, port closures, and government export restrictions qualify.
  Internal supply chain issues at supplier do not qualify as force majeure.
        """.strip()
    ),

    Document(
        doc_id="CONTRACT-SUP-003",
        title="Supplier Contract — Delta Components LLC (SUP-003)",
        category="contract",
        supplier_id="SUP-003",
        content="""
SUPPLIER CONTRACT — Delta Components LLC (SUP-003)
Contract Reference: SC-2024-003
Effective Date: February 1, 2024
Review Date: January 31, 2026

APPROVED PARTS:
  SUP-003 is approved to supply: PRT-104, PRT-105, PRT-110, PRT-111
  Note: PRT-104 approval added via Amendment SC-2024-003-A (June 2024).
  SUP-003 is a qualified alternate supplier for PRT-104 when primary supplier delayed.

LEAD TIME GUARANTEE:
  Standard lead time: 7 calendar days (domestic US supplier).
  Maximum guaranteed lead time: 10 calendar days.
  Same-day dispatch available for orders placed before 12:00 PM EST.

DELAY NOTIFICATION:
  Supplier must notify buyer within 12 hours of any anticipated delay.
  Domestic suppliers held to stricter notification standard.

PENALTY CLAUSES:
  Delay 1-2 days: No penalty. Phone call explanation required.
  Delay 3-5 days: 5% of purchase order value deducted from invoice.
  Delay 6-10 days: 10% of purchase order value deducted from invoice.
  Delay > 10 days: Buyer may cancel. 15% compensation payable.

EMERGENCY SOURCING TERMS:
  Delta Components LLC is pre-approved for emergency purchase orders
  up to $25,000 without additional procurement approval.
  Emergency orders above $25,000 require Procurement Manager sign-off.
  Emergency premium: 15% above standard unit price applies to rush orders.

QUALITY REQUIREMENTS:
  Defect rate must not exceed 1.0% per shipment.
  Delta Components LLC holds ISO 9001:2015 certification.

PREFERRED ALTERNATE STATUS:
  Designated as Tier-2 alternate supplier for hydraulic components.
  Subject to annual qualification review in October each year.
        """.strip()
    ),

    Document(
        doc_id="CONTRACT-SUP-004",
        title="Supplier Contract — Shenzhen FastParts Co. (SUP-004)",
        category="contract",
        supplier_id="SUP-004",
        content="""
SUPPLIER CONTRACT — Shenzhen FastParts Co. (SUP-004)
Contract Reference: SC-2024-004
Effective Date: April 1, 2024
Review Date: March 31, 2025

APPROVED PARTS:
  SUP-004 is approved to supply: PRT-108, PRT-112
  Low-cost parts category only. Not approved for safety-critical components.

LEAD TIME GUARANTEE:
  Standard lead time: 30 calendar days (sea freight from China).
  Maximum guaranteed lead time: 38 calendar days.
  Air freight option: 12 calendar days at 60% surcharge.

DELAY NOTIFICATION:
  Supplier must notify buyer 5 days before any confirmed delay.
  Extended notification window due to distance and logistics complexity.

PENALTY CLAUSES:
  Delay 1-7 days: No penalty. Written explanation required.
  Delay 8-14 days: 3% of purchase order value deducted.
  Delay 15-30 days: 6% of purchase order value deducted.
  Delay > 30 days: Buyer may cancel. 8% compensation payable.

IMPORT DUTIES:
  All applicable import duties and tariffs are buyer's responsibility.
  Supplier provides commercial invoice with accurate HS codes.
  Certificate of Origin required for all shipments.

QUALITY REQUIREMENTS:
  Pre-shipment inspection by third-party inspector required for orders > $10,000.
  Defect rate must not exceed 2.0% per shipment (higher tolerance, lower cost tier).

RISK NOTE:
  Single-source risk: If geopolitical disruption affects China exports,
  buyer must activate alternate sourcing within 48 hours.
  SUP-004 NOT suitable as emergency source due to lead time constraints.
        """.strip()
    ),

    Document(
        doc_id="CONTRACT-SUP-005",
        title="Supplier Contract — Apex Hydraulics Ltd (SUP-005)",
        category="contract",
        supplier_id="SUP-005",
        content="""
SUPPLIER CONTRACT — Apex Hydraulics Ltd (SUP-005)
Contract Reference: SC-2024-005
Effective Date: January 15, 2024
Review Date: January 14, 2026

APPROVED PARTS:
  SUP-005 is approved to supply: PRT-104, PRT-106
  Hydraulic components specialist. Primary supplier for PRT-104 (Hydraulic Valve C-104).

LEAD TIME GUARANTEE:
  Standard lead time: 18 calendar days from purchase order confirmation.
  Maximum guaranteed lead time: 22 calendar days.
  Rush orders: 10 calendar days with 35% freight and handling surcharge.

DELAY NOTIFICATION:
  Supplier must notify buyer within 24 hours of any anticipated delay.
  Notification must include: reason for delay, revised ETA, mitigation plan.

PENALTY CLAUSES:
  Delay 1-3 days: No penalty. Written explanation and revised ETA required.
  Delay 4-7 days: 5% of purchase order value deducted from invoice.
                  Buyer may request partial shipment of available stock.
  Delay 8-14 days: 10% of purchase order value deducted from invoice.
                   Buyer may activate alternate supplier without notice.
  Delay > 14 days: Buyer may cancel order. 15% of PO value as compensation.
                   Supplier placed on 90-day performance watch list.

PARTIAL SHIPMENT CLAUSE:
  If full order cannot be fulfilled, supplier must ship available units immediately.
  Remaining units shipped as soon as available at no additional freight cost.

EXPEDITE CLAUSE:
  Buyer may request air freight expediting for delayed shipments.
  Expediting surcharge: supplier and buyer share cost equally (50/50 split).
  Expedited shipment must depart within 48 hours of buyer request.

PERFORMANCE HISTORY NOTE:
  SUP-005 had 2 delayed shipments in 2023 (delays of 3 days and 6 days).
  Current reliability score: 74%. Below company preferred threshold of 80%.
  Supplier is on informal performance improvement plan since Q3 2023.
  Continued delays may result in reduction of approved part list.

FORCE MAJEURE:
  Production line equipment failures do NOT qualify as force majeure.
  Equipment maintenance is supplier's responsibility.
  Natural disasters and government actions qualify with 12-hour notification.
        """.strip()
    ),
]


# ---------------------------------------------------------------------------
# SECTION 2: INTERNAL POLICIES
# Company rules for procurement, inventory, and logistics decisions
# ---------------------------------------------------------------------------

INTERNAL_POLICIES = [

    Document(
        doc_id="POLICY-PROCUREMENT-001",
        title="Emergency Sourcing Policy",
        category="policy",
        supplier_id=None,
        content="""
INTERNAL POLICY — Emergency Sourcing (POL-PROC-001)
Issued by: Procurement Director
Effective: January 1, 2024
Review: Annually

PURPOSE:
  This policy governs how emergency purchase orders may be placed when
  the primary supplier cannot deliver on time.

APPROVED VENDOR LIST (AVL):
  All alternate suppliers used in emergencies MUST be on the Approved Vendor List.
  Using a non-AVL supplier requires written VP of Operations approval.
  AVL is maintained by the Procurement team and updated quarterly.

APPROVAL THRESHOLDS FOR EMERGENCY POs:
  Emergency PO value up to $5,000    : Procurement Manager approval
  Emergency PO value $5,001-$25,000  : Procurement Director approval
  Emergency PO value above $25,000   : VP of Operations approval
  All emergency POs must be logged in the procurement system within 2 hours.

PRICE PREMIUM LIMITS:
  Emergency sourcing premiums are acceptable up to 20% above standard price.
  Premiums above 20% require Procurement Director written justification.
  Premiums above 35% require VP of Operations approval.

ALTERNATE SUPPLIER QUALIFICATION:
  SUP-003 (Delta Components LLC) is pre-qualified for hydraulic components.
  SUP-001 (Bosch Industrial) is pre-qualified for standard industrial parts.
  New suppliers may not be used in emergencies without a minimum 48-hour qualification.

DOCUMENTATION REQUIREMENTS:
  Every emergency PO must be documented with:
    1. Reason for emergency (reference disruption event ID)
    2. Supplier selected and justification
    3. Price comparison against standard cost
    4. Approver name and timestamp
    5. Expected delivery date and monitoring plan
        """.strip()
    ),

    Document(
        doc_id="POLICY-INVENTORY-001",
        title="Inventory Transfer Policy",
        category="policy",
        supplier_id=None,
        content="""
INTERNAL POLICY — Warehouse Inventory Transfer (POL-INV-001)
Issued by: Operations Director
Effective: March 1, 2024
Review: Annually

PURPOSE:
  This policy governs the transfer of inventory between company warehouses
  to respond to stock shortages at production facilities.

TRANSFER AUTHORIZATION:
  Transfers up to 50 units    : Warehouse Supervisor approval (source warehouse)
  Transfers 51-200 units      : Warehouse Manager approval (source warehouse)
  Transfers above 200 units   : Operations Director approval
  Emergency transfers (same-day): Operations Director approval regardless of quantity

TRANSIT TIME STANDARDS:
  WH-01 (Chicago) to WH-02 (Dallas)  : 2 business days standard, 1 day express
  WH-01 (Chicago) to WH-03 (Atlanta) : 2 business days standard, 1 day express
  WH-02 (Dallas)  to WH-03 (Atlanta) : 3 business days standard, 2 days express
  Express transfer incurs $200 handling surcharge.

MINIMUM STOCK RETENTION:
  Source warehouse must retain minimum 20% of on-hand stock after transfer.
  Transfer cannot reduce source warehouse below safety stock level.
  Safety stock levels are defined in the inventory master and reviewed monthly.

TRANSFER COST ACCOUNTING:
  Transfer cost = freight cost + handling fee ($150 standard, $200 express)
  Freight calculated at $2.50 per unit for standard parts.
  Heavy/oversized parts: freight calculated by actual weight and dimensions.
  Transfer costs charged to the receiving production order cost center.

DOCUMENTATION:
  Transfer request must reference disruption event ID.
  Physical count at source and destination required within 24 hours of arrival.
        """.strip()
    ),

    Document(
        doc_id="POLICY-LOGISTICS-001",
        title="Air Freight and Expediting Policy",
        category="policy",
        supplier_id=None,
        content="""
INTERNAL POLICY — Air Freight and Expediting (POL-LOG-001)
Issued by: Logistics Director
Effective: February 1, 2024
Review: Annually

PURPOSE:
  Air freight is significantly more expensive than standard freight.
  This policy ensures air freight is only used when genuinely necessary.

CRITERIA FOR AIR FREIGHT APPROVAL:
  ALL of the following conditions must be met:
    1. Delay is confirmed to be 5 or more days beyond original ETA
    2. Financial exposure from the delay exceeds $10,000
    3. No alternate sourcing option is available within the required timeframe
    4. Logistics Manager has confirmed air freight will actually save enough time

  Meeting only 1 or 2 criteria is NOT sufficient for approval.

COST SHARING WITH SUPPLIER:
  Per supplier contracts (where applicable): 50/50 cost split for expediting.
  Where no expedite clause exists: buyer bears 100% of additional freight cost.
  Expediting surcharge typically 2-3x standard freight cost.

APPROVAL AUTHORITY:
  Air freight up to $2,000 additional cost  : Logistics Manager
  Air freight $2,001-$10,000 additional cost: Logistics Director
  Air freight above $10,000 additional cost : VP of Operations

TIME SAVINGS REQUIREMENT:
  Air freight must save at least 3 days versus standard freight to be justified.
  Saving only 1-2 days rarely justifies the cost premium.

NOTE ON CURRENT SITUATION (EVT-001 reference):
  A 4-day delay on SHP-441 does NOT meet the 5-day threshold for air freight.
  Air freight should only be considered if delay extends beyond 5 days.
  Recommend monitoring current stock levels before approving expedite.
        """.strip()
    ),
]


# ---------------------------------------------------------------------------
# SECTION 3: PAST DECISIONS
# Records of how similar disruptions were handled before
# ---------------------------------------------------------------------------

PAST_DECISIONS = [

    Document(
        doc_id="DECISION-2024-001",
        title="Past Decision — SUP-003 Delay on PRT-105 (March 2024)",
        category="past_decision",
        supplier_id="SUP-003",
        content="""
PAST DECISION RECORD — March 2024
Decision ID: DEC-2024-001
Event: SUP-003 (Delta Components) delayed PRT-105 by 6 days
Disruption Type: Supplier Delay
Severity: Medium

SITUATION SUMMARY:
  Delta Components LLC notified a 6-day delay on PO-305 (800 units of PRT-105).
  Available stock at WH-01: 320 units. Daily consumption: 45 units/day.
  Stock coverage: 7.1 days. Delay gap: 6 days. Margin: 1.1 days.

OPTIONS CONSIDERED:
  Option A (Use Stock): Marginally feasible — only 1.1 day buffer. Too risky.
  Option B (Transfer from WH-03): WH-03 had 300 units available. 2-day transit.
  Option C (Expedite): SUP-003 offered air freight. Would save 3 days.
  Option D (Alt Supplier): No other qualified supplier for PRT-105.

DECISION MADE:
  Option B approved — Transfer 250 units from WH-03 to WH-01.
  Approved by: Sarah Chen (Procurement Manager)
  Rationale: Transfer was cheapest option ($425 total). Alt supplier not available.
             Air freight cost ($1,800) was not justified given 1.1 day margin was
             too tight but transfer was safer and cheaper.

OUTCOME:
  Transfer arrived in 2 days as expected. Production was not delayed.
  SUP-003 delayed shipment arrived 5 days late (1 day earlier than worst case).
  Total extra cost: $425 (transfer freight + handling). Decision was correct.

LESSONS LEARNED:
  1. Always verify source warehouse has 20%+ safety stock before approving transfer.
  2. Delta Components (SUP-003) has been reliable despite this delay.
  3. No alternate supplier for PRT-105 is a concentration risk — flag for review.
        """.strip()
    ),

    Document(
        doc_id="DECISION-2024-002",
        title="Past Decision — SUP-005 Delay on PRT-104 (August 2023)",
        category="past_decision",
        supplier_id="SUP-005",
        content="""
PAST DECISION RECORD — August 2023
Decision ID: DEC-2023-008
Event: SUP-005 (Apex Hydraulics) delayed PRT-104 by 6 days
Disruption Type: Supplier Delay
Severity: High

SITUATION SUMMARY:
  Apex Hydraulics Ltd notified a 6-day delay on PO-831 (150 units PRT-104).
  Available stock: 18 units only. Daily consumption: 12 units/day.
  Stock coverage: 1.5 days. This was a critical shortage situation.
  Three production orders at risk: PRD-201, PRD-202, PRD-205.
  Financial exposure: $38,500 across 4 customer orders.

OPTIONS CONSIDERED:
  Option A (Use Stock): NOT feasible. Only 1.5 days coverage.
  Option B (Transfer from WH-02): WH-02 had only 8 units. Insufficient.
  Option C (Expedite SHP-831): Air freight would save 3 days, arrive day 3.
  Option D (Alt Supplier - Delta Components): 7-day lead time. Too slow.

DECISION MADE:
  Option C approved — Expedite SHP-831 via air freight.
  50/50 cost split with SUP-005 per contract clause.
  Total expedite cost: $2,400 (buyer share: $1,200).
  Approved by: Michael Torres (Procurement Director)
  Rationale: Stock coverage only 1.5 days. Transfer insufficient.
             Alt supplier too slow. Expediting was the only viable option.
             $1,200 cost far less than $38,500 exposure.

OUTCOME:
  Expedited shipment arrived on day 3 as planned. Production saved.
  SUP-005 paid their 50% share. Penalty clause also applied: 5% of PO value.
  Total recovery cost: $1,200. Total exposure avoided: $38,500.
  Decision was correct. Expediting justified given critical stock level.

LESSONS LEARNED:
  1. SUP-005 has now had 3 delays in 18 months — escalate to performance review.
  2. Safety stock for PRT-104 should be raised from 15 to 30 units minimum.
  3. Delta Components (SUP-003) should be formally qualified as alternate for PRT-104.
  4. Always invoke the 5% penalty clause immediately on confirmed delay > 3 days.
        """.strip()
    ),

    Document(
        doc_id="DECISION-2024-003",
        title="Past Decision — Monitor and Hold Decision (January 2024)",
        category="past_decision",
        supplier_id="SUP-001",
        content="""
PAST DECISION RECORD — January 2024
Decision ID: DEC-2024-003
Event: SUP-001 (Bosch Industrial) notified 3-day delay on PRT-101
Disruption Type: Supplier Delay
Severity: Low

SITUATION SUMMARY:
  Bosch Industrial GmbH notified a 3-day delay on PO-101 (500 units PRT-101).
  Available stock at WH-01: 480 units. Daily consumption: 38 units/day.
  Stock coverage: 12.6 days. Delay: 3 days. Large comfortable buffer.
  No production orders starting within 10 days. Zero financial exposure.

OPTIONS CONSIDERED:
  Option A (Use Stock): FEASIBLE. 12.6 days coverage, shipment in 3 days.
  No other options evaluated — situation did not warrant further action.

DECISION MADE:
  Option A approved — Monitor stock levels daily. No action required.
  Approved by: James Wilson (Inventory Manager)
  Rationale: 12.6 days of stock more than covers a 3-day delay.
             Activating transfer or expedite would waste money unnecessarily.
             Daily monitoring sufficient to catch any deterioration.

OUTCOME:
  Shipment arrived 2 days late (not 3 as notified — supplier recovered 1 day).
  Stock never dropped below 380 units. Production was never at risk.
  Total extra cost: $0. Correct decision — no action was the right action.

LESSONS LEARNED:
  1. Not every supplier delay requires an active response.
  2. Calculate actual stock coverage FIRST before deciding to act.
  3. "Monitor and hold" is a valid and often optimal decision.
  4. Bosch Industrial (SUP-001) recovered 1 day — reliable supplier behavior.
        """.strip()
    ),
]


# ---------------------------------------------------------------------------
# SECTION 4: RISK RUNBOOK
# Step-by-step response procedures for different disruption types
# ---------------------------------------------------------------------------

RISK_RUNBOOKS = [

    Document(
        doc_id="RUNBOOK-SUPPLIER-DELAY",
        title="Risk Runbook — Supplier Delay Response Procedure",
        category="runbook",
        supplier_id=None,
        content="""
RISK RUNBOOK — Supplier Delay Response (RB-001)
Maintained by: Supply Chain Risk Team
Last Updated: October 2024

TRIGGER:
  This runbook applies whenever a supplier notifies a delivery delay
  OR when a shipment misses its scheduled arrival date.

IMMEDIATE ACTIONS (within 2 hours of notification):
  Step 1: Log the disruption event in the supply chain system with:
            - Supplier ID, PO number, part number
            - Original ETA, revised ETA, delay in days
            - Reason provided by supplier
  Step 2: Run inventory coverage analysis for the affected part
            - Calculate available stock across ALL warehouses
            - Calculate daily consumption from upcoming production orders
            - Calculate coverage days and theoretical shortage date
  Step 3: Assess severity based on coverage gap:
            - Coverage days > delay days + 3 buffer : LOW severity
            - Coverage days within 0-3 days of delay : MEDIUM severity
            - Coverage days < delay days             : HIGH severity

RESPONSE BY SEVERITY:

  LOW SEVERITY (stock bridge exists, comfortable buffer):
    - Monitor daily. No immediate action required.
    - Notify inventory manager by email within 4 hours.
    - Check again in 2 days to confirm situation unchanged.
    - Document decision as "monitor and hold."

  MEDIUM SEVERITY (stock bridge exists but tight):
    - Notify procurement manager within 1 hour.
    - Evaluate transfer option from alternate warehouse.
    - Prepare contingency plan but do not execute without approval.
    - Daily monitoring mandatory.
    - Escalate to HIGH if situation deteriorates.

  HIGH SEVERITY (shortage confirmed or imminent):
    - Notify procurement manager IMMEDIATELY by phone.
    - Run full impact analysis: affected production orders, customer orders, exposure.
    - Evaluate all 4 recovery options: use stock, transfer, expedite, alternate supplier.
    - Present ranked options to Procurement Director within 3 hours.
    - Procurement Director approves recovery action.
    - Execute approved action immediately.
    - Notify affected customers if delivery dates are at risk.

PENALTY CLAUSE ACTIVATION:
  Delays > 3 days: Automatically calculate penalty per supplier contract.
  Send penalty notification to supplier within 24 hours of delay confirmation.
  Do not waive penalty without VP of Operations written approval.

ESCALATION PATH:
  Inventory Manager → Procurement Manager → Procurement Director → VP Operations
  Each escalation must happen within 1 hour of previous level being notified.

DOCUMENTATION:
  All decisions must be logged with: event ID, options considered, rationale,
  approver, timestamp, and expected outcome.
  Post-event review required within 5 business days of resolution.
        """.strip()
    ),
]


# ---------------------------------------------------------------------------
# MAIN EXPORT: all documents in one list
# The embedder.py script imports this list and loads everything into ChromaDB
# ---------------------------------------------------------------------------

ALL_DOCUMENTS: list[Document] = (
    SUPPLIER_CONTRACTS +
    INTERNAL_POLICIES +
    PAST_DECISIONS +
    RISK_RUNBOOKS
)


# ---------------------------------------------------------------------------
# QUICK PREVIEW (run this file directly to see all doc IDs and titles)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\nDocument Library Summary")
    print("=" * 50)
    print(f"Total documents: {len(ALL_DOCUMENTS)}")
    print()

    categories = {}
    for doc in ALL_DOCUMENTS:
        categories.setdefault(doc.category, []).append(doc)

    for cat, docs in categories.items():
        print(f"  {cat.upper()} ({len(docs)} docs):")
        for doc in docs:
            sup = f" [{doc.supplier_id}]" if doc.supplier_id else ""
            print(f"    {doc.doc_id}{sup} — {doc.title}")
    print()
