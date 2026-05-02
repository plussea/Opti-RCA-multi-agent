# -*- coding: utf-8 -*-
"""End-to-end DB verification using curl/docker — no psycopg2 needed."""
import json, subprocess, time, sys

CSV = "E:/Opti-RCA-multi-agent/input/data/alarm_datasets/alarm_ep1_step1.csv"
API = "http://localhost"

def cmd(c):
    r = subprocess.run(c, shell=True, capture_output=True)
    out = r.stdout.decode("utf-8", errors="replace") + r.stderr.decode("utf-8", errors="replace")
    return out.strip()

def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")

def row(label, val):
    print(f"  {label:<35} {val}")

def docker_exec(container, sql):
    c = f'docker exec {container} psql -U postgres -d omniops -c "{sql}"'
    return cmd(c)

def redis(redis_cmd):
    c = f'docker exec opti-rca-multi-agent-redis-1 redis-cli {redis_cmd}'
    return cmd(c)

# ── Step 0: health
section("STEP 0 - Service Health")
health = json.loads(cmd('curl -s http://localhost/v1/health'))
row("status", health["status"])
for k,v in health["components"].items():
    row(k, v)

# ── Step 1: upload CSV
section("STEP 1 - Upload CSV, Create Session")
out = cmd(f'curl -s -X POST http://localhost/v1/sessions -F "file=@{CSV}"')
session = json.loads(out)
sid = session["session_id"]
row("session_id", sid)
row("status", session["status"])
time.sleep(3)

# ── Step 2: check Redis state
section("STEP 2 - Redis State")
status = redis(f"HGET session:{sid} status").strip()
step = redis(f"HGET session:{sid} current_step").strip()
diag_raw = redis(f"HGET session:{sid} diagnosis_result").strip()
row("status", status)
row("current_step", step)
if diag_raw:
    try:
        d = json.loads(diag_raw)
        row("root_cause", d.get("root_cause","-"))
        row("confidence", d.get("confidence","-"))
    except:
        row("diagnosis_result", "decode error")

# ── Step 3: PostgreSQL sessions
section("STEP 3 - PostgreSQL sessions")
sql = f"SELECT session_id, status, perception_metadata->>'alarm_count' as alarms, perception_metadata->>'topology_id' as topo, perception_metadata->>'ne_count' as nes, diagnosis_result->>'root_cause' as root_cause FROM sessions WHERE session_id='{sid}';"
out = docker_exec("opti-rca-multi-agent-postgres-1", sql)
print(out[:600])

# ── Step 4: PostgreSQL alarm_records
section("STEP 4 - PostgreSQL alarm_records")
sql = f"SELECT ne_name, alarm_name, severity, topology_id, location FROM alarm_records WHERE session_id='{sid}' ORDER BY ne_name;"
out = docker_exec("opti-rca-multi-agent-postgres-1", sql)
print(out[:800])

# ── Step 5: agent_conversations
section("STEP 5 - PostgreSQL agent_conversations")
sql = f"SELECT agent_name, step_order, duration_ms, error_message FROM agent_conversations WHERE session_id='{sid}' ORDER BY step_order;"
out = docker_exec("opti-rca-multi-agent-postgres-1", sql)
print(out[:600] or "  (no rows)")

# ── Step 6: RabbitMQ
section("STEP 6 - RabbitMQ Queues")
out = cmd('curl -s -u omniops:omniops123 http://localhost:15672/api/queues -p omniops')
try:
    qs = json.loads(out)
    for q in qs:
        print(f"  {q['name']:<30} messages={q['messages']:>5}  state={q.get('state','?')}")
except:
    print(f"  RabbitMQ API: {out[:200]}")

# ── Step 7: Neo4j
section("STEP 7 - Neo4j")
out = cmd('curl -s -u "neo4j:password" http://localhost:7474/db/neo4j/tx/commit -H "Content-Type: application/json" -d \'{"statements":[{"statement":"RETURN 1 as n"}]}\'')
try:
    d = json.loads(out)
    if d.get("errors") == []:
        row("Neo4j", "connected OK")
except:
    row("Neo4j", "connection failed")

# ── Step 8: All Redis keys
section("STEP 8 - Redis Session Keys")
keys = redis("--scan --pattern 'session:*'").strip().split("\n")
keys = [k for k in keys if k]
for k in keys[-10:]:
    st = redis(f"HGET {k} status").strip()
    print(f"  {k} -> {st}")

# ── Summary
section("FINAL SUMMARY")
out = cmd(f'curl -s http://localhost/v1/sessions/{sid}/result')
result = json.loads(out)
diag = result.get("diagnosis") or {}
print(f"  root_cause:      {diag.get('root_cause','-')}")
print(f"  confidence:     {diag.get('confidence','-')}")
imp = result.get("impact") or {}
print(f"  affected_ne:    {imp.get('affected_ne',[])}")
print(f"  affected_links: {imp.get('affected_links',[])}")
print(f"  affected_svc:   {imp.get('affected_services',[])}")
sug = result.get("suggestion") or {}
print(f"  risk_level:     {sug.get('risk_level','-')}")
print(f"  needs_approval: {sug.get('needs_approval','-')}")
for a in sug.get("suggested_actions",[]):
    print(f"  Step {a['step']}: {a['action']}")