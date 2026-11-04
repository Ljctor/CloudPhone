// Generic plugin table: clean sprites compose observed indicators separately.
// Legacy image boxes retain their existing calibrated capture rendering.
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

// Clean item art and observed indicators remain separate DOM layers. Missing
// indicators stay absent: a missing star count is not zero awakening.
function Sprite({ image, indicators = {}, label, tr }) {
  const element = indicators.element;
  const badge = { position: 'absolute', fontSize: 10, lineHeight: 1.2,
    textShadow: '0 1px 2px #000, 1px 0 2px #000' } as const;
  const integer = (value) => Number.isInteger(value) && value >= 0;
  return <span data-inventory-sprite={image.asset} style={{ display: 'block', position: 'relative',
    width: '100%', maxWidth: 72, height: 80, margin: '0 auto' }}>
    <img src={image.url} alt={label} loading="lazy"
      style={{ width: '100%', height: 64, objectFit: 'contain', imageRendering: 'pixelated' }} />
    {indicators.rarity && <span data-inventory-rarity="true" style={{ ...badge, top: 0, left: 0,
      color: indicators.rarity_color ?? '#e1e6ed', fontSize: 9 }}>{tr(indicators.rarity)}</span>}
    {element && <img data-inventory-element={element.id} src={element.image} alt={tr(element.label)}
      title={tr(element.label)} style={{ position: 'absolute', right: -2, top: -3,
        width: 18, height: 18, objectFit: 'contain', imageRendering: 'pixelated' }} />}
    {integer(indicators.stars) && <span data-inventory-stars={indicators.stars}
      aria-label={`${tr('Étoiles')} : ${indicators.stars}`}
      style={{ ...badge, left: 0, right: 0, bottom: 0, color: '#ffd45a',
        fontSize: 12, overflowWrap: 'anywhere' }}>
      {indicators.star_image && indicators.stars > 0 && indicators.stars <= 6
        ? Array.from({ length: indicators.stars }, (_, i) => <img key={i} src={indicators.star_image} alt=""
          style={{ width: 14, height: 14, objectFit: 'contain', imageRendering: 'pixelated' }} />)
        : `${indicators.stars} ★`}
    </span>}
    {indicators.equipped === true && <span data-inventory-equipped="true"
      aria-label={tr('Équipé')} style={{ ...badge, left: 0, bottom: 18, color: '#fff' }}>E</span>}
    {integer(indicators.awakening) && <span data-inventory-awakening={indicators.awakening}
      style={{ ...badge, right: 0, top: 20, color: '#c8a7ff' }}>+{indicators.awakening}</span>}
    {integer(indicators.count) && <span data-inventory-count={indicators.count}
      style={{ ...badge, right: 0, bottom: 18, color: '#fff' }}>×{indicators.count}</span>}
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
            {cell.image && (cell.image.kind === 'sprite'
              ? <Sprite image={cell.image} indicators={cell.indicators} label={tr(cell.label ?? '')} tr={tr} />
              : <Crop image={cell.image} label={tr(cell.label ?? '')} />)}
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
