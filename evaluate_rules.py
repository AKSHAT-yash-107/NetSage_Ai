"""
NetSage AI — deterministic engine evaluator v3.

`expected_fault` is used ONLY here as ground truth.
It is never passed to the checker.
"""

import argparse
import csv
import importlib.util
from pathlib import Path


def expected_rule(fault):
    s = str(fault).lower()

    # Exact semantic meanings for the supplied dataset.
    if "dns server's interface is administratively down" in s:
        return "interface_down"
    if "stale/incorrect a record" in s or "decommissioned host" in s:
        return "stale_dns_record"
    if "required static route is absent" in s:
        return "missing_route"
    if "nat source acl" in s and "excluded from translation" in s:
        return "nat_acl_problem"
    if "ap uplink trunk does not carry" in s:
        return "trunk_vlan_not_allowed"
    if "inter-switch link is configured as an access port" in s:
        return "trunk_mode_mismatch"
    if "next-hop interface is down" in s:
        return "interface_down"
    if "acl blocks intended admin subnet" in s:
        return "acl_block"
    if "guest isolation acl is missing/overly permissive" in s:
        return "acl_shadowing"
    if "port is assigned to default vlan" in s:
        return "wrong_vlan_assignment"
    if "default gateway is outside" in s:
        return "gateway_mismatch"
    if "incorrect default gateway supplied" in s:
        return "gateway_mismatch"

    # Specific semantic meanings first.
    if "assigned to wrong vlan" in s or "incorrect vlan assignment" in s or "assigned to default vlan" in s:
        return "wrong_vlan_assignment"
    if "trunk" in s and ("not permitted" in s or "not allowed" in s or "not carried" in s or "allowed list" in s):
        return "trunk_vlan_not_allowed"
    if "native vlan mismatch" in s:
        return "native_vlan_mismatch"
    if "access port instead of trunk" in s:
        return "trunk_mode_mismatch"
    if "vtp revision" in s:
        return "vtp_revision_problem"
    if ("svi" in s and "shut down" in s) or "administratively down" in s:
        return "interface_down"
    if "line protocol down" in s or "interface is down" in s or "interface.*down" in s:
        return "interface_down"
    if "subinterface" in s:
        return "missing_route"
    if "duplicate ip" in s:
        return "duplicate_ip"

    if "ip helper-address" in s or "dhcp relay" in s:
        return "missing_dhcp_relay"
    if "dns-server" in s:
        return "missing_dhcp_dns_option"
    if "same network" in s or "address overlap" in s:
        return "dhcp_pool_overlap"
    if "dhcp pool subnet mask too small" in s:
        return "dhcp_pool_exhaustion"
    if "pool is nearly exhausted" in s or "pool exhausted" in s:
        return "dhcp_pool_exhaustion"
    if "wrong network" in s and "dhcp" in s:
        return "wrong_dhcp_network"
    if "dhcp service is disabled" in s:
        return "dhcp_service_disabled"
    if "dhcp default gateway" in s:
        return "gateway_mismatch"

    if "stale" in s or "decommissioned host" in s or "old 192.168.10.20" in s:
        return "stale_dns_record"

    if "forwarder" in s:
        return "missing_dns_forwarder"
    if "stale" in s and "dns" in s:
        return "stale_dns_record"
    if "a record" in s or "dns record" in s:
        return "missing_dns_record"
    if "dns server is unreachable" in s:
        return "dns_unreachable"
    if "incorrect dns server" in s:
        return "wrong_dns_server"
    if "internal dns zone" in s:
        return "dns_zone_problem"

    if "ospf area" in s:
        return "ospf_area_mismatch"
    if "ospf timer" in s:
        return "ospf_timer_mismatch"
    if "ospf network" in s:
        return "ospf_network_statement"
    if "routing loop" in s:
        return "routing_loop"
    if "return route" in s or "static route" in s or "default route" in s or "route is absent" in s:
        return "missing_route"
    if "next-hop interface is down" in s:
        return "interface_down"

    if "acl number" in s or "access-class" in s:
        return "acl_vty_mismatch"
    if "shadow" in s or "overly permissive" in s:
        return "acl_shadowing"
    if "explicit deny appears before" in s:
        return "acl_ordering"
    if "acl" in s and ("blocks" in s or "denies" in s or "missing" in s):
        return "acl_block"

    if "nat outside" in s:
        return "nat_outside_missing"
    if "nat inside" in s:
        return "nat_inside_missing"
    if "pat/nat overload" in s:
        return "pat_missing"
    if "static nat" in s:
        return "static_nat_problem"
    if "nat acl" in s:
        return "nat_acl_problem"
    if "excluded from translation" in s:
        return "nat_acl_problem"
    if "nat pool" in s:
        return "nat_pool_exhaustion"

    if "gateway" in s:
        return "gateway_mismatch"
    if "subnet mask" in s:
        return "wrong_mask"
    if "old ip configuration" in s:
        return "stale_ip_configuration"

    if "vlan" in s and ("missing" in s or "absent" in s):
        return "missing_vlan"

    return "UNMAPPED"


def load_checker():
    path = Path(__file__).resolve().parent / "checker" / "rule_checker.py"
    spec = importlib.util.spec_from_file_location("netsage_checker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="data/cases.csv")
    args = p.parse_args()

    checker = load_checker()

    with open(args.cases, newline="", encoding="utf-8") as f:
        cases = list(csv.DictReader(f))

    rows = []
    for case in cases:
        expected = expected_rule(case["expected_fault"])
        detected = {x.check for x in checker.run_case(case).findings}

        if expected == "UNMAPPED":
            status = "UNMAPPED"
        elif expected in detected:
            status = "CORRECT"
        elif detected:
            status = "WRONG_RULE"
        else:
            status = "MISSED"

        rows.append((case, expected, detected, status))

    print("=" * 90)
    print("NETSAGE AI - DETERMINISTIC RULE AUDIT v3")
    print("=" * 90)

    for case, expected, detected, status in rows:
        print(
            f'{case["case_id"]:<6} {status:<11} '
            f'expected={expected:<25} '
            f'detected={", ".join(sorted(detected)) or "NONE"}'
        )

    total = len(rows)
    correct = sum(x[3] == "CORRECT" for x in rows)
    wrong = sum(x[3] == "WRONG_RULE" for x in rows)
    missed = sum(x[3] == "MISSED" for x in rows)
    unmapped = sum(x[3] == "UNMAPPED" for x in rows)

    print("\nSUMMARY")
    print("-" * 90)
    print(f"Total cases       : {total}")
    print(f"Correct           : {correct}")
    print(f"Wrong rule        : {wrong}")
    print(f"Missed            : {missed}")
    print(f"Unmapped expected : {unmapped}")

    mapped = total - unmapped
    if mapped:
        print(f"Accuracy          : {correct / mapped * 100:.1f}%")

    print("\nMISSED / WRONG")
    print("-" * 90)
    for case, expected, detected, status in rows:
        if status in ("MISSED", "WRONG_RULE"):
            print(
                f'{case["case_id"]:<6} {status:<11} '
                f'expected={expected:<25} '
                f'detected={", ".join(sorted(detected)) or "NONE"}'
            )


if __name__ == "__main__":
    main()
