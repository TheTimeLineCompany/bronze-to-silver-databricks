# Bronze discovery: S07_container_moves

Read this file first. Full detail: tables.csv, columns.csv, keys.csv, links.csv, domains.csv, derived.csv, graph.json.

## Tables (lineage level 0 = root)

| lvl | table | role (conf) | grain key | business object (conf) | scope |
|---|---|---|---|---|---|
| 0 | carrier_contacts | master (agent) | OWNER + CONTACT_NAME | NEW:CarrierContact (agent) | in_scope |
| 0 | container_types | reference (agent) | TYPE_CD | NEW:ContainerType (agent) | in_scope |
| 0 | locations | master (agent) | LOC_CD | Location (agent) | in_scope |
| 0 | user_logins | technical (high) | SESSION_ID | - (none) | out_of_scope |
| 1 | containers | master (medium) | CNTR_NO | Container (high) | in_scope |
| 1 | leg_daily_summary | aggregate (agent) | DEP_DATE + FROM_LOC | none (agent) | derive_instead |
| 1 | shipments | transaction_header (agent) | SHPMT_ID | Shipment (agent) | in_scope |
| 2 | legs | event (agent) | SHPMT_ID + LEG_NO | ShipmentLeg (agent) | in_scope |
| - | legs_bkp_2025 | staging (high) | SHPMT_ID + LEG_NO | - (none) | out_of_scope |

Confidence 'agent' = decided on a card (see tables.csv decided_by).

## Links (foreign-key candidates)

| from | to | card. | containment raw / normalised | note |
|---|---|---|---|---|
| containers.TYPE_CD | container_types.TYPE_CD | N:1 | 1.0 / 1.0 |  |
| leg_daily_summary.FROM_LOC | locations.LOC_CD | N:1 | 1.0 / 1.0 |  |
| legs.CNTR_NO | containers.CNTR_NO | N:1 | 0.8545 / 1.0 | matches only after normalisation (trim/upper/remove spaces and dashes): needs a key rule |
| legs.SHPMT_ID | shipments.SHPMT_ID | N:1 | 1.0 / 1.0 |  |
| legs.FROM_LOC | locations.LOC_CD | N:1 | 0.5 / 1.0 | matches only after normalisation (trim/upper/remove spaces and dashes): needs a key rule |
| legs.TO_LOC | locations.LOC_CD | N:1 | 1.0 / 1.0 |  |
| shipments.ORIGIN_LOC | locations.LOC_CD | N:1 | 1.0 / 1.0 |  |
| shipments.DEST_LOC | locations.LOC_CD | N:1 | 1.0 / 1.0 |  |

## Derived tables

- leg_daily_summary <- legs: 1/2 grouping columns in bronze.container_track.legs; 2738 > 1571 rows

## Shared code domains

- carrier_contacts.OWNER ~ containers.OWNER (Jaccard 1.0)

## Unity Catalog metadata

Sections: tables not available, columns not available, tags not available, masks_and_filters not available, constraints not available, detail_history not available, column_stats ok (0), lineage not available, column_lineage not available.
Tables without a comment: carrier_contacts, container_types, locations, user_logins, containers, leg_daily_summary, shipments, legs.

## Documents vs bronze

- In bronze, NOT in documents: bronze.container_track.carrier_contacts, bronze.container_track.container_types, bronze.container_track.containers, bronze.container_track.leg_daily_summary, bronze.container_track.legs_bkp_2025, bronze.container_track.locations, bronze.container_track.shipments, bronze.container_track.user_logins

Budgets: sample 200000 rows/table, max 25 key checks/table, max 400 link checks.
