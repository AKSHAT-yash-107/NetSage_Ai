"""
NetSage AI diagnosis runner — Gemini version.

Usage:
    python diagnose.py ..\\data\\cases.csv --case C001

Environment:
    GEMINI_API_KEY   Required for live Gemini diagnosis.
    GEMINI_MODEL     Optional; defaults to gemini-2.5-flash.
"""

import argparse
import csv
import json
import os
from pathlib import Path


REQUIRED_FIELDS = [
    "root_cause",
    "evidence",
    "osi_layer",
    "confidence",
    "next_command",
    "fix_steps",
    "alternate_causes",
]


def load_prompt(path):
    prompt_path = Path(path)

    if not prompt_path.is_absolute():
        local_prompt = Path(__file__).resolve().parent / prompt_path
        if local_prompt.exists():
            prompt_path = local_prompt

    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {prompt_path.resolve()}"
        )

    text = prompt_path.read_text(encoding="utf-8")

    marker = "## System Prompt"
    start = text.find(marker)

    if start == -1:
        return text.strip()

    block_start = text.find("```", start)

    if block_start == -1:
        return text[start + len(marker):].strip()

    block_end = text.find("```", block_start + 3)

    if block_end == -1:
        raise ValueError(
            "Unclosed prompt code block in diagnose_prompt.md"
        )

    return text[block_start + 3:block_end].strip()


def load_case(csv_path, case_id):
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames or "case_id" not in reader.fieldnames:
            raise ValueError(
                "Cases CSV must contain a case_id column."
            )

        for row in reader:
            if row["case_id"].strip().upper() == case_id.strip().upper():
                return row

    raise ValueError(
        f"Case {case_id} not found in {csv_path}"
    )


def build_user_message(case):
    return f"""CASE_ID: {case.get("case_id", "")}

CATEGORY:
{case.get("category", "")}

SEVERITY:
{case.get("severity", "")}

EXPECTED FAULT:
{case.get("expected_fault", "")}

SYMPTOM:
{case.get("symptom", "")}

TOPOLOGY NOTE:
{case.get("topology_note", "")}

SHOW-COMMAND OUTPUT:
{case.get("show_output", "")}
"""


def call_gemini(system_prompt, user_message):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. "
            "Set it before running live diagnosis."
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError(
            "google-genai is not installed. Run:\n"
            "C:\\Python313\\python.exe -m pip install -U google-genai"
        ) from exc

    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.6-flash"
    )

    # IMPORTANT:
    # Gemini's response_schema is a protobuf-backed JSON schema.
    # Do NOT send JSON Schema's "additionalProperties" here.
    schema = {
        "type": "OBJECT",
        "properties": {
            "root_cause": {
                "type": "STRING"
            },
            "evidence": {
                "type": "STRING"
            },
            "osi_layer": {
                "type": "STRING"
            },
            "confidence": {
                "type": "STRING"
            },
            "next_command": {
                "type": "STRING"
            },
            "fix_steps": {
                "type": "ARRAY",
                "items": {
                    "type": "STRING"
                }
            },
            "alternate_causes": {
                "type": "ARRAY",
                "items": {
                    "type": "STRING"
                }
            }
        },
        "required": REQUIRED_FIELDS
    }

    client = genai.Client(api_key=api_key)

    full_prompt = f"""SYSTEM INSTRUCTIONS:

{system_prompt}

USER CASE:

{user_message}

Return ONLY valid JSON matching the requested diagnosis fields.
Use only evidence supported by the case.
Do not invent command output, configuration, or test results.
"""

    try:
        response = client.models.generate_content(
            model=model,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
    except Exception as exc:
        raise RuntimeError(
            f"Gemini API request failed: {exc}"
        ) from exc

    raw = getattr(response, "text", None)

    if not raw:
        raise RuntimeError(
            "Gemini returned no text response."
        )

    try:
        diagnosis = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Gemini returned invalid JSON:\n" + raw
        ) from exc

    missing = [
        field
        for field in REQUIRED_FIELDS
        if field not in diagnosis
    ]

    if missing:
        raise RuntimeError(
            "Diagnosis JSON is missing fields: "
            + ", ".join(missing)
        )

    return diagnosis


def main():
    parser = argparse.ArgumentParser(
        description="Run NetSage AI Gemini diagnosis"
    )

    parser.add_argument("csv_path")

    parser.add_argument(
        "--case",
        required=True
    )

    parser.add_argument(
        "--prompt",
        default="diagnose_prompt.md"
    )

    parser.add_argument("--output")

    args = parser.parse_args()

    case = load_case(
        args.csv_path,
        args.case
    )

    prompt = load_prompt(
        args.prompt
    )

    diagnosis = call_gemini(
        prompt,
        build_user_message(case)
    )

    diagnosis["case_id"] = case["case_id"]
    diagnosis["model"] = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.6-flash"
    )

    print(
        json.dumps(
            diagnosis,
            indent=2,
            ensure_ascii=False
        )
    )

    if args.output:
        Path(args.output).write_text(
            json.dumps(
                diagnosis,
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

        print(
            f"\nSaved diagnosis to {args.output}"
        )


if __name__ == "__main__":
    main()
