"""Z-Grid generator (Design B, mutation-pair variant).
Deterministic oracle answers + Z-typed mutated candidate answers, T assigned
by exact comparison — no model calls. Manifest hashed BEFORE any evaluation.
Domains: D1 quantity problems (number+unit), D2 string transforms (exact
string), D3 counting over intervals (integer).
Z classes: z1 boundary/off-by-one, z2 unit/scale, z3 negation/complement.
Doses: 1 (subtle/auxiliary), 2 (primary quantity), 3 (primary+secondary)."""
import json, hashlib, random, os
from pathlib import Path

OUT = Path("/home/Drew/selfcorr-benchmarks/zgrid")
SEED = 20261121
N_PER_DOMAIN = 24

rng = random.Random(SEED)

def h(s): return hashlib.sha256(json.dumps(s, sort_keys=True).encode()).hexdigest()[:16]

# ── D1: rate problems with unit conversion ─────────────────────────────
def d1_items():
    items = []
    for i in range(N_PER_DOMAIN):
        speed = rng.randint(20, 120)                     # km/h
        hours = rng.choice([2, 2.5, 3, 3.5, 4, 5])
        dist = speed * hours                             # km
        prose = (f"A vehicle travels at a constant {speed} km/h for {hours} hours. "
                 f"How many km does it travel in total? Answer with a number and unit.")
        ans = f"{dist:g} km"
        muts = {
            ("z1", 1): f"{dist + hours:g} km",                       # + per-hour creep
            ("z1", 2): f"{dist + speed:g} km",                       # off-by main quantity
            ("z1", 3): f"{dist + speed + hours:g} km",
            ("z2", 1): f"{dist:g} m",                                # wrong unit, same number
            ("z2", 2): f"{dist * 1000:g} m",                         # right conversion of wrong reading
            ("z2", 3): f"{dist * 10:g} km",                          # scale ×10
            ("z3", 1): f"-{dist:g} km",
            ("z3", 2): f"{speed:g} km",                              # rate returned, not distance
            ("z3", 3): f"{dist / hours:g} km",                       # inverse quantity
        }
        items.append({"domain": "D1", "idx": i, "prose": prose, "oracle": ans, "mutations": muts})
    return items

# ── D2: string transformations ─────────────────────────────────────────
def d2_items():
    items = []
    words_bank = ["alpha", "Beta", "GAMMA", "delta", "Epsilon", "zeta", "Omega", "kappa",
                  "Sigma", "tau", "Rho", "lambda", "Chi", "psi", "phi", "mu",
                  "nu", "xi", "omicron", "upsilon", "theta", "iota", "eta", "zeta"]
    for i in range(N_PER_DOMAIN):
        k = rng.randint(3, 5)
        words = rng.sample(words_bank, k)
        sep = rng.choice(["-", "_", ""])
        target = sep.join(w.lower() for w in words)
        prose = (f"Convert the words {', '.join(words)} into a single identifier: "
                 f"all lowercase, joined with '{sep if sep else 'nothing'}'. "
                 f"Answer with the exact resulting string only.")
        ans = target
        muts = {
            ("z1", 1): sep.join(w.lower() for w in words[:-1]),      # dropped last word
            ("z1", 2): target + sep,                                  # trailing separator
            ("z1", 3): sep.join(w.lower() for w in words) + "s",      # suffix creep
            ("z2", 1): target.upper(),                                # case scale wrong
            ("z2", 2): "-".join(w.lower() for w in words) if sep != "-" else "_".join(w.lower() for w in words),
            ("z2", 3): "".join(w.lower() for w in words) if sep else "_".join(w.lower() for w in words),
            ("z3", 1): sep.join(w.lower() for w in reversed(words)),  # order negated
            ("z3", 2): sep.join(w.capitalize() for w in words),       # rule negated (not lowercase)
            ("z3", 3): sep.join(w.lower() for w in sorted(words)),    # sort imposed (scope)
        }
        items.append({"domain": "D2", "idx": i, "prose": prose, "oracle": ans, "mutations": muts})
    return items

# ── D3: counting over half-open intervals ──────────────────────────────
def d3_items():
    items = []
    for i in range(N_PER_DOMAIN):
        a = rng.randint(10, 200); b = a + rng.randint(20, 120)
        m = rng.choice([3, 4, 5, 6, 7])
        total = sum(1 for x in range(a, b) if x % m == 0)
        prose = (f"How many integers x satisfy {a} <= x < {b} and x is divisible by {m}? "
                 f"Answer with an integer only.")
        ans = str(total)
        span = b - a
        muts = {
            ("z1", 1): str(total + 1),                                # boundary included
            ("z1", 2): str(total - 1),
            ("z1", 3): str(total + (2 if total > 2 else -2)),
            ("z2", 1): str(total * 10),
            ("z2", 2): str(round(total * m)),
            ("z2", 3): str(span),                                     # scale to span count
            ("z3", 1): str(span - total),                             # complement
            ("z3", 2): str(m),                                        # the modulus returned
            ("z3", 3): str(b),                                        # interval endpoint returned
        }
        items.append({"domain": "D3", "idx": i, "prose": prose, "oracle": ans, "mutations": muts})
    return items

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    items = d1_items() + d2_items() + d3_items()
    # build candidates, verify T by exact comparison
    grid = []
    dropped = 0
    for it in items:
        cands = [{"z": "clean", "dose": 0, "answer": it["oracle"], "T": 1}]
        for (z, dose), mut in it["mutations"].items():
            T = 1 if mut == it["oracle"] else 0        # exact-match ground truth
            if T == 1: dropped += 1; continue          # mutation collided with truth: invalid
            cands.append({"z": z, "dose": dose, "answer": mut, "T": 0})
        for c in cands:
            c["item_id"] = f"{it['domain']}{it['idx']:02d}"
            c["prose"] = it["prose"]
            c["oracle"] = it["oracle"]
            c["sha"] = h(c)
            grid.append(c)
    rng2 = random.Random(SEED + 1)
    # calibration/test split by ITEM (20% items calib)
    item_ids = sorted({c["item_id"] for c in grid})
    rng2.shuffle(item_ids)
    ncal = max(1, len(item_ids) // 5)
    calib = set(item_ids[:ncal])
    for c in grid:
        c["split"] = "calib" if c["item_id"] in calib else "test"
    json.dump({"seed": SEED, "n_items": len(items), "n_candidates": len(grid),
               "n_calib_items": len(calib), "dropped_collisions": dropped},
              open(OUT / "meta.json", "w"), indent=1)
    with open(OUT / "grid.jsonl", "w") as f:
        for c in grid: f.write(json.dumps(c) + "\n")
    manifest = hashlib.sha256(open(OUT / "grid.jsonl", "rb").read()).hexdigest()
    open(OUT / "manifest.sha256", "w").write(manifest + "\n")
    # T-balance per z/dose
    from collections import Counter
    tz = Counter((c["z"], c["dose"], c["T"]) for c in grid)
    print(f"items: {len(items)} candidates: {len(grid)} dropped-collisions: {dropped}")
    print(f"T=0 (incorrect): {sum(1 for c in grid if c['T']==0)} | T=1: {sum(1 for c in grid if c['T']==1)}")
    print("manifest:", manifest[:16])
    for z in ("z1", "z2", "z3"):
        counts = [tz[(z, d, 0)] for d in (1, 2, 3)]
        print(f"  {z} mutants by dose: {counts}")

if __name__ == "__main__":
    main()
