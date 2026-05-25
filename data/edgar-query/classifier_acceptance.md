# tra-classify acceptance log

Append-only chronological log of `tra-classify` iteration acceptance events. One
line per event. Format:

```
YYYY-MM-DD | classifier_version=N | status=<accepted|revised|in_progress> | <one-line note>
```

Status meanings:

- `accepted`: the user has reviewed iteration N's `classifications-vN.csv` and
  signed off; this version becomes the input to `--mode finalize` and the
  authoritative source for the confirmed-TRA-CIK list. Only one `accepted`
  entry per version (a re-acceptance after a manual edit gets a new line with
  a higher version number).
- `revised`: iteration N was rejected; the user requested changes to the
  signal catalog or rules. Subsequent iteration starts at version N+1.
- `in_progress`: iteration N has been kicked off (signal catalog updated,
  classifier-version bumped) but the user has not yet reviewed the output.

`classify.py --mode finalize` reads the latest line where `status=accepted` to
determine which version to re-run end-to-end. Explicitly passing
`--classifier-version N` on the CLI bypasses this lookup.

---

2026-05-25 | classifier_version=2 | status=in_progress | F2 round 1: title-band S1 tightening + rule-4 demotion (see signal-catalog.md v2); 46/1805 uncertain rows reviewed by tra-reviewer (0 disagreements with v2); 10/10 hand-verified by user; remaining ~1759 uncertain rows pending A4 review
