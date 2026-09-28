"""No-model routing baseline: keyword rules over title+description only."""
import json, re, sys
PLAN = re.compile(r"\b(decide|decision|undecided|open question|design (?:a|the)|proposal|rfc|sequenc|ownership|which (?:repo|owner)|tbd|options?:)\b", re.I)
HARD = re.compile(r"\b(migrat|authority|protocol|lifecycle|parity|state[- ]machine|lease|compare-and-swap|cas\b|idempot|concurren|reconcil|backend)\w*", re.I)
STANDARD = re.compile(r"\b(investigat|diagnos|root cause|flaky|intermittent|unclear|figure out|find where)\w*", re.I)
REVIEW = re.compile(r"\b(credential|secret|token|auth|prod(?:uction)?|cluster|delete|irreversib|openbao|kubernetes)\w*", re.I)
def label(text):
    if PLAN.search(text): return "needs_planning"
    if HARD.search(text): return "hard"
    if STANDARD.search(text): return "standard"
    return "bounded"
for line in open(sys.argv[1]):
    r = json.loads(line); t = f"{r['title']}\n{r['description']}"
    print(json.dumps({"item_id": r["item_id"], "tier": label(t), "operator_review_warranted": bool(REVIEW.search(t))}))
