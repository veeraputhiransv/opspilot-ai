# Hypothesis confidence

OpsPilot persists multiple ranked hypotheses per incident. Each row stores:

- title and description
- `confidence` in `[0, 1]`
- evidence IDs that supported the hypothesis
- short evidence bullets for the inspector

**Product contract:** `confidence` is a **deterministic reasoner score** (weighted evidence signals in `DeterministicReasoner`). It is not a calibrated probability and is not model self-reported confidence. The UI must label it as an investigation score, not as statistical certainty.

Historical retrieval may support a hypothesis as evidence. Retrieval never authorizes a tool.
