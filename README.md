NetSage AI

AI-assisted Network Fault Detection & Human Review Platform

NetSage AI is a network troubleshooting platform that combines a deterministic Cisco/network rule engine, Gemini-powered diagnosis, and a human-in-the-loop review workflow.

The system is designed around a simple principle:

deterministic evidence first → AI explanation second → human validation before acceptance

It currently evaluates a dataset of 80 network troubleshooting cases (C001–C080) covering VLANs, trunking, DHCP, DNS, routing, OSPF, ACLs, NAT/PAT, IP configuration, and related network faults.

What NetSage AI Does

For each troubleshooting case, NetSage AI:

Loads the network symptom, topology information, and command output.

Runs deterministic rules against the evidence.

Identifies the relevant network fault family.

Sends the case to Gemini for an explainable diagnosis.

Produces:

root cause

supporting evidence

OSI layer

confidence

next diagnostic command

recommended fix steps

alternative causes

Presents the diagnosis in a Streamlit interface.

Allows a human reviewer to:

Accept

Edit

Reject

Stores the review decision in reviews/review_log.csv.

Architecture

                         ┌──────────────────────┐
                         │      cases.csv       │
                         │     C001 - C080      │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │  Deterministic Rule  │
                         │       Checker        │
                         └──────────┬───────────┘
                                    │
                         verified fault evidence
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │    Gemini Diagnosis  │
                         │  explanation layer   │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │    Streamlit App     │
                         │  Diagnosis + Review  │
                         └──────────┬───────────┘
                                    │
                         human decision
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │    review_log.csv    │
                         │ Accept/Edit/Reject   │
                         └──────────────────────┘

Key Design Decision

NetSage AI does not rely on an LLM alone to decide whether a network fault exists.

The deterministic rule engine provides the verified fault-detection layer. Gemini is used to turn the available evidence into a structured, human-readable diagnosis.

This reduces the risk of an LLM inventing a network condition that is not supported by the supplied command output.

Project Structure

NETSAGE_AI/
│
├── ai/
│   ├── diagnose.py
│   └── diagnose_prompt.md
│
├── checker/
│   └── rule_checker.py
│
├── dashboard/
│   └── dashboard.html
│
├── data/
│   └── cases.csv
│
├── reviews/
│   └── review_log.csv
│
├── app.py
├── build_dashboard.py
├── build_review_log.py
├── evaluate_rules.py
├── main.py
├── README.md
├── requirements.txt
└── .gitignore

Rule Coverage

The deterministic checker currently covers fault families including:

Fault family

Example

wrong_vlan_assignment

Access port assigned to the wrong VLAN

trunk_vlan_not_allowed

Required VLAN missing from trunk allowed list

missing_vlan

Required VLAN is absent

vtp_revision_problem

Incorrect VTP database revision

gateway_mismatch

Incorrect default gateway

interface_down

Relevant interface/link is down

duplicate_ip

Duplicate host IP configuration

wrong_mask

Incorrect subnet mask

missing_dhcp_relay

Missing DHCP helper/relay

dhcp_pool_exhaustion

DHCP pool exhausted

dhcp_pool_overlap

Overlapping DHCP networks

missing_dhcp_dns_option

Missing DNS option in DHCP pool

wrong_dhcp_network

DHCP pool serves the wrong network

dhcp_service_disabled

DHCP service disabled

missing_dns_record

Required DNS record missing

missing_dns_forwarder

DNS forwarder missing

stale_dns_record

Stale DNS record

dns_unreachable

DNS service unreachable

wrong_dns_server

Incorrect DNS server configured

dns_zone_problem

DNS zone problem

missing_route

Required route missing

routing_loop

Routing loop

ospf_area_mismatch

OSPF area mismatch

ospf_timer_mismatch

OSPF timer mismatch

ospf_network_statement

Incorrect OSPF network statement

acl_block

ACL blocks required traffic

acl_shadowing

ACL rule shadowing

acl_ordering

Incorrect ACL rule ordering

acl_vty_mismatch

Wrong ACL applied to VTY

nat_inside_missing

Missing NAT inside designation

nat_outside_missing

Missing NAT outside designation

pat_missing

PAT/overload configuration missing

static_nat_problem

Static NAT problem

nat_acl_problem

NAT source ACL problem

nat_pool_exhaustion

NAT pool exhausted

stale_ip_configuration

Host retains stale IP configuration

trunk_mode_mismatch

Trunk/access mode mismatch

native_vlan_mismatch

Native VLAN mismatch

Validation

The current deterministic audit covers all 80 cases.

Latest validation result:

Total cases       : 80
Correct           : 77
Wrong rule        : 0
Missed            : 0
Unmapped expected : 3
Accuracy          : 100.0%

What the 100% means

The reported 100% is the accuracy of the mapped deterministic rule evaluation.

There are 3 cases whose expected fault is intentionally UNMAPPED. They are not counted as successful fault mappings:

Correct mapped cases : 77
Wrong mapped cases   : 0
Missed mapped cases  : 0
Unmapped expected   : 3

This distinction is kept explicit instead of treating unmapped cases as correct predictions.

Human Review

NetSage AI includes a human review layer because an AI-generated explanation should not automatically become the final operational decision.

Each case can be marked:

Accepted — reviewer agrees with the diagnosis.

Edited — reviewer changes/corrects the diagnosis.

Rejected — reviewer does not accept the diagnosis.

The review log preserves:

case_id
category
severity
ai_root_cause
ai_confidence
human_status
agreement
reviewer_note

Cases that have not been reviewed remain:

Pending

The system does not fabricate human decisions.

Gemini Integration

The AI diagnosis layer uses Google's Gemini API through the google-genai Python SDK.

The API key is read from an environment variable:

GEMINI_API_KEY

The key is intentionally not stored in source code or the repository.

Set the key on Windows PowerShell

$env:GEMINI_API_KEY="YOUR_GEMINI_API_KEY"

Verify:

C:\Python313\python.exe -c "import os; print('KEY OK' if os.getenv('GEMINI_API_KEY') else 'KEY MISSING')"

Expected:

KEY OK

You can optionally choose the model:

$env:GEMINI_MODEL="gemini-3.6-flash"

Installation

Python 3.13 is used for the current development environment.

Install dependencies:

C:\Python313\python.exe -m pip install -r requirements.txt

If google-genai is not already present:

C:\Python313\python.exe -m pip install -U google-genai

Run the Deterministic Audit

From the project root:

C:\Python313\python.exe evaluate_rules.py

This evaluates the complete C001–C080 dataset and reports:

correct detections

wrong rules

missed cases

unmapped expected faults

per-rule results

overall accuracy

Build the Review Log

The review-log builder validates that all 80 cases are represented.

C:\Python313\python.exe build_review_log.py

It maintains:

C001
C002
...
C080

and preserves existing human decisions rather than fabricating them.

Build the Dashboard

C:\Python313\python.exe build_dashboard.py

The generated dashboard is written to:

dashboard/dashboard.html

Run the Streamlit Application

Use Streamlit through the same Python installation:

C:\Python313\python.exe -m streamlit run app.py

Then open the local URL shown by Streamlit, normally:

http://localhost:8501

Typical Workflow

1. Select a case

Example:

C001

2. Run the deterministic checker

The application displays the verified rule finding.

Example:

[HIGH] wrong_vlan_assignment

3. Run Gemini diagnosis

Gemini receives the case evidence and returns a structured diagnosis.

Example output:

OSI Layer       : Layer 2
Confidence      : high
Severity        : Medium

Root Cause:
Interface FastEthernet0/2 is incorrectly configured in VLAN 20
instead of VLAN 10.

Next Command:
show running-config interface Fa0/2

4. Human review

The reviewer chooses:

Accepted
Edited
Rejected

and can add a reviewer note.

5. Persist the decision

The decision is stored in:

reviews/review_log.csv

Example Case

C001

Problem

A host is experiencing connectivity problems because its access switchport is assigned to the wrong VLAN.

Deterministic finding

wrong_vlan_assignment

AI explanation

The AI can explain why the command output supports the finding and recommend the next Cisco command to inspect the interface.

Human reviewer

The reviewer confirms, edits, or rejects the diagnosis.

This demonstrates the complete:

Evidence
   ↓
Rule
   ↓
AI Explanation
   ↓
Human Validation
   ↓
Audit Log

Safety and Reliability

NetSage AI is designed as a troubleshooting assistant, not an autonomous network-change system.

The application:

does not automatically change Cisco configurations

does not fabricate human approvals

keeps deterministic detection separate from AI explanation

exposes the evidence used for the diagnosis

provides a next diagnostic command before recommending a fix

records human review decisions

Any configuration change should still be validated by an authorized network administrator.

Technologies

Python

Pandas

Streamlit

Google Gemini API

google-genai

CSV

HTML/CSS/JavaScript

Cisco networking concepts

Deterministic rule-based fault detection

Human-in-the-loop review

Project Goal

NetSage AI is built to demonstrate how traditional deterministic network troubleshooting can be combined with modern AI without giving the AI complete control over the decision process.

The core idea is:

Use rules for what can be verified, AI for explanation and reasoning, and humans for final judgment.

Current Status

Dataset                     : 80 cases
Deterministic validation    : 77 mapped correct
Wrong deterministic rules  : 0
Missed mapped cases        : 0
Unmapped expected cases    : 3
Streamlit application       : Working
Gemini diagnosis            : Working
Human review workflow       : Working
Review log                  : 80-case aligned
Dashboard                   : Working

Future Improvements

Potential next steps include:

Expand the deterministic rule library.

Map the remaining intentionally unmapped fault families.

Add richer Cisco command parsing.

Add reviewer authentication and timestamps.

Add case-level audit history.

Add automated regression tests for every rule.

Add confidence calibration against reviewer outcomes.

Add retrieval of Cisco documentation for evidence-backed recommendations.

Add deployment with secure secret management.

Add monitoring of AI-vs-human disagreement patterns.

Author

Akshat Shrivastav

NetSage AI — Network Fault Detection & Human Review Platform