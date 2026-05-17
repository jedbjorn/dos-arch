---
name: redline_review
description: Review PNG redlines from /shared/redlines/ — find by filename match, describe what is seen, interpret intent, propose implementation. No code until approved.
category: workflow
common: 0
---
# redline_review

- **skill_id:** 20
- **category:** workflow
- **common:** 0
- **description:** Review PNG redlines from shared/redlines/ — find by filename match, describe what is seen, interpret intent, propose implementation. No code until approved.

---

## Redline Review Skill

**Dev_Ref discipline:** Pre-change check dr_* for current state. Post-change write dr_log row (≤50 char summary, session_id).

**Trigger:** Jed says "redlines" (with or without specific context).

### Steps

1. **Find the image**
   - List files in shared/redlines/
   - Match filename to prompt context using fuzzy/keyword matching
   - If one file present and no strong mismatch, use it
   - If multiple files, pick best filename match; flag ambiguity if unclear

2. **Read the image**
   - Use the Read tool to load the PNG visually

3. **Report in three parts — do not skip any:**
   - **What I see:** Literal description of the image (layout, labels, UI elements, annotations, markups)
   - **What I understand:** Interpreted intent — what change or requirement this redline is communicating
   - **What I propose:** Concrete implementation plan (files, components, approach)

4. **Hold**
   - Do not write or execute any code until Jed explicitly approves the proposal

5. **After resolution confirmed**
   - Once Jed confirms the redline is resolved, delete the source .png from shared/redlines/
   - Delete only after explicit confirmation — never on assumed completion
