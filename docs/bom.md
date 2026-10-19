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
| `unit` | What the part is counted in: `each` (the default), or `mm`, `m`, `in`, `ft`, `mm^2`, `m^2`, `in^2`, `ft^2`, `g`, `kg`, `ml`, `l`. |
| `quantity` | How many `unit` one piece uses, for stock cut to size: a pad cut from sheet is `"unit": "ft^2", "quantity": 0.02`. Defaults to 1. |
| `fabrication` | How it is made: one of the methods below, spelled exactly so a parts list can be sorted and counted by process. |
| `notes` | Anything a buyer or the shop needs. |

## Fabrication methods

| Value | Meaning |
| --- | --- |
| `Purchased` | Bought as is (also set `"bought": true`) |
| `FDM` | Filament 3D printing |
| `SLS` | Powder-bed polymer printing, laser (e.g. Fuse 1, EOS) |
| `MJF` | Powder-bed polymer printing, HP Multi Jet Fusion |
| `SLA` | Resin printing, laser |
| `DLP` | Resin printing, projector or LCD |
| `Metal AM` | Metal printing (laser powder bed, binder jet, ...) |
| `Machined` | Milled, CNC or manual |
| `Turned` | Lathe work |
| `Laser cut` | Cut from sheet or plate by laser |
| `Waterjet cut` | Cut from sheet or plate by waterjet |
| `Sheet metal` | Cut and bent sheet |
| `Cast` | Poured into a mould (metal, urethane, epoxy) |
| `Moulded` | Injection or compression moulded |
| `Cut from stock` | Cut to length or size from bought stock (rod, tube, sheet) |
| `Hand made` | Made by hand (assembly jigs, trimmed foam, ...) |

Anything not on the list is written `Other: <what it is>` (e.g. `Other: EDM`),
and is a sign the list should grow: add it here and in
`FABRICATION_METHODS` in `scripts/check_geometry.py`.

## What is required

`scripts/check_geometry.py` checks every part file:

- A bought part (`"bought": true`) names `vendor` and `vendor_part_number`.
- A made part (anything else) says its `fabrication`.
- A `fabrication` value is one of the methods above, spelled as listed, or
  `Other: <what it is>`. A wrong case (`sls`) is pointed to the right spelling.
- Every field present is well formed: `unit` from the list above, a
  `unit_price` and `quantity` that are numbers, a revision `x.y.z`.

A missing `unit_price` is reported, not failed: leave it out until there is a
real one. A part that genuinely has none of this (salvaged hardware with no
source, say) declares it in `metadata.geometry_exceptions.bom` with the reason.

Nothing here is ever guessed, and tools reading it do not fill gaps from
other text (a McMaster number in the description, a process from the
material). A missing fact shows as missing.
