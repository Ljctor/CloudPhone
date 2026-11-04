// Generic plugin table. Image boxes are pixel coordinates in a source image;
// cropping preserves its original colours and never creates replacement art.
import React from 'react';

function Crop({ image, label }) {
  const [left, top, right, bottom] = image.box ?? [];
  const valid = [left, top, right, bottom, image.width, image.height].every(Number.isFinite)
    && left >= 0 && top >= 0 && right > left && bottom > top
    && right <= image.width && bottom <= image.height;
  if (!valid || !image.url) return null;
  const scale = Math.min(64 / (right - left), 72 / (bottom - top));
  return <span style={{ display: 'inline-block', overflow: 'hidden', position: 'relative',
    width: (right - left) * scale, height: (bottom - top) * scale }}>
    <img src={image.url} alt={label} loading="lazy" onError={(event) => { event.currentTarget.style.visibility = 'hidden'; }}
      style={{ position: 'absolute', maxWidth: 'none', width: image.width * scale,
        height: image.height * scale, left: -left * scale, top: -top * scale, imageRendering: 'pixelated' }} />
  </span>;
}

export function InventoryTable({ option, tr }) {
  const rows = option.rows?.() ?? [];
  const caption = option.caption?.();
  return <div style={{ margin: '8px 0', maxWidth: '100%' }}>
    <div style={{ fontWeight: 600, marginBottom: 4 }}>{tr(option.label)}</div>
    {caption && <div style={{ color: '#a8afb9', fontSize: 11, marginBottom: 5 }}>{tr(caption)}</div>}
    <div style={{ overflowX: 'auto' }}>
      <table aria-label={tr(option.label)} style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>
        <tbody>{rows.map((row, index) => <tr key={row.key ?? index}>
          <th scope="row" style={{ textAlign: 'left', fontWeight: 500, padding: 4, verticalAlign: 'middle' }}>{tr(row.label)}</th>
          {(row.cells ?? []).map((cell, column) => <td key={cell.key ?? column}
            style={{ padding: '4px 6px', textAlign: 'center', verticalAlign: 'top', minWidth: 66 }}>
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
