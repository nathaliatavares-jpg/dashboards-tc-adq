"""
Queries BigQuery for TC card usage data and updates uso.html.
Same data as update_uso.ps1 but targets dashboards-tc-adq/uso.html.
"""
import subprocess
import csv
import io
import re
import sys
from collections import defaultdict

BQ_PROJECT = "ddme000725-g9rtvpqr28z-furyid"
BQ_CMD     = "bq.cmd" if sys.platform == "win32" else "bq"
HTML_PATH  = "uso.html"

PLACEMENTS = [
    "One Page", "Bottom Sheet", "HOME_MINICARD_MP_RESTYLING",
    "CHO - CHECKOUT ML", "Onboarding", "BANNER_DASHBOARD", "PUSH", "EA",
    "PUSH_ML_ENCENDIDO_D1", "VIP", "CARDS_LISTING_RESTYLING_FULL_TC",
    "PUSH_ML_D10", "PDP", "VIP_WEB", "MODAL_DE_PAGOS",
]
TIMINGS = ["Same Day", "10D", "30D", "60D", "60D+", "Sem Uso"]

QUERY = """
SELECT
  FORMAT_DATE('%Y%m', DATE(DT_ENCENDIDO)) AS safra,
  placement,
  timing_uso_ccard AS timing,
  CASE WHEN TRIM(FLAG_TC) = '1. TC Full' THEN 'full' ELSE 'micro' END AS tc,
  SUM(qtde) AS qtde
FROM `meli-bi-data.SBOX_CREDITSTC.base_projecao_emissao_igor`
WHERE
  DT_ENCENDIDO IS NOT NULL
  AND placement IS NOT NULL AND placement != '' AND placement != 'UNKNOWN'
  AND timing_uso_ccard IS NOT NULL
  AND DATE(DT_ENCENDIDO) >= '2024-01-01'
GROUP BY ALL
ORDER BY safra, placement, tc, timing
"""


def run_bq(sql):
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
        raise RuntimeError(f"bq query falhou (rc={result.returncode}):\n{result.stderr[:500]}")
    lines = [l for l in result.stdout.splitlines()
             if not l.startswith("Waiting on") and not l.startswith("Current status")]
    return "\n".join(lines)


def tkey(t):
    label = re.sub(r"[^a-zA-Z0-9]", "_", t)
    if label[0].isdigit():
        return f"'{label}'"
    return label


def rnd(n):
    return str(round(n, 1))


def build_js(rows):
    # Build aggregation dict: (tc, placement, safra, timing) -> qtde
    agg = defaultdict(float)
    safra_set = set()
    for r in rows:
        key = (r["tc"], r["placement"], r["safra"], r["timing"])
        agg[key] += float(r["qtde"] or 0)
        safra_set.add(r["safra"])

    safras = sorted(s for s in safra_set if s >= "202401")
    last3  = safras[-3:] if len(safras) >= 3 else safras

    tc_names = {"full": "full", "micro": "micro"}

    js_parts = []
    js_parts.append("const SAFRAS=['" + "','".join(safras) + "'];")

    pl_escaped = [f"'{p.replace(chr(39), chr(92)+chr(39))}'" for p in PLACEMENTS]
    js_parts.append("const PLS=[" + ",".join(pl_escaped) + "];")

    for tc_key in ("full", "micro"):
        obj_parts = []
        for pl in PLACEMENTS:
            uso_pct = []
            vol_arr = []
            t_break  = {t: 0.0 for t in TIMINGS}
            t_total  = 0.0
            ts_arrays = {t: [] for t in TIMINGS}

            for s in safras:
                total   = sum(agg[(tc_key, pl, s, t)] for t in TIMINGS)
                sem_uso = agg[(tc_key, pl, s, "Sem Uso")]

                if total > 0:
                    uso_pct.append(rnd((total - sem_uso) / total * 100))
                    vol_arr.append(rnd(total / 1000))
                    for t in TIMINGS:
                        ts_arrays[t].append(rnd(agg[(tc_key, pl, s, t)] / total * 100))
                else:
                    uso_pct.append("null")
                    vol_arr.append("null")
                    for t in TIMINGS:
                        ts_arrays[t].append("null")

                if s in last3:
                    for t in TIMINGS:
                        v = agg[(tc_key, pl, s, t)]
                        t_break[t] += v
                        t_total    += v

            tim_parts = []
            ts_parts  = []
            for t in TIMINGS:
                k = tkey(t)
                pct = rnd(t_break[t] / t_total * 100) if t_total > 0 else "0"
                tim_parts.append(f"{k}:{pct}")
                ts_parts.append(f"{k}:[{','.join(ts_arrays[t])}]")

            pl_safe = pl.replace("'", "\\'")
            obj_parts.append(
                f"'{pl_safe}':{{uso:[{','.join(uso_pct)}],"
                f"vol:[{','.join(vol_arr)}],"
                f"t:{{{','.join(tim_parts)}}},"
                f"ts:{{{','.join(ts_parts)}}}}}"
            )

        js_parts.append(f"const D_{tc_key.upper()}={{{','.join(obj_parts)}}};")

    return "\n".join(js_parts)


def main():
    print("Rodando query BigQuery (uso do cartao)...")
    csv_text = run_bq(QUERY)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    if not rows:
        raise ValueError("Query retornou 0 linhas")
    print(f"{len(rows)} linhas recebidas.")

    js_data = build_js(rows)

    with open(HTML_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # Replace everything between // ===== DATA ===== and </script>
    new_html = re.sub(
        r"(// ===== DATA =====\n).*?(\n</script>)",
        lambda m: m.group(1) + js_data + m.group(2),
        html,
        flags=re.DOTALL,
    )

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"uso.html atualizado: {len(rows)} linhas, {js_data.count('const')} blocos JS")


if __name__ == "__main__":
    main()
