import re

CATEGORIES = ["Router/Gateway","Smartphone/Tablet","Laptop/Desktop","Smart TV","IoT/Smart Home","Network Printer","Server/NAS","Unknown"]

def _text(d):
    return " ".join(str(x or "") for x in [d.get("hostname"), d.get("vendor"), str(d.get("metadata"))]).lower()

def classify(device) -> dict:
    data = device if isinstance(device, dict) else {
        "hostname": getattr(device, "hostname", None),
        "vendor": getattr(device, "vendor", None),
        "metadata": getattr(device, "extra", None),
    }
    t = _text(data)
    reasons = []
    cat = "Unknown"
    conf = 0.3
    rules = [
        (r"router|gateway|ap\b", "Router/Gateway", 0.8, "hostname/vendor indicates router/gateway"),
        (r"iphone|android|phone|tablet|ipad", "Smartphone/Tablet", 0.75, "hostname indicates mobile device"),
        (r"laptop|desktop|pc|macbook|thinkpad", "Laptop/Desktop", 0.75, "hostname indicates computer"),
        (r"tv|smarttv|roku|chromecast", "Smart TV", 0.75, "hostname indicates smart TV"),
        (r"printer|print", "Network Printer", 0.8, "hostname indicates printer"),
        (r"nas|server|pi-hole|pihole", "Server/NAS", 0.7, "hostname indicates server/NAS"),
        (r"iot|sensor|camera|thermostat|bulb|plug", "IoT/Smart Home", 0.7, "hostname indicates IoT device"),
    ]
    for pat, c, score, reason in rules:
        if re.search(pat, t):
            cat = c
            conf = score
            reasons.append(reason)
            break
    if cat == "Unknown":
        reasons.append("Insufficient evidence; classified as Unknown")
    return {"category": cat, "confidence": conf, "reasons": reasons, "vendor_identified": bool(data.get("vendor"))}