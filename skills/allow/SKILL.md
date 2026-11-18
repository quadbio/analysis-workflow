---
name: allow
description: >-
  Lift one guard hook of the analysis-workflow conventions for this session. Only the human runs it, by typing
  `/analysis-workflow:allow <guard>` after a guard refused something they want done.
disable-model-invocation: true
argument-hint: <guard>
---

A guard is lifted only when a hook's message in this turn says so, which it does when the human typed this command
in a repo that follows these conventions. Without that message nothing changed: the guards refuse as before, and
only the human can lift one.
