import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "cases.csv"
DIAGNOSE = ROOT / "ai" / "diagnose.py"
CHECKER = ROOT / "checker" / "rule_checker.py"
REVIEWS = ROOT / "reviews" / "review_log.csv"

REVIEW_FIELDS = [
    "case_id",
    "category",
    "severity",
    "ai_root_cause",
    "ai_confidence",
    "human_status",
    "agreement",
    "reviewer_note",
]


def load_cases():
    with open(DATA, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_reviews():
    if not REVIEWS.exists():
        return {}

    with open(REVIEWS, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    return {
        row.get("case_id", "").strip(): row
        for row in rows
        if row.get("case_id")
    }


def save_review(case, diagnosis, status, correction, notes):
    """
    Update ONE case while preserving all other review rows and
    the review-log schema used by build_review_log.py.
    """

    rows = []

    if REVIEWS.exists():
        with open(REVIEWS, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    case_id = case["case_id"]

    ai_root_cause = diagnosis.get("root_cause", "")

    # For an Edited review, keep the original AI diagnosis in
    # ai_root_cause and put the human correction in reviewer_note.
    if status == "Edited":
        reviewer_note = (
            f"Corrected diagnosis: {correction}\n"
            f"Why edited: {notes}"
        )
        agreement = "No"
    elif status == "Rejected":
        reviewer_note = notes
        agreement = "No"
    else:
        reviewer_note = notes or "Accepted by reviewer."
        agreement = "Yes"

    record = {
        "case_id": case_id,
        "category": case.get("category", ""),
        "severity": case.get("severity", ""),
        "ai_root_cause": ai_root_cause,
        "ai_confidence": diagnosis.get("confidence", ""),
        "human_status": status,
        "agreement": agreement,
        "reviewer_note": reviewer_note,
    }

    # Replace only this case.
    found = False

    for i, row in enumerate(rows):
        if row.get("case_id", "").strip() == case_id:
            rows[i] = record
            found = True
            break

    if not found:
        rows.append(record)

    # Keep exactly the expected columns.
    cleaned = []

    for row in rows:
        cleaned.append({
            field: row.get(field, "")
            for field in REVIEW_FIELDS
        })

    REVIEWS.parent.mkdir(parents=True, exist_ok=True)

    with open(
        REVIEWS,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=REVIEW_FIELDS
        )
        writer.writeheader()
        writer.writerows(cleaned)


def run_rule_checker(case_id):
    result = subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            str(DATA),
            "--case",
            case_id,
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )

    return result.stdout or result.stderr


def run_diagnosis(case_id):
    env = os.environ.copy()

    result = subprocess.run(
        [
            sys.executable,
            str(DIAGNOSE),
            str(DATA),
            "--case",
            case_id,
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )

    if result.returncode != 0:
        return None, result.stderr or result.stdout

    try:
        return json.loads(result.stdout), None

    except json.JSONDecodeError:
        return (
            None,
            "The model response was not valid JSON:\n"
            + result.stdout
        )


# ============================================================
# STREAMLIT UI
# ============================================================

st.set_page_config(
    page_title="NetSage AI",
    page_icon="🌐",
    layout="wide",
)

st.title("🌐 NetSage AI")
st.caption(
    "AI-assisted Cisco troubleshooting with mandatory human review"
)

if not DATA.exists():
    st.error(f"Missing dataset: {DATA}")
    st.stop()

if not CHECKER.exists():
    st.error(f"Missing rule checker: {CHECKER}")
    st.stop()

if not DIAGNOSE.exists():
    st.warning(
        f"AI diagnosis script not found: {DIAGNOSE}"
    )


cases = load_cases()
reviews = load_reviews()

# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("Case Selection")

case_id = st.sidebar.selectbox(
    "Choose troubleshooting case",
    [c["case_id"] for c in cases],
)

case = next(
    c for c in cases
    if c["case_id"] == case_id
)

# Existing review for selected case.
existing_review = reviews.get(case_id, {})


# ============================================================
# CASE INFORMATION
# ============================================================

col1, col2 = st.columns(2)

with col1:

    st.subheader("Problem")

    st.write(
        case.get("symptom", "")
    )

    st.subheader("Topology")

    st.info(
        case.get("topology_note", "")
    )


with col2:

    st.subheader("Show-command evidence")

    st.code(
        case.get("show_output", ""),
        language="text",
    )


st.divider()


# ============================================================
# DETERMINISTIC CHECKER
# ============================================================

if st.button(
    "🔎 Run Deterministic Rule Checker",
    use_container_width=True,
):

    with st.spinner("Running deterministic rules..."):

        st.session_state["rules"] = (
            run_rule_checker(case_id)
        )


if "rules" in st.session_state:

    st.subheader("Deterministic Findings")

    st.code(
        st.session_state["rules"],
        language="text",
    )


st.divider()


# ============================================================
# AI DIAGNOSIS
# ============================================================

if DIAGNOSE.exists():

    if st.button(
        "🤖 Run NetSage AI Diagnosis",
        type="primary",
        use_container_width=True,
    ):

        with st.spinner(
            "Running NetSage AI diagnosis..."
        ):

            diagnosis, error = run_diagnosis(
                case_id
            )

        if error:

            st.error(error)

        else:

            st.session_state[
                f"diagnosis_{case_id}"
            ] = diagnosis


diagnosis = st.session_state.get(
    f"diagnosis_{case_id}"
)


# ============================================================
# DISPLAY DIAGNOSIS
# ============================================================

if diagnosis:

    st.subheader("AI Diagnosis")

    a, b, c = st.columns(3)

    a.metric(
        "OSI Layer",
        diagnosis.get(
            "osi_layer",
            "Unknown"
        ),
    )

    b.metric(
        "Confidence",
        diagnosis.get(
            "confidence",
            "Unknown"
        ),
    )

    c.metric(
        "Severity",
        case.get(
            "severity",
            "Unknown"
        ),
    )

    st.markdown("**Root Cause**")

    st.write(
        diagnosis.get(
            "root_cause",
            ""
        )
    )

    st.markdown("**Evidence**")

    st.info(
        diagnosis.get(
            "evidence",
            ""
        )
    )

    st.markdown("**Next Command**")

    st.code(
        diagnosis.get(
            "next_command",
            ""
        ),
        language="text",
    )

    st.markdown("**Fix Steps**")

    for i, step in enumerate(
        diagnosis.get("fix_steps", []),
        1,
    ):

        st.write(
            f"{i}. {step}"
        )

    st.markdown("**Alternative Causes**")

    for cause in diagnosis.get(
        "alternate_causes",
        [],
    ):

        st.write(
            f"- {cause}"
        )


    # ========================================================
    # HUMAN REVIEW
    # ========================================================

    st.divider()

    st.subheader("👤 Human Review")

    current_status = existing_review.get(
        "human_status",
        "Pending"
    )

    status_options = [
        "Accepted",
        "Edited",
        "Rejected",
    ]

    default_index = (
        status_options.index(current_status)
        if current_status in status_options
        else 0
    )

    status = st.radio(
        "Reviewer decision",
        status_options,
        index=default_index,
        horizontal=True,
    )

    correction = ""
    notes = ""

    if status == "Edited":

        correction = st.text_area(
            "Corrected diagnosis",
            value="",
        )

        notes = st.text_area(
            "Why was the AI diagnosis edited?",
            value="",
        )

    elif status == "Rejected":

        notes = st.text_area(
            "Why was the AI diagnosis rejected?",
            value="",
        )

    else:

        notes = st.text_area(
            "Reviewer note (optional)",
            value="",
        )

    if st.button(
        "💾 Save Human Review",
        use_container_width=True,
    ):

        if status == "Edited" and not correction.strip():

            st.error(
                "Enter the corrected diagnosis before saving."
            )

        elif status == "Rejected" and not notes.strip():

            st.error(
                "Enter the rejection reason before saving."
            )

        else:

            save_review(
                case,
                diagnosis,
                status,
                correction,
                notes,
            )

            st.success(
                f"{case_id} saved as {status}."
            )

            st.rerun()


# ============================================================
# REVIEW STATUS
# ============================================================

st.divider()

st.subheader("📊 Review Status")

updated_reviews = load_reviews()

status_counts = {
    status: sum(
        1
        for row in updated_reviews.values()
        if row.get("human_status", "") == status
    )
    for status in [
        "Pending",
        "Accepted",
        "Edited",
        "Rejected",
    ]
}

x1, x2, x3, x4 = st.columns(4)

x1.metric("Pending", status_counts["Pending"])
x2.metric("Accepted", status_counts["Accepted"])
x3.metric("Edited", status_counts["Edited"])
x4.metric("Rejected", status_counts["Rejected"])

st.caption(
    f"Review log: {len(updated_reviews)}/80 cases currently stored."
)
