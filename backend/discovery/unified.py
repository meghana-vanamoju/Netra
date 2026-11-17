def merge_devices(existing, new):
    # merge by mac or ip, preserve provenance
    out = []
    for d in existing + new:
        match = None
        for o in out:
            if (d.get("mac_address") and d.get("mac_address")==o.get("mac_address")) or (d.get("ip_address") and d.get("ip_address")==o.get("ip_address")):
                match = o
                break
        if match:
            for k,v in d.items():
                if v is not None and match.get(k) is None:
                    match[k] = v
            if d.get("discovery_source") and d["discovery_source"] not in match.get("sources",[]):
                match.setdefault("sources",[]).append(d["discovery_source"])
        else:
            d = dict(d)
            d["sources"] = [d.get("discovery_source")] if d.get("discovery_source") else []
            out.append(d)
    return out