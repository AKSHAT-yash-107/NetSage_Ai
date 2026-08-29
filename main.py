"""
NetSage AI - single Streamlit entry point.

Run:
    streamlit run main.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
DATA_XLSX = ROOT / "data" / "cases.xlsx"
DATA_CSV = ROOT / "data" / "_cases_runtime.csv"
DIAGNOSE = ROOT / "ai" / "diagnose.py"
PROMPT = ROOT / "ai" / "diagnose_prompt.md"
CHECKER = ROOT / "checker" / "rule_checker.py"
REVIEWS = ROOT / "reviews" / "review_log.csv"


REVIEW_COLUMNS = [
    "case_id",
    "category",
    "severity",
    "ai_root_cause",
    "ai_confidence",
    "human_status",
    "agreement",
    "reviewer_note",
]


@st.cache_data
def load_cases():
    if not DATA_XLSX.exists():
        st.error(f"Missing dataset: {DATA_XLSX}")
        st.stop()

    df = pd.read_excel(DATA_XLSX, sheet_name="cases")
    required = [
        "case_id", "category", "symptom", "topology_note",
        "show_output", "expected_fault", "osi_layer",
        "concept_tag", "severity",
    ]

    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error("Dataset missing: " + ", ".join(missing))
        st.stop()

    df = df[required].copy()
    df["case_id"] = df["case_id"].astype(str).str.strip()

    if len(df) != 80 or df["case_id"].nunique() != 80:
        st.error("Dataset must contain exactly 80 unique cases.")
        st.stop()

    expected = {f"C{i:03d}" for i in range(1, 81)}
    if set(df["case_id"]) != expected:
        st.error("Case IDs must be exactly C001-C080.")
        st.stop()

    DATA_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA_CSV, index=False, encoding="utf-8")
    return df


def load_reviews():
    if not REVIEWS.exists():
        return pd.DataFrame(columns=REVIEW_COLUMNS)

    try:
        df = pd.read_csv(REVIEWS)
    except Exception as exc:
        st.error(f"Could not read review log: {exc}")
        return pd.DataFrame(columns=REVIEW_COLUMNS)

    for col in REVIEW_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    return df[REVIEW_COLUMNS]


def save_review(case, diagnosis, status, correction, notes):
    reviews = load_reviews()

    if status == "Accepted":
        agreement = "match"
        reviewer_note = notes
    elif status == "Edited":
        agreement = "partial"
        reviewer_note = correction or notes
    else:
        agreement = "mismatch"
        reviewer_note = notes

    record = {
        "case_id": case["case_id"],
        "category": case["category"],
        "severity": case["severity"],
        "ai_root_cause": diagnosis.get("root_cause", ""),
        "ai_confidence": diagnosis.get("confidence", ""),
        "human_status": status,
        "agreement": agreement,
        "reviewer_note": reviewer_note,
    }

    reviews = reviews[reviews["case_id"].astype(str) != case["case_id"]]
    reviews = pd.concat([reviews, pd.DataFrame([record])], ignore_index=True)

    reviews["_sort"] = reviews["case_id"].astype(str).str.extract(
        r"(\d+)"
    ).astype(int)
    reviews = reviews.sort_values("_sort").drop(columns="_sort")

    REVIEWS.parent.mkdir(parents=True, exist_ok=True)
    reviews.to_csv(REVIEWS, index=False, encoding="utf-8")


def run_checker(case_id):
    result = subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            str(DATA_CSV),
            "--case",
            case_id,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout or result.stderr


def run_diagnosis(case_id):
    if not os.getenv("OPENAI_API_KEY"):
        return None, "OPENAI_API_KEY is not set."

    result = subprocess.run(
        [
            sys.executable,
            str(DIAGNOSE),
            str(DATA_CSV),
            "--case",
            case_id,
            "--prompt",
            str(PROMPT),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    if result.returncode != 0:
        return None, result.stderr or result.stdout

    raw = result.stdout.strip()

    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end + 1]), None
            except json.JSONDecodeError:
                pass

    return None, "AI returned invalid JSON:\n" + raw


st.set_page_config(
    page_title="NetSage AI",
    page_icon="🌐",
    layout="wide",
)

st.title("🌐 NetSage AI")
st.caption("AI-assisted Cisco troubleshooting • Human review required")

cases = load_cases()
reviews = load_reviews()

accepted = int((reviews["human_status"] == "Accepted").sum())
edited = int((reviews["human_status"] == "Edited").sum())
rejected = int((reviews["human_status"] == "Rejected").sum())
pending = len(cases) - len(
    reviews[reviews["human_status"].isin(["Accepted", "Edited", "Rejected"])]
)
reviewed = accepted + edited + rejected
agreement = accepted / reviewed * 100 if reviewed else 0

m = st.columns(5)
m[0].metric("Cases", len(cases))
m[1].metric("Accepted", accepted)
m[2].metric("Edited", edited)
m[3].metric("Rejected", rejected)
m[4].metric("Pending", pending)

st.sidebar.header("Case Selection")

category = st.sidebar.selectbox(
    "Category",
    ["All"] + sorted(cases["category"].unique().tolist()),
)

filtered = cases if category == "All" else cases[cases["category"] == category]

case_id = st.sidebar.selectbox("Case", filtered["case_id"].tolist())
case = cases[cases["case_id"] == case_id].iloc[0].to_dict()

st.sidebar.metric("Reviewed", reviewed)
st.sidebar.metric("Agreement", f"{agreement:.1f}%")

left, right = st.columns(2)

with left:
    st.subheader(f"Case {case_id}")
    st.write(f"**Category:** {case['category']}")
    st.write(f"**Severity:** {case['severity']}")
    st.write(f"**Concept:** {case['concept_tag']}")
    st.markdown("**Symptom**")
    st.write(case["symptom"])
    st.markdown("**Topology**")
    st.info(case["topology_note"])

with right:
    st.subheader("Show-Command Evidence")
    st.code(case["show_output"], language="text")

st.divider()

st.subheader("1. Deterministic Rule Checker")

if st.button("Run Rule Checker", use_container_width=True):
    st.session_state["rule_output"] = run_checker(case_id)

if "rule_output" in st.session_state:
    st.code(st.session_state["rule_output"], language="text")

st.divider()

st.subheader("2. AI Diagnosis")

if st.button("Run NetSage AI", type="primary", use_container_width=True):
    diagnosis, error = run_diagnosis(case_id)
    if error:
        st.error(error)
    else:
        st.session_state["diagnosis"] = diagnosis
        st.session_state["diagnosis_case"] = case_id

if (
    "diagnosis" in st.session_state
    and st.session_state.get("diagnosis_case") == case_id
):
    diagnosis = st.session_state["diagnosis"]

    a, b, c = st.columns(3)
    a.metric("OSI Layer", diagnosis.get("osi_layer", "Unknown"))
    b.metric("Confidence", diagnosis.get("confidence", "Unknown"))
    c.metric("Severity", case["severity"])

    st.markdown("### Root Cause")
    st.write(diagnosis.get("root_cause", ""))

    st.markdown("### Evidence")
    st.info(diagnosis.get("evidence", ""))

    st.markdown("### Next Command")
    st.code(diagnosis.get("next_command", ""), language="text")

    st.markdown("### Fix Steps")
    for i, step in enumerate(diagnosis.get("fix_steps", []), 1):
        st.write(f"{i}. {step}")

    st.markdown("### Alternate Causes")
    for cause in diagnosis.get("alternate_causes", []):
        st.write(f"- {cause}")

    st.divider()
    st.subheader("3. Human Review")
    st.warning("Do not apply a fix based only on the AI suggestion.")

    status = st.radio(
        "Decision",
        ["Accepted", "Edited", "Rejected"],
        horizontal=True,
    )

    correction = ""
    notes = ""

    if status == "Edited":
        correction = st.text_area("Corrected diagnosis")
        notes = st.text_area("Why was it edited?")
    elif status == "Rejected":
        notes = st.text_area("Why was it rejected?")
    else:
        notes = st.text_area("Reviewer note")

    if st.button("Save Human Review", use_container_width=True):
        save_review(case, diagnosis, status, correction, notes)
        st.success(f"{case_id} saved as {status}.")
        st.rerun()

st.divider()

st.subheader("Review Log")

current = load_reviews()
if current.empty:
    st.info("No reviews yet.")
else:
    st.dataframe(current, use_container_width=True, hide_index=True)
