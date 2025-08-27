import os, json, subprocess, shutil
from pathlib import Path
from openai import OpenAI

def run(kind: str="node", name: str="ai-app", goal: str="scaffold app", max_loops: int=5) -> dict:
    client = OpenAI()
    work = Path.cwd()/name
    work.mkdir(exist_ok=True)
    loops = []
    err = ""

    for i in range(max_loops):
        prompt = f"""
You are a build agent. Goal: {goal}
Project: {kind}, name: {name}
Last error (if any): {err}
Return a JSON with:
- files: array of {{path, content}}
- commands: array of shell commands to run
"""
        msg = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL","gpt-4o-mini"),
            messages=[{"role":"user","content":prompt}],
            temperature=0.2
        ).choices[0].message.content

        plan = json.loads(msg) if msg.strip().startswith("{") else {}
        # write files
        for f in plan.get("files", []):
            p = work/f["path"]; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f["content"], encoding="utf-8")

        # run commands
        errs=[]
        for c in plan.get("commands", []):
            out = subprocess.run(c, cwd=work, shell=True, capture_output=True, text=True)
            if out.returncode != 0:
                errs.append({"cmd": c, "stderr": out.stderr[-4000:], "stdout": out.stdout[-1000:]})
        if not errs:
            return {"ok": True, "path": str(work), "loops": i+1}

        err = " ; ".join([e["stderr"] for e in errs])[:8000]
        loops.append({"i":i+1, "errors": errs})
    return {"ok": False, "path": str(work), "loops": loops, "reason":"max_loops"}
