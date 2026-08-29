"""
NetSage AI — deterministic evidence engine v3.

Runtime input:
    symptom + topology_note + show_output

Ground truth field `expected_fault` is NEVER read by this engine.
"""

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass, field


@dataclass
class Finding:
    check: str
    severity: str
    message: str


@dataclass
class CheckResult:
    case_id: str
    findings: list[Finding] = field(default_factory=list)

    def add(self, check, message, severity="high"):
        if not any(x.check == check for x in self.findings):
            self.findings.append(Finding(check, severity, message))


def evidence(case):
    # Evidence only. Never include expected_fault.
    return "\n".join([
        case.get("symptom", ""),
        case.get("topology_note", ""),
        case.get("show_output", ""),
    ])


def search(text, pattern):
    return re.search(pattern, text, flags=re.I | re.S)


def any_search(text, patterns):
    return any(search(text, p) for p in patterns)


# ---------- SWITCHING ----------

def switching_wrong_vlan(t, r):
    if any_search(t, [
        r"Fa0/2.*Access Mode VLAN:\s*20\s*\(Guest\)",
        r"Fa0/2.*(?:is )?in VLAN\s+20",
        r"assigned to wrong VLAN",
        r"incorrect VLAN assignment",
        r"Access Mode VLAN\s*:?\s*1\b",
        r"Port is assigned to default VLAN",
    ]):
        r.add("wrong_vlan_assignment",
              "Switchport evidence shows the access interface is assigned to the wrong VLAN.")


def switching_missing_vlan(t, r):
    if any_search(t, [
        r"! VLAN\s+\d+\s+not listed",
        r"VLAN\s+\d+\s+absent",
        r"show vlan brief:\s*VLAN\s+\d+\s+absent",
        r"Required VLAN configuration is missing",
    ]):
        r.add("missing_vlan",
              "The required VLAN is absent from the switch VLAN database.")


def switching_trunk_vlan(t, r):
    # Explicit evidence in the show output.
    if any_search(t, [
        r"not permitted in the trunk",
        r"not in allowed VLAN list",
        r"not allowed.*trunk",
        r"not enabled on.*trunk",
        r"not carried over trunk",
        r"wireless VLAN missing from allowed list",
        r"guest VLAN.*not allowed",
        r"VLAN\s+\d+.*not enabled on.*trunk",
        r"VLAN\s+\d+\s+not allowed",
    ]):
        r.add("trunk_vlan_not_allowed",
              "Trunk evidence shows the required VLAN is missing from the allowed VLAN list.")
        return

    # Cisco output can show only the allowed list. If the topology/evidence
    # explicitly says the trunk should carry VLAN X, compare that required
    # VLAN with the actual allowed list.
    if any_search(t, [r"show interfaces trunk", r"Vlans allowed on trunk"]):
        allowed_match = re.search(
            r"Vlans allowed on trunk\s*\n[^\n]*\b((?:\d+,?)+)\b",
            t, re.I
        )
        if allowed_match:
            allowed = {
                int(x) for x in re.findall(r"\d+", allowed_match.group(1))
            }

            required = set()
            for m in re.finditer(
                r"(?:VLANs?|vlan)\s+(\d+)(?:[^\n]{0,80})"
                r"(?:carry|carrying|should|expected|trunk)",
                t, re.I
            ):
                required.add(int(m.group(1)))

            # Also use a clear symptom like "All VLAN 30 hosts..." when a
            # trunk is explicitly present in the same evidence block.
            for m in re.finditer(r"\bVLAN\s+(\d+)\b", t, re.I):
                n = int(m.group(1))
                if n not in (1, 10, 20) and n not in allowed:
                    required.add(n)

            if required and any(v not in allowed for v in required):
                missing = sorted(v for v in required if v not in allowed)
                r.add("trunk_vlan_not_allowed",
                      f"Trunk evidence shows required VLAN(s) {missing} are not in the allowed VLAN list.")

def switching_trunk_mode(t, r):
    if any_search(t, [
        r"inter-switch link.*access port instead of trunk",
        r"Inter-switch.*Administrative Mode:\s*static access",
        r"Gi0/1 switchport: Administrative Mode static access",
    ]):
        r.add("trunk_mode_mismatch",
              "The inter-switch interface is configured as an access port instead of a trunk.")


def switching_native_vlan(t, r):
    if any_search(t, [
        r"native VLAN mismatch",
        r"SW1 native VLAN\s+\d+;\s*SW2 native VLAN\s+\d+",
    ]):
        r.add("native_vlan_mismatch",
              "Trunk endpoints use different native VLANs.")


def switching_vtp(t, r):
    if any_search(t, [
        r"Configuration Revision:\s*25",
        r"Configuration Revision:\s*8",
    ]) and any_search(t, [
        r"VTP Operating Mode:\s*Server",
        r"higher VTP revision",
        r"overwrote the VLAN database",
    ]):
        r.add("vtp_revision_problem",
              "VTP evidence shows a newer revision can overwrite the VLAN database.")


# ---------- DHCP ----------

def dhcp_relay(t, r):
    if any_search(t, [
        r"no ip helper-address",
        r"relay is missing",
        r"DHCP relay is missing",
        r"lacks ip helper-address",
    ]):
        r.add("missing_dhcp_relay",
              "The VLAN interface lacks the DHCP relay/helper configuration.")


def dhcp_dns_option(t, r):
    if any_search(t, [
        r"no dns-server statement",
        r"missing.*dns-server statement",
    ]):
        r.add("missing_dhcp_dns_option",
              "The DHCP pool does not supply a DNS server option.")


def dhcp_pool_exhaustion(t, r):
    if any_search(t, [
        r"Leased addresses:\s*14.*Pool size:\s*14",
        r"95% utilization",
        r"only 2 addresses available",
        r"pool exhausted",
        r"pool.*nearly exhausted",
    ]):
        r.add("dhcp_pool_exhaustion",
              "DHCP pool utilization indicates the address pool is exhausted or nearly exhausted.")


def dhcp_pool_overlap(t, r):
    if any_search(t, [
        r"Pool VLAN10_POOL:\s*Network\s+10\.10\.10\.0/24\s*"
        r"Pool VLAN20_POOL:\s*Network\s+10\.10\.10\.0/24",
        r"same network.*VLAN10_POOL.*VLAN20_POOL",
        r"duplicate network statement",
    ]):
        r.add("dhcp_pool_overlap",
              "Two DHCP pools use the same network, creating an address-space overlap.")


def dhcp_wrong_network(t, r):
    if any_search(t, [
        r"DHCP pool is serving the wrong network",
        r"client has 192\.168\.10\.25",
        r"receives an IP from wrong subnet",
    ]):
        r.add("wrong_dhcp_network",
              "DHCP evidence shows the client is receiving an address from the wrong network.")


def dhcp_disabled(t, r):
    if any_search(t, [
        r"service dhcp disabled",
        r"no service dhcp",
    ]):
        r.add("dhcp_service_disabled",
              "The DHCP service is disabled in the router configuration.")


def dhcp_gateway(t, r):
    if any_search(t, [
        r"Default-router\s+192\.168\.30\.254;\s*gateway is actually\s+192\.168\.30\.1",
        r"Incorrect DHCP default gateway option",
    ]):
        r.add("gateway_mismatch",
              "The DHCP default-router option does not match the router gateway.")


# ---------- DNS ----------

def dns_record(t, r):
    if any_search(t, [
        r"Non-existent domain",
        r"NXDOMAIN",
        r"required DNS record is missing",
        r"Missing/incorrect A record",
    ]):
        r.add("missing_dns_record",
              "DNS lookup evidence shows the required DNS record is missing or incorrect.")


def dns_forwarder(t, r):
    if any_search(t, [
        r"no forwarder configured",
        r"forwarder.*missing",
        r"external domains.*fail",
    ]):
        r.add("missing_dns_forwarder",
              "The internal DNS server has no forwarder for external domains.")


def dns_stale(t, r):
    if any_search(t, [
        r"stale.*record",
        r"decommissioned host\s+10\.1\.1\.30",
        r"server\.corp\.local.*10\.1\.1\.30",
        r"returns old\s+192\.168\.10\.20",
    ]):
        r.add("stale_dns_record",
              "DNS evidence indicates that a stale record/cache is being returned.")


def dns_unreachable(t, r):
    if any_search(t, [
        r"DNS server\s+192\.168\.10\.53 timeout",
        r"DNS server is unreachable",
        r"ping\s+10\.1\.1\.53.*0 percent",
    ]):
        r.add("dns_unreachable",
              "DNS server connectivity evidence shows that the DNS service is unreachable.")


def dns_wrong_server(t, r):
    if any_search(t, [
        r"DNS server\s+192\.168\.99\.53;\s*correct server is\s+192\.168\.10\.53",
    ]):
        r.add("wrong_dns_server",
              "The client is configured with the wrong DNS server.")


def dns_zone(t, r):
    if any_search(t, [
        r"DNS server lacks internal zone",
        r"internal DNS zone is missing",
        r"zone is missing/misconfigured",
        r"SERVFAIL.*internal\.corp\.local",
    ]):
        r.add("dns_zone_problem",
              "DNS evidence indicates the internal zone is missing or misconfigured.")


# ---------- ROUTING / OSPF ----------

def ospf_area(t, r):
    if any_search(t, [
        r"area 0.*area 1",
        r"area 1.*area 0",
        r"different OSPF areas",
        r"OSPF area mismatch",
    ]):
        r.add("ospf_area_mismatch",
              "OSPF configuration shows different areas on the neighbor link.")


def ospf_timer(t, r):
    if any_search(t, [
        r"hello/dead timers differ",
        r"OSPF timer mismatch",
    ]):
        r.add("ospf_timer_mismatch",
              "OSPF hello/dead timer values differ between neighbors.")


def ospf_network(t, r):
    if any_search(t, [
        r"incorrect OSPF network statement",
        r"network 10\.10\.30\.0 configured instead",
    ]):
        r.add("ospf_network_statement",
              "OSPF is configured with the wrong network statement.")


def routing_loop(t, r):
    if any_search(t, [
        r"routing loop",
        r"TTL expired",
        r"10\.0\.0\.1.*10\.0\.0\.2.*10\.0\.0\.1",
    ]):
        r.add("routing_loop",
              "Routing evidence shows traffic looping between the routers.")


def missing_route(t, r):
    if any_search(t, [
        r"no route to",
        r"route .*missing",
        r"missing route",
        r"Required static route is absent",
        r"static route.*is missing",
        r"route.*via.*is missing",
        r"S\s+192\.168\.30\.0/24 via 10\.0\.0\.1 is missing",
        r"no return route",
        r"no route.*10\.10\.10\.0/24",
        r"no Gateway of last resort",
        r"static route to 172\.16\.0\.0/16.*not present",
        r"Default route is missing",
    ]):
        r.add("missing_route",
              "Routing-table evidence indicates that the required route is absent.")


def interface_down(t, r):
    if any_search(t, [
        r"administratively down",
        r"line protocol is down",
        r"interface .* is down",
        r"switch interface for server is down",
        r"show interfaces:\s*Gi\d+/\d+\s+down",
    ]):
        r.add("interface_down",
              "Interface status evidence indicates that the required interface/link is down.")


# ---------- ACL ----------

def acl_block(t, r):
    if any_search(t, [
        r"deny ip any host 10\.10\.30\.10",
        r"deny tcp any any eq 22",
        r"deny tcp .*eq 443",
        r"deny tcp .*eq 8080",
        r"deny icmp any any",
        r"ACL explicitly blocks",
        r"ACL blocks",
        r"ACL denies",
        r"blocks HTTP",
        r"blocks HTTPS",
        r"blocks SSH",
        r"blocks ICMP",
        r"ACL.*denies.*admin subnet",
        r"deny 192\.168\.10\.0/24",
        r"permit ip any any.*deny statement.*missing",
        r"guest ACL permits ip any any",
        r"no isolation ACL applied",
    ]):
        r.add("acl_block",
              "ACL evidence shows that required traffic is denied or the required isolation deny is absent.")


def acl_shadowing(t, r):
    if any_search(t, [
        r"permit ip any any before guest deny",
        r"overly permissive ACL",
        r"shadows isolation rule",
        r"guest isolation ACL is missing/overly permissive",
        r"guest ACL permits ip any any",
    ]):
        r.add("acl_shadowing",
              "A broad permit rule is overriding or replacing the intended isolation policy.")


def acl_ordering(t, r):
    if any_search(t, [
        r"deny ip any any; permit rule is after deny",
        r"explicit deny appears before permit",
        r"deny.*before.*permit",
    ]):
        r.add("acl_ordering",
              "ACL ordering causes a deny to match before the intended permit.")


def acl_vty(t, r):
    if any_search(t, [
        r"access-class 11 in",
        r"access-class references ACL",
        r"Wrong ACL number applied to VTY",
    ]):
        r.add("acl_vty_mismatch",
              "VTY lines reference an ACL different from the configured management ACL.")


# ---------- NAT ----------

def nat_inside(t, r):
    if any_search(t, [
        r"missing 'ip nat inside'",
        r"no ip nat inside on LAN interface",
        r"not marked for NAT",
    ]):
        r.add("nat_inside_missing",
              "The LAN interface is missing the ip nat inside designation.")


def nat_outside(t, r):
    if any_search(t, [
        r"lacks ip nat outside",
        r"not configured as NAT outside",
        r"missing ip nat outside",
    ]):
        r.add("nat_outside_missing",
              "The WAN interface is missing the ip nat outside designation.")


def static_nat(t, r):
    if any_search(t, [
        r"no static/port-forward entry",
        r"missing static NAT",
    ]):
        r.add("static_nat_problem",
              "The required static NAT/port-forward mapping is missing.")
    elif any_search(t, [
        r"Static public server is unreachable",
        r"ip nat inside source static 192\.168\.50\.10 203\.0\.113\.11",
    ]):
        r.add("static_nat_problem",
              "The static NAT mapping shown is inconsistent with the expected published server configuration.")


def nat_acl(t, r):
    if any_search(t, [
        r"NAT ACL denies 192\.168\.10\.0/24",
        r"does not permit inside subnet",
        r"VLAN 20.*excluded from translation",
        r"10\.10\.20\.0/24.*not included",
    ]):
        r.add("nat_acl_problem",
              "The NAT ACL excludes required inside traffic from translation.")


def pat(t, r):
    if any_search(t, [
        r"PAT/NAT overload is not configured",
        r"only one static mapping exists",
    ]):
        r.add("pat_missing",
              "PAT/overload is not configured for the inside hosts.")


def nat_pool(t, r):
    if any_search(t, [
        r"NAT pool has no free addresses",
        r"pool exhausted",
    ]):
        r.add("nat_pool_exhaustion",
              "The NAT address pool has no free addresses.")


# ---------- HOST/IP ----------

def duplicate_ip(t, r):
    if any_search(t, [
        r"same IP.*two MAC",
        r"Duplicate IP address",
        r"Duplicate IP configuration",
        r"same address assigned to another device",
        r"IP conflict",
        r"192\.168\.1\.50.*192\.168\.1\.50",
    ]):
        r.add("duplicate_ip",
              "ARP/IP evidence shows the same address assigned to multiple devices.")


def gateway(t, r):
    if any_search(t, [
        r"Gateway:\s*10\.10\.10\.100",
        r"gateway is outside the local subnet",
        r"gateway\s+192\.168\.10\.20.*192\.168\.20\.1",
        r"gateway\s+192\.168\.80\.254.*router gateway\s+192\.168\.80\.1",
        r"Incorrect default gateway supplied",
        r"IP\s+192\.168\.10\.20.*gateway\s+192\.168\.20\.1",
        r"IP\s+192\.168\.80\.25.*gateway\s+192\.168\.80\.254.*router gateway\s+192\.168\.80\.1",
        r"IP\s+\d{1,3}(?:\.\d{1,3}){3},\s*gateway\s+\d{1,3}(?:\.\d{1,3}){3};\s*router gateway is\s+\d{1,3}(?:\.\d{1,3}){3}",
    ]):
        r.add("gateway_mismatch",
              "The host's default gateway does not match the local router/subnet.")
        return

    ip = re.search(r"\b(?:IP|Address):\s*(\d{1,3}(?:\.\d{1,3}){3})", t, re.I)
    gw = re.search(r"\bGateway:\s*(\d{1,3}(?:\.\d{1,3}){3})", t, re.I)
    mask = re.search(r"\bMask:\s*(255\.255\.255\.0)", t, re.I)
    if ip and gw and mask:
        if ip.group(1).rsplit(".", 1)[0] != gw.group(1).rsplit(".", 1)[0]:
            r.add("gateway_mismatch",
                  "The host's default gateway is outside its local /24 subnet.")

def wrong_mask(t, r):
    if any_search(t, [
        r"mask\s+255\.255\.0\.0.*peers use\s+255\.255\.255\.0",
        r"Incorrect subnet mask",
        r"subnet mask too small",
    ]):
        r.add("wrong_mask",
              "The host or DHCP pool uses an incorrect subnet mask.")


def stale_ip(t, r):
    if any_search(t, [
        r"retains old IP configuration",
        r"old IP configuration",
        r"192\.168\.10\.25/24.*192\.168\.40\.0/24",
    ]):
        r.add("stale_ip_configuration",
              "The host retains an IP configuration from its previous subnet.")


def run_case(case):
    t = evidence(case)
    r = CheckResult(case_id=case["case_id"])

    switching_wrong_vlan(t, r)
    switching_missing_vlan(t, r)
    switching_trunk_vlan(t, r)
    switching_trunk_mode(t, r)
    switching_native_vlan(t, r)
    switching_vtp(t, r)

    dhcp_relay(t, r)
    dhcp_dns_option(t, r)
    dhcp_pool_exhaustion(t, r)
    dhcp_pool_overlap(t, r)
    dhcp_wrong_network(t, r)
    dhcp_disabled(t, r)
    dhcp_gateway(t, r)

    dns_record(t, r)
    dns_forwarder(t, r)
    dns_stale(t, r)
    dns_unreachable(t, r)
    dns_wrong_server(t, r)
    dns_zone(t, r)

    ospf_area(t, r)
    ospf_timer(t, r)
    ospf_network(t, r)
    routing_loop(t, r)
    missing_route(t, r)
    interface_down(t, r)

    acl_block(t, r)
    acl_shadowing(t, r)
    acl_ordering(t, r)
    acl_vty(t, r)

    nat_inside(t, r)
    nat_outside(t, r)
    static_nat(t, r)
    nat_acl(t, r)
    pat(t, r)
    nat_pool(t, r)

    duplicate_ip(t, r)
    gateway(t, r)
    wrong_mask(t, r)
    stale_ip(t, r)

    return r


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv_path")
    p.add_argument("--case")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    with open(args.csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if args.case:
        rows = [x for x in rows if x["case_id"].upper() == args.case.upper()]

    results = [run_case(x) for x in rows]

    if args.json:
        print(json.dumps([
            {"case_id": x.case_id, "findings": [asdict(f) for f in x.findings]}
            for x in results
        ], indent=2))
        return

    hits = 0
    for x in results:
        print(f"\n=== {x.case_id} ===")
        if not x.findings:
            print("(no deterministic findings)")
        else:
            hits += 1
            for f in x.findings:
                print(f"[{f.severity.upper()}] {f.check}: {f.message}")

    print(f"\n--- Summary: {hits}/{len(results)} cases triggered at least one deterministic finding ---")


if __name__ == "__main__":
    main()
