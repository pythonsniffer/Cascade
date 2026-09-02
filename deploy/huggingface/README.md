---
title: Cascade Digital Twin
emoji: 🏭
colorFrom: gray
colorTo: red
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Live digital twin for a 35-station vehicle assembly line
---

# Cascade — Digital Twin

Bottleneck forecasting (BSTAN) + defect detection (fine-tuned YOLOv8) + defect-chain
prediction, joined into one live twin-state for a 35-station vehicle assembly line.

Press **Play** in the top bar. The first two shifts report *warming up* — the forecaster
needs a 3-shift history window before it predicts. That is the honest state, not a bug.

## What is real, and what is simulated

**Real** — the fine-tuned YOLOv8 detector (mAP50 0.910 recorded in the checkpoint),
the BSTAN bottleneck forecaster (test RMSE 2.689, beating persistence 3.44 and
moving-average 3.23), and the defect-chain engine (3/3 planted chains recovered,
lifts 1.53 / 1.44 / 1.36). All loaded from exported artifacts — nothing trains here.

**Simulated** — the line itself: the 35-station layout, buffer sizes, per-shift process
features and inspection history, generated with seed 42. Also the `vehicle_id`,
`station_id` and `timestamp` on defect events, because the defect images carry no
automotive line context.

**Assumed** — the camera→station mapping, the visual→process defect mapping, and every
P&L cost, all user-editable.

The **What's real** page in the app renders this breakdown live from the API, not from
this text. The P&L view never shows a number without its disclaimer and breakdown.

Source: https://github.com/pythonsniffer/Cascade
