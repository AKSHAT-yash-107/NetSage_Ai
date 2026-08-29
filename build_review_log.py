"""
NetSage AI — Review Log Builder

Pipeline:

    cases.csv / cases.xlsx
            |
            v
    deterministic rule_checker.py
            |
            v
    AI root cause + confidence
            |
            v
    review_log.csv
            |
            v
    human review

IMPORTANT:
- expected_fault is NEVER passed to rule_checker.py.
- Existing human decisions are preserved.
- New cases are Pending.
- Exactly C001-C080 are written.
- Supports both CSV and XLSX case files.
"""

import argparse
import importlib.util
from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

EXPECTED_IDS = [
    f"C{i:03d}"
    for i in range(1, 81)
]

COLUMNS = [
    "case_id",
    "category",
    "severity",
    "ai_root_cause",
    "ai_confidence",
    "human_status",
    "agreement",
    "reviewer_note",
]

VALID_STATUSES = {
    "Pending",
    "Accepted",
    "Edited",
    "Rejected",
}

# Deterministic evidence-based findings.
# This is NOT pretending that an LLM probability was calculated.
DETERMINISTIC_CONFIDENCE = 0.99


# ============================================================
# LOAD RULE CHECKER
# ============================================================

def load_rule_checker(path):
    """
    Dynamically load checker/rule_checker.py.
    """

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"rule_checker.py not found:\n"
            f"{path.resolve()}"
        )

    spec = importlib.util.spec_from_file_location(
        "netsage_rule_checker",
        path
    )

    if spec is None or spec.loader is None:
        raise ImportError(
            f"Could not load rule_checker.py:\n"
            f"{path.resolve()}"
        )

    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    if not hasattr(module, "run_case"):
        raise AttributeError(
            "rule_checker.py must contain:\n\n"
            "    run_case(case)"
        )

    return module


# ============================================================
# LOAD CASES
# ============================================================

def load_cases(path):
    """
    Load cases from CSV or XLSX.
    """

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Cases file not found:\n"
            f"{path.resolve()}"
        )

    extension = path.suffix.lower()

    # -------------------------------
    # CSV
    # -------------------------------

    if extension == ".csv":

        cases = pd.read_csv(path)

    # -------------------------------
    # Excel
    # -------------------------------

    elif extension in {".xlsx", ".xls"}:

        cases = pd.read_excel(
            path,
            sheet_name="cases"
        )

    else:

        raise ValueError(
            f"Unsupported cases file: {path}\n"
            f"Use .csv, .xlsx, or .xls"
        )

    # -------------------------------
    # Required column
    # -------------------------------

    if "case_id" not in cases.columns:

        raise ValueError(
            "Cases file is missing the required "
            "'case_id' column."
        )

    # -------------------------------
    # Normalize IDs
    # -------------------------------

    cases["case_id"] = (
        cases["case_id"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # -------------------------------
    # Exactly 80 rows
    # -------------------------------

    if len(cases) != 80:

        raise ValueError(
            f"Cases file must contain exactly 80 rows.\n"
            f"Found: {len(cases)}"
        )

    # -------------------------------
    # Duplicate IDs
    # -------------------------------

    duplicates = sorted(
        set(
            cases.loc[
                cases["case_id"].duplicated(keep=False),
                "case_id"
            ]
        )
    )

    if duplicates:

        raise ValueError(
            "Duplicate case IDs found:\n"
            f"{duplicates}"
        )

    # -------------------------------
    # Validate C001-C080
    # -------------------------------

    actual_ids = set(cases["case_id"])

    expected_ids = set(EXPECTED_IDS)

    missing_ids = sorted(
        expected_ids - actual_ids
    )

    extra_ids = sorted(
        actual_ids - expected_ids
    )

    if missing_ids or extra_ids:

        raise ValueError(
            "Cases file must contain exactly "
            "C001-C080.\n\n"
            f"Missing IDs: {missing_ids}\n"
            f"Extra IDs:   {extra_ids}"
        )

    # -------------------------------
    # Sort C001 -> C080
    # -------------------------------

    cases["_case_number"] = (
        cases["case_id"]
        .str.extract(r"C(\d+)")[0]
        .astype(int)
    )

    cases = (
        cases
        .sort_values("_case_number")
        .drop(columns="_case_number")
        .reset_index(drop=True)
    )

    return cases


# ============================================================
# LOAD EXISTING REVIEW LOG
# ============================================================

def load_reviews(path):
    """
    Load existing human-review decisions.

    If the file doesn't exist, return an empty review table.
    """

    path = Path(path)

    if not path.exists():

        return pd.DataFrame(
            columns=COLUMNS
        )

    reviews = pd.read_csv(path)

    # -------------------------------
    # Required ID
    # -------------------------------

    if "case_id" not in reviews.columns:

        raise ValueError(
            "Existing review_log.csv must contain "
            "'case_id'."
        )

    reviews["case_id"] = (
        reviews["case_id"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # -------------------------------
    # Invalid IDs
    # -------------------------------

    invalid_ids = sorted(
        set(reviews["case_id"])
        - set(EXPECTED_IDS)
    )

    if invalid_ids:

        raise ValueError(
            "Existing review log contains invalid "
            "case IDs:\n"
            f"{invalid_ids}"
        )

    # -------------------------------
    # Duplicate reviews
    # -------------------------------

    duplicates = sorted(
        set(
            reviews.loc[
                reviews["case_id"].duplicated(keep=False),
                "case_id"
            ]
        )
    )

    if duplicates:

        raise ValueError(
            "Existing review log contains duplicate "
            "rows for:\n"
            f"{duplicates}\n\n"
            "Fix the duplicate reviews instead of "
            "silently deleting one."
        )

    # -------------------------------
    # Add missing columns
    # -------------------------------

    for column in COLUMNS:

        if column not in reviews.columns:

            reviews[column] = ""

    return reviews[COLUMNS]


# ============================================================
# STATUS VALIDATION
# ============================================================

def clean_status(value):
    """
    Normalize and validate human status.
    """

    if pd.isna(value):

        return "Pending"

    value = str(value).strip()

    if value == "":

        return "Pending"

    if value not in VALID_STATUSES:

        raise ValueError(
            f"Invalid human_status: {value!r}\n\n"
            f"Allowed values:\n"
            f"{sorted(VALID_STATUSES)}"
        )

    return value


# ============================================================
# RUN DETERMINISTIC ENGINE
# ============================================================

def run_deterministic_ai(case, checker):
    """
    Send ONLY evidence to the deterministic engine.

    IMPORTANT:
    expected_fault is intentionally excluded.

    Since cases were loaded with case_id as the DataFrame index,
    case.name contains the case ID.
    """

    evidence_case = {

        # FIX:
        # case["case_id"] would fail because case_id
        # became the DataFrame index.
        "case_id": str(case.name),

        "symptom": str(
            case.get("symptom", "")
        ),

        "topology_note": str(
            case.get("topology_note", "")
        ),

        "show_output": str(
            case.get("show_output", "")
        ),
    }

    # --------------------------------------------------------
    # Run checker
    # --------------------------------------------------------

    result = checker.run_case(
        evidence_case
    )

    findings = getattr(
        result,
        "findings",
        []
    )

    # --------------------------------------------------------
    # No finding
    # --------------------------------------------------------

    if not findings:

        return "", ""

    # --------------------------------------------------------
    # Convert findings into root cause text
    # --------------------------------------------------------

    root_causes = []

    for finding in findings:

        check = getattr(
            finding,
            "check",
            ""
        )

        message = getattr(
            finding,
            "message",
            ""
        )

        if check and message:

            root_causes.append(
                f"{check}: {message}"
            )

        elif message:

            root_causes.append(
                message
            )

        elif check:

            root_causes.append(
                check
            )

    root_cause = " | ".join(
        root_causes
    )

    return (
        root_cause,
        DETERMINISTIC_CONFIDENCE
    )


# ============================================================
# BUILD FINAL REVIEW LOG
# ============================================================

def build_review_log(
    cases,
    reviews,
    checker
):
    """
    Build exactly one review row per case.
    """

    # case_id becomes the index here.
    case_map = cases.set_index(
        "case_id"
    )

    # Existing review rows.
    if reviews.empty:

        review_map = {}

    else:

        review_map = (
            reviews
            .set_index("case_id")
            .to_dict("index")
        )

    rows = []

    # ========================================================
    # C001 -> C080
    # ========================================================

    for case_id in EXPECTED_IDS:

        case = case_map.loc[
            case_id
        ]

        # ----------------------------------------------------
        # AI / deterministic finding
        # ----------------------------------------------------

        ai_root_cause, ai_confidence = (
            run_deterministic_ai(
                case,
                checker
            )
        )

        # ----------------------------------------------------
        # Existing human review
        # ----------------------------------------------------

        if case_id in review_map:

            old = review_map[
                case_id
            ]

            human_status = clean_status(
                old.get(
                    "human_status",
                    ""
                )
            )

            reviewer_note = old.get(
                "reviewer_note",
                ""
            )

            if pd.isna(
                reviewer_note
            ):

                reviewer_note = ""

            reviewer_note = str(
                reviewer_note
            ).strip()

            if (
                human_status == "Pending"
                and not reviewer_note
            ):

                reviewer_note = (
                    "Not yet reviewed."
                )

            row = {

                "case_id": case_id,

                "category": case.get(
                    "category",
                    ""
                ),

                "severity": case.get(
                    "severity",
                    ""
                ),

                "ai_root_cause":
                    ai_root_cause,

                "ai_confidence":
                    ai_confidence,

                # Preserve human decision.
                "human_status":
                    human_status,

                "agreement":
                    old.get(
                        "agreement",
                        ""
                    ),

                "reviewer_note":
                    reviewer_note,
            }

        # ----------------------------------------------------
        # New review
        # ----------------------------------------------------

        else:

            row = {

                "case_id": case_id,

                "category": case.get(
                    "category",
                    ""
                ),

                "severity": case.get(
                    "severity",
                    ""
                ),

                "ai_root_cause":
                    ai_root_cause,

                "ai_confidence":
                    ai_confidence,

                "human_status":
                    "Pending",

                "agreement":
                    "",

                "reviewer_note":
                    "Not yet reviewed.",
            }

        rows.append(row)

    return pd.DataFrame(
        rows,
        columns=COLUMNS
    )


# ============================================================
# VALIDATE FINAL LOG
# ============================================================

def validate_review_log(final):

    # --------------------------------------------------------
    # Row count
    # --------------------------------------------------------

    if len(final) != 80:

        raise ValueError(
            f"Review log must contain exactly "
            f"80 rows.\n"
            f"Found: {len(final)}"
        )

    # --------------------------------------------------------
    # Unique IDs
    # --------------------------------------------------------

    if final["case_id"].nunique() != 80:

        raise ValueError(
            "Review log contains duplicate "
            "case IDs."
        )

    # --------------------------------------------------------
    # Exact ordering
    # --------------------------------------------------------

    if (
        final["case_id"].tolist()
        != EXPECTED_IDS
    ):

        raise ValueError(
            "Review log IDs are not exactly "
            "C001-C080 in order."
        )

    # --------------------------------------------------------
    # Status validation
    # --------------------------------------------------------

    invalid_statuses = (
        set(final["human_status"])
        - VALID_STATUSES
    )

    if invalid_statuses:

        raise ValueError(
            f"Invalid human statuses:\n"
            f"{sorted(invalid_statuses)}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Build and validate the "
            "NetSage AI review log."
        )
    )

    parser.add_argument(
        "--cases",
        default="data/cases.csv",
        help=(
            "Path to cases.csv or cases.xlsx"
        )
    )

    parser.add_argument(
        "--reviews",
        default="reviews/review_log.csv",
        help=(
            "Existing review log."
        )
    )

    parser.add_argument(
        "--output",
        default="reviews/review_log.csv",
        help=(
            "Output review log."
        )
    )

    parser.add_argument(
        "--checker",
        default="checker/rule_checker.py",
        help=(
            "Path to rule_checker.py"
        )
    )

    args = parser.parse_args()

    print("=" * 70)
    print(
        "NETSAGE AI - REVIEW LOG BUILDER"
    )
    print("=" * 70)

    # ========================================================
    # LOAD CASES
    # ========================================================

    print(
        f"\nLoading cases: {args.cases}"
    )

    cases = load_cases(
        args.cases
    )

    print(
        f"Cases loaded : {len(cases)}"
    )

    # ========================================================
    # LOAD RULE CHECKER
    # ========================================================

    print(
        f"Loading checker: {args.checker}"
    )

    checker = load_rule_checker(
        args.checker
    )

    print(
        "Rule checker loaded successfully."
    )

    # ========================================================
    # LOAD EXISTING REVIEWS
    # ========================================================

    print(
        f"Loading reviews: {args.reviews}"
    )

    reviews = load_reviews(
        args.reviews
    )

    if reviews.empty:

        print(
            "No existing review log found."
        )

        print(
            "Creating 80 Pending cases."
        )

    else:

        print(
            f"Existing review rows: "
            f"{len(reviews)}"
        )

    # ========================================================
    # BUILD
    # ========================================================

    final = build_review_log(
        cases,
        reviews,
        checker
    )

    # ========================================================
    # VALIDATE
    # ========================================================

    validate_review_log(
        final
    )

    # ========================================================
    # SAVE
    # ========================================================

    output = Path(
        args.output
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    final.to_csv(
        output,
        index=False,
        encoding="utf-8"
    )

    # ========================================================
    # STATISTICS
    # ========================================================

    counts = (
        final["human_status"]
        .value_counts()
    )

    ai_findings = (
        final["ai_root_cause"]
        .fillna("")
        .astype(str)
        .str.strip()
        .ne("")
        .sum()
    )

    # ========================================================
    # REPORT
    # ========================================================

    print()
    print("=" * 70)
    print(
        "VALIDATION"
    )
    print("=" * 70)

    print(
        f"Cases checked : "
        f"{len(cases)}"
    )

    print(
        f"Review rows   : "
        f"{len(final)}"
    )

    print(
        f"Unique IDs    : "
        f"{final['case_id'].nunique()}"
    )

    print(
        f"ID range      : "
        f"{final['case_id'].iloc[0]} "
        f"- "
        f"{final['case_id'].iloc[-1]}"
    )

    print(
        f"AI findings   : "
        f"{ai_findings}/80"
    )

    print()
    print(
        "Status:"
    )

    for status in [
        "Pending",
        "Accepted",
        "Edited",
        "Rejected",
    ]:

        print(
            f"{status:<10}: "
            f"{int(counts.get(status, 0))}"
        )

    print()
    print(
        "PASS: review log contains "
        "exactly C001-C080."
    )

    print(
        f"Output: "
        f"{output.resolve()}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()