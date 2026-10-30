"""Stand-in OpenAI-compatible server for testing the AI path without a GPU. It is NOT a model: it answers with
simple keyword logic so the connector, datamarking, schema handling and quote verification can be exercised.

Run:  .venv/bin/python scripts/fake_llm.py   (serves http://127.0.0.1:8099/v1)
Then: EHDS_LLM_BASE_URL=http://127.0.0.1:8099/v1 EHDS_LLM_MODEL=fake ...
"""
import json
import re
import time

import uvicorn
from fastapi import FastAPI

app = FastAPI()
RULES = [("insurance_exclusion_or_premiums", "premium"), ("advertising_or_marketing", "advertis"), ("decisions_detrimental_to_persons", "employee"),
         ("harmful_products", "nicotine"), ("harmful_products", "alcohol"), ("advertising_or_marketing", "sales force"), ("ethics_violation", "resell"),
         ("decisions_detrimental_to_persons", "credit scor")]


@app.post("/v1/chat/completions")
def chat(body: dict):
    system, user = body["messages"][0]["content"], body["messages"][1]["content"]
    marker = re.search(r"marker '([^']+)'", system).group(1)
    data = json.loads(user.split("<request>", 1)[1].rsplit("</request>", 1)[0])
    text = {k: v.replace(marker, " ") if isinstance(v, str) else v for k, v in data.items()}
    purpose = text.get("purpose", "")
    kind = body["response_format"]["json_schema"]["name"]
    hit = next(((c, w) for c, w in RULES if w in purpose.lower()), None)
    quote = ""
    if hit:
        i = purpose.lower().index(hit[1])
        quote = purpose[max(0, i - 20): i + 25]
    if kind == "classifier":
        allowed = "algorithm_training_and_testing" if "model" in purpose.lower() else "scientific_research"
        out = {"rationale": "keyword stand-in", "evidence_quote": quote, "prohibited_category": hit[0] if hit else "none",
               "allowed_purpose": "none" if hit else allowed}
    elif kind == "redteam":
        out = {"who_could_be_harmed": "customers" if hit else "nobody identified", "commercial_interest": "yes" if hit else "none",
               "evidence_quote": quote, "prohibited_category": hit[0] if hit else "none"}
    else:
        m = re.search(r"aggregates are not enough|individual-level histories", purpose, re.I)
        out = {"rationale": "keyword stand-in", "evidence_quote": m.group(0) if m else "", "statistics_insufficient_explained": bool(m)}
    return {"id": "fake", "object": "chat.completion", "created": int(time.time()), "model": body.get("model"),
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(out)}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8099, log_level="warning")
