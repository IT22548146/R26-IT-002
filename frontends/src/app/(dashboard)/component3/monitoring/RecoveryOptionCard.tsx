import styles from './monitoring.module.css';

export interface RecoveryOption {
  option_id: string;
  title: string;
  feasible_before_deadline: boolean;
  rationale: string;
  daily_capacity?: number;
  daily_capacity_gain?: number;
  required_overtime_hours_per_day?: number;
  additional_workers?: number;
  repaired_machines?: number;
  expected_machine_repair_hours?: number;
  backup_machines?: number;
  backup_line_daily_capacity_used?: number;
  required_working_days?: number | null;
  projected_completion_date?: string | null;
  deadline_margin_working_days?: number | null;
  external_daily_capacity_required?: number | null;
}

function formatCapacity(value: number | null | undefined) {
  return Number.isFinite(value) ? Number(value).toFixed(2).replace(/\.00$/, '') : '—';
}

interface RecoveryOptionCardProps {
  option: RecoveryOption;
  recommended?: boolean;
}

export default function RecoveryOptionCard({
  option,
  recommended = false,
}: RecoveryOptionCardProps) {
  const resourceMetrics = [
    option.additional_workers
      ? { label: 'Add workers', value: String(option.additional_workers) }
      : null,
    option.required_overtime_hours_per_day
      ? {
          label: 'OT hours / day',
          value: formatCapacity(option.required_overtime_hours_per_day),
        }
      : null,
    option.repaired_machines
      ? { label: 'Repair machines', value: String(option.repaired_machines) }
      : null,
    option.repaired_machines && option.expected_machine_repair_hours !== undefined
      ? {
          label: 'Expected repair time',
          value: `${formatCapacity(option.expected_machine_repair_hours)} hr`,
        }
      : null,
    option.backup_machines
      ? { label: 'Backup machines', value: String(option.backup_machines) }
      : null,
    option.backup_line_daily_capacity_used
      ? {
          label: 'Backup line / day',
          value: formatCapacity(option.backup_line_daily_capacity_used),
        }
      : null,
    option.external_daily_capacity_required !== undefined &&
    option.external_daily_capacity_required !== null
      ? {
          label: 'External capacity / day',
          value: formatCapacity(option.external_daily_capacity_required),
        }
      : null,
  ].filter((metric): metric is { label: string; value: string } => metric !== null);

  return (
    <article
      className={`${styles.recoveryOption} ${
        recommended ? styles.recommendedOption : ''
      }`}
    >
      <div className={styles.optionHeading}>
        <div>
          {recommended && <span className={styles.recommendedLabel}>Recommended</span>}
          <h4>{option.title}</h4>
        </div>
        <span
          className={`${styles.feasibilityBadge} ${
            option.feasible_before_deadline
              ? styles.feasibleBadge
              : styles.infeasibleBadge
          }`}
        >
          {option.feasible_before_deadline ? 'Deadline feasible' : 'Not sufficient'}
        </span>
      </div>

      <p>{option.rationale}</p>

      {resourceMetrics.length > 0 && (
        <div className={styles.resourceMetrics}>
          {resourceMetrics.map((metric) => (
            <div key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
          ))}
        </div>
      )}

      {(option.daily_capacity !== undefined || option.projected_completion_date) && (
        <dl className={styles.optionForecast}>
          {option.daily_capacity !== undefined && (
            <div>
              <dt>Recovered daily capacity</dt>
              <dd>{formatCapacity(option.daily_capacity)} pieces</dd>
            </div>
          )}
          {option.daily_capacity_gain !== undefined && (
            <div>
              <dt>Daily capacity gain</dt>
              <dd>+{formatCapacity(option.daily_capacity_gain)} pieces</dd>
            </div>
          )}
          {option.required_working_days !== undefined &&
            option.required_working_days !== null && (
              <div>
                <dt>Working days required</dt>
                <dd>{option.required_working_days}</dd>
              </div>
            )}
          {option.projected_completion_date && (
            <div>
              <dt>New completion date</dt>
              <dd>{option.projected_completion_date}</dd>
            </div>
          )}
          {option.deadline_margin_working_days !== undefined &&
            option.deadline_margin_working_days !== null && (
              <div>
                <dt>Deadline margin</dt>
                <dd>
                  {option.deadline_margin_working_days >= 0 ? '+' : ''}
                  {option.deadline_margin_working_days} working day(s)
                </dd>
              </div>
            )}
        </dl>
      )}
    </article>
  );
}
