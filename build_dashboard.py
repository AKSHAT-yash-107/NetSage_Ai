import argparse
from pathlib import Path
import json
import html
import pandas as pd

EXPECTED_IDS = [f"C{i:03d}" for i in range(1, 81)]
STATUSES = ["Pending", "Accepted", "Edited", "Rejected"]

def load_cases(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Cases file not found: {path.resolve()}")
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    elif path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path, sheet_name="cases")
    else:
        raise ValueError("Cases file must be CSV or XLSX.")
    if "case_id" not in df.columns:
        raise ValueError("cases file must contain case_id.")
    df["case_id"] = df["case_id"].astype(str).str.strip().str.upper()
    if len(df) != 80 or df["case_id"].nunique() != 80:
        raise ValueError("Cases must contain exactly 80 unique rows.")
    if set(df["case_id"]) != set(EXPECTED_IDS):
        raise ValueError("Cases must contain exactly C001-C080.")
    return df.set_index("case_id").loc[EXPECTED_IDS].reset_index()

def load_reviews(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Review log not found: {path.resolve()}\n"
            "Run build_review_log.py first."
        )
    df = pd.read_csv(path)
    required = [
        "case_id","category","severity","ai_root_cause",
        "ai_confidence","human_status","agreement","reviewer_note"
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"review_log.csv is missing columns: {missing}")
    df["case_id"] = df["case_id"].astype(str).str.strip().str.upper()
    if len(df) != 80 or df["case_id"].nunique() != 80:
        raise ValueError("Review log must contain exactly 80 unique rows.")
    if set(df["case_id"]) != set(EXPECTED_IDS):
        raise ValueError("Review log must contain exactly C001-C080.")
    return df.set_index("case_id").loc[EXPECTED_IDS].reset_index()

def safe(v):
    if pd.isna(v):
        return ""
    return html.escape(str(v))

def metrics(reviews):
    status = {
        s: int((reviews["human_status"].fillna("") == s).sum())
        for s in STATUSES
    }
    findings = reviews["ai_root_cause"].fillna("").astype(str).str.strip().ne("")
    reviewed = reviews["human_status"].fillna("").astype(str).str.strip().ne("Pending")
    conf = pd.to_numeric(reviews["ai_confidence"], errors="coerce")
    agreement = reviews["agreement"].fillna("").astype(str).str.strip().str.lower()
    yes = int(agreement.isin({"yes","true","1","agreed","match"}).sum())
    no = int(agreement.isin({"no","false","0","disagreed","mismatch"}).sum())
    return {
        "total": 80,
        "ai_findings": int(findings.sum()),
        "reviewed": int(reviewed.sum()),
        "pending": status["Pending"],
        "accepted": status["Accepted"],
        "edited": status["Edited"],
        "rejected": status["Rejected"],
        "completion": round(reviewed.mean()*100, 1),
        "avg_confidence": round(conf.mean()*100, 1) if conf.notna().any() else None,
        "agreement_yes": yes,
        "agreement_no": no,
    }

def build(cases, reviews, output):
    m = metrics(reviews)
    status_data = [{"label":s,"value":m[s.lower()]} for s in STATUSES]
    category = reviews["category"].fillna("Unknown").astype(str).value_counts().to_dict()
    severity = reviews["severity"].fillna("Unknown").astype(str).value_counts().to_dict()

    finding = {}
    for text in reviews["ai_root_cause"].fillna("").astype(str):
        for part in text.split(" | "):
            rule = part.split(":",1)[0].strip()
            if rule:
                finding[rule] = finding.get(rule,0) + 1

    rows = []
    for _, r in reviews.iterrows():
        rows.append({c: ("" if pd.isna(r[c]) else r[c]) for c in [
            "case_id","category","severity","ai_root_cause",
            "ai_confidence","human_status","agreement","reviewer_note"
        ]})

    payload = {
        "metrics":m,
        "status":status_data,
        "category":category,
        "severity":severity,
        "findings":finding,
        "rows":rows
    }

    data = json.dumps(payload, ensure_ascii=False).replace("</","<\\/")

    doc = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NetSage AI - Review Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
*{box-sizing:border-box}
body{margin:0;font-family:Arial,sans-serif;background:#f4f6f8;color:#17202a}
header{background:#101820;color:white;padding:28px 40px}
header h1{margin:0 0 6px;font-size:28px}
header p{margin:0;opacity:.75}
main{max-width:1400px;margin:30px auto;padding:0 24px}
.grid{display:grid;gap:18px}
.metrics{grid-template-columns:repeat(6,1fr)}
.card{background:white;border-radius:12px;padding:20px;box-shadow:0 2px 10px rgba(0,0,0,.06)}
.metric-label{color:#65727e;font-size:13px;margin-bottom:10px}
.metric-value{font-size:30px;font-weight:700}
.charts{grid-template-columns:1fr 1fr;margin-top:20px}
.chart-card{height:380px}
.chart-card canvas{max-height:300px}
.table-card{margin-top:20px}
.controls{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap}
input,select{padding:10px 12px;border:1px solid #ccd3d9;border-radius:8px;background:white}
input{min-width:260px}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:11px;border-bottom:1px solid #e6e9ec;text-align:left;vertical-align:top}
th{background:#f7f8f9;position:sticky;top:0}
.badge{display:inline-block;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:700;background:#e9edf1}
.section-title{margin:0 0 15px}
@media(max-width:1100px){.metrics{grid-template-columns:repeat(3,1fr)}}
@media(max-width:700px){.metrics,.charts{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
<h1>NetSage AI</h1>
<p>Network Fault Detection & Human Review Dashboard</p>
</header>
<main>
<section class="grid metrics">
<div class="card"><div class="metric-label">TOTAL CASES</div><div class="metric-value" id="total"></div></div>
<div class="card"><div class="metric-label">AI FINDINGS</div><div class="metric-value" id="findings"></div></div>
<div class="card"><div class="metric-label">REVIEWED</div><div class="metric-value" id="reviewed"></div></div>
<div class="card"><div class="metric-label">PENDING</div><div class="metric-value" id="pending"></div></div>
<div class="card"><div class="metric-label">AVG AI CONFIDENCE</div><div class="metric-value" id="confidence"></div></div>
<div class="card"><div class="metric-label">REVIEW COMPLETION</div><div class="metric-value" id="completion"></div></div>
</section>

<section class="grid charts">
<div class="card chart-card"><h2 class="section-title">Human Review Status</h2><canvas id="statusChart"></canvas></div>
<div class="card chart-card"><h2 class="section-title">Severity Distribution</h2><canvas id="severityChart"></canvas></div>
<div class="card chart-card"><h2 class="section-title">Cases by Category</h2><canvas id="categoryChart"></canvas></div>
<div class="card chart-card"><h2 class="section-title">Detected Rule Families</h2><canvas id="findingChart"></canvas></div>
</section>

<section class="card table-card">
<h2 class="section-title">Case Review Detail</h2>
<div class="controls">
<input id="search" placeholder="Search case, category, finding...">
<select id="status"><option value="">All statuses</option><option>Pending</option><option>Accepted</option><option>Edited</option><option>Rejected</option></select>
<select id="severity"><option value="">All severities</option></select>
</div>
<div class="table-wrap">
<table>
<thead><tr><th>Case</th><th>Category</th><th>Severity</th><th>AI Root Cause</th><th>Confidence</th><th>Human Status</th><th>Agreement</th><th>Reviewer Note</th></tr></thead>
<tbody id="table"></tbody>
</table>
</div>
</section>
</main>

<script>
const DATA=__DATA__;
const m=DATA.metrics;
document.getElementById("total").textContent=m.total;
document.getElementById("findings").textContent=m.ai_findings+"/"+m.total;
document.getElementById("reviewed").textContent=m.reviewed;
document.getElementById("pending").textContent=m.pending;
document.getElementById("confidence").textContent=m.avg_confidence===null?"-":m.avg_confidence+"%";
document.getElementById("completion").textContent=m.completion+"%";

function chart(id,type,labels,values){
new Chart(document.getElementById(id),{
type:type,data:{labels:labels,datasets:[{label:"Cases",data:values}]},
options:{responsive:true,maintainAspectRatio:false}
});
}
chart("statusChart","doughnut",DATA.status.map(x=>x.label),DATA.status.map(x=>x.value));
chart("severityChart","bar",Object.keys(DATA.severity),Object.values(DATA.severity));
chart("categoryChart","bar",Object.keys(DATA.category),Object.values(DATA.category));
chart("findingChart","bar",Object.keys(DATA.findings),Object.values(DATA.findings));

const sf=document.getElementById("severity");
[...new Set(DATA.rows.map(x=>String(x.severity||"Unknown")))].sort().forEach(x=>{
let o=document.createElement("option");o.value=x;o.textContent=x;sf.appendChild(o);
});

function esc(v){
let d=document.createElement("div");d.textContent=v??"";return d.innerHTML;
}

function render(){
const q=document.getElementById("search").value.toLowerCase();
const st=document.getElementById("status").value;
const sv=document.getElementById("severity").value;
const body=document.getElementById("table");
body.innerHTML="";

DATA.rows.filter(r=>{
const text=[r.case_id,r.category,r.severity,r.ai_root_cause,r.human_status,r.reviewer_note].join(" ").toLowerCase();
return (!q||text.includes(q))&&(!st||r.human_status===st)&&(!sv||String(r.severity)===sv);
}).forEach(r=>{
const tr=document.createElement("tr");
const c=r.ai_confidence===""?"-":(Number(r.ai_confidence)*100).toFixed(0)+"%";
tr.innerHTML="<td><b>"+esc(r.case_id)+"</b></td>"+
"<td>"+esc(r.category)+"</td>"+
"<td><span class='badge'>"+esc(r.severity)+"</span></td>"+
"<td>"+esc(r.ai_root_cause)+"</td>"+
"<td>"+c+"</td>"+
"<td><span class='badge'>"+esc(r.human_status)+"</span></td>"+
"<td>"+esc(r.agreement)+"</td>"+
"<td>"+esc(r.reviewer_note)+"</td>";
body.appendChild(tr);
});
}
["search","status","severity"].forEach(id=>document.getElementById(id).addEventListener(id==="search"?"input":"change",render));
render();
</script>
</body>
</html>"""

    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(doc.replace("__DATA__",data),encoding="utf-8")
    return m

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cases",default="data/cases.csv")
    p.add_argument("--reviews",default="reviews/review_log.csv")
    p.add_argument("--output",default="dashboard/dashboard.html")
    a=p.parse_args()

    print("="*70)
    print("NETSAGE AI - DASHBOARD BUILDER")
    print("="*70)

    cases=load_cases(a.cases)
    reviews=load_reviews(a.reviews)
    m=build(cases,reviews,a.output)

    print(f"Cases loaded     : {len(cases)}")
    print(f"Review rows      : {len(reviews)}")
    print(f"AI findings      : {m['ai_findings']}/80")
    print(f"Reviewed         : {m['reviewed']}")
    print(f"Pending          : {m['pending']}")
    print(f"Accepted         : {m['accepted']}")
    print(f"Edited           : {m['edited']}")
    print(f"Rejected         : {m['rejected']}")
    print(f"Review completion: {m['completion']}%")
    print(f"Output           : {Path(a.output).resolve()}")
    print("\nPASS: dashboard generated from actual review_log.csv.")

if __name__=="__main__":
    main()
