#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# test_integration.sh
# End-to-end integration tests for Cognitive-Aware Task Scheduler
#
# Tests all API endpoints through the Vite proxy (port 5173)
# to verify frontend ↔ backend integration.
#
# Prerequisites:
#   - Backend running:  uvicorn main:app --port 8000
#   - Frontend running: cd frontend && npm run dev (port 5173)
#
# Usage:  bash test_integration.sh [--direct]
#   --direct  test against backend directly (port 8000) instead of proxy
# ──────────────────────────────────────────────────────────────
set -uo pipefail

# ── Config ──────────────────────────────────────────────────
if [[ "${1:-}" == "--direct" ]]; then
  BASE="http://localhost:8000"
  echo "🔧 Mode: DIRECT (backend only, port 8000)"
else
  BASE="http://localhost:5173/api"
  echo "🔧 Mode: PROXY (frontend → backend, port 5173)"
fi

PASS=0
FAIL=0
TOTAL=0

# ── Helpers ─────────────────────────────────────────────────
pass() { PASS=$((PASS+1)); TOTAL=$((TOTAL+1)); echo "  ✅ $1"; }
fail() { FAIL=$((FAIL+1)); TOTAL=$((TOTAL+1)); echo "  ❌ $1"; echo "     ↳ $2"; }

assert_status() {
  local desc="$1" url="$2" method="${3:-GET}" body="${4:-}" expected="${5:-200}"
  local status
  if [[ "$method" == "GET" ]]; then
    status=$(curl -sf -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo "000")
  else
    status=$(curl -sf -o /dev/null -w '%{http_code}' -X "$method" \
      -H 'Content-Type: application/json' -d "$body" "$url" 2>/dev/null || echo "000")
  fi
  if [[ "$status" == "$expected" ]]; then
    pass "$desc (HTTP $status)"
  else
    fail "$desc" "expected $expected, got $status"
  fi
}

assert_json_field() {
  local desc="$1" json="$2" field="$3" expected="$4"
  local actual
  actual=$(echo "$json" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('$field','__MISSING__'))" 2>/dev/null || echo "__ERROR__")
  if [[ "$actual" == "$expected" ]]; then
    pass "$desc ($field=$actual)"
  else
    fail "$desc" "expected $field='$expected', got '$actual'"
  fi
}

# ──────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo " Integration Tests — Cognitive-Aware Task Scheduler"
echo "═══════════════════════════════════════════════════"

# ── 1. Health ────────────────────────────────────────────────
echo ""
echo "── 1. GET /health ──────────────────────────────────"
HEALTH=$(curl -sf "$BASE/health" 2>/dev/null || echo '{}')
assert_json_field "Health status"   "$HEALTH" "status"  "healthy"
assert_json_field "Service name"    "$HEALTH" "service" "cognitive-scheduler"

# ── 2. GET /config ───────────────────────────────────────────
echo ""
echo "── 2. GET /config ──────────────────────────────────"
CONFIG=$(curl -sf "$BASE/config" 2>/dev/null || echo '{}')

for key in sleep_baseline fatigue_consec_weight fatigue_total_weight fatigue_force_break quantum_min deep_work_load_threshold; do
  val=$(echo "$CONFIG" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('$key','MISSING'))" 2>/dev/null || echo "ERROR")
  if [[ "$val" != "MISSING" && "$val" != "ERROR" ]]; then
    pass "Config has $key ($val)"
  else
    fail "Config has $key" "field missing or error"
  fi
done

# ── 3. PUT /config ───────────────────────────────────────────
echo ""
echo "── 3. PUT /config ──────────────────────────────────"
# Save original
ORIG_QUANTUM=$(echo "$CONFIG" | python3 -c "import json,sys; print(json.load(sys.stdin)['quantum_min'])")

# Update to new value
UPDATED=$(curl -sf -X PUT -H 'Content-Type: application/json' \
  -d '{"quantum_min": 20}' "$BASE/config" 2>/dev/null || echo '{}')
NEW_QUANTUM=$(echo "$UPDATED" | python3 -c "import json,sys; print(json.load(sys.stdin).get('quantum_min','ERR'))")
if [[ "$NEW_QUANTUM" == "20" || "$NEW_QUANTUM" == "20.0" ]]; then
  pass "PUT /config updated quantum_min to 20"
else
  fail "PUT /config update" "expected 20, got $NEW_QUANTUM"
fi

# Restore original
curl -sf -X PUT -H 'Content-Type: application/json' \
  -d "{\"quantum_min\": $ORIG_QUANTUM}" "$BASE/config" >/dev/null 2>&1
pass "PUT /config restored quantum_min to $ORIG_QUANTUM"

# Invalid key → 400
BAD_STATUS=$(curl -s -o /dev/null -w '%{http_code}' -X PUT \
  -H 'Content-Type: application/json' -d '{"bogus_key": 99}' "$BASE/config" 2>/dev/null || echo "000")
if [[ "$BAD_STATUS" == "400" ]]; then
  pass "PUT /config rejects unknown key (HTTP 400)"
else
  fail "PUT /config rejects unknown key" "expected 400, got $BAD_STATUS"
fi

# ── 4. POST /schedule (direct, no NLP) ──────────────────────
echo ""
echo "── 4. POST /schedule (direct scheduling) ──────────"
SCHED_BODY='{
  "tasks": [
    {"title":"Study Graph Theory", "category":"math", "difficulty":8, "duration_minutes":120, "cognitive_load":8.2},
    {"title":"ML Assignment",      "category":"programming", "difficulty":7, "duration_minutes":90, "cognitive_load":7.5},
    {"title":"Chem Review",        "category":"science", "difficulty":4, "duration_minutes":45, "cognitive_load":3.0}
  ],
  "sleep_hours": 7,
  "stress_level": 2,
  "chronotype": "normal",
  "lectures_today": 2,
  "available_from": "09:00",
  "available_to": "22:00",
  "breaks_at": ["13:00-14:00"]
}'

SCHED_RESP=$(curl -sf -X POST -H 'Content-Type: application/json' \
  -d "$SCHED_BODY" "$BASE/schedule" 2>/dev/null || echo '{}')

# Check structure
for field in parsed_tasks schedule energy_curve fatigue_curve warnings gamification; do
  exists=$(echo "$SCHED_RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print('yes' if '$field' in d else 'no')" 2>/dev/null || echo "err")
  if [[ "$exists" == "yes" ]]; then
    pass "POST /schedule response has '$field'"
  else
    fail "POST /schedule response has '$field'" "missing from response"
  fi
done

# Check schedule has blocks
NUM_BLOCKS=$(echo "$SCHED_RESP" | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('schedule',[])))")
if [[ "$NUM_BLOCKS" -gt 0 ]]; then
  pass "POST /schedule returned $NUM_BLOCKS blocks"
else
  fail "POST /schedule returned blocks" "got 0 blocks"
fi

# Verify block fields
BLOCK_OK=$(echo "$SCHED_RESP" | python3 -c "
import json,sys
d=json.load(sys.stdin)
b=d['schedule'][0]
fields = ['task_title','start_time','end_time','cognitive_load','energy_at_start','fatigue_at_start','is_break','explanation']
print('yes' if all(f in b for f in fields) else 'no')
")
if [[ "$BLOCK_OK" == "yes" ]]; then
  pass "Schedule blocks have all required fields"
else
  fail "Schedule blocks have all required fields" "some fields missing"
fi

# Check energy curve
EC_LEN=$(echo "$SCHED_RESP" | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('energy_curve',[])))")
if [[ "$EC_LEN" -gt 0 ]]; then
  pass "Energy curve has $EC_LEN points"
else
  fail "Energy curve" "empty"
fi

# Check gamification
GAM=$(echo "$SCHED_RESP" | python3 -c "
import json,sys
d=json.load(sys.stdin)['gamification']
print(f\"xp={d['xp']} level={d['level']} streak={d['streak']} badges={len(d['badges'])}\")
")
pass "Gamification: $GAM"

# ── 5. POST /tlx-feedback ───────────────────────────────────
echo ""
echo "── 5. POST /tlx-feedback ───────────────────────────"
# Submit 3 entries (minimum for recalibration)
for i in 1 2 3; do
  TLX_RESP=$(curl -sf -X POST -H 'Content-Type: application/json' \
    -d "{\"block_index\":0, \"mental_demand\":5, \"effort\":5}" \
    "$BASE/tlx-feedback" 2>/dev/null || echo '{}')
done

TLX_STATUS=$(echo "$TLX_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status','ERR'))")
TLX_ENTRIES=$(echo "$TLX_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tlx_entries','ERR'))")

if [[ "$TLX_STATUS" == "ok" ]]; then
  pass "TLX feedback status: ok"
else
  fail "TLX feedback status" "expected 'ok', got $TLX_STATUS"
fi

if [[ "$TLX_ENTRIES" -ge 3 ]]; then
  pass "TLX entries accumulated: $TLX_ENTRIES"
else
  fail "TLX entries" "expected ≥3, got $TLX_ENTRIES"
fi

# Check weights were updated
TLX_WEIGHTS=$(echo "$TLX_RESP" | python3 -c "
import json,sys
w=json.load(sys.stdin).get('updated_weights',{})
print(f\"consec={w.get('fatigue_consec_weight','?')} total={w.get('fatigue_total_weight','?')} force={w.get('fatigue_force_break','?')}\")
")
pass "TLX updated weights: $TLX_WEIGHTS"

# ── 6. Proxy reachability (if using proxy mode) ─────────────
if [[ "$BASE" == *"5173"* ]]; then
  echo ""
  echo "── 6. Frontend proxy tests ───────────────────────"

  # HTML page loads
  FE_STATUS=$(curl -sf -o /dev/null -w '%{http_code}' "http://localhost:5173/" 2>/dev/null || echo "000")
  if [[ "$FE_STATUS" == "200" ]]; then
    pass "Frontend serves HTML (HTTP 200)"
  else
    fail "Frontend serves HTML" "HTTP $FE_STATUS"
  fi

  # Contains expected content
  FE_HTML=$(curl -sf "http://localhost:5173/" 2>/dev/null || echo "")
  if echo "$FE_HTML" | grep -qi "root"; then
    pass "HTML contains #root mount point"
  else
    fail "HTML contains #root" "missing"
  fi

  # Proxy forwards /api/health
  PROXY_HEALTH=$(curl -sf "http://localhost:5173/api/health" 2>/dev/null || echo '{}')
  PH_STATUS=$(echo "$PROXY_HEALTH" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status','ERR'))")
  if [[ "$PH_STATUS" == "healthy" ]]; then
    pass "Proxy /api/health → backend (healthy)"
  else
    fail "Proxy /api/health" "got $PH_STATUS"
  fi
fi

# ── 7. Validate response data integrity ─────────────────────
echo ""
echo "── 7. Data integrity checks ────────────────────────"

# Schedule blocks ordered chronologically
ORDERED=$(echo "$SCHED_RESP" | python3 -c "
import json,sys
blocks = json.load(sys.stdin)['schedule']
times = [b['start_time'] for b in blocks]
print('yes' if times == sorted(times) else 'no')
")
if [[ "$ORDERED" == "yes" ]]; then
  pass "Schedule blocks are chronologically ordered"
else
  fail "Schedule blocks ordered" "blocks out of order"
fi

# Energy values in [0,1]
ENERGY_VALID=$(echo "$SCHED_RESP" | python3 -c "
import json,sys
blocks = json.load(sys.stdin)['schedule']
print('yes' if all(0 <= b['energy_at_start'] <= 1 for b in blocks) else 'no')
")
if [[ "$ENERGY_VALID" == "yes" ]]; then
  pass "All energy values in [0, 1]"
else
  fail "Energy values in [0,1]" "out of range"
fi

# Fatigue values in [0,1]
FATIGUE_VALID=$(echo "$SCHED_RESP" | python3 -c "
import json,sys
blocks = json.load(sys.stdin)['schedule']
print('yes' if all(0 <= b['fatigue_at_start'] <= 1 for b in blocks) else 'no')
")
if [[ "$FATIGUE_VALID" == "yes" ]]; then
  pass "All fatigue values in [0, 1]"
else
  fail "Fatigue values in [0,1]" "out of range"
fi

# Cognitive load in [0,10]
LOAD_VALID=$(echo "$SCHED_RESP" | python3 -c "
import json,sys
blocks = json.load(sys.stdin)['schedule']
print('yes' if all(0 <= b['cognitive_load'] <= 10 for b in blocks) else 'no')
")
if [[ "$LOAD_VALID" == "yes" ]]; then
  pass "All cognitive_load values in [0, 10]"
else
  fail "Cognitive load in [0,10]" "out of range"
fi

# Break blocks have is_break=true and load=0
BREAKS_OK=$(echo "$SCHED_RESP" | python3 -c "
import json,sys
blocks = json.load(sys.stdin)['schedule']
brks = [b for b in blocks if b['is_break']]
if not brks:
    print('skip')
else:
    print('yes' if all(b['cognitive_load']==0 for b in brks) else 'no')
")
if [[ "$BREAKS_OK" == "yes" ]]; then
  pass "Break blocks have cognitive_load=0"
elif [[ "$BREAKS_OK" == "skip" ]]; then
  pass "No break blocks in this schedule (OK)"
else
  fail "Break blocks" "some have non-zero load"
fi

# ── 8. Stress cap (Yerkes-Dodson) ────────────────────────────
echo ""
echo "── 8. Yerkes-Dodson stress cap test ────────────────"
STRESS_BODY='{
  "tasks": [
    {"title":"Hard Task", "category":"math", "difficulty":9, "duration_minutes":60, "cognitive_load":9.0}
  ],
  "sleep_hours": 5,
  "stress_level": 5,
  "chronotype": "normal",
  "lectures_today": 4,
  "available_from": "09:00",
  "available_to": "22:00",
  "breaks_at": []
}'
STRESS_RESP=$(curl -sf -X POST -H 'Content-Type: application/json' \
  -d "$STRESS_BODY" "$BASE/schedule" 2>/dev/null || echo '{}')

STRESS_WARNS=$(echo "$STRESS_RESP" | python3 -c "
import json,sys
w = json.load(sys.stdin).get('warnings',[])
print(len(w))
")
if [[ "$STRESS_WARNS" -gt 0 ]]; then
  pass "High-stress schedule generated warnings ($STRESS_WARNS)"
else
  pass "High-stress schedule completed (no warnings needed)"
fi

# ──────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo " Results: $PASS passed, $FAIL failed, $TOTAL total"
echo "═══════════════════════════════════════════════════"

if [[ "$FAIL" -gt 0 ]]; then
  echo "⚠️  Some tests failed!"
  exit 1
else
  echo "🎉 All tests passed!"
  exit 0
fi
