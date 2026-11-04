// Generic plugin table. Image boxes are pixel coordinates in a source image;
// cropping preserves its original colours and never creates replacement art.
import React from 'react';

function Crop({ image, label }) {
  const [left, top, right, bottom] = image.box ?? [];
  const valid = [left, top, right, bottom, image.width, image.height].every(Number.isFinite)
    && left >= 0 && top >= 0 && right > left && bottom > top
    && right <= image.width && bottom <= image.height;
  if (!valid || !image.url) return null;
  const cropWidth = right - left, cropHeight = bottom - top;
  return <span style={{ display: 'block', overflow: 'hidden', position: 'relative',
    width: '100%', maxWidth: Math.min(64, 72 * cropWidth / cropHeight),
    aspectRatio: `${cropWidth} / ${cropHeight}`, margin: '0 auto' }}>
    <img src={image.url} alt={label} loading="lazy" onError={(event) => { event.currentTarget.style.visibility = 'hidden'; }}
      style={{ position: 'absolute', maxWidth: 'none', width: `${image.width / cropWidth * 100}%`,
        height: `${image.height / cropHeight * 100}%`, left: `${-left / cropWidth * 100}%`, top: `${-top / cropHeight * 100}%`, imageRendering: 'pixelated' }} />
  </span>;
}

export function InventoryTable({ option, tr }) {
  const originalRows = option.rows?.() ?? [];
  const columns = Math.min(6, Math.max(1, ...originalRows.map((row) => row.cells?.length ?? 0)));
  const rows = originalRows.flatMap((row) => Array.from({ length: Math.max(1, Math.ceil((row.cells?.length ?? 0) / columns)) },
    (_, index) => ({ ...row, label: index ? '' : row.label, key: `${row.key ?? row.label}-${index}`,
      cells: (row.cells ?? []).slice(index * columns, (index + 1) * columns) })));
  const rowLabelWidth = Math.min(64, Math.max(18, ...rows.map((row) => String(row.label ?? '').length * 6)));
  const caption = option.caption?.();
  return <div style={{ margin: '8px 0', maxWidth: '100%' }}>
    <div style={{ fontWeight: 600, marginBottom: 4 }}>{tr(option.label)}</div>
    {caption && <div style={{ color: '#a8afb9', fontSize: 11, marginBottom: 5 }}>{tr(caption)}</div>}
    <div style={{ minWidth: 0 }}>
      <table aria-label={tr(option.label)} style={{ borderCollapse: 'collapse', width: '100%', tableLayout: 'fixed', fontSize: 12 }}>
        <colgroup><col style={{ width: rowLabelWidth }} />{Array.from({ length: columns }, (_, index) => <col key={index} />)}</colgroup>
        <tbody>{rows.map((row, index) => <tr key={row.key ?? index}>
          <th scope="row" style={{ textAlign: 'left', fontWeight: 500, padding: '4px 1px', verticalAlign: 'middle', overflowWrap: 'anywhere' }}>{tr(row.label)}</th>
          {(row.cells ?? []).map((cell, column) => <td key={cell.key ?? column} colSpan={columns % row.cells.length === 0 ? columns / row.cells.length : 1}
            style={{ padding: '4px 2px', textAlign: 'center', verticalAlign: 'top', minWidth: 0, overflowWrap: 'anywhere' }}>
            {cell.image && <Crop image={cell.image} label={tr(cell.label ?? '')} />}
            <div>{tr(cell.label ?? '')}</div>
            <div style={{ color: cell.value === 'never read' ? '#8a919c' : '#e1e6ed', maxWidth: 180, fontSize: 11, overflowWrap: 'anywhere' }}>
              {tr(cell.value ?? 'never read')}
            </div>
            {(cell.bonuses ?? []).map((bonus, bonusIndex) => <div key={bonusIndex}
              style={{ color: bonus.role === 'inheritance' ? '#00ffff' : bonus.role === 'primary' ? '#fff' : bonus.color ?? '#fff',
                whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 11, maxWidth: 180 }}>
              {bonus.display_text}
            </div>)}
          </td>)}
        </tr>)}</tbody>
      </table>
    </div>
  </div>;
}
