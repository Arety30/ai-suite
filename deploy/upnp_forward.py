#!/usr/bin/env python3
"""Ask the router (via UPnP IGD) to forward external port 80 -> this PC:80.

Pure Python, no sudo, no router login. Works only if the router has UPnP enabled.
If discovery finds no gateway, UPnP is off and only router access or a VPS can
make the duckdns subdomain reachable.
"""
import re
import socket
import urllib.request
from urllib.parse import urljoin

LAN_IP = "LAN_IP"
EXT_PORT = 80
INT_PORT = 80

SSDP_ADDR, SSDP_PORT = "239.255.255.250", 1900
SRC_IP = "LAN_IP"   # force discovery out the wifi interface to the router
STS = [
    "urn:schemas-upnp-org:device:InternetGatewayDevice:1",
    "urn:schemas-upnp-org:device:InternetGatewayDevice:2",
    "urn:schemas-upnp-org:service:WANIPConnection:1",
    "urn:schemas-upnp-org:service:WANPPPConnection:1",
    "ssdp:all",
]


def _msearch(st):
    return "\r\n".join([
        "M-SEARCH * HTTP/1.1",
        f"HOST: {SSDP_ADDR}:{SSDP_PORT}",
        'MAN: "ssdp:discover"',
        "MX: 2",
        f"ST: {st}",
        "", ""]).encode()


def discover():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # pin multicast to the wifi interface, not a docker bridge
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(SRC_IP))
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    try:
        s.bind((SRC_IP, 0))
    except OSError:
        pass
    s.settimeout(4)
    for st in STS:
        for _ in range(2):
            s.sendto(_msearch(st), (SSDP_ADDR, SSDP_PORT))
    try:
        while True:
            data, addr = s.recvfrom(65507)
            text = data.decode("latin-1")
            m = re.search(r"LOCATION:\s*(\S+)", text, re.I)
            if m and ("InternetGateway" in text or "WAN" in text or "rootDesc" in m.group(1)
                      or ":1900" not in m.group(1)):
                return m.group(1)
    except socket.timeout:
        return None


def find_control(location):
    xml = urllib.request.urlopen(location, timeout=5).read().decode("latin-1")
    # find a WAN(IP|PPP)Connection service block and its controlURL
    for svc in re.findall(r"<service>.*?</service>", xml, re.S):
        if "WANIPConnection" in svc or "WANPPPConnection" in svc:
            stype = re.search(r"<serviceType>(.*?)</serviceType>", svc, re.S).group(1).strip()
            ctrl = re.search(r"<controlURL>(.*?)</controlURL>", svc, re.S).group(1).strip()
            return stype, urljoin(location, ctrl)
    return None, None


def add_mapping(stype, control_url):
    body = f"""<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
<s:Body><u:AddPortMapping xmlns:u="{stype}">
<NewRemoteHost></NewRemoteHost>
<NewExternalPort>{EXT_PORT}</NewExternalPort>
<NewProtocol>TCP</NewProtocol>
<NewInternalPort>{INT_PORT}</NewInternalPort>
<NewInternalClient>{LAN_IP}</NewInternalClient>
<NewEnabled>1</NewEnabled>
<NewPortMappingDescription>abrar-chatbot</NewPortMappingDescription>
<NewLeaseDuration>0</NewLeaseDuration>
</u:AddPortMapping></s:Body></s:Envelope>"""
    req = urllib.request.Request(
        control_url, data=body.encode(),
        headers={"Content-Type": 'text/xml; charset="utf-8"',
                 "SOAPAction": f'"{stype}#AddPortMapping"'})
    try:
        urllib.request.urlopen(req, timeout=6).read()
        return True, "ok"
    except urllib.error.HTTPError as e:
        return False, f"router refused: HTTP {e.code} — {e.read().decode('latin-1')[:200]}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


print("1) discovering router UPnP…")
loc = discover()
if not loc:
    print("   ✗ no UPnP gateway found — router has UPnP disabled/blocked.")
    print("   -> the duckdns subdomain needs router access or a VPS; can't be done from here.")
    raise SystemExit(1)
print("   ✓ gateway:", loc)

print("2) finding WAN connection service…")
stype, ctrl = find_control(loc)
if not ctrl:
    print("   ✗ no WAN connection service exposed over UPnP.")
    raise SystemExit(1)
print("   ✓", stype)

print(f"3) requesting forward  WAN:{EXT_PORT} -> {LAN_IP}:{INT_PORT} TCP …")
ok, msg = add_mapping(stype, ctrl)
print("   ✓ port opened!" if ok else f"   ✗ {msg}")
