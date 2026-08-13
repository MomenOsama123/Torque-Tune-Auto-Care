# Diagnostic & Repair Decision Procedures

*Internal decision trees service writers use to decide what to quote a
customer. These intentionally chain together policy, warranty, and TSB
knowledge -- a full answer to a real customer question usually needs more
than one section below plus a cross-check against `technical_service_bulletins.md`
and `supplier_warranty_terms.md`.*

## Procedure: Brake System Comeback (repeat brake noise/wear complaint)

1. Confirm which caliper assembly is fitted. If it is the CS-3 assembly,
   check TSB-2021-045 before quoting anything -- pads-only replacement is
   the wrong fix and will cause a second comeback.
2. If the original pads are under 6 months old and the part is category
   `brakes` with an unresolved manufacturing defect (not wear), check
   WT-100 for warranty eligibility -- wear-based claims are excluded past
   6 months, but manufacturing defects are not.
3. If neither TSB-2021-045 nor a warranty defect applies, the comeback is
   billed as a standard repair, not covered.

## Procedure: Electrical No-Start Diagnosis

1. Determine whether the fault is battery, starter, or alternator before
   ordering any part -- ordering the wrong component wastes both the
   customer's time and a warranty claim window.
2. If alternator whine is present at idle, cross-check TSB-2022-118. A
   pre-week-22 `CAE-ALT-*` unit should be replaced outright, not repaired.
3. Once the failed component is identified, check whether it was installed
   by a certified technician (see `InventoryLogs.reason` / work order) --
   WT-204 voids the warranty for non-certified installs on starters and
   alternators specifically.
4. Only after both the TSB check and the warranty/install check are done
   should the part be quoted as warranty-covered, discounted, or full price.

## Procedure: Drivetrain Vibration / Clutch Pedal Complaint

1. Distinguish CV joint symptoms (vibration, grease at boot seam) from
   clutch symptoms (soft or slipping pedal) before pulling any part.
2. For CV joint boot cracking, check TSB-2023-072: boot-only replacement is
   insufficient for first-run units, and remanufactured (`-RM`) units are
   explicitly excluded from that bulletin.
3. For a soft clutch pedal, check TSB-2024-118 for slave-cylinder
   cross-contamination before assuming the clutch kit itself failed --
   pairing an IDS clutch kit with a non-OEM slave cylinder is a known
   compatibility issue, not necessarily a defective clutch.
4. Whichever part is ultimately replaced, confirm its warranty term under
   WT-441: remanufactured (`-RM`) units carry 12 months, not the standard
   36 months / 36,000 miles, and a warranty-replaced part inherits the
   remaining term of the part it replaced, not a fresh term.

## Procedure: Cabin Air Filter Replacement on Older Vehicles

1. If the vehicle's cabin air filter housing is more than 3 years old,
   check TSB-2024-009 before ordering just the filter -- the retaining
   clip is known to be fragile at that age.
2. If the clip is original and aged past 3 years, add the housing clip kit
   to the order alongside the Meridian Filtration Co. filter.
3. Remember filters are non-returnable once opened per WT-317 -- confirm
   the correct filter part number with the customer before installation,
   not after.
