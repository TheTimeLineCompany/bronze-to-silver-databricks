# Source brief: S07_container_moves (CNTRK)

**Business scope.** Domain LOGI, process P-LOGI-02 (track container leg events). Business object: **ShipmentLeg** (event), linked to Container, Location, Shipment. (E-0004)

**In scope.** One bronze table: `bronze.container_track.legs`. Soft deletes via `IS_DELETED`. (E-0004)

**Grain.** One row per container per shipment leg. Key `CNTR_NO + SHPMT_ID + LEG_NO` is unique in bronze. (E-0004)

**Keys and links.**
- `CNTR_NO` = ISO container number → Container master, rule `container_number`. (E-0001, E-0002)
- `FROM_LOC` / `TO_LOC` → Location master, rule `generic_code`; 0.3% need case normalisation. (E-0005, E-0006)
- `SHPMT_ID` → Shipment (kept as business key; no Shipment master yet). (E-0003)

**Timestamps.** `ATD_TS`, `ATA_TS` epoch seconds UTC (E-0007). `ETA_TS` has two formats; time zone unknown → Q-0001 (blocking). (E-0008)

**Business rules.** BR-LOGI-001 transit days = arrival − departure in days. Needs CP4b. (E-0009)

**Not used.** `CARRIER_REF` (55% null, meaning unclear, 40% confidence) — excluded until the client explains it.

**Read but not relied on.** Profile report HTML (supporting). Workshop notes and email: background for Q-0001 only.
