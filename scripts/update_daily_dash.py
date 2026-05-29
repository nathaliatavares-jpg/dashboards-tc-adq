"""
Queries BigQuery for daily placement TC ADQ data and updates daily.html.
"""
import subprocess
import csv
import io
import re
import json
import sys
from datetime import date, datetime, timedelta
from collections import defaultdict

BQ_PROJECT = "ddme000725-g9rtvpqr28z-furyid"
BQ_CMD     = "bq.cmd" if sys.platform == "win32" else "bq"
START_DATE  = "2026-03-21"
HTML_PATH   = "daily.html"

QUERY_PL = f"""
SELECT
  CAST(dt_aceite AS STRING) AS data,
  PLACEMENT AS placement,
  COUNT(DISTINCT CUS_CUST_ID) AS usuarios
FROM `meli-bi-data.SBOX_CREDITSTC.0_AUT_TBL_CONGRATS_ADQ_MLB_TOTAL_AJUSTADA`
WHERE dt_aceite >= '{START_DATE}'
GROUP BY 1, 2
ORDER BY 1, 2
"""

QUERY_TOTAL = f"""
SELECT
  CAST(dt_aceite AS STRING) AS data,
  COUNT(DISTINCT CUS_CUST_ID) AS usuarios
FROM `meli-bi-data.SBOX_CREDITSTC.0_AUT_TBL_CONGRATS_ADQ_MLB_TOTAL_AJUSTADA`
WHERE dt_aceite >= '{START_DATE}'
GROUP BY 1
ORDER BY 1
"""

SHORT_NAMES = {
    "HOME_MINICARD_MP_RESTYLING":       "MINICARD REST.",
    "EA":                                "EA",
    "CHO - CHECKOUT ML":                 "CHO Checkout",
    "One Page":                          "One Page",
    "Bottom Sheet":                      "Bottom Sheet",
    "Onboarding":                        "Onboarding",
    "CARDS_LISTING_RESTYLING_FULL_TC":   "CARDS FULL TC",
    "PUSH_ML_ENCENDIDO_D1":              "PUSH ENC.D1",
    "PUSH_ML_D10":                       "PUSH D10",
    "PUSH":                              "PUSH",
    "VIP":                               "VIP",
    "CARDS_LISTING_RESTYLING_MICRO_TC":  "CARDS MICRO TC",
    "PDP":                               "PDP",
    "VIP_WEB":                           "VIP_WEB",
    "CREDIT_NUMERIC_SCORING":            "CREDIT SCORING",
}


def run_bq(sql):
    # Collapse to single line so Windows cmd.exe handles the argument correctly
    sql_flat = " ".join(sql.split())
    result = subprocess.run(
        [BQ_CMD, "query",
         f"--project_id={BQ_PROJECT}",
         "--use_legacy_sql=false",
         "--format=csv",
         "--max_rows=500000",
         sql_flat],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"bq query falhou (rc={result.returncode}):\nSTDOUT: {result.stdout[:500]}\nSTDERR: {result.stderr[:500]}")
    lines = [l for l in result.stdout.splitlines()
             if not l.startswith("Waiting on") and not l.startswith("Current status")]
    return "\n".join(lines)


def is_pontual(pl):
    return bool(re.search(r"\d{6}", pl))


def short(pl):
    return SHORT_NAMES.get(pl, pl.replace("_", " ")[:18])


def acel_short(pl):
    m = {
        "HOME_MINICARD_MP_RESTYLING":       "MINICARD REST.",
        "EA":                                "EA",
        "CHO - CHECKOUT ML":                 "CHO ML",
        "One Page":                          "One Page",
        "Bottom Sheet":                      "Bottom Sheet",
        "Onboarding":                        "Onboarding",
        "CARDS_LISTING_RESTYLING_FULL_TC":   "CARDS FULL TC",
        "PUSH_ML_ENCENDIDO_D1":              "PUSH ENC.D1",
        "PUSH_ML_D10":                       "PUSH D10",
        "PUSH":                              "PUSH",
        "VIP":                               "VIP",
        "CARDS_LISTING_RESTYLING_MICRO_TC":  "CARDS MICRO TC",
        "PDP":                               "PDP",
        "VIP_WEB":                           "VIP_WEB",
        "CREDIT_NUMERIC_SCORING":            "CREDIT SCORING",
    }
    return m.get(pl, pl.replace("_", " ")[:18])


def fmt_br(n):
    return f"{n:,}".replace(",", ".")


def build_js_obj(d: dict) -> str:
    parts = []
    for k, v in d.items():
        safe_k = k.replace("'", "\\'")
        parts.append(f"'{safe_k}':{json.dumps(v)}")
    return "{" + ",".join(parts) + "}"


def build_js_arr_of_obj(items: list, fields: list) -> str:
    parts = []
    for item in items:
        kv = []
        for f in fields:
            v = item.get(f)
            if isinstance(v, str):
                kv.append(f"{f}:'{v}'")
            elif v is None:
                kv.append(f"{f}:null")
            else:
                kv.append(f"{f}:{v}")
        parts.append("{" + ",".join(kv) + "}")
    return "[" + ",".join(parts) + "]"


def main():
    today = date.today()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)

    print("Rodando query de placements por dia...")
    pl_csv = run_bq(QUERY_PL)
    print("Rodando query de total por dia...")
    tot_csv = run_bq(QUERY_TOTAL)

    pl_rows  = list(csv.DictReader(io.StringIO(pl_csv)))
    tot_rows = list(csv.DictReader(io.StringIO(tot_csv)))

    # Build date list from START_DATE to today
    start_d  = date.fromisoformat(START_DATE)
    dates    = [start_d + timedelta(days=i) for i in range((today - start_d).days + 1)]
    date_strs = [d.isoformat() for d in dates]
    n = len(dates)

    # Total per day (deduplicated)
    total_map = {r["data"]: int(r["usuarios"]) for r in tot_rows}
    total_arr = [total_map.get(d, 0) for d in date_strs]

    # Placement data by date
    pl_by_date = defaultdict(lambda: defaultdict(int))
    all_pl = set()
    for r in pl_rows:
        pl_by_date[r["data"]][r["placement"]] = int(r["usuarios"])
        all_pl.add(r["placement"])

    permanent = sorted(p for p in all_pl if not is_pontual(p))
    pontuais  = sorted(p for p in all_pl if is_pontual(p))

    pl_obj = {p: [pl_by_date[d].get(p, 0) for d in date_strs] for p in permanent}

    # Pontual (UNICOS) placements
    unicos_pl = []
    for p in pontuais:
        vals = [pl_by_date[d].get(p, 0) for d in date_strs]
        total = sum(vals)
        if total > 0:
            unicos_pl.append({"pl": p, "total": total, "vals": vals})
    unicos_pl.sort(key=lambda x: -x["total"])

    unicos_arr = [0] * n
    for u in unicos_pl:
        for i, v in enumerate(u["vals"]):
            unicos_arr[i] += v

    weekends = [d.weekday() >= 5 for d in dates]

    # KPI helpers
    yday_idx = date_strs.index(yesterday.isoformat()) if yesterday.isoformat() in date_strs else n - 2
    ontem_val = total_arr[yday_idx]
    total_clean = total_arr[:yday_idx + 1]  # up to and including yesterday
    last7 = total_clean[-7:] if len(total_clean) >= 7 else total_clean
    media_7d = round(sum(last7) / len(last7)) if last7 else 0
    pico_val = max(total_clean) if total_clean else 0
    pico_idx = total_clean.index(pico_val) if pico_val else 0
    pico_date = dates[pico_idx].strftime("%d/%m")

    if yday_idx >= 1:
        antes_val = total_arr[yday_idx - 1]
        delta_ontem = round((ontem_val - antes_val) / antes_val * 100, 1) if antes_val else 0
    else:
        delta_ontem = 0

    # NOVOS: first appeared in last 14 days
    cutoff14 = today - timedelta(days=14)
    novos = []
    all_pl_vals = list(pl_obj.items()) + [(u["pl"], u["vals"]) for u in unicos_pl]
    for p, vals in all_pl_vals:
        first = next((i for i, v in enumerate(vals) if v > 0), None)
        if first is None:
            continue
        if dates[first] >= cutoff14:
            novos.append({"pl": p, "total": sum(vals), "from": dates[first].strftime("%d/%m")})
    novos.sort(key=lambda x: -x["total"])

    # ACEL: last 14 complete days vs prior 14 (permanent only)
    end14   = yesterday
    start14 = end14 - timedelta(days=13)
    start_prev = start14 - timedelta(days=14)
    end_prev   = start14 - timedelta(days=1)

    def sum_range(vals, sd, ed):
        return sum(v for d, v in zip(dates, vals) if sd <= d <= ed)

    acel = []
    for p in permanent:
        vals  = pl_obj[p]
        atual = sum_range(vals, start14, end14)
        prev  = sum_range(vals, start_prev, end_prev)
        if atual == 0 and prev == 0:
            continue
        if prev > 0:
            delta = round((atual - prev) / prev * 100, 1)
        elif atual > 0:
            delta = 999
        else:
            delta = -100
        acel.append({"pl": acel_short(p), "atual": atual, "prev": prev, "delta": delta})
    acel.sort(key=lambda x: -x["delta"])

    # KPI: maior aceleração / maior queda
    maior_acel = acel[0]  if acel else None
    maior_queda = acel[-1] if acel else None

    # HM: top 13 permanent placements by 14d volume, last 14 complete days
    pl_14d = {p: sum_range(pl_obj[p], start14, end14) for p in permanent}
    hm_pls  = sorted(permanent, key=lambda p: -pl_14d[p])[:13]
    hm_start_d = start14.isoformat()
    hm_end_d   = end14.isoformat()
    hm_start = date_strs.index(hm_start_d) if hm_start_d in date_strs else n - 14
    hm_end   = date_strs.index(hm_end_d)   if hm_end_d   in date_strs else n - 2
    hm_short_names = [short(p) for p in hm_pls]

    # ALERTAS: D-1 drops/stops/spikes
    alertas = []
    if yday_idx >= 1:
        dm2_idx = yday_idx - 1
        for p in permanent:
            v1 = pl_obj[p][yday_idx]
            v2 = pl_obj[p][dm2_idx]
            if v2 > 100:
                if v1 == 0:
                    alertas.append({"tipo": "stop", "pl": p, "ontem": v1, "antes": v2, "delta": -100})
                elif v2 > 0:
                    d = round((v1 - v2) / v2 * 100)
                    if d <= -50:
                        alertas.append({"tipo": "drop", "pl": p, "ontem": v1, "antes": v2, "delta": d})
            if v2 < v1 and v1 >= 1000:
                d = round((v1 - v2) / max(v2, 1) * 100)
                if d >= 200:
                    alertas.append({"tipo": "spike", "pl": p, "ontem": v1, "antes": v2, "delta": d})

    labels = [d.strftime("%d/%m") for d in dates]
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    yday_fmt = yesterday.strftime("%d/%m")
    dbefore_fmt = day_before.strftime("%d/%m")

    # Build replacement JS strings
    datas_js    = json.dumps(date_strs)
    labels_js   = json.dumps(labels)
    weekends_js = json.dumps(weekends)
    total_js    = json.dumps(total_arr)
    unicos_js   = json.dumps(unicos_arr)
    pl_js       = build_js_obj(pl_obj)
    hm_pl_js    = json.dumps(hm_pls)
    hm_short_js = json.dumps(hm_short_names)
    novos_js    = build_js_arr_of_obj(novos,  ["pl", "total", "from"])
    acel_js     = build_js_arr_of_obj(acel,   ["pl", "atual", "prev", "delta"])
    alertas_js  = build_js_arr_of_obj(alertas, ["tipo", "pl", "ontem", "antes", "delta"])

    unicos_pl_parts = []
    for u in unicos_pl:
        safe_pl = u["pl"].replace("'", "\\'")
        unicos_pl_parts.append(f"{{pl:'{safe_pl}',total:{u['total']},vals:{json.dumps(u['vals'])}}}")
    unicos_pl_js = "[" + ",".join(unicos_pl_parts) + "]"

    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    def sub(pattern, repl, s, flags=0):
        return re.sub(pattern, lambda _: repl, s, flags=flags)

    # Subtitle
    html = sub(
        r'21/03/2026 &rarr; \d{2}/\d{2} &middot; atualizado em [^<]+',
        f"21/03/2026 &rarr; {yday_fmt} &middot; atualizado em {now_str}",
        html,
    )

    # KPI: ontem
    html = sub(r"Ontem \(\d{2}/\d{2}\)", f"Ontem ({yday_fmt})", html)
    html = sub(
        r'(<div class="kpi-value" style="color:var\(--accent\)">)[\d.]+(?=<)',
        f'<div class="kpi-value" style="color:var(--accent)">{fmt_br(ontem_val)}',
        html,
    )
    arrow = "&#9650;" if delta_ontem >= 0 else "&#9660;"
    cls   = "up"      if delta_ontem >= 0 else "down"
    sign  = "+"       if delta_ontem >= 0 else ""
    html = sub(
        r'<div class="kpi-sub (?:up|down)">&#96[56]0; [+-]?[\d.]+% vs dia anterior</div>',
        f'<div class="kpi-sub {cls}">{arrow} {sign}{delta_ontem}% vs dia anterior</div>',
        html,
    )

    # KPI: média 7d
    html = sub(
        r'(<div class="kpi-label">Media ultimos 7 dias</div>\s*<div class="kpi-value">)[\d.]+(?=<)',
        f'<div class="kpi-label">Media ultimos 7 dias</div>\n  <div class="kpi-value">{fmt_br(media_7d)}',
        html,
    )

    # KPI: pico
    html = sub(
        r'(<div class="kpi-label">Pico no periodo</div>\s*<div class="kpi-value" style="color:var\(--green\)">)[\d.]+(?=<)',
        f'<div class="kpi-label">Pico no periodo</div>\n  <div class="kpi-value" style="color:var(--green)">{fmt_br(pico_val)}',
        html,
    )
    html = sub(
        r'(<div class="kpi-sub" style="color:var\(--muted\)">)\d{2}/\d{2}(?=<)',
        f'<div class="kpi-sub" style="color:var(--muted)">{pico_date}',
        html,
    )

    # KPI: maior aceleração
    if maior_acel:
        html = sub(
            r'(<div class="kpi-label">Maior aceleracao 14d</div>\s*<div class="kpi-value" style="color:var\(--green\);font-size:16px;">)[^<]+(?=<)',
            f'<div class="kpi-label">Maior aceleracao 14d</div>\n    <div class="kpi-value" style="color:var(--green);font-size:16px;">{maior_acel["pl"]}',
            html,
        )
        html = sub(
            r'(<div class="kpi-sub up">&#9650; \+)[^<]+(vs 14d ant\.)',
            f'<div class="kpi-sub up">&#9650; +{maior_acel["delta"]}% vs 14d ant.',
            html,
        )

    # KPI: maior queda
    if maior_queda:
        html = sub(
            r'(<div class="kpi-label">Maior queda 14d</div>\s*<div class="kpi-value" style="color:var\(--red\);font-size:16px;">)[^<]+(?=<)',
            f'<div class="kpi-label">Maior queda 14d</div>\n    <div class="kpi-value" style="color:var(--red);font-size:16px;">{maior_queda["pl"]}',
            html,
        )
        html = sub(
            r'(<div class="kpi-sub down">&#9660; )[^<]+(vs 14d ant\.)',
            f'<div class="kpi-sub down">&#9660; {maior_queda["delta"]}% vs 14d ant.',
            html,
        )

    # JS arrays/objects (all single-line in the HTML)
    html = sub(r"const DATAS\s*=\s*\[.*?\];",   f"const DATAS   = {datas_js};",    html)
    html = sub(r"const LABELS\s*=\s*\[.*?\];",  f"const LABELS  = {labels_js};",   html)
    html = sub(r"const WEEKENDS\s*=\s*\[.*?\];", f"const WEEKENDS= {weekends_js};", html)
    html = sub(r"const TOTAL\s*=\s*\[.*?\];",   f"const TOTAL   = {total_js};",    html)
    html = sub(r"const UNICOS\s*=\s*\[.*?\];",  f"const UNICOS  = {unicos_js};",   html)
    html = sub(r"const PL\s*=\s*\{.*?\};",      f"const PL      = {pl_js};",       html)
    html = sub(r"const NOVOS\s*=\s*\[.*?\];",   f"const NOVOS   = {novos_js};",    html)
    html = sub(r"const ACEL\s*=\s*\[.*?\];",    f"const ACEL    = {acel_js};",     html)
    html = sub(r"const HM_PL\s*=\s*\[.*?\];",   f"const HM_PL      = {hm_pl_js};",    html)
    html = sub(r"const HM_SHORT\s*=\s*\[.*?\];", f"const HM_SHORT   = {hm_short_js};", html)
    html = sub(r"const HM_START\s*=\s*\d+;",    f"const HM_START   = {hm_start};",    html)
    html = sub(r"const HM_END\s*=\s*\d+;",      f"const HM_END     = {hm_end};",      html)
    html = sub(r"const ALERTAS\s*=\s*\[.*?\];",  f"const ALERTAS    = {alertas_js};",  html)
    html = sub(r"const UNICOS_PL\s*=\s*\[.*?\];", f"const UNICOS_PL  = {unicos_pl_js};", html)
    html = sub(r"const DM1_LABEL\s*=\s*'[^']*';", f"const DM1_LABEL  = '{yday_fmt}';",    html)
    html = sub(r"const DM2_LABEL\s*=\s*'[^']*';", f"const DM2_LABEL  = '{dbefore_fmt}';", html)

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(
        f"daily.html atualizado: {n} dias ({START_DATE} a {today}), "
        f"{len(permanent)} placements permanentes, {len(pontuais)} pontuais"
    )


if __name__ == "__main__":
    main()
