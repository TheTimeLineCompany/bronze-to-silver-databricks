# Source brief: <source_id> (<SYSTEM_CODE>)

**Business scope.** Domain <DOMAIN>, process <P-...>. Business objects: **<Object>** (<data_class>), linked to <Object>, <Object>. (E-xxxx)

**In scope.** Bronze tables: `<bronze.schema.table>` ... Filters (soft deletes, test data). (E-xxxx)

**Grain.** One row per <...> per <...>. Key `<COLS>` is unique (to be confirmed in P2). (E-xxxx)

**Keys and links.**
- `<COL>` = <meaning> -> <Object> master, key rule `<rule>`. (E-xxxx)

**Time and history.** Timestamps, time zones, how changes arrive. (E-xxxx)

**Code values.** Status codes and their meaning. (E-xxxx)

**Business rules.** BR-xxx-nnn <one line>. Needs CP4b: yes / no. (E-xxxx)

**Not used.** Columns or tables left out, and why.

**Read but not relied on.** Supporting or background files and why.

**Open questions.** Q-xxxx (blocking / not blocking).
