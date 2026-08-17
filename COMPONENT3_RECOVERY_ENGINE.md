# Component 3 Emergency Recovery Planning Engine

## Purpose

The existing Component 3 machine-learning models detect the risk type and the
order-risk level. The recovery engine is a separate, deterministic decision
layer. It answers the operational question:

> Given the remaining quantity, available working days, current output, and
> resource limits, what action can still complete the order before the buyer
> deadline?

No new model is trained for this step. Every recommendation includes the values
used to calculate it, so a supervisor can review the decision.

## API

Use the existing endpoint:

```text
POST /api/component3/predict
```

Add the optional `recovery_parameters` object to the existing request:

```json
{
  "recovery_parameters": {
    "planned_worker_count": 50,
    "planned_machine_count": 40,
    "normal_shift_hours": 8,
    "max_overtime_hours_per_day": 2,
    "max_additional_workers": 5,
    "available_backup_machines": 2,
    "backup_line_daily_capacity": 150,
    "expected_machine_repair_hours": 4
  }
}
```

All recovery parameters are optional. The engine uses these safe defaults:

- `normal_shift_hours`: `8`
- `max_overtime_hours_per_day`: `2`
- `max_additional_workers`: the reported worker-shortage count
- `available_backup_machines`: `0`
- `backup_line_daily_capacity`: `0`

The engine does not invent planned worker counts, planned machine counts, or
repair time. When an incident needs one of these values and it was not sent,
the name is returned in `missing_parameters`.

## Calculations

The current production day is assumed to be complete and included in
`cumulative_completed_qty`.

```text
remaining quantity = full order quantity - cumulative completed quantity

required daily rate = remaining quantity / available future working days

daily recovery gap = max(0, required daily rate - plant daily output)

required working days = ceil(remaining quantity / option daily capacity)
```

Working days currently mean Monday to Friday. Public and factory holidays are
not included in version 1.

Capacity estimates are:

```text
hourly output = current daily output / normal shift hours

daily output per worker = daily commitment / planned worker count

daily output per machine = daily commitment / planned machine count
```

## Returned plan

The normal prediction response now contains `recovery_plan`:

```json
{
  "recovery_plan": {
    "engine_version": "v1-rules",
    "status": "recovery_required",
    "triggered_by": ["Worker Shortage"],
    "remaining_quantity": 45585,
    "available_working_days": 106,
    "required_daily_rate": 430.05,
    "current_daily_capacity": 407.0,
    "daily_recovery_gap": 23.05,
    "missing_parameters": [],
    "recommended_option": {
      "option_id": "add_workers",
      "title": "Reassign or add operators",
      "additional_workers": 3,
      "daily_capacity": 432.8,
      "required_working_days": 106,
      "projected_completion_date": "2024-11-27",
      "feasible_before_deadline": true
    },
    "alternatives": [],
    "manual_escalation_required": false
  }
}
```

The evaluated actions can include:

- continue the current plan;
- add controlled overtime;
- add or reassign workers;
- repair failed machines;
- activate backup machines;
- move quantity to a backup line;
- combine multiple internal recovery actions;
- manually escalate and reallocate external capacity when internal limits are
  insufficient.

The recommendation order prefers the least disruptive feasible action:
current plan, restored normal resources, backup machines, overtime, backup
line, and finally a combined plan.

## Current limitations

- Capacity gains are linear planning estimates, not causal predictions.
- Skills, machine types, style complexity, holidays, and costs are not yet
  included. Repair is assumed to start on the next working day, and capacity
  returns proportionally during the shift in which the repair finishes.
- A manager must approve actions before execution.
- Actual results should be stored daily so the estimates can be calibrated in
  the next phase.

These limitations are why this module is described as a recovery planning
engine, not as a newly trained recommendation model.
