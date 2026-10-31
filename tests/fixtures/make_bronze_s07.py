"""Create a small FAKE bronze schema for S07_container_moves, to try P2.2 discovery locally or in a dev workspace.

    from tests.fixtures.make_bronze_s07 import make
    make(spark, "container_track")          # local Spark database, or "dev_catalog.bronze_demo" in Databricks
Deliberate traps: container numbers with spaces/dashes in legs, mixed-case location codes, a 55%-null column,
two ETA formats, an aggregate table, a backup copy, an application login log (user_logins), a contact table with
personal data (carrier_contacts), and one log column hidden in a business table (shipments.BOOKED_FROM).
"""
import random
from datetime import datetime, timedelta


def make(spark, schema="container_track", seed=1):
    rnd = random.Random(seed)
    spark.sql(f"CREATE DATABASE IF NOT EXISTS {schema}")
    types = [("20GP", "20ft general"), ("40GP", "40ft general"), ("40HC", "40ft high cube"), ("20RF", "20ft reefer"), ("45HC", "45ft high cube")]
    locs = [(c, f"Port {c}", c[:2], tz) for c, tz in [("DEHAM", "Europe/Berlin"), ("NLRTM", "Europe/Amsterdam"), ("CNSHA", "Asia/Shanghai"),
            ("SGSIN", "Asia/Singapore"), ("USLAX", "America/Los_Angeles"), ("USNYC", "America/New_York"), ("BEANR", "Europe/Brussels"),
            ("KRPUS", "Asia/Seoul"), ("AEJEA", "Asia/Dubai"), ("GBFXT", "Europe/London")]]
    cntrs = [(f"MSCU{rnd.randint(1000000, 9999999)}", rnd.choice(types)[0], rnd.choice(["MSC", "MAERSK", "CMA"]), rnd.randint(2005, 2024)) for _ in range(800)]
    cntrs = list({c[0]: c for c in cntrs}.values())
    t0 = datetime(2026, 1, 1)
    ships, legs = [], []
    for i in range(1500):
        sid = f"S{i:06d}"
        o, dst = rnd.sample(locs, 2)
        bdt = t0 + timedelta(days=rnd.randint(0, 200))
        ships.append((sid, bdt.date(), o[0], dst[0], rnd.choice(["ACME", "GLOBEX", "INITECH", "UMBRELLA"]),
                      f"10.{rnd.randint(0, 255)}.{rnd.randint(0, 255)}.{rnd.randint(1, 254)}"))
        c = rnd.choice(cntrs)[0]
        path = [o[0]] + [x[0] for x in rnd.sample(locs, rnd.randint(0, 2)) if x[0] not in (o[0], dst[0])] + [dst[0]]
        t = bdt + timedelta(days=2)
        for n in range(len(path) - 1):
            atd = t + timedelta(hours=rnd.randint(0, 48))
            ata = atd + timedelta(days=rnd.randint(1, 20))
            cn = c if rnd.random() > 0.05 else f"{c[:4]} {c[4:10]}-{c[10:]}"
            fl = path[n] if rnd.random() > 0.03 else path[n].lower()
            eta = str(int((ata + timedelta(hours=rnd.randint(-12, 12))).timestamp())) if rnd.random() > 0.3 else (ata.strftime("%d/%m/%Y %H:%M"))
            legs.append((cn, sid, n + 1, fl, path[n + 1], int(atd.timestamp()), int(ata.timestamp()), eta, "N",
                         None if rnd.random() < 0.55 else f"CR{rnd.randint(100, 999)}", datetime(2026, 9, 1)))
            t = ata
    spark.createDataFrame(types, "TYPE_CD string, TYPE_DESC string").write.mode("overwrite").saveAsTable(f"{schema}.container_types")
    spark.createDataFrame(locs, "LOC_CD string, LOC_NAME string, COUNTRY_CD string, TZ_NAME string").write.mode("overwrite").saveAsTable(f"{schema}.locations")
    spark.createDataFrame(cntrs, "CNTR_NO string, TYPE_CD string, OWNER string, BUILD_YEAR int").write.mode("overwrite").saveAsTable(f"{schema}.containers")
    spark.createDataFrame(ships, "SHPMT_ID string, BOOKING_DT date, ORIGIN_LOC string, DEST_LOC string, CUSTOMER string, BOOKED_FROM string").write.mode("overwrite").saveAsTable(f"{schema}.shipments")
    ldf = spark.createDataFrame(legs, "CNTR_NO string, SHPMT_ID string, LEG_NO int, FROM_LOC string, TO_LOC string, ATD_TS long, ATA_TS long, "
                                      "ETA_TS string, IS_DELETED string, CARRIER_REF string, _ingest_ts timestamp")
    ldf.write.mode("overwrite").saveAsTable(f"{schema}.legs")
    ldf.limit(300).write.mode("overwrite").saveAsTable(f"{schema}.legs_bkp_2025")
    spark.sql(f"""SELECT to_date(from_unixtime(ATD_TS)) AS DEP_DATE, upper(FROM_LOC) AS FROM_LOC, count(*) AS N_LEGS,
                         avg((ATA_TS - ATD_TS) / 86400.0) AS AVG_TRANSIT_DAYS
                  FROM {schema}.legs GROUP BY 1, 2""").write.mode("overwrite").saveAsTable(f"{schema}.leg_daily_summary")
    agents = ["Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/120.0", "Mozilla/5.0 (Macintosh) Safari/605.1", "okhttp/4.9.0"]
    logins = [(f"U{rnd.randint(1, 60):04d}", t0 + timedelta(minutes=rnd.randint(0, 300000)),
               f"192.168.{rnd.randint(0, 255)}.{rnd.randint(1, 254)}", rnd.choice(agents), f"{rnd.getrandbits(128):032x}")
              for _ in range(2000)]
    spark.createDataFrame(logins, "USER_ID string, LOGIN_TS timestamp, IP_ADDR string, USER_AGENT string, SESSION_ID string") \
        .write.mode("overwrite").saveAsTable(f"{schema}.user_logins")
    first = ["Anna", "Ben", "Chen", "Dara", "Eli", "Fatima", "Goran", "Hana"]
    last = ["Meyer", "Smith", "Wang", "Okafor", "Silva", "Novak", "Tanaka", "Haddad"]
    contacts = [(car, f"{f} {l}", f"{f.lower()}.{l.lower()}@{car.lower()}-line.example", f"+49 40 {rnd.randint(1000000, 9999999)}", "dispatch")
                for car in ("MSC", "MAERSK", "CMA") for f, l in zip(rnd.sample(first, 4), rnd.sample(last, 4))]
    spark.createDataFrame(contacts, "OWNER string, CONTACT_NAME string, EMAIL_ADDR string, TEL string, ROLE_TXT string") \
        .write.mode("overwrite").saveAsTable(f"{schema}.carrier_contacts")
    return [f"{schema}.{t}" for t in ("container_types", "locations", "containers", "shipments", "legs", "legs_bkp_2025", "leg_daily_summary",
                                      "user_logins", "carrier_contacts")]


def make_sap_po(spark, schema="sap_po", seed=2):
    """FAKE SAP-style purchasing tables with COMPOSITE keys: EKKO (header), EKPO (line), EKET (schedule line).
    Two clients (MANDT) reuse the same order numbers, so EBELN alone is not a key."""
    rnd = random.Random(seed)
    spark.sql(f"CREATE DATABASE IF NOT EXISTS {schema}")
    ekko, ekpo, eket = [], [], []
    for mandt in ("100", "200"):
        for i in range(300):
            ebeln = f"45{i:08d}"
            ekko.append((mandt, ebeln, f"V{rnd.randint(1, 50):05d}", datetime(2026, 1, 1) + timedelta(days=rnd.randint(0, 200))))
            for p in range(1, rnd.randint(2, 4)):
                ebelp = f"{p * 10:05d}"
                ekpo.append((mandt, ebeln, ebelp, f"M{rnd.randint(1, 400):06d}", float(rnd.randint(1, 500))))
                for s in range(1, rnd.randint(2, 3)):
                    eket.append((mandt, ebeln, ebelp, s, datetime(2026, 3, 1) + timedelta(days=rnd.randint(0, 90)), float(rnd.randint(1, 100))))
    spark.createDataFrame(ekko, "MANDT string, EBELN string, LIFNR string, BEDAT timestamp").write.mode("overwrite").saveAsTable(f"{schema}.ekko")
    spark.createDataFrame(ekpo, "MANDT string, EBELN string, EBELP string, MATNR string, MENGE double").write.mode("overwrite").saveAsTable(f"{schema}.ekpo")
    spark.createDataFrame(eket, "MANDT string, EBELN string, EBELP string, ETENR int, EINDT timestamp, MENGE double").write.mode("overwrite").saveAsTable(f"{schema}.eket")
    return [f"{schema}.{t}" for t in ("ekko", "ekpo", "eket")]
