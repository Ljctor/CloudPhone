// The information panels' rows: a label and its value, and titled
// sections of them ([title, [[label, value], ...]], French source texts).
import { tr } from './i18n';
import { styles } from './styles';

// One row; label is already translated.
export function infoRow(label, value) {
  return (
    <div key={label} style={styles.infoRow}>
      <span style={styles.infoLabel}>{label}</span>
      <span>{value}</span>
    </div>
  );
}

export function infoSections(list) {
  return list.map(([title, rows]) => (
    <div key={title}>
      <div style={styles.infoSection}>{tr(title)}</div>
      {rows.map(([label, value]) => infoRow(tr(label), value))}
    </div>
  ));
}
