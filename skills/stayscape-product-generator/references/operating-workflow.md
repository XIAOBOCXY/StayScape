# Product generator operating workflow

The calling service owns the deterministic sequence:

1. Query rooms, services, approved partner resources, weather, aggregate
   demand, and sourced public knowledge.
2. Choose a room and a non-overlapping formal selection before the model call.
3. Call this Skill for a bounded candidate JSON document.
4. Lock allowed IDs and quantities, then calculate capacity, cost, price,
   gross margin, age, weather, and time validity in FastAPI.
5. Persist only a PENDING_CONFIRMATION proposal. A hotel operator makes the
   separate DRAFT or PUBLISH decision.

The Skill must not shortcut or reorder this sequence.
