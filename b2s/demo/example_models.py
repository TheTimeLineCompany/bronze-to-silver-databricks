"""Small, valid examples of the five models for the fake application S90_yardops (supply-chain logistics)."""

DEPENDENCIES = {
    "app": "S90_yardops",
    "systems": [
        {"id": "MARS", "name": "MARS", "relation": "upstream", "gives": ["container master", "vessel schedule"],
         "status": "known", "evidence": ["E-0001"]},
        {"id": "TOS", "name": "Terminal operating system", "relation": "downstream", "gives": ["move instructions"],
         "status": "unknown", "question": "Q-0001"},
    ],
}

PROCESS = {
    "processes": [
        {"id": "PR01", "business_process": "P-LOGI-01", "name": "Plan container move",
         "steps": [
             {"id": "ST01", "name": "Create move plan", "records": ["yard.mv_plan"], "status": "known"},
             {"id": "ST02", "name": "Approve plan", "records": [], "status": "unknown", "question": "Q-0002"},
             {"id": "ST03", "name": "Execute leg", "records": ["yard.mv_leg"], "status": "assumed", "assumption": "A-0001"},
         ],
         "flows": [
             {"from": "ST01", "to": "ST02", "status": "assumed", "assumption": "A-0002"},
             {"from": "ST02", "to": "ST03", "status": "known"},
         ]},
    ],
}

CONCEPTUAL = {
    "objects": [
        {"name": "Container", "status": "known", "tables": ["yard.cntr_mst"]},
        {"name": "Shipment", "status": "known", "tables": ["yard.mv_plan"]},
        {"name": "ShipmentLeg", "status": "known", "tables": ["yard.mv_leg"]},
        {"name": "Location", "status": "assumed", "assumption": "A-0003", "tables": ["yard.loc"]},
    ],
    "relationships": [
        {"from": "ShipmentLeg", "to": "Shipment", "verb": "part_of", "cardinality": "N:1", "status": "known"},
        {"from": "ShipmentLeg", "to": "Container", "verb": "moves", "cardinality": "N:1", "status": "known"},
        {"from": "ShipmentLeg", "to": "Location", "verb": "departs_from", "cardinality": "N:1",
         "status": "unknown", "question": "Q-0003"},
    ],
}

LOGICAL = {
    "tables": [
        {"name": "slv_container", "business_object": "Container", "data_class": "master",
         "grain": "One row per container number per validity period.", "primary_key": ["container_sk"],
         "business_key": ["container_no"], "status": "known",
         "columns": [{"name": "container_sk", "type": "string"}, {"name": "container_no", "type": "string"},
                     {"name": "iso_type", "type": "string"}]},
        {"name": "slv_shipment", "business_object": "Shipment", "data_class": "event",
         "grain": "One row per move plan.", "primary_key": ["shipment_sk"], "business_key": ["plan_id"],
         "status": "known",
         "columns": [{"name": "shipment_sk", "type": "string"}, {"name": "plan_id", "type": "string"},
                     {"name": "plan_status", "type": "string", "status": "unknown", "question": "Q-0004"}]},
        {"name": "slv_shipment_leg", "business_object": "ShipmentLeg", "data_class": "event",
         "grain": "One row per leg of a move plan.", "primary_key": ["shipment_leg_sk"],
         "business_key": ["plan_id", "leg_no"], "status": "known",
         "columns": [{"name": "shipment_leg_sk", "type": "string"}, {"name": "plan_id", "type": "string"},
                     {"name": "leg_no", "type": "int"}, {"name": "shipment_sk", "type": "string"},
                     {"name": "container_sk", "type": "string"},
                     {"name": "moved_at", "type": "timestamp", "status": "assumed", "assumption": "A-0004"}]},
    ],
    "relationships": [
        {"from": "slv_shipment_leg", "to": "slv_shipment", "fk_column": "shipment_sk", "cardinality": "N:1",
         "label": "part of", "status": "known"},
        {"from": "slv_shipment_leg", "to": "slv_container", "fk_column": "container_sk", "cardinality": "N:1",
         "label": "moves", "status": "assumed", "assumption": "A-0005"},
    ],
}

MAPPING = {
    "links": [
        {"business_object": "Container", "bronze_table": "yard.cntr_mst", "bronze_columns": ["cntr_no"],
         "silver_table": "slv_container", "silver_columns": ["container_no"], "key_rule": "container_no",
         "status": "known"},
        {"business_object": "Shipment", "bronze_table": "yard.mv_plan", "bronze_columns": ["plan_id"],
         "silver_table": "slv_shipment", "silver_columns": ["plan_id"], "status": "known"},
        {"business_object": "ShipmentLeg", "bronze_table": "yard.mv_leg", "bronze_columns": ["plan_id", "leg_no"],
         "silver_table": "slv_shipment_leg", "silver_columns": ["plan_id", "leg_no"], "status": "known"},
        {"business_object": "ShipmentLeg", "bronze_table": "yard.mv_leg", "bronze_columns": ["cntr_no"],
         "silver_table": "slv_shipment_leg", "silver_columns": ["container_sk"], "key_rule": "container_no",
         "status": "assumed", "assumption": "A-0005"},
    ],
}

ALL = {"dependencies": DEPENDENCIES, "process": PROCESS, "conceptual": CONCEPTUAL, "logical": LOGICAL,
       "mapping": MAPPING}
