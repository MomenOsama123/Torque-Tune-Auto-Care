# Auto Care Warehouse & Inventory Policy
*Exposed via `resources/list` + `resources/read` as `warehouse://policy/inventory`.
This is a Resource, not a Tool: it is static reference material the model
should read once and reason over, not something it "calls" with arguments.*
## 1. Stock Thresholds
- Every part has a `minimum_stock` value. A part at or below `minimum_stock`
  is **low stock**.
- A part at `quantity = 0` is **out of stock**, regardless of `minimum_stock`.
- Discontinued parts (`status = 'discontinued'`) are never restocked and
  should not trigger low-stock alerts.
## 2. Who Can Change Inventory
- **Technicians** may search parts, check quantity, and request alternatives.
  They may **not** call `update_inventory`.
- **Managers** are the only role authorized to call `update_inventory`. This
  is enforced in the tool handler itself, independent of whatever the
  client-side UI shows.
## 3. Confirmation Requirements (Elicitation Triggers)
A stock adjustment must pause for explicit human confirmation
(`elicitation/create`) before completing when either is true:
- The adjustment would **bring a part's quantity to zero**, or
- The adjustment is a **decrease of more than 20 units in a single call**.
Increases, and small decreases that keep quantity above zero, may proceed
without confirmation.
## 4. Alternative Parts
- An alternative is only valid if it belongs to the **same category** and is
  **not discontinued**. `suggest_alternative()` must never surface a
  discontinued part as a live substitute.
## 5. Audit Trail
- Every successful `update_inventory` call must write exactly one row to
  `InventoryLogs` recording the acting user, the old and new quantity, the
  action type, and a human-readable reason. No inventory change is valid
  without a corresponding log row.