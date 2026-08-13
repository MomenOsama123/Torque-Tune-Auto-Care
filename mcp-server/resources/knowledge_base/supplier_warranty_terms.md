# Supplier Warranty & Returns Terms

*Internal reference for warehouse and service-desk staff. Not exposed as an
MCP tool -- claims still go through the supplier portal by hand. This
document exists so staff (and the assistant) can answer "is this part still
under warranty / can I return it" without opening five different supplier
PDFs.*

## WT-100: TorqueParts Direct (brake & suspension lines)

- Standard warranty window: **18 months** from `InventoryLogs` receipt date.
- Claim code prefix: **TPD-**. Any part with a supplier SKU starting
  `TPD-` follows this section.
- Returns require the original claim code plus photographic proof of the
  defect. No claim code, no return -- even inside the 18-month window.
- Brake pads and rotors (category `brakes`) are **excluded** from wear-based
  claims after 6 months; only manufacturing defects qualify past that point.

## WT-204: Coastal Auto Electric (batteries, alternators, starters)

- Standard warranty window: **24 months**, prorated after month 12: refund
  percentage = `(24 - months_since_purchase) / 24`.
- Claim code prefix: **CAE-**.
- Batteries returned with a charge below 40% are inspected for improper
  storage before any refund is issued; improper storage voids the claim.
- Starters and alternators installed by a non-certified technician void the
  warranty entirely -- check the `InventoryLogs.reason` field for install
  attribution before approving.

## WT-317: Meridian Filtration Co. (oil, air, cabin filters)

- Filters are **non-returnable once the packaging is opened**, regardless of
  defect, unless the defect is a manufacturing seal failure documented at
  time of receipt.
- Claim code prefix: **MFC-**.
- Warranty window: **90 days**, receipt date only, no proration.

## WT-441: Ironclad Drivetrain Supply (transmissions, CV joints, clutches)

- Standard warranty window: **36 months / 36,000 miles**, whichever comes
  first. Mileage must be recorded on the work order.
- Claim code prefix: **IDS-**.
- Remanufactured units (SKU suffix `-RM`) carry a **12-month** warranty
  instead of the standard 36 months -- always check the suffix before
  quoting a warranty period to a customer.
- A part replaced under an IDS claim inherits the **remaining** warranty of
  the original part, not a fresh 36-month term.

## General Return Processing Rule

- Regardless of supplier, a return can only be logged against `update_inventory`
  as a `decrease` with reason `"supplier_return"`. Any other reason string on
  a return-driven decrease should be treated as a data-entry error, not a
  policy violation, and corrected rather than escalated.
