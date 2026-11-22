"""Who a write is from: whois first, the sidecar's headers as fallback, and
the host itself for a request that did not come through the sidecar."""

from colophon.server.identity import caller


def whois_person(ip, socket_path=""):
    return {"Node": {"ComputedName": "laptop", "Name": "laptop.example.ts.net.", "Tags": None},
            "UserProfile": {"LoginName": "you@example.com", "DisplayName": "Alex Example"}}


def whois_tagged(ip, socket_path=""):
    return {"Node": {"ComputedName": "lights", "Tags": ["tag:svc-lights"]}, "UserProfile": {}}


def test_whois_names_person_and_machine():
    c = caller({"X-Forwarded-For": "100.64.1.2"}, who=whois_person)
    assert (c.name, c.login, c.machine, c.source) == ("Alex Example", "you@example.com", "laptop", "tailnet")
    assert c.author == "Alex Example <you@example.com>"


def test_headers_when_whois_cannot_be_asked():
    c = caller({"Tailscale-User-Login": "you@example.com", "Tailscale-User-Name": "Alex",
                "X-Forwarded-For": "100.64.1.2"}, who=lambda ip, s="": None)
    assert (c.login, c.machine) == ("you@example.com", "100.64.1.2")


def test_encoded_header_names_are_decoded():
    c = caller({"Tailscale-User-Login": "a@b", "Tailscale-User-Name": "=?utf-8?q?Zo=C3=AB?="},
               who=lambda ip, s="": None)
    assert c.name == "Zoë"


def test_tagged_node_is_named_by_its_tag():
    c = caller({"X-Forwarded-For": "100.64.9.9"}, who=whois_tagged)
    assert (c.name, c.login, c.machine) == ("tag:svc-lights", "svc-lights@tagged", "lights")


def test_local_request_is_the_host():
    c = caller({}, who=whois_person)
    assert c.source == "local" and "@" in c.login and c.machine


def test_non_tailnet_forwarded_address_is_ignored():
    c = caller({"X-Forwarded-For": "192.168.1.5"}, who=whois_person)
    assert c.source == "local"
