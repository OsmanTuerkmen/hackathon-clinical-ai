# hackathon-clinical-ai
Hackathon Clinical AI

## Track 3 – European Health Data Space: Doccess

**Doccess** (Doctor/Document + Access) is a health data access desk for EHDS secondary use. It is a hackathon
simulation on synthetic data, with a simulated ID Austria sign-in, and not a real approval system. See
[track3-ehds/README.md](track3-ehds/README.md) for the architecture, metrics and demo script.

```bash
cd track3-ehds
python3 -m desk            # http://127.0.0.1:8000
python3 -m desk evaluate   # 10/10 decisions, 6/6 numbers, 0 leaks, 10/10 consistent
```
