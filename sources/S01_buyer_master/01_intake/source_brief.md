# Source brief: S01_buyer_master (BUYMGR)

**Business scope.** Domains PROC and ORG, process P-PROC-01. System of record for **Buyer** (master) and **Department**. (E-0001, E-0004)

**In scope.** `bronze.buyer_mgmt.t_buyer` (soft delete `REC_STATUS = 'D'`), lookup `t_dept`. (E-0004)

**Grain and key.** One row per buyer ID per validity period (SCD2). `BUYER_ID` is unique and never re-used. (E-0001, E-0002)

**Codes.** `STATUS_CD`: A = active, I = inactive. (E-0005)

**Links.** `DEPT_CD` → `t_dept` (N:1). Department name kept as an attribute for now; Department is not yet a shared entity. (E-0004)
