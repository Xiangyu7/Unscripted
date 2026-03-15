# Unscripted Roadmap

## Product target

Target product shape:

- Multi-character long-term autonomy
- Strict private information isolation
- Controlled narrative pacing
- Script-murder style play loop: investigate, perform, vote, resolve

Current status:

- `Investigate / perform / resolve`: partially available
- `Vote / public confrontation loop`: missing
- `Autonomy`: promising foundation, not yet long-horizon
- `Information isolation`: player-facing redaction exists, system-grade isolation does not
- `Pacing`: closest to target, but still soft-controlled rather than hard-budgeted

## Roadmap summary

### V1: Play Loop Closure

Goal:
Make the game feel structurally like a script-murder session rather than an open-ended AI chat.

Deliverables:

- Add endgame phases:
  - free investigation
  - public confrontation
  - voting
  - reveal / settlement
- Add accusation and voting state models
- Let NPCs publicly state positions during confrontation
- Add final vote tally and different settlement outcomes
- Keep deduction validator as the final truth judge, but place it after the confrontation/vote flow

Core changes:

- Add `GamePhase` / `VoteState` / `ConfrontationState`
- Add public accusation endpoint flow inside turn engine
- Add frontend UI for:
  - initiating public confrontation
  - nominating suspects
  - showing NPC stances
  - confirming final vote

Affected files:

- `/Users/xinyueke/Desktop/Unscripted/backend/schemas/game_state.py`
- `/Users/xinyueke/Desktop/Unscripted/backend/engine/turn_engine.py`
- `/Users/xinyueke/Desktop/Unscripted/backend/agents/dm_agent.py`
- `/Users/xinyueke/Desktop/Unscripted/backend/agents/deduction_validator.py`
- `/Users/xinyueke/Desktop/Unscripted/frontend/src/lib/types.ts`
- `/Users/xinyueke/Desktop/Unscripted/frontend/src/app/page.tsx`
- `/Users/xinyueke/Desktop/Unscripted/frontend/src/components/QuickActions.tsx`

Acceptance criteria:

- Player can trigger a public confrontation intentionally
- NPCs can react publicly and shift blame in front of each other
- Voting can happen as an explicit phase, not just implied accusation
- Game always ends through a clear settlement path
- A full session has a recognizable beginning, middle, and closure

Why V1 first:

- This is the missing product loop
- Without it, the experience is still closer to AI narrative exploration than script-murder gameplay

---

### V2: Information Permissions

Goal:
Turn information handling from prompt convention into structured game rules.

Deliverables:

- Replace loose private text blobs with scoped fact storage
- Separate facts into:
  - public facts
  - player-known facts
  - npc-private facts
  - shared-secret facts
  - truth facts
- Add fact visibility rules and disclosure transitions
- Generate character prompts from scoped facts only
- Add logging for who learned what and when

Core changes:

- Introduce structured `Fact` or `KnowledgeNode` model
- Add disclosure events such as:
  - overheard
  - confessed
  - inferred
  - publicly revealed
- Prevent character prompts from reading unrestricted scenario truth
- Prevent one NPC from using facts they have not learned

Affected files:

- `/Users/xinyueke/Desktop/Unscripted/backend/schemas/game_state.py`
- `/Users/xinyueke/Desktop/Unscripted/backend/stories/gu_family_case.py`
- `/Users/xinyueke/Desktop/Unscripted/backend/agents/character_agent.py`
- `/Users/xinyueke/Desktop/Unscripted/backend/engine/turn_engine.py`
- `/Users/xinyueke/Desktop/Unscripted/backend/systems/continuity_system.py`
- `/Users/xinyueke/Desktop/Unscripted/backend/systems/conspiracy_system.py`

Acceptance criteria:

- Player API never leaks protected truth or NPC-private facts
- Character prompts only receive facts within their scope
- NPC replies stay consistent with what that NPC actually knows
- Shared secrets can spread only through explicit in-game events

Why V2 second:

- This is the foundation for believable social play
- Without this, “private information isolation” is still mostly cosmetic

---

### V3: Long-Horizon NPC Autonomy

Goal:
Make NPCs feel like persistent actors pursuing plans, not just reacting turn-by-turn.

Deliverables:

- Add per-NPC long-term goal tree
- Add short-term plans with success/failure transitions
- Add private NPC-to-NPC information exchange
- Add world-state consequences from autonomous action
- Add plan revision when pressure, clues, or votes change the situation

Core changes:

- Upgrade autonomy from action pool selection to:
  - current objective
  - subgoal
  - next action
  - fallback plan
- Connect psychology and conspiracy systems into plan selection
- Let NPC actions alter:
  - evidence
  - alliances
  - item locations
  - access routes
  - public suspicion

Affected files:

- `/Users/xinyueke/Desktop/Unscripted/backend/systems/npc_behavior_system.py`
- `/Users/xinyueke/Desktop/Unscripted/backend/systems/psychology_system.py`
- `/Users/xinyueke/Desktop/Unscripted/backend/systems/conspiracy_system.py`
- `/Users/xinyueke/Desktop/Unscripted/backend/engine/world_state.py`
- `/Users/xinyueke/Desktop/Unscripted/backend/engine/turn_engine.py`

Acceptance criteria:

- NPCs can continue meaningful agendas for 10+ turns
- NPCs can adapt after failed plans or player intervention
- NPCs can protect allies, betray allies, destroy evidence, or bait the player
- Revisiting a location can reveal world changes caused by NPCs, not just player actions

Why V3 third:

- This is where the game becomes truly “multi-character autonomous”
- It depends on V2, because plans only matter if knowledge boundaries are real

---

### V4: Hard Pacing Control

Goal:
Make pacing a system budget, not just narrative taste.

Deliverables:

- Add reveal budget per act
- Add tension budget per phase
- Add event cooldowns:
  - betrayal cooldown
  - major clue cooldown
  - twist cooldown
  - confession cooldown
- Add “stuck recovery” rules with escalating interventions
- Add endgame trigger thresholds based on progress, tension, and time

Core changes:

- Convert current Story Architect and DM control into explicit constraints
- Track:
  - clue reveal count by act
  - unresolved dramatic threads
  - recent high-intensity turns
  - unanswered player pushes
- Prevent overfiring of dramatic events in adjacent turns

Affected files:

- `/Users/xinyueke/Desktop/Unscripted/backend/agents/story_architect_agent.py`
- `/Users/xinyueke/Desktop/Unscripted/backend/agents/dm_agent.py`
- `/Users/xinyueke/Desktop/Unscripted/backend/engine/turn_engine.py`

Acceptance criteria:

- The session reliably moves through setup, escalation, confrontation, and closure
- Players do not get flooded with too many reveals in a short span
- Stalled sessions recover without random-feeling deus ex machina
- Final acts feel denser and more decisive than early acts

Why V4 after V3:

- Pacing control becomes much more valuable once the world is actually dynamic

## Recommended execution order

1. V1 Play Loop Closure
2. V2 Information Permissions
3. V3 Long-Horizon NPC Autonomy
4. V4 Hard Pacing Control

## Suggested milestone cadence

### Milestone A

- Finish V1
- Target outcome: “This already feels like a playable script-murder prototype”

### Milestone B

- Finish V2
- Target outcome: “NPC knowledge feels trustworthy and socially coherent”

### Milestone C

- Finish V3
- Target outcome: “NPCs feel alive even when the player is not directly interacting with them”

### Milestone D

- Finish V4
- Target outcome: “Sessions feel authored without becoming railroaded”

## What not to do yet

- Do not add many new cases before V1 and V2 are stable
- Do not overinvest in image generation or visual polish before the loop is closed
- Do not rely on prompt wording alone for secrecy or pacing guarantees

## Immediate next build recommendation

If only one version is started now, start with V1.

Concrete first slice:

- Add `public_confrontation` and `voting` phases
- Let player nominate a suspect
- Let three NPCs output short public stance lines
- Let system resolve vote result
- Feed the result into current deduction ending logic

That is the shortest path from “AI mystery demo” to “script-murder style game loop”.
