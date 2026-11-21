"""Z-Grid evaluator runner (Design B phase 2 — models judge frozen candidates).
Arms: SELF (same model as... candidates are oracle/mutator-built, so SELF =
each model judges in plain mode), RECOMP (solve-then-judge), and CROSS is
implicit (every model judges every candidate; cross-vs-self contrast comes
from Z_bad defined per family on the calibration split — here 'family' =
model, since candidates are model-independent).
Simplification for v1 (oracle-free arm mapping): two instructions per model:
PLAIN and RECOMP, R=2 replicates each, over all candidates.
4 models x 708 candidates x 2 arms x 2 reps = 11,328 calls."""
import json, hashlib, time, sys, re, os
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading

OUT = Path("/home/Drew/selfcorr-benchmarks/zgrid")
KEY = open("/home/Drew/.keys/openrouter").read().strip()
API = "https://openrouter.ai/api/v1/chat/completions"
MODELS = {
    "sol":  "openai/gpt-6.2-sol",
    "qwen": "qwen/qwen3.8-flash",
    "glm":  "z-ai/glm-5.3-flash",
    "ds":   "deepseek/deepseek-v4.1-flash",
}
CONC = 12

def plain_prompt(prose, answer):
    return (f"[QUESTION]\n{prose}\n\n[PROPOSED ANSWER]\n{answer}\n\n"
            "Decide whether the proposed answer is correct for the question exactly as stated "
            "(correct value, correct format, correct units where applicable). Do not restate or solve it; judge only.\n"
            "End with exactly one final line containing only one of:\n"
            "VERDICT: ACCEPT\nVERDICT: REJECT")

def recomp_prompt(prose, answer):
    return (f"[QUESTION]\n{prose}\n\n"
            "First solve the question yourself, showing your working briefly. "
            f"Then compare your result with this proposed answer: {answer}\n"
            "Decide whether the proposed answer is correct exactly as stated.\n"
            "End with exactly one final line containing only one of:\n"
            "VERDICT: ACCEPT\nVERDICT: REJECT")

VERDICT_RX = re.compile(r"VERDICT:\s*(ACCEPT|REJECT)\s*$", re.M)

def strict_verdict(text):
    if not text: return None
    ms = VERDICT_RX.findall(text)
    return ms[-1] if ms else None

def call(model, prompt):
    for attempt in range(3):
        try:
            body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                               "temperature": 0}).encode()
            req = urllib.request.Request(API, data=body, headers={
                "Authorization": "Bearer " + KEY, "Content-Type": "application/json",
                "HTTP-Referer": "https://ad-research.org", "X-Title": "zgrid"})
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=600) as r:
                d = json.loads(r.read())
            return d, time.time() - t0
        except Exception as e:
            if attempt == 2: raise
            time.sleep(20 if "Name or service" in str(e) else 5)

def main():
    grid = [json.loads(l) for l in open(OUT / "grid.jsonl")]
    ev_path = OUT / "eval_events.jsonl"
    done = set()
    if ev_path.exists():
        for l in open(ev_path):
            try:
                d = json.loads(l)
                if not d.get("error") and d.get("verdict"): done.add(d["event_key"])
            except Exception: pass

    work = []
    for mk, mid in MODELS.items():
        for c in grid:
            for arm, pfn in (("plain", plain_prompt), ("recomp", recomp_prompt)):
                for rep in (1, 2):
                    key = f"{mk}|{c['item_id']}|{c['z']}|{c['dose']}|{arm}|{rep}"
                    work.append((key, mk, mid, c, arm, pfn, rep))
    todo = [w for w in work if w[0] not in done]
    print(f"work: {len(work)} | done: {len(done)} | todo: {len(todo)}", flush=True)

    lock = threading.Lock()
    fh = open(ev_path, "a")
    ri = [len(done)]
    t0 = time.time()

    def one(w):
        key, mk, mid, c, arm, pfn, rep = w
        prompt = pfn(c["prose"], c["answer"])
        with lock:
            i = ri[0]; ri[0] += 1
        ev = {"event_key": key, "request_index": i, "model_key": mk, "model": mid,
              "item_id": c["item_id"], "z": c["z"], "dose": c["dose"], "T": c["T"],
              "arm": arm, "replicate": rep, "split": c["split"],
              "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
              "enqueue_ts": time.time()}
        try:
            d, dur = call(mid, prompt)
            ch = d["choices"][0]; u = d.get("usage") or {}
            ev.update({"response_ts": time.time(), "duration_s": round(dur, 3),
                       "response_model": d.get("model"), "finish_reason": ch.get("finish_reason"),
                       "prompt_tokens": u.get("prompt_tokens"),
                       "completion_tokens": u.get("completion_tokens"),
                       "raw_response": (ch.get("message") or {}).get("content"),
                       "verdict": strict_verdict((ch.get("message") or {}).get("content"))})
        except Exception as e:
            ev.update({"error": f"{type(e).__name__}: {e}"[:300], "response_ts": time.time()})
        with lock:
            fh.write(json.dumps(ev) + "\n"); fh.flush()

    with ThreadPoolExecutor(max_workers=CONC) as ex:
        futs = [ex.submit(one, w) for w in todo]
        for n, f in enumerate(futs):
            f.result()
            if n % 200 == 0:
                print(f"{n}/{len(todo)} | {time.time()-t0:.0f}s", flush=True)
    fh.close()
    print("ZGRID EVAL COMPLETE", flush=True)

if __name__ == "__main__":
    main()
