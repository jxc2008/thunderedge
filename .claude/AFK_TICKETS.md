# AFK Work Tickets

Fill this out before going AFK. The team lead reads it and dispatches to agents.

---

## How to use

1. Copy the ticket template below for each piece of work.
2. Assign each ticket to ONE agent: `frontend`, `backend`, or `data`.
3. Make tickets non-overlapping (no two tickets touch the same files).
4. Tell Claude: "Dispatch these AFK tickets."

---

## Ticket Template

```
### TICKET-N: <short title>

Agent: frontend | backend | data
Priority: high | medium | low

Goal (1 sentence):


Scope:
- Files to change:
- Files NOT to touch:

Acceptance criteria:
- [ ] <specific, checkable thing>
- [ ] <specific, checkable thing>
- [ ] Validation script passes

Notes / context:

```

---

## Active Tickets

<!-- Add your tickets below this line -->

### TICKET-1: Example

Agent: frontend
Priority: medium

Goal: Update the pick/ban section header to say "Map Pool Activity" instead of "Pick / Ban Tendencies"

Scope:
- Files to change: `components/matchup-page.tsx`
- Files NOT to touch: backend/, scripts/

Acceptance criteria:
- [ ] Header text updated
- [ ] No other UI changes
- [ ] `bash scripts/validate_frontend.sh` passes
