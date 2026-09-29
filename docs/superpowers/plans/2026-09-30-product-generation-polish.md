# Product Generation Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the natural-language product-generation workspace concise, readable, and correct for resource changes in both draft and generated-product states.

**Architecture:** Keep one concise decision statement and move supporting evidence into folds. Drafts use the advisor; persisted products use the product refiner and refresh the same primary-card model. The refiner owns capacity, time-conflict, cost, and price validation.

**Tech Stack:** Vue 3 + TypeScript, FastAPI, SQLAlchemy, pytest, Docker Compose.

## Global Constraints

- Do not push to GitHub.
- Every resource action must visibly change the current product or explain why it cannot.
- Keep recommendation text in one visible location; evidence and risks are default-collapsed.
- Default itinerary activity text must be at least 14px.
- Verify server tests, web state tests, and a production web build before deployment.

---

### Task 1: Test and implement persisted-product resource actions

**Files:**

- Modify: `apps/server/tests/test_final_enhancements.py`
- Modify: `apps/server/app/services/product_refine_service.py`

- [ ] Add failing tests for named experience replacement, experience addition, hotel-service addition, duplicate add, and time-conflict refusal.
- [ ] Implement explicit resource intent parsing and validated resource add/swap in `ProductRefiner._apply_equity`.
- [ ] Run `docker compose run --rm --entrypoint pytest server apps/server/tests/test_final_enhancements.py -q`.

### Task 2: Refresh the visible primary product after an action

**Files:**

- Modify: `apps/web/src/views/hotel/AiOperationsView.vue`
- Test: `apps/web/src/views/hotel/productGenerationState.test.mjs`

- [ ] Add a failing state test for resource rows becoming visible experiences/services.
- [ ] Add a primary refresh helper; use the refiner for persisted products and keep advisor behavior for unpersisted drafts.
- [ ] Run `node --test src/views/hotel/productGenerationState.test.mjs` in the web container.

### Task 3: Reduce duplication and improve itinerary readability

**Files:**

- Modify: `apps/web/src/views/hotel/AiOperationsView.vue`

- [ ] Retain one concise recommendation, removing duplicated current-plan and standalone AI recommendation copy.
- [ ] Keep activities visible; fold addresses, transfers, and verification notes beneath each day.
- [ ] Raise itinerary typography to 14–15px with stronger time/title hierarchy.
- [ ] Run `docker compose run --rm web npm run build`.

### Task 4: Deploy and verify

- [ ] Run the full server suite and web state test.
- [ ] Rebuild/restart the production containers and check health.
- [ ] Browser-test resource swap, compatible/incompatible add, date, route, price, and crowd instructions; verify current card and operation record.
- [ ] Update checkboxes and commit locally without pushing.
