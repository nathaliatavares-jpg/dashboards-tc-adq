"""
Roda a query BigQuery de TC Aquisição, atualiza o RAW array no dashboard HTML
e atualiza SAFRAS/LABELS automaticamente com os meses presentes nos dados.
"""
import subprocess
import csv
import io
import re
from datetime import datetime

BQ_PROJECT = "ddme000725-g9rtvpqr28z-furyid"

QUERY = """
WITH proposals AS (
  SELECT DISTINCT
    prop.CUS_CUST_ID,
    CAST(prop.CCARD_PROP_CREATION_DT AS DATE)  AS data_encendido,
    CAST(prop.CCARD_PROP_UPDATE_DT AS DATE)    AS data_update,
    FORMAT_DATE("%Y-%m", CAST(prop.CCARD_PROP_CREATION_DT AS DATE)) AS safra,
    prop.CCARD_PROP_ID,
    prop.CCARD_PROP_STATUS,
    CASE WHEN prop.CCARD_GLOBAL_LIMIT_AMT_LC > 300 THEN "FULL" ELSE "MICRO" END      AS flag_tc,
    CASE WHEN prop.CCARD_PROP_STATUS = "accepted" THEN "aceito" ELSE "nao_aceito" END AS grupo,
    COALESCE(tt.FLAG_APP_ATIVO, "Sem Info")                                           AS flag_app_ativo,
    CASE WHEN congrats.CUS_CUST_ID IS NOT NULL THEN "EA" ELSE NULL END                AS ea_mp
  FROM `meli-bi-data.WHOWNER.BT_CCARD_PROPOSAL` prop
  LEFT JOIN `meli-bi-data.SBOX_CREDITSTC.SCORE_PROPOSTAS_CCARD` tt
    ON prop.CCARD_PROP_ID = tt.CCARD_PROP_ID
  LEFT JOIN (
    SELECT DISTINCT CUS_CUST_ID, DATE_TRUNC(DT_aceite, MONTH) AS mes_aceite
    FROM `meli-bi-data.SBOX_CREDITSTC.0_AUT_TBL_CONGRATS_ADQ_MLB_TOTAL_AJUSTADA`
    WHERE placement = "EA"
  ) congrats
    ON prop.CUS_CUST_ID = congrats.CUS_CUST_ID
    AND DATE_TRUNC(CAST(prop.CCARD_PROP_UPDATE_DT AS DATE), MONTH) = congrats.mes_aceite
  WHERE prop.SIT_SITE_ID = "MLB"
    AND CAST(prop.CCARD_PROP_CREATION_DT AS DATE) >= "2026-01-01"
),
communications AS (
  SELECT NT.CUS_CUST_ID, NT.SENT_DATE, NT.CAMPAIGN_NAME, NT.APP
  FROM `meli-bi-data.SBOX_MARKETING.BT_OC_CUST_EVENT` NT
  WHERE NT.SIT_SITE_ID = "MLB"
    AND NT.FLAG_NOTIFICATION_CENTER = "N"
    AND NT.EVENT_TYPE IN ("shown","open","arrived")
    AND CAST(NT.SENT_DATE AS DATE) >= "2026-01-01"
    AND (
      NT.CAMPAIGN_NAME LIKE "%TC-AQS%"       OR NT.CAMPAIGN_NAME LIKE "%TCAQS%"
      OR NT.CAMPAIGN_NAME LIKE "%TCADQ%"     OR NT.CAMPAIGN_NAME LIKE "%TCAQUI%"
      OR NT.CAMPAIGN_NAME LIKE "%TC_AQS%"    OR NT.CAMPAIGN_NAME LIKE "%TCAQUISICAO%"
      OR UPPER(NT.CAMPAIGN_NAME) LIKE "%FLOWS_COMMUNICATION_ELDO_FEV_ML_%"
      OR NT.CAMPAIGN_NAME LIKE "%MLB_I_EG_NEW_TC_SOL_ENC%"
      OR NT.CAMPAIGN_NAME LIKE "%MLB_I_EG_XSELLT1_T_TC_SOL_ENC%"
      OR NT.CAMPAIGN_NAME LIKE "%MLB_I_EG_XSELLT1_T_TC_SOL_UP%"
      OR NT.CAMPAIGN_NAME LIKE "%MLB_I_EG_XSELLT1_T_TC_SOL_ST%"
      OR NT.CAMPAIGN_NAME LIKE "%NIA-CCARDACQ-D1%"   OR NT.CAMPAIGN_NAME LIKE "%CCARDACQ-D1-MIC%"
      OR NT.CAMPAIGN_NAME LIKE "%CCARDACQ-D6-MIC%"   OR NT.CAMPAIGN_NAME LIKE "%CCARDACQ-D14-MIC%"
      OR NT.CAMPAIGN_NAME LIKE "%CCARDACQ-BARRIDA%"  OR NT.CAMPAIGN_NAME LIKE "%CCARDACQ-UP1%"
      OR NT.CAMPAIGN_NAME LIKE "%CCARDACQ-SIN-TC-ENR-ML%"
      OR NT.CAMPAIGN_NAME LIKE "%PUSH-SOL-TC2%"      OR NT.CAMPAIGN_NAME LIKE "%CAR_REQ%ENC_TC%"
      OR NT.CAMPAIGN_NAME LIKE "%NIA-CCARD-BARR%"    OR NT.CAMPAIGN_NAME LIKE "%POST-COMPRA-TC%"
      OR NT.CAMPAIGN_NAME LIKE "%POST-PAGO-TC%"      OR NT.CAMPAIGN_NAME LIKE "%PUSH-TC-MELIPLUS%"
      OR NT.CAMPAIGN_NAME LIKE "%UPSELL_TC%"
    )
),
per_prop AS (
  SELECT p.safra, p.flag_tc, p.grupo, p.flag_app_ativo, p.ea_mp,
    COUNT(DISTINCT ct.CAMPAIGN_NAME || "|" || COALESCE(ct.APP, ""))              AS num_total,
    COUNT(DISTINCT CASE WHEN ct.APP = "MERCADOPAGO" THEN ct.CAMPAIGN_NAME END)   AS num_mp,
    COUNT(DISTINCT CASE WHEN ct.APP = "MERCADOLIBRE" THEN ct.CAMPAIGN_NAME END)  AS num_ml
  FROM proposals p
  LEFT JOIN communications ct
    ON p.CUS_CUST_ID = ct.CUS_CUST_ID
    AND (
      (p.CCARD_PROP_STATUS = "pending"  AND CAST(ct.SENT_DATE AS DATE) BETWEEN p.data_encendido AND CURRENT_DATE()) OR
      (p.CCARD_PROP_STATUS != "pending" AND CAST(ct.SENT_DATE AS DATE) BETWEEN p.data_encendido AND p.data_update)
    )
  GROUP BY p.safra, p.flag_tc, p.grupo, p.flag_app_ativo, p.ea_mp, p.CCARD_PROP_ID, p.CUS_CUST_ID
)
SELECT safra, flag_tc, grupo, flag_app_ativo, ea_mp,
  COUNTIF(num_total=0) AS sem_total, COUNTIF(num_total BETWEEN 1 AND 3) AS c13_total,
  COUNTIF(num_total BETWEEN 4 AND 7) AS c47_total, COUNTIF(num_total>=8) AS c8_total,
  COUNTIF(num_mp=0) AS sem_mp, COUNTIF(num_mp BETWEEN 1 AND 3) AS c13_mp,
  COUNTIF(num_mp BETWEEN 4 AND 7) AS c47_mp, COUNTIF(num_mp>=8) AS c8_mp,
  COUNTIF(num_ml=0) AS sem_ml, COUNTIF(num_ml BETWEEN 1 AND 3) AS c13_ml,
  COUNTIF(num_ml BETWEEN 4 AND 7) AS c47_ml, COUNTIF(num_ml>=8) AS c8_ml,
  COUNT(*) AS total
FROM per_prop
GROUP BY 1,2,3,4,5 ORDER BY 1,2,3,4,5
"""

MONTH_PT = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
}


def run_query():
    print("Rodando query BigQuery...")
    result = subprocess.run(
        [
            "bq", "query",
            f"--project_id={BQ_PROJECT}",
            "--use_legacy_sql=false",
            "--format=csv",
            "--max_rows=1000",
            QUERY,
        ],
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if result.returncode != 0:
        raise RuntimeError(f"bq query falhou:\n{result.stderr}")
    # remove linhas de status "Waiting on..."
    lines = [l for l in result.stdout.splitlines() if not l.startswith("Waiting on")]
    return "\n".join(lines)


def parse_csv(csv_text):
    reader = csv.DictReader(io.StringIO(csv_text))
    return list(reader)


def rows_to_js(rows):
    safras = sorted(set(r["safra"] for r in rows))
    js_lines = []
    for r in rows:
        ea = f"'EA'" if r["ea_mp"] == "EA" else "''"
        nums = [
            r["sem_total"], r["c13_total"], r["c47_total"], r["c8_total"],
            r["sem_mp"],    r["c13_mp"],    r["c47_mp"],    r["c8_mp"],
            r["sem_ml"],    r["c13_ml"],    r["c47_ml"],    r["c8_ml"],
            r["total"],
        ]
        line = (
            f"['{r['safra']}','{r['flag_tc']}','{r['grupo']}',"
            f"'{r['flag_app_ativo']}',{ea},"
            + ",".join(nums)
            + "]"
        )
        js_lines.append(line)
    return safras, js_lines


def safra_label(safra):
    year, month = safra.split("-")
    return f"{MONTH_PT[month]}/{year[2:]}"


def update_html(html_path, safras, js_lines):
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    # --- RAW array ---
    start_marker = "const RAW = ["
    end_marker = "\n];"
    si = content.index(start_marker)
    ei = content.index(end_marker, si) + len(end_marker)
    new_raw = "const RAW = [\n" + ",\n".join(js_lines) + ",\n];"
    content = content[:si] + new_raw + content[ei:]

    # --- SAFRAS ---
    safras_js = "[" + ",".join(f"'{s}'" for s in safras) + "]"
    content = re.sub(r"const SAFRAS\s*=\s*\[[^\]]*\];", f"const SAFRAS = {safras_js};", content)

    # --- LABELS ---
    labels_js = "[" + ",".join(f"'{safra_label(s)}'" for s in safras) + "]"
    content = re.sub(r"const LABELS\s*=\s*\[[^\]]*\];", f"const LABELS = {labels_js};", content)

    # --- Data de geração no header ---
    today = datetime.now().strftime("%d/%m/%Y")
    content = re.sub(r"Gerado em: \d{2}/\d{2}/\d{4}", f"Gerado em: {today}", content)

    # --- Período no header ---
    last_day = datetime.now().strftime("%d/%m/%Y")
    content = re.sub(
        r"Período: 01/01/2026 – \d{2}/\d{2}/\d{4}",
        f"Período: 01/01/2026 – {last_day}",
        content,
    )

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Dashboard atualizado: {len(js_lines)} linhas, safras: {safras}")


if __name__ == "__main__":
    csv_text = run_query()
    rows = parse_csv(csv_text)
    if not rows:
        raise ValueError("Query retornou 0 linhas — abortando")
    safras, js_lines = rows_to_js(rows)
    update_html("dash_tc_comunicacoes.html", safras, js_lines)
