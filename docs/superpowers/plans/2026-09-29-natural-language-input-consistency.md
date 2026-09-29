# Natural Language Input Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every natural-language adjustment update only explicitly requested product fields, reject invalid dates clearly, preserve constraints across turns, and generate candidates from the final state.

**Architecture:** Keep parsing and state merging in `ProductAdvisor`, but separate explicit audience vocabulary from experience-theme vocabulary and validate requested dates before inventory fallback. Return a structured `validation_error` for rejected adjustments, then let the Vue page retain the current primary and show the exact reason through a small tested state helper.

**Tech Stack:** FastAPI, SQLAlchemy, pytest/TestClient, Vue 3, TypeScript, Node built-in test runner, Docker Compose.

## Global Constraints

- Only explicitly mentioned fields may change.
- Past or unavailable dates never silently switch to another date.
- Resource and service names never infer audience or party size.
- Budget and route constraints persist across later turns.
- Candidate generation never publishes a product and must copy the final primary state.

---

### Task 1: Reject Invalid Dates Without Replacing the Current Primary

**Files:**
- Modify: `apps/server/tests/test_final_enhancements.py`
- Modify: `apps/server/app/services/product_advisor_service.py`

**Interfaces:**
- Consumes: `ProductAdvisor.respond(message: str, state: dict) -> dict`
- Produces: `advisor.validation_error = {code, message, requested_value, available_dates}`

- [ ] **Step 1: Write failing API tests**

Add tests that create a conversation, establish a primary, then submit yesterday and `2099-12-30`. Assert the previous `target_date` remains unchanged, `validation_error.code` is respectively `PAST_DATE` and `DATE_UNAVAILABLE`, and at most three available dates are returned. Add a positive test using the first date from `/api/v1/hotel/rooms` and assert the primary uses it.

- [ ] **Step 2: Run tests and verify RED**

Run: `docker compose exec -T server pytest -q tests/test_final_enhancements.py -k "date"`

Expected: the invalid-date assertions fail because the current implementation silently selects another inventory date.

- [ ] **Step 3: Implement minimal date validation**

Change month/day parsing to keep the current year. In `respond`, compare an explicitly parsed date with `date.today()` and the available dates in `rooms` before selecting `room_row`. Return the structured validation result with `plan: state` and no new primary when invalid.

- [ ] **Step 4: Verify GREEN**

Run the same focused pytest command and expect all date tests to pass.

---

### Task 2: Prevent Resource Names From Changing Audience or Party Size

**Files:**
- Modify: `apps/server/tests/test_final_enhancements.py`
- Modify: `apps/server/app/services/product_advisor_service.py`

**Interfaces:**
- Produces: `CROWD_INTENT_KEYWORDS`, containing only explicit audience expressions.

- [ ] **Step 1: Write failing tests**

Start a single-person plan, replace its experience with `沉浸式城市演出`, and add `客房夜宵`. Assert every response remains `crowd == "SOLO"`, `party_size == 1`, and the requested resource/service is present.

- [ ] **Step 2: Verify RED**

Run: `docker compose exec -T server pytest -q tests/test_final_enhancements.py -k "resource_name or service_adjustment"`

Expected: the resource-name test fails with `COUPLE` and party size `2`.

- [ ] **Step 3: Implement explicit audience parsing**

Replace `_parse` audience detection based on `THEME_KEYWORDS` with strong phrases such as `单人`, `一个人`, `情侣`, `双人`, `亲子`, `家庭`, `朋友同行`. Leave resource selection independent from audience parsing.

- [ ] **Step 4: Verify GREEN**

Run the focused tests and expect the audience, party, resource, and service assertions to pass.

---

### Task 3: Persist Budget and Route Constraints Across Turns

**Files:**
- Modify: `apps/server/tests/test_final_enhancements.py`
- Modify: `apps/server/app/services/product_advisor_service.py`

**Interfaces:**
- Consumes and persists: `plan.visitor_budget`, `plan.route_note`

- [ ] **Step 1: Write failing state-chain test**

Set a price ceiling using both integer and decimal phrasing, then adjust the route and replace a resource. Assert `visitor_budget` stays unchanged, the suggested price does not exceed the ceiling when feasible, and `route_note` remains visible.

- [ ] **Step 2: Verify RED**

Run: `docker compose exec -T server pytest -q tests/test_final_enhancements.py -k "budget_persists"`

Expected: the later route turn loses the budget and recalculates a higher price.

- [ ] **Step 3: Implement state fallback**

Set `_turn_budget` from the explicit parsed budget when present; otherwise restore it from `state["visitor_budget"]`. Extend the numeric parser to accept decimal ceilings without truncating the value.

- [ ] **Step 4: Verify GREEN**

Run the focused budget test and expect all chained assertions to pass.

---

### Task 4: Surface Rejected Adjustments and Verify Candidate Output

**Files:**
- Modify: `apps/web/src/views/hotel/productGenerationState.mjs`
- Modify: `apps/web/src/views/hotel/productGenerationState.test.mjs`
- Modify: `apps/web/src/views/hotel/AiOperationsView.vue`
- Modify: `apps/server/tests/test_final_enhancements.py`

**Interfaces:**
- Produces: `validationChangeNote(validationError, fallback) -> string`

- [ ] **Step 1: Write failing frontend and candidate tests**

Add a Node test asserting a structured date error becomes a visible Chinese change note. Add an API chain that sets date, single audience, resource, service, budget, and route, generates candidates, then asserts every proposal matches date and party size and its creative direction contains the selected route/resource information.

- [ ] **Step 2: Verify RED**

Run:

```bash
node --test src/views/hotel/productGenerationState.test.mjs
docker compose exec -T server pytest -q tests/test_final_enhancements.py -k "candidate_inherits"
```

Expected: the helper is missing and at least one full-state inheritance assertion fails before the earlier tasks are complete.

- [ ] **Step 3: Implement frontend feedback**

Add `validationChangeNote` to the state helper. In `applyAdvisor`, prefer `nextAdvisor.validation_error.message`, retain `previousPrimary`, and write the rejected instruction plus reason into the existing operation log.

- [ ] **Step 4: Run complete verification**

Run:

```bash
docker compose exec -T server pytest -q tests/test_final_enhancements.py
npm run build
node --test src/views/hotel/productGenerationState.test.mjs
```

Expected: all tests pass and the Vue production build exits 0.

- [ ] **Step 5: Deploy and run real HTTP acceptance**

Rebuild `server` and `web`, restart both, verify `/health`, then execute a non-publishing HTTP sequence covering invalid past date, valid future date, single audience, experience, service, price, route, and candidate generation. Compare the printed state after every turn.

- [ ] **Step 6: Commit exact files locally on the server**

Stage only the design, plan, server advisor/tests, Vue view, and state helper/tests. Commit locally without pushing GitHub.
