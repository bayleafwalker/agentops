import hashlib
import os

import restate


claim = restate.VirtualObject("WorkItemClaim")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def read_claim(ctx: restate.ObjectContext) -> dict | None:
    return await ctx.get("claim", type_hint=dict)


def public(state: dict) -> dict:
    return {
        "owner": state["owner"],
        "revision": state["revision"],
        "proof_digest": state["proof_digest"],
    }


def checked_proof(state: dict | None, proof: str) -> dict | None:
    if state is None or digest(proof) != state["proof_digest"]:
        return None
    return state


@claim.handler("acquire")
async def acquire(ctx: restate.ObjectContext, request: dict) -> dict:
    state = await read_claim(ctx)
    if state is not None:
        return {"accepted": False, "reason": "already-held"}
    proof = str(ctx.uuid())
    state = {"owner": request["owner"], "proof_digest": digest(proof), "revision": 1}
    ctx.set("claim", state)
    return {"accepted": True, **public(state), "proof": proof}


@claim.handler("mutate")
async def mutate(ctx: restate.ObjectContext, request: dict) -> dict:
    state = checked_proof(await read_claim(ctx), request.get("proof", ""))
    if state is None:
        return {"accepted": False, "reason": "proof-rejected"}
    state["revision"] += 1
    ctx.set("claim", state)
    return {"accepted": True, **public(state)}


@claim.handler("transfer")
async def transfer(ctx: restate.ObjectContext, request: dict) -> dict:
    state = checked_proof(await read_claim(ctx), request.get("proof", ""))
    if state is None:
        return {"accepted": False, "reason": "proof-rejected"}
    proof = str(ctx.uuid())
    state = {
        "owner": request["new_owner"],
        "proof_digest": digest(proof),
        "revision": state["revision"] + 1,
    }
    ctx.set("claim", state)
    return {"accepted": True, **public(state), "proof": proof}


@claim.handler("recover")
async def recover(ctx: restate.ObjectContext, request: dict) -> dict:
    if request.get("recovery_key") != os.environ["RECOVERY_KEY"]:
        return {"accepted": False, "reason": "recovery-authority-rejected"}
    state = await read_claim(ctx)
    if state is None:
        return {"accepted": False, "reason": "not-held"}
    proof = str(ctx.uuid())
    state = {
        "owner": request["new_owner"],
        "proof_digest": digest(proof),
        "revision": state["revision"] + 1,
    }
    ctx.set("claim", state)
    return {"accepted": True, **public(state), "proof": proof}


@claim.handler("inspect", kind="shared")
async def inspect_claim(ctx: restate.ObjectContext) -> dict | None:
    state = await read_claim(ctx)
    return None if state is None else public(state)


app = restate.app([claim])
