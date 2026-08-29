# NetSage AI — Responsible AI Log

This log documents every case where the human reviewer **edited or rejected**
the AI's diagnosis, why the AI got it wrong, and what that implies about the
assistant's limits. Full machine-readable record: `review_log.csv`
(`human_status` = Edited/Rejected rows).

Summary: **25 Accepted · 3 Edited · 2 Rejected** out of 30 cases
(AI/human raw agreement rate ≈ 83%).

---

### C009 — DHCP relay missing (VLAN 30)
- **AI said:** DHCP pool for VLAN 30 is exhausted.
- **Actual cause:** Missing `ip helper-address` on the VLAN 30 SVI — DHCP
  broadcasts from clients never reach the DHCP server at all.
- **Status:** Edited
- **Why the AI got it wrong:** No pool utilization numbers (leased/pool
  size) were present in the show output, so "exhausted" was an unsupported
  guess. The AI pattern-matched "no address received" to the most common
  DHCP failure mode instead of checking whether a relay path even existed.
- **Lesson:** When evidence doesn't include quantitative pool data, the
  prompt should force "insufficient evidence" + `next_command` rather than
  a confident-sounding guess. We tightened the reviewer instruction to
  double-check DHCP cases for a helper-address line before accepting.

### C011 — DHCP pool overlap (VLAN 10 / VLAN 20)
- **AI said:** DHCP server's binding database is corrupted.
- **Actual cause:** VLAN10_POOL and VLAN20_POOL were both configured with
  network `10.10.10.0/24` — an overlapping pool definition.
- **Status:** Rejected
- **Why the AI got it wrong:** "Database corruption" isn't verifiable from
  a Packet Tracer `show ip dhcp pool` output and isn't a fault type in our
  taxonomy. This is a case of the model defaulting to a real-world-sounding
  cause that isn't actually checkable evidence.
- **Lesson:** Added a rule to the prompt: root causes must map to one of
  the eight documented concept tags; anything else needs a "low confidence,
  needs more evidence" flag instead of a fabricated cause.

### C016 — Stale DNS record
- **AI said:** DNS server is unreachable, causing resolution to fall back
  to a cached address.
- **Actual cause:** The DNS server *did* resolve the name — it just
  returned a wrong/stale A record pointing at a decommissioned host.
- **Status:** Rejected
- **Why the AI got it wrong:** The AI conflated "wrong answer returned" with
  "no answer returned." The nslookup output clearly shows a successful
  response, which the AI's root_cause contradicted.
- **Lesson:** This is exactly the kind of subtle evidence-reading error a
  junior engineer could also make — reinforces why review is mandatory
  even on "confident-sounding" AI output.

### C025 — Wrong ACL number bound to VTY lines
- **AI said:** ACL 10 itself is too permissive / misconfigured.
- **Actual cause:** ACL 10 is written correctly; the problem is that
  `access-class 11 in` on the VTY lines references a *different* ACL
  number than the one that was configured.
- **Status:** Edited
- **Why the AI got it wrong:** The AI focused on the ACL body (which looked
  fine) and didn't cross-reference the `access-class` binding shown further
  down in the same output — a "read the whole evidence block" failure.
- **Lesson:** Updated the prompt's evidence instruction to explicitly
  require checking for a mismatch between *where an ACL is defined* and
  *where/how it's applied* (access-group vs access-class number).

### C028 — NAT source ACL incomplete
- **AI said:** NAT overload is not enabled on the router interface for
  VLAN 20.
- **Actual cause:** NAT overload *is* enabled; the NAT source ACL (ACL 1)
  simply doesn't include VLAN 20's subnet, so those packets are never
  selected for translation.
- **Status:** Edited (partial match — right general area, wrong mechanism)
- **Why the AI got it wrong:** The AI reasoned from the symptom pattern
  ("VLAN 20 has no internet, VLAN 10 does") to a plausible-sounding but
  incorrect mechanism, rather than reading the specific ACL 1 output that
  was provided as evidence.
- **Lesson:** This case, along with C025, shows a recurring pattern —
  the AI sometimes reasons from symptom-to-cause pattern matching instead
  of grounding strictly in the evidence line. We now require the
  review-assist prompt to specifically check whether `evidence` actually
  quotes/references the decisive line of output.

---

## Patterns across corrections
1. **Evidence-grounding failures (4/5 cases):** the AI proposed a cause that
   *sounded* plausible for the symptom category but wasn't supported by the
   specific show output given (C009, C011, C016, C028).
2. **Incomplete evidence reading (1/5 cases):** the AI didn't cross-reference
   all relevant lines in the same output block (C025).
3. **No case involved a dangerous or unsafe fix being proposed** — errors
   were all in diagnosis accuracy, not in suggesting harmful configuration
   changes. This is expected given the lab-only scope, but is worth
   re-checking if this assistant were ever pointed at production evidence.

## Process takeaway
None of these five errors would have reached a real device, because every
diagnosis is routed through mandatory human review before any fix is
applied (per the "Human review" safety rule). This log is the evidence
trail for that control: it demonstrates review is catching real,
substantive errors — not just being a rubber stamp.
