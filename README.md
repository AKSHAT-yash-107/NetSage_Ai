# NetSage AI — Project Package

AI-assisted troubleshooter for Packet Tracer lab problems, with mandatory
human review before any diagnosis is accepted as a fix.

## Files in this package

| File | Deliverable | Description |
|---|---|---|
| `cases.csv` | Case dataset | 30 troubleshooting cases across VLAN, Gateway, DHCP, DNS, Routing, ACL, NAT, Wireless |
| `diagnose_prompt.md` | AI prompt library | Structured JSON-output diagnosis prompt + 3 worked examples |
| `review_assist_prompt.md` | AI prompt library (helper) | QA pass that flags AI/expected mismatches for the reviewer |
| `rule_checker.py` | Python checker | Deterministic checks (dup IP, interface down, missing route/VLAN/DHCP relay, ACL gaps, undersized DHCP pool) |
| `review_log.csv` | Human review log | AI diagnosis, confidence, and human Accepted/Edited/Rejected decision per case |
| `responsible_ai_log.md` | Responsible AI log | Detailed write-up of the 5 corrected AI diagnoses |
| `netsage_dashboard.xlsx` | Dashboard | Cases-by-category, cases-by-severity, and AI/human agreement rate, with charts |
| `build_cases.py`, `build_review_log.py`, `build_dashboard.py` | — | Generator scripts (re-run to regenerate any file above) |

## Case coverage

8 categories, 30 cases: VLAN (4), Gateway (4), DHCP (4), DNS (4), Routing (5),
ACL (4), NAT (3), Wireless (2). Every row includes symptom, topology note,
show-command evidence, expected fault, OSI layer, concept tag, and severity.

## How the pieces fit together (workflow)

1. **Pick a case** from `cases.csv` (symptom + topology_note + show_output).
2. **Run the AI diagnosis**: feed those three fields, plus the case_id, into
   the system+user prompt in `diagnose_prompt.md`. The model returns the
   required JSON object (`root_cause`, `osi_layer`, `confidence`, `evidence`,
   `next_command`, `fix_steps`, `alternate_causes`).
3. **Run the deterministic checker** independently:
   `python3 rule_checker.py cases.csv --case C0XX` — this never depends on
   the AI and catches a subset of mistakes on its own, as a sanity cross-check.
4. **Human review**: the reviewer reads the AI's JSON, the rule checker's
   findings, and the actual evidence, then marks the case Accepted / Edited /
   Rejected in `review_log.csv`, with a short note either way.
5. **Log corrections**: any Edited/Rejected case gets a full write-up in
   `responsible_ai_log.md` explaining what the AI got wrong and why.
6. **Dashboard**: `netsage_dashboard.xlsx` aggregates all of the above —
   category counts, severity counts, and the AI/human agreement rate — with
   two charts, computed live via spreadsheet formulas (not hardcoded).

## Rule checker — sample run

```
$ python3 rule_checker.py cases.csv

=== C017 ===
  [HIGH  ] missing_route: Expected subnet has no matching entry in 'show ip route'.

=== C022 ===
  [MEDIUM] acl_implicit_deny: ACL permits ICMP only; all other IP traffic (e.g. HTTP) falls through to a deny.
...
--- Summary: 11/30 cases triggered at least one rule-based finding ---
```

Use `--json` for machine-readable output (useful for cross-checking against
the AI's `evidence` field programmatically), or `--case C0XX` to inspect one
case at a time.

## Current results

- **30/30 cases** documented with full evidence.
- **AI/human agreement rate: 83%** (25 Accepted / 3 Edited / 2 Rejected).
- **5 corrected cases** logged in `responsible_ai_log.md`, spanning DHCP,
  DNS, ACL, and NAT categories — with a shared root cause identified across
  4 of them: the AI pattern-matching a plausible cause for the *symptom
  category* instead of strictly grounding in the *specific evidence given*.

## Demo video script (5–10 min)

Suggested structure for the required demo:

1. **(1 min) Intro** — state the problem (symptom-to-root-cause gap for
   junior engineers) and the safety rule (human review is mandatory, AI
   never applies a fix directly).
2. **(2 min) Show a broken lab** — open the Packet Tracer topology for one
   case (e.g. C017, inter-VLAN routing), demonstrate the symptom live
   (ping fails), and pull the relevant `show` command output.
3. **(2 min) Run the AI diagnosis** — feed the evidence into
   `diagnose_prompt.md`, show the JSON output on screen, and separately run
   `rule_checker.py --case C017` to show the independent deterministic
   cross-check agreeing.
4. **(2 min) Human review** — walk through marking the case in
   `review_log.csv` (Accepted, in this case), or better, walk through one of
   the 5 corrected cases (e.g. C009) to show a *rejection* and explain why,
   referencing `responsible_ai_log.md`.
5. **(2 min) Apply the fix and verify** — apply the reviewer-approved
   `fix_steps` in Packet Tracer, re-run the failing ping/traceroute to
   confirm it now succeeds, and show the case flip to "Accepted" with
   verified evidence.
6. **(1 min) Dashboard** — open `netsage_dashboard.xlsx`, point out the
   category/severity breakdown and the 83% agreement rate, and close with
   the responsible-AI takeaway: review caught real errors, not just
   rubber-stamped the AI.

## Regenerating files

```
python3 build_cases.py         # regenerates cases.csv
python3 build_review_log.py    # regenerates review_log.csv (reads cases.csv)
python3 build_dashboard.py     # regenerates netsage_dashboard.xlsx (reads both CSVs)
python3 /mnt/skills/public/xlsx/scripts/recalc.py netsage_dashboard.xlsx   # bake formula values
```
