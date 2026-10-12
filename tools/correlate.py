import hashlib
from dataclasses import dataclass
from typing import Optional

DEPS = {"checkout": ["payments-api", "cart"], "payments-api": ["payments-db"]}  # CMDB

@dataclass
class Alert:
    name: str; service: str; env: str; ts: float; deploy_id: Optional[str] = None

def fingerprint(a: Alert) -> str:                       # etapa 4: deduplicacion
    return hashlib.sha1(f"{a.name}|{a.service}|{a.env}".encode()).hexdigest()[:12]

def dedup(alerts, window=300):
    seen, out = {}, []
    for a in sorted(alerts, key=lambda x: x.ts):
        fp = fingerprint(a)
        if fp in seen and a.ts - seen[fp] <= window:
            continue                                    # duplicado dentro de la ventana
        seen[fp] = a.ts; out.append(a)
    return out

def downstream(svc, firing):                            # dependencias (transitivas) en falla
    stack, found = list(DEPS.get(svc, [])), set()
    while stack:
        d = stack.pop()
        if d in firing and d not in found:
            found.add(d); stack += DEPS.get(d, [])
    return found

def correlate(alerts, window=600):                      # etapa 5: correlacion
    firing = {a.service for a in alerts}
    incidents = {}
    for a in sorted(alerts, key=lambda x: x.ts):
        causes = downstream(a.service, firing)
        root = a.service if not causes else sorted(causes, key=lambda s: len(downstream(s, firing)))[0]
        key = (a.env, root, a.deploy_id, int(a.ts // window))
        incidents.setdefault(key, []).append(a)
    return incidents                                    # 1 notificacion por incidente

if __name__ == "__main__":
    base = 1_700_000_000
    raw = [Alert("LatencyAnomaly", "payments-db", "prod", base + i*60) for i in range(0, 5)]
    raw += [Alert("LatencyAnomaly", "payments-api", "prod", base + 30 + i*60) for i in range(0, 5)]
    raw += [Alert("LatencyAnomaly", "checkout", "prod", base + 45 + i*60) for i in range(0, 4)]
    raw += [Alert("CPUHigh", "cart", "prod", base + 700)]
    d = dedup(raw); inc = correlate(d)
    print(len(raw), "alertas ->", len(d), "tras dedup ->", len(inc), "incidentes")
    for k, v in inc.items(): print(k[1], len(v))
