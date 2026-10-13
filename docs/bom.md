# Parts-list fields: `metadata.bom`

Every part file and assembly file can carry the facts its parts-list row
needs that the geometry cannot give: what it is called on a purchase order,
who sells it, what it costs, and how it is made. The SDM viewer's BOM table
reads them. Quantities are never written here: they are counted from the
assembly's instances, so they cannot drift from the model.

```json
"metadata": {
  "bought": true,
  "description": "Heat-set insert M2 x 4.0",
  "bom": {
    "part_number": "94459A120",
    "revision": "1.1.1",
    "vendor": "McMaster-Carr",
    "vendor_part_number": "94459A120",
    "unit_price": 0.31,
    "currency": "USD",
    "unit": "each",
    "fabrication": "Purchased",
    "url": "https://www.mcmaster.com/94459A120",
    "notes": "on hand"
  }
}
```

| Field | Meaning |
| --- | --- |
| `part_number` | Our number for the part. Omit until there is one. |
| `revision` | `x.y.z`, engineering-playbook `conventions/part-revisions.md`. A CEM that stamps `metadata.source.revision` need not repeat it here. |
| `vendor`, `vendor_part_number`, `url` | Where a bought part comes from. |
| `unit_price`, `currency` | Price of one `unit`. `currency` defaults to `USD`. Only a price someone quoted or paid; never an estimate. |
| `unit` | What the part is counted in: `each` (the default), or `mm`, `m`, `in`, `ft`, `mm^2`, `ft^2`, `g`, `kg`, `ml`. |
| `quantity` | How many `unit` one piece uses, for stock cut to size: a pad cut from sheet is `"unit": "ft^2", "quantity": 0.02`. Defaults to 1. |
| `fabrication` | How it is made: `Purchased`, `SLS`, `FDM`, `SLA`, `Machined`, `Laser cut`, `Cut from stock`, ... |
| `notes` | Anything a buyer or the shop needs. |

Every field is optional. Where one is missing the viewer works out what it
can (vendor and part number from a McMaster number in the description, the
process from the material, `Purchased` from `bought`) and shows it as a guess,
so a missing fact is visible rather than silently filled in.
