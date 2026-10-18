// Slayer Legend plugin, page side: loaded by the Cloud Phone page (see
// plugins.ts in part 04 for the API). Among its features:
// - "Lancer le jeu": the gateway starts the game and brings it to the
//   battle screen (TAP TO START, then Confirm on the latest save).
// - The emerald and diamond counters, on this screen only (nothing is sent to Android),
//   either cut at its comma ("284,086" shows "284"), or rewritten: covered
//   with the bar's colour and, in the game's font and colour at the game's
//   size for that many digits, either the digits after its comma (leading
//   zeros dropped) or a number the user chose are written over it.
// - "Enregistrer mes parcours" (on by default): each tap the user makes on
//   the game is sent to the gateway, which records the screen before and
//   after it, building a graph of the game's screens (never replayed).
import { AREA, DIAMOND_AREA, findEmeraldMask } from './emerald_mask.js';
import { FONT, MASKS, shade } from './emerald_font.js';

const ENGLISH = {
  'Farmer la mine': 'Farm the mine',
  'Étage à farmer': 'Floor to farm',
  'Mode': 'Mode',
  'défaut': 'default',
  'Configuration : farming mpw18': 'Settings: mpw18 farming',
  'Configuration : farming mpw4': 'Settings: mpw4 farming',
  'Configuration : mine fermée': 'Settings: Closed Mine',
  'Arme, gravure, réglages de combat': 'Weapon, engraving, battle settings',
  'à venir': 'coming',
  'Plumes': 'Feathers',
  'Gold': 'Gold',
  'Gold par seconde': 'Gold per second',
  'Overlay gold/s': 'Gold/s overlay',
  'Affiché': 'Shown',
  'Masqué': 'Hidden',
  'pas encore mesuré': 'not measured yet',
  'non visible (économie d’énergie ?)': 'not visible (Power Saving Mode?)',
  'Farming mpw18 (par défaut)': 'mpw18 farming (default)',
  'Farming mpw4': 'mpw4 farming',
  'Farming mpw18': 'mpw18 farming',
  'Jeu libre': 'Free play',
  'Mine fermée': 'Closed Mine',
  'Plus haut stage débloqué': 'Highest stage unlocked',
  'Stage mpw18': 'mpw18 stage',
  'Stage mpw4': 'mpw4 stage',
  '— choisir —': '— choose —',
  'État': 'State',
  'Zone à farmer': 'Area to farm',
  'Minuteur': 'Timer',
  'Ajuster (minutes)': 'Adjust (minutes)',
  'plus de parchemin doré': 'no gold scroll',
  'Combat en cours, sans parchemin doré': 'Fighting, without the gold scroll',
  'Sans limite': 'No limit',
  'reste {time}': '{time} left',
  'Durée écoulée : « Repeat entry » décoché, la mine s’arrête après cette entrée':
    'Time is up: "Repeat entry" unticked, the mine stops after this entry',
  'Durée écoulée : pas de relance': 'Time is up: no restart',
  'Durée écoulée, mais « Repeat entry » ne se décoche pas': 'Time is up, but "Repeat entry" does not untick',
  'Mine': 'Mine',
  'Surveillance de la mine': 'Watching the mine',
  'Combat en cours, parchemin doré actif': 'Fighting, gold scroll on',
  'Mine relancée': 'Mine started again',
  'Le jeu n’est pas au premier plan': 'The game is not in front',
  'Écran autre que la mine : rien à faire': 'Not a mine screen: nothing to do',
  'Parchemin doré pas vu depuis 5 minutes : pas de relance': 'Gold scroll not seen for 5 minutes: no restart',
  'Plus de parchemin doré : « Repeat entry » décoché, la mine s’arrête après cette entrée':
    'Gold scroll gone: "Repeat entry" unticked, the mine stops after this entry',
  'Plus de parchemin doré, mais « Repeat entry » ne se décoche pas': 'Gold scroll gone, but "Repeat entry" does not untick',
  'La relance a échoué 3 fois : relance la mine à la main': 'Restarting failed 3 times: start the mine by hand',
  'Choisis l’étage et la zone': 'Choose the floor and the area',
  'arrêtée': 'off',
  'Lancer le jeu': 'Launch the game',
  'Lancer': 'Launch',
  'Lancement': 'Launch',
  'Compteur d’émeraudes': 'Emerald counter',
  'Jeu': 'Game',
  'Mode et farming': 'Mode and farming',
  'Émeraudes': 'Emeralds',
  'Diamants': 'Diamonds',
  'Compteur de diamants': 'Diamond counter',
  'Inchangé': 'Unchanged',
  'Coupé à la virgule': 'Cut at the comma',
  'Réécrit': 'Rewritten',
  'Détection du compteur': 'Counter detection',
  'Nombre affiché (vide : après la virgule)': 'Number shown (empty: after the comma)',
  'détecté': 'detected',
  'non détecté': 'not detected',
  'Ouverture du jeu': 'Opening the game',
  'Écran titre touché, connexion': 'Title screen tapped, signing in',
  'Dernière sauvegarde confirmée, chargement': 'Latest save confirmed, loading',
  'Le jeu est sur l’écran de combat': 'The game is on the battle screen',
  'Sortie du mode économie d’énergie': 'Leaving Power Saving Mode',
  'Le mode économie d’énergie ne se ferme pas : touche son bouton à la main': 'Power Saving Mode does not close: tap its button by hand',
  'Écran inattendu : termine le lancement à la main': 'Unexpected screen: finish the launch by hand',
  'Le jeu n’a pas atteint l’écran de combat en 3 minutes': 'The game did not reach the battle screen in 3 minutes',
  'Android ne répond pas': 'Android does not answer',
  'Un lancement est déjà en cours': 'A launch is already running',
  'Écran détecté': 'Detected screen',
  'Écran titre': 'Title screen',
  'Choix de la sauvegarde': 'Save choice',
  'Combat': 'Battle',
  'Économie d’énergie': 'Power Saving',
  'Autre (menu, chargement…)': 'Other (menu, loading…)',
  'Pas de capture d’écran': 'No screenshot',
  'Menu du jeu': 'Game menu',
  'Autre application': 'Another app',
  'Stage sélectionné': 'Selected stage',
  'vu en mode économie d’énergie, à confirmer': 'seen in Power Saving Mode, to be confirmed',
  'inconnu : passe en mode économie d’énergie pour le lire': 'unknown: go to Power Saving Mode to read it',
  'Monstres par vague': 'Monsters per wave',
  'Équipement lâché': 'Equipment dropped',
  'Arme': 'Weapon',
  'Accessoire': 'Accessory',
  'Commun': 'Common',
  'Supérieur': 'Great',
  'Épique': 'Epic',
  'Légendaire': 'Legendary',
  'Couleur des âmes': 'Soul colour',
  'verte': 'green',
  'bleue': 'blue',
  'rouge': 'red',
  'déduite, non vérifiée': 'deduced, not checked',
  'Navigation': 'Navigation',
  'Enregistrer mes parcours': 'Record my paths',
  'Activé': 'On',
  'Désactivé': 'Off',
  'Parcours enregistrés': 'Recorded paths',
  '{nodes} écrans, {taps} appuis': '{nodes} screens, {taps} taps',
  'indisponible (passerelle sans dossier de données)': 'unavailable (the gateway has no data directory)',
};

// Ways to copy the video's pixels. Some browsers (Firefox on Android, with
// hardware decoding) hand a blank image to drawImage(video); another path may
// still work. The first one giving a non-blank image is kept.
const CAPTURE_METHODS = {
  // Only the search area.
  crop: async (video, context, area) => {
    context.drawImage(video, area.x, area.y, area.width, area.height, 0, 0, area.width, area.height);
  },
  // The whole frame, then the area.
  full: async (video, context, area, scratch) => {
    scratch.canvas.width = video.videoWidth;
    scratch.canvas.height = video.videoHeight;
    scratch.drawImage(video, 0, 0);
    context.drawImage(scratch.canvas, area.x, area.y, area.width, area.height, 0, 0, area.width, area.height);
  },
  bitmap: async (video, context, area) => {
    const bitmap = await createImageBitmap(video, area.x, area.y, area.width, area.height);
    context.drawImage(bitmap, 0, 0);
    bitmap.close();
  },
  // Through a WebGL texture, read back with readPixels.
  webgl: async (video, context, area, scratch, gl) => {
    if (!gl) throw new Error('none');
    gl.canvas.width = video.videoWidth;
    gl.canvas.height = video.videoHeight;
    const texture = gl.createTexture();
    const framebuffer = gl.createFramebuffer();
    try {
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, video);
      gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, texture, 0);
      const data = new Uint8ClampedArray(area.width * area.height * 4);
      // Texture rows are in the video's order: row 0 is the top.
      gl.readPixels(area.x, area.y, area.width, area.height, gl.RGBA, gl.UNSIGNED_BYTE, data);
      context.putImageData(new ImageData(data, area.width, area.height), 0, 0);
    } finally {
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.deleteFramebuffer(framebuffer);
      gl.deleteTexture(texture);
    }
  },
  frame: async (video, context, area) => {
    if (typeof VideoFrame === 'undefined') throw new Error('none');
    const frame = new VideoFrame(video);
    try {
      context.drawImage(frame, area.x, area.y, area.width, area.height, 0, 0, area.width, area.height);
    } finally {
      frame.close();
    }
  },
};

// When no method gives an image, the gateway finds the mask on an emulator
// screenshot instead (slower to follow, costs the server a little CPU).
const SERVER_MS = 500;

// True when every pixel is the same: the copy failed.
function blank(data) {
  for (let i = 4; i < data.length; i += 4) {
    if (data[i] !== data[0] || data[i + 1] !== data[1] || data[i + 2] !== data[2]) return false;
  }
  return true;
}

// The game's counter font, in digit heights: how far each digit and the
// comma advance, and how much bigger the digits are with 5 digits or fewer
// than with 6 or more. Measured at 480x1040 on "284,086" (6 digits, 9 px
// high, 39 px wide with the comma) and the diamonds' "306" (10 px high,
// 19 px wide): about 1 px of precision.
const DIGIT_ADVANCE = 0.68;
const COMMA_ADVANCE = 0.35;
const SHORT_NUMBER_SCALE = 1.11;
// Margin the finder leaves around the number, in 360-wide pixels.
const NUMBER_PAD = 1;

function digitsShown(number) {
  const perHeight = number.width / number.digitHeight;
  for (let digits = 1; digits <= 9; digits++) {
    const commas = Math.floor((digits - 1) / 3);
    if (digits * DIGIT_ADVANCE + commas * COMMA_ADVANCE >= perHeight - 0.4) return digits;
  }
  return 9;
}

// The digits after the comma, cut out of `rgba` (width × height pixels,
// 4 bytes each) as glyphs: [{ from, to }] column ranges, left to right.
export function glyphs(rgba, width, height) {
  const lum = (x, y) => {
    const i = (y * width + x) * 4;
    return (rgba[i] * 299 + rgba[i + 1] * 587 + rgba[i + 2] * 114) / 1000;
  };
  let low = 255, high = 0;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      low = Math.min(low, lum(x, y));
      high = Math.max(high, lum(x, y));
    }
  }
  // High enough that the anti-aliased edges between touching digits stay
  // below it ("086" at 480 px wide merges into one glyph at 0.5).
  const level = low + (high - low) * 0.7;
  const ink = (x, y) => lum(x, y) > level;
  const used = (x) => {
    for (let y = 0; y < height; y++) if (ink(x, y)) return true;
    return false;
  };
  const list = [];
  // A glyph wider than 1.5 digits is several touching digits: split it by
  // the digit pitch (digits are 0.68 of their height apart; the crop has one
  // row of margin above and below).
  const pitch = Math.max(2, DIGIT_ADVANCE * (height - 2));
  for (let x = 0; x < width; x++) {
    if (!used(x)) continue;
    let to = x;
    while (to + 1 < width && used(to + 1)) to++;
    const parts = to - x + 1 > 1.5 * pitch ? Math.round((to - x + 2) / pitch) : 1;
    for (let k = 0; k < parts; k++) {
      list.push({
        from: x + Math.round((k * (to - x + 1)) / parts),
        to: x + Math.round(((k + 1) * (to - x + 1)) / parts) - 1,
      });
    }
    x = to;
  }
  return { list, ink };
}

// A "0": one hole through the middle. Down its centre column, ink at the
// top and the bottom with no ink in between (an 8 has ink in the middle,
// a 6 or a 9 a hole on one half only).
export function isZero(glyph, ink, height) {
  if (glyph.to - glyph.from < 2) return false;
  const x = Math.round((glyph.from + glyph.to) / 2);
  const rows = [];
  for (let y = 0; y < height; y++) rows.push(ink(x, y));
  const first = rows.indexOf(true);
  const last = rows.lastIndexOf(true);
  if (first < 0 || last - first < 4) return false;
  let y = first;
  while (y <= last && rows[y]) y++;
  const holeTop = y;
  while (y <= last && !rows[y]) y++;
  const holeBottom = y - 1;
  // The hole spans most of the height and ends on the bottom stroke.
  return holeBottom - holeTop + 1 >= (last - first + 1) * 0.45 && rows.slice(y, last + 1).every(Boolean);
}

// The digits the glyphs show, read against the game's 9-row font: each
// glyph's ink, resampled to each digit's grid, goes to the closest digit.
// Null when one is too far from every digit (then the pixels are copied).
export function readDigits(list, ink, height) {
  let top = height, bottom = -1;
  for (const glyph of list) {
    for (let y = 0; y < height; y++) {
      for (let x = glyph.from; x <= glyph.to; x++) {
        if (ink(x, y)) { top = Math.min(top, y); bottom = Math.max(bottom, y); }
      }
    }
  }
  if (bottom < 0) return null;
  let text = '';
  for (const glyph of list) {
    const w = glyph.to - glyph.from + 1, h = bottom - top + 1;
    let best = null, distance = Infinity;
    for (const [digit, mask] of Object.entries(MASKS[9])) {
      if (digit === ',') continue;
      const rows = 9, cols = mask[0].length;
      let d = 0;
      for (let gy = 0; gy < rows; gy++) {
        for (let gx = 0; gx < cols; gx++) {
          // Ink share of the glyph's cell under this mask pixel.
          let on = 0, all = 0;
          for (let y = Math.floor((gy * h) / rows); y < Math.max(Math.floor((gy * h) / rows) + 1, Math.floor(((gy + 1) * h) / rows)); y++) {
            for (let x = Math.floor((gx * w) / cols); x < Math.max(Math.floor((gx * w) / cols) + 1, Math.floor(((gx + 1) * w) / cols)); x++) {
              all++;
              if (ink(glyph.from + x, top + y)) on++;
            }
          }
          d += (on / all - (mask[gy][gx] === '#' ? 1 : 0)) ** 2;
        }
      }
      d /= rows * cols;
      if (d < distance) { best = digit; distance = d; }
    }
    if (distance > 0.15) return null;
    text += best;
  }
  return text;
}

// The chosen number in the game's style: 1,234,567.
function grouped(value) {
  return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// The colour of the digits: the mean of the brightest pixels of `rgba`
// (the copied digits), as [r, g, b].
function inkColour(rgba) {
  let high = 0;
  for (let i = 0; i < rgba.length; i += 4) high = Math.max(high, rgba[i] + rgba[i + 1] + rgba[i + 2]);
  const sum = [0, 0, 0];
  let n = 0;
  for (let i = 0; i < rgba.length; i += 4) {
    if (rgba[i] + rgba[i + 1] + rgba[i + 2] >= high * 0.9) {
      sum[0] += rgba[i]; sum[1] += rgba[i + 1]; sum[2] += rgba[i + 2]; n++;
    }
  }
  return n ? sum.map((v) => v / n) : [255, 255, 255];
}

// Writes `text` (digits and commas) into `canvas` in the game's font, as
// the game draws it at 480 px wide with digits `rows` (9 or 10) pixels
// high: ink over `paper`, by each pixel's coverage.
function drawText(canvas, text, rows, ink, paper) {
  const { width, height, cover } = shade(text, rows);
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d');
  const image = context.createImageData(width, height);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const a = cover[y][x];
      const i = (y * width + x) * 4;
      for (let c = 0; c < 3; c++) image.data[i + c] = paper[c] + (ink[c] - paper[c]) * a;
      image.data[i + 3] = 255;
    }
  }
  context.putImageData(image, 0, 0);
}

// The counters that can be cut or rewritten: where to look, their options,
// and the gateway's route for browsers that cannot read the video.
const COUNTERS = {
  emerald: { area: AREA, mode: 'emeraldMode', count: 'emeraldCount', path: '/emerald-mask' },
  diamond: { area: DIAMOND_AREA, mode: 'diamondMode', count: 'diamondCount', path: '/emerald-mask?counter=diamond' },
};

// Every 250 ms, finds the counter (emeralds by default) and covers it with the bar's
// colour in api.layer, then writes over it, at the game's size for that many
// digits: the chosen number if there is one, else the digits after the
// comma, copied from the video, without leading zeros ("284,086" shows 86).
// Returns a function that stops it.
function startEmeraldMask(api, state, counter = COUNTERS.emerald) {
  const AREA = counter.area;
  const box = document.createElement('div');
  box.style.cssText = 'position:absolute;display:none;box-sizing:border-box';
  // The digits sit on the game's baseline: bigger digits grow upwards, so
  // that they line up with the diamonds' digits, as the game draws them.
  // Scaled smoothly, like the browser scales the video around them.
  const copy = document.createElement('canvas');
  copy.style.cssText = 'position:absolute;display:block';
  box.append(copy);
  api.layer.appendChild(box);
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d', { willReadFrequently: true });
  const scratch = document.createElement('canvas').getContext('2d');
  let gl = null;
  try {
    gl = document.createElement('canvas').getContext('webgl', { preserveDrawingBuffer: true });
  } catch {
    gl = null;
  }
  let server = false;
  let lastServer = 0;
  let method = null;
  const tried = {};
  let busy = false;
  // rgba: the search area's pixels (width areaWidth), or for the gateway's
  // answer the decimals' own pixels as base64 RGB.
  const show = (mask, problem, rgba = null, areaWidth = 0) => {
    const wanted = String(api.setting(counter.count) ?? '').replace(/\D/g, '').replace(/^0+(?=\d)/, '');
    if (mask && modeOf(api, counter) === 'cut') {
      const k = api.screenWidth() / 360;
      copy.style.display = 'none';
      // Half a pixel more on the left: the video's smoothing spreads the
      // comma's edge into the next column.
      const margin = 0.5 * (360 / (api.video()?.videoWidth || 360));
      Object.assign(box.style, {
        display: 'block', left: `${(mask.x - margin) * k}px`, top: `${mask.y * k}px`,
        width: `${(mask.width + margin) * k}px`, height: `${mask.height * k}px`, background: mask.color,
      });
    } else if (mask?.number && mask.decimals) {
      const k = api.screenWidth() / 360;
      const number = mask.number;
      // Digit height the game uses for 6 digits, then for the shown number.
      const sixDigitHeight = digitsShown(number) <= 5 ? number.digitHeight / SHORT_NUMBER_SCALE : number.digitHeight;
      const heightFor = (digits) => (digits <= 5 ? sixDigitHeight * SHORT_NUMBER_SCALE : sixDigitHeight);
      Object.assign(box.style, {
        display: 'block', left: `${number.x * k}px`, top: `${number.y * k}px`,
        // Wide enough to hide the game's number; the new one may be longer.
        width: `${number.width * k}px`, height: `${number.height * k}px`,
        background: mask.color,
      });
      // The digits' bottom inside the box (the box has 1 px of margin).
      const baseline = (NUMBER_PAD + number.digitHeight) * k;
      drawDecimals(mask, rgba, areaWidth, heightFor, k, baseline, wanted);
    } else {
      box.style.display = 'none';
    }
    const changed = state.found !== Boolean(mask) || state.problem !== problem;
    state.found = Boolean(mask);
    state.problem = problem;
    if (changed) api.refresh();
  };
  // Copies the digits after the comma into `copy`, leading zeros dropped,
  // scaled to the game's size for that many digits.
  const drawDecimals = (mask, rgba, areaWidth, heightFor, k, baseline, wanted) => {
    const box360 = mask.decimals.pixels;
    let crop;
    if (box360.rgb) {
      const rgb = Uint8Array.from(atob(box360.rgb), (c) => c.charCodeAt(0));
      crop = new Uint8ClampedArray(box360.width * box360.height * 4);
      for (let i = 0, j = 0; i < rgb.length; i += 3, j += 4) {
        crop[j] = rgb[i]; crop[j + 1] = rgb[i + 1]; crop[j + 2] = rgb[i + 2]; crop[j + 3] = 255;
      }
    } else if (rgba) {
      crop = new Uint8ClampedArray(box360.width * box360.height * 4);
      for (let y = 0; y < box360.height; y++) {
        const from = ((box360.y + y) * areaWidth + box360.x) * 4;
        crop.set(rgba.subarray(from, from + box360.width * 4), y * box360.width * 4);
      }
    } else {
      copy.style.display = 'none';
      return;
    }
    if (wanted) {
      // The game's font at its size for that many digits, in the colour of
      // the digits it replaces, drawn in 480 px wide pixels then scaled to
      // the screen like the video.
      const rows = Math.round(heightFor(wanted.length) * FONT.scale);
      drawText(copy, grouped(wanted), rows, inkColour(crop), mask.color.match(/\d+/g).map(Number));
      const below = FONT.below;
      Object.assign(copy.style, {
        display: 'block',
        left: `${NUMBER_PAD * k}px`,
        width: `${(copy.width / FONT.scale) * k}px`,
        height: `${(copy.height / FONT.scale) * k}px`,
        top: `${baseline - ((copy.height - below) / FONT.scale) * k}px`,
      });
      return;
    }
    const { list, ink } = glyphs(crop, box360.width, box360.height);
    // The digits after the comma, read and written again in the game's font
    // at the right size (the game's 5-digit font is not its 6-digit one
    // enlarged); copied as pixels when they cannot be read.
    const read = list.length ? readDigits(list, ink, box360.height) : null;
    if (read && !wanted) return drawDecimals(mask, rgba, areaWidth, heightFor, k, baseline, read.replace(/^0+(?=\d)/, ''));
    let first = 0;
    while (first < list.length - 1 && isZero(list[first], ink, box360.height)) first++;
    if (!list.length) {
      copy.style.display = 'none';
      return;
    }
    const from = list[first].from;
    const to = list[list.length - 1].to;
    const source = document.createElement('canvas');
    source.width = box360.width;
    source.height = box360.height;
    source.getContext('2d').putImageData(new ImageData(crop, box360.width, box360.height), 0, 0);
    // Source pixels per 360-wide pixel, then the zoom to the new digit size.
    const sourceScale = box360.width / mask.decimals.width;
    const zoom = heightFor(list.length - first) / mask.number.digitHeight;
    copy.width = to - from + 1;
    copy.height = box360.height;
    copy.getContext('2d').drawImage(source, from, 0, copy.width, copy.height, 0, 0, copy.width, copy.height);
    // Rows of the crop below the digits' bottom (the comma's tail row).
    const digitBottom = Math.round((mask.number.y + NUMBER_PAD + mask.number.digitHeight - AREA.y) * sourceScale);
    const below = box360.y + box360.height - digitBottom;
    const height = (copy.height / sourceScale) * zoom * k;
    Object.assign(copy.style, {
      display: 'block',
      left: `${NUMBER_PAD * k}px`,
      width: `${(copy.width / sourceScale) * zoom * k}px`,
      height: `${height}px`,
      top: `${baseline - height + (below / sourceScale) * zoom * k}px`,
    });
  };
  const capture = async (video, name, area) => {
    context.clearRect(0, 0, area.width, area.height);
    await CAPTURE_METHODS[name](video, context, area, scratch, gl);
    return context.getImageData(0, 0, area.width, area.height).data;
  };
  const timer = window.setInterval(async () => {
    if (busy) return;
    const video = api.video();
    if (!context || !scratch) return show(null, 'canvas');
    if (!video?.videoWidth) return show(null, 'video');
    busy = true;
    try {
      if (server) {
        if (Date.now() - lastServer < SERVER_MS) return;
        lastServer = Date.now();
        const answer = await api.get(counter.path);
        if (!answer) throw new Error('gateway');
        show(answer.mask, answer.mask ? null : `${answer.reason}, serveur`);
        return;
      }
      const scale = video.videoWidth / 360;
      const area = {
        x: Math.round(AREA.x * scale),
        y: Math.round(AREA.y * scale),
        width: Math.round(AREA.width * scale),
        height: Math.round(AREA.height * scale),
      };
      canvas.width = area.width;
      canvas.height = area.height;
      let pixels = null;
      for (const name of method ? [method] : Object.keys(CAPTURE_METHODS)) {
        try {
          pixels = await capture(video, name, area);
          tried[name] = blank(pixels) ? 'blank' : 'ok';
        } catch (error) {
          tried[name] = String(error?.message === 'none' ? 'none' : error?.name ?? error);
          pixels = null;
        }
        if (tried[name] === 'ok') {
          method = name;
          break;
        }
      }
      if (!method && Object.keys(tried).length === Object.keys(CAPTURE_METHODS).length) {
        server = true;
        return;
      }
      const why = {};
      const found = pixels ? findEmeraldMask(pixels, area.width, area.height, scale, why, AREA) : null;
      if (found) {
        // The finder counts from AREA; the area really starts at a whole
        // pixel. Without this the mask lands up to half a pixel off.
        const dx = area.x / scale - AREA.x;
        const dy = area.y / scale - AREA.y;
        found.x += dx; found.y += dy;
        found.number.x += dx; found.number.y += dy;
        found.decimals.x += dx;
      }
      const methods = Object.entries(tried).map(([name, result]) => `${name}:${result}`).join(' ');
      show(found, found ? null : `${why.reason ?? 'capture'}, ${video.videoWidth}×${video.videoHeight}, ${methods}`,
        pixels, area.width);
    } catch (error) {
      show(null, String(error?.message ?? error));
    } finally {
      busy = false;
    }
  }, 250);
  return () => {
    window.clearInterval(timer);
    box.remove();
    state.found = false;
    state.problem = null;
  };
}

// '' (unchanged), 'cut' or 'rewrite'.
function modeOf(api, counter) {
  return api.setting(counter.mode) ?? '';
}

function emeraldMode(api) {
  return modeOf(api, COUNTERS.emerald);
}

export default function activate(api) {
  api.addTranslations(ENGLISH);
  const emerald = { found: false, problem: null };
  let stopEmerald = null;
  const setEmerald = (on) => {
    if (on && !stopEmerald) stopEmerald = startEmeraldMask(api, emerald);
    if (!on && stopEmerald) {
      stopEmerald();
      stopEmerald = null;
    }
  };
  setEmerald(Boolean(emeraldMode(api)));
  const diamond = { found: false, problem: null };
  let stopDiamond = null;
  const setDiamond = (on) => {
    if (on && !stopDiamond) stopDiamond = startEmeraldMask(api, diamond, COUNTERS.diamond);
    if (!on && stopDiamond) {
      stopDiamond();
      stopDiamond = null;
    }
  };
  setDiamond(Boolean(modeOf(api, COUNTERS.diamond)));

  // Launch state from the gateway, followed while a launch runs.
  const launch = { state: 'idle', message: '' };
  let poll = null;
  const follow = async () => {
    const answer = await api.get('/launch').catch(() => null);
    if (answer) Object.assign(launch, answer);
    api.refresh();
    const running = ['starting', 'loading'].includes(launch.state);
    if (running && !poll) poll = window.setInterval(follow, 2000);
    if (!running && poll) {
      window.clearInterval(poll);
      poll = null;
    }
  };
  follow();

  // The game's screen, asked to the gateway only while the options panel
  // shows it: each render asks again once the last answer is 3 s old.
  const SCREENS = {
    title: 'Écran titre', save: 'Choix de la sauvegarde', battle: 'Combat',
    saver: 'Économie d’énergie', other: 'Autre (menu, chargement…)',
    menu: 'Menu du jeu', away: 'Autre application',
  };
  const GRADES = { Common: 'Commun', Great: 'Supérieur', Rare: 'Rare', Epic: 'Épique', Legendary: 'Légendaire' };
  const COLOURS = { green: 'verte', blue: 'bleue', red: 'rouge' };
  const stageRow = (label, value) => ({
    type: 'status', label, visible: () => Boolean(screen.answer?.stage?.name), value,
  });
  const screen = { answer: null, at: 0, busy: false, timer: null };
  // The last stage number read, kept in this browser so that the gateway
  // still knows it after a restart (it reads it only in Power Saving Mode).
  const STORE = 'cloudphone-slayer-legend-stage';
  let remembered = null;
  try {
    remembered = Number(window.localStorage.getItem(STORE)) || null;
  } catch {
    remembered = null;
  }
  const watchScreen = () => {
    if (screen.busy || Date.now() - screen.at < 3000) return;
    screen.busy = true;
    api.get(remembered ? `/screen?known=${remembered}` : '/screen').catch(() => null).then((answer) => {
      const number = answer?.stage?.checked ? answer.stage.number : null;
      if (number && number !== remembered) {
        remembered = number;
        try {
          window.localStorage.setItem(STORE, String(number));
        } catch {
          // Not kept: read again in Power Saving Mode.
        }
      }
      Object.assign(screen, { answer, at: Date.now(), busy: false });
      api.refresh();
      window.clearTimeout(screen.timer);
      screen.timer = window.setTimeout(api.refresh, 3000);
    });
  };

  // The mode (mpw18 farming by default, or a timed mode: mpw4 farming, free
  // play, the mine) runs in the gateway; this browser's
  // options are sent to it when they change, and on load if the gateway has
  // not been told since it started. Its state is asked every 10 s.
  const farm = { answer: null, timer: null, stages: null };
  // This browser's copy of when the timed mode ends (Unix seconds), as the
  // gateway last said; sent again after a gateway restart.
  const UNTIL = 'cloudphone-slayer-legend-mode-until';
  const load = (name) => {
    try {
      return window.localStorage.getItem(name);
    } catch {
      return null;
    }
  };
  const keep = (name, value) => {
    try {
      if (value) window.localStorage.setItem(name, String(value));
      else window.localStorage.removeItem(name);
    } catch {
      // Not kept: lost on reload.
    }
  };
  const mode = () => api.setting('mode') || 'mpw18';
  const modeOptions = () => ({
    mode: mode(),
    until: farm.answer?.until ?? (Number(load(UNTIL)) || null),
    stage18: Number(api.setting('stage18')) || null,
    stage4: Number(api.setting('stage4')) || null,
    highest: Number(api.setting('highestStage')) || null,
    floor: Number(api.setting('mineFloor')) || null,
    area: Number(api.setting('mineArea') || 1),
  });
  const left = () => {
    const seconds = (farm.answer?.until ?? 0) - Date.now() / 1000;
    if (!farm.answer?.until || seconds <= 0) return api.tr('Sans limite');
    const minutes = Math.ceil(seconds / 60);
    const text = minutes >= 60 ? `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')}` : `${minutes} min`;
    const end = new Date(farm.answer.until * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return `${api.tr('reste {time}', { time: text })} (${end})`;
  };
  const remember = (answer) => {
    farm.answer = answer;
    if (answer) keep(UNTIL, answer.until);
  };
  const askMode = async () => {
    remember(await api.get('/mode').catch(() => null));
    api.refresh();
    window.clearTimeout(farm.timer);
    farm.timer = window.setTimeout(askMode, 10000);
  };
  const sendMode = async () => {
    const result = await api.post('/mode', modeOptions()).catch(() => null);
    if (result?.ok) remember(result.body);
    else if (result) farm.error = result.body?.error ?? `HTTP ${result.status}`;
    await askMode();
  };
  const moveTimer = async (minutes) => {
    const result = await api.post('/mode/timer', { add: minutes }).catch(() => null);
    if (result?.ok) remember(result.body);
    api.refresh();
  };
  // The mpw18 and mpw4 stages up to the highest one unlocked.
  const loadStages = async () => {
    const highest = Number(api.setting('highestStage')) || remembered || '';
    farm.stages = await api.get(`/stages?highest=${highest}`).catch(() => null);
    api.refresh();
  };
  const DOTS = { green: '🟢', blue: '🔵', red: '🔴' };
  const stageChoices = (mpw) => [
    { value: '', label: api.tr('— choisir —') },
    ...(farm.stages?.[`mpw${mpw}`] ?? []).map((stage) => ({
      value: String(stage.number),
      label: `${DOTS[stage.colour] ?? '⚪'} mpw${mpw} · ${stage.number}`,
    })),
  ];
  api.get('/mode').catch(() => null).then((answer) => {
    // After a gateway restart it knows nothing: send this browser's options.
    if (answer && !answer.configured) {
      farm.answer = null;
      sendMode();
    } else {
      remember(answer);
      askMode();
    }
  });
  loadStages();

  // Gold per second, measured by the gateway (a reading every 10 s, the
  // slope over 5 minutes), written in brackets after the game's gold
  // counter, where the gateway last read it.
  const gold = { answer: null, timer: null, font: null };
  // Written in the counter's own pixel font (from the gateway) at its
  // size: one game pixel is one cell, outlined in black like the game.
  const label = document.createElement('canvas');
  label.style.cssText = 'position:absolute;image-rendering:pixelated';
  api.get('/gold-font').catch(() => null).then((font) => {
    gold.font = font;
    showGold();
  });
  // Lines of text on a canvas, `cell` CSS pixels per game pixel. Letters
  // without accents: the font has none.
  const drawText = (canvas, lines, cell) => {
    const plain = (text) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    const glyphLines = lines.map((text) => [...plain(text)].map((c) => gold.font.glyphs[c]).filter(Boolean));
    const rows = gold.font.height;
    // A game pixel of space between glyphs, one round the text for the
    // outline, two between lines.
    const widths = glyphLines.map((glyphs) => glyphs.reduce((sum, glyph) => sum + glyph[0].length + 1, 0) + 1);
    const width = Math.max(...widths);
    const height = lines.length * (rows + 2) + (lines.length - 1) * 2;
    const scale = cell * (window.devicePixelRatio || 1);
    canvas.width = Math.ceil(width * scale);
    canvas.height = Math.ceil(height * scale);
    canvas.style.width = `${width * cell}px`;
    canvas.style.height = `${height * cell}px`;
    const context = canvas.getContext('2d');
    for (const [colour, grow] of [['#000', 1], ['#ffa31a', 0]]) {
      context.fillStyle = colour;
      glyphLines.forEach((glyphs, line) => {
        const base = 1 + line * (rows + 4);
        let pen = 1;
        for (const glyph of glyphs) {
          glyph.forEach((row, y) => [...row].forEach((ink, x) => {
            if (ink === '#') {
              // Whole device pixels: fractional edges leave seams between cells.
              const left = Math.round((pen + x - grow) * scale);
              const top = Math.round((base + y - grow) * scale);
              context.fillRect(left, top, Math.round((pen + x + 1 + grow) * scale) - left,
                Math.round((base + y + 1 + grow) * scale) - top);
            }
          }));
          pen += glyph[0].length + 1;
        }
      });
    }
  };
  // The selected mode, under the player's level (top left), and below it
  // "(défaut)" or the time left on the timer.
  const modeLabel = document.createElement('canvas');
  modeLabel.style.cssText = 'position:absolute;image-rendering:pixelated;left:3%;top:5.6%';
  const MODE_NAMES = { mpw18: 'Farming mpw18', mpw4: 'Farming mpw4', free: 'Jeu libre', mine: 'Mine fermée' };
  let modeDrawn = '';
  const showMode = (shown) => {
    if (!shown) {
      modeLabel.remove();
      modeDrawn = '';
      return;
    }
    if (!modeLabel.isConnected) api.layer.appendChild(modeLabel);
    const current = farm.answer?.mode ?? mode();
    const seconds = Math.max(0, Math.round((farm.answer?.until ?? 0) - Date.now() / 1000));
    const two = (n) => String(n).padStart(2, '0');
    const time = seconds >= 3600
      ? `${Math.floor(seconds / 3600)}:${two(Math.floor(seconds / 60) % 60)}:${two(seconds % 60)}`
      : `${two(Math.floor(seconds / 60))}:${two(seconds % 60)}`;
    const lines = [
      api.tr(MODE_NAMES[current] ?? current).toUpperCase(),
      `(${(current === 'mpw18' || !farm.answer?.until ? api.tr('défaut') : time).toUpperCase()})`,
    ];
    // As high as the level's text above it (8 game pixels, the screen
    // being 1040 of them high), not the gold counter's 13.
    const cell = api.layer.offsetHeight / 1040 * 8 / gold.font.height;
    const key = `${lines.join('|')}@${cell}`;
    if (key !== modeDrawn) {
      drawText(modeLabel, lines, cell);
      modeDrawn = key;
    }
  };
  const modeTick = window.setInterval(() => {
    if (modeLabel.isConnected) showMode(true);
  }, 1000);
  const goldText = () => {
    const answer = gold.answer;
    if (!answer) return '…';
    if (answer.rate_text) return `${answer.span < 285 ? '~' : ''}${answer.rate_text}/s`;
    return answer.read ? api.tr('pas encore mesuré') : api.tr('non visible (économie d’énergie ?)');
  };
  const showGold = () => {
    const answer = gold.answer;
    const box = answer?.box;
    // Only while the counter was read lately: it moves with the game's
    // panels and Power Saving Mode hides it.
    const fresh = box && answer.read && Date.now() / 1000 - answer.read < 25;
    showMode(Boolean(fresh && gold.font));
    if (api.setting('goldOverlay') === 'off' || !fresh || !gold.font) {
      label.remove();
      return;
    }
    if (!label.isConnected) api.layer.appendChild(label);
    // One game pixel on this screen: the counter's text is font.height high.
    const cell = (box[3] - box[1]) * api.layer.offsetHeight / gold.font.height;
    label.style.left = `${box[2] * api.layer.offsetWidth + 3 * cell}px`;
    label.style.top = `${box[1] * api.layer.offsetHeight - cell}px`;
    // "~" while the 5-minute window is not full yet.
    const partial = answer.span < 285 ? '~' : '';
    drawText(label, [`(${answer.rate_text ? `${partial}${answer.rate_text}/s` : '...'})`], cell);
  };
  const askGold = async () => {
    gold.answer = await api.get('/gold').catch(() => null);
    showGold();
    api.refresh();
    window.clearTimeout(gold.timer);
    gold.timer = window.setTimeout(askGold, 10000);
  };
  askGold();

  // Navigation trace: each tap on the game goes to the gateway, which
  // records the screens before and after it (screen name and a small grey
  // thumbnail, never a screenshot). On unless the user turned it off.
  // Fire and forget: a lost tap is only a missing edge.
  const tracing = () => api.setting('traceTaps') !== 'off';
  const stopTrace = api.onTap?.((tap) => {
    if (tracing()) api.post('/trace', tap).catch(() => null);
  });
  // The counts, asked only while the panel shows them, at most every 5 s.
  const traced = { answer: null, at: 0, busy: false };
  const watchTrace = () => {
    if (traced.busy || Date.now() - traced.at < 5000) return;
    traced.busy = true;
    api.get('/trace').catch(() => null).then((answer) => {
      Object.assign(traced, { answer, at: Date.now(), busy: false });
      api.refresh();
    });
  };

  return {
    options: [
      { type: 'section', key: 'game', label: 'Jeu' },
      {
        type: 'status', label: 'Écran détecté',
        value: () => {
          watchScreen();
          const name = screen.answer?.screen;
          if (!screen.at) return '…';
          return api.tr(name ? SCREENS[name] ?? name : 'Pas de capture d’écran');
        },
      },
      {
        type: 'status', label: 'Stage sélectionné',
        visible: () => Boolean(screen.at),
        value: () => {
          const stage = screen.answer?.stage;
          if (!stage?.number) return api.tr('inconnu : passe en mode économie d’énergie pour le lire');
          const text = `${stage.number}${stage.name ? ` · ${stage.name}` : ''}`;
          return stage.checked ? text : `${text} (${api.tr('vu en mode économie d’énergie, à confirmer')})`;
        },
      },
      stageRow('Monstres par vague', () => String(screen.answer.stage.monsters_per_wave ?? '–')),
      stageRow('Équipement lâché', () => {
        const stage = screen.answer.stage;
        const [grade, level] = String(stage.grade ?? '').split(' ');
        return `${api.tr(stage.drop === 'A' ? 'Accessoire' : 'Arme')}, ${api.tr(GRADES[grade] ?? grade)} ${level ?? ''}`.trim();
      }),
      stageRow('Couleur des âmes', () => {
        const stage = screen.answer.stage;
        if (!stage.soul_colour) return '–';
        const colour = api.tr(COLOURS[stage.soul_colour] ?? stage.soul_colour);
        return stage.soul_colour_confirmed ? colour : `${colour} (${api.tr('déduite, non vérifiée')})`;
      }),
      {
        type: 'action', label: 'Lancer le jeu', button: 'Lancer',
        disabled: () => ['starting', 'loading'].includes(launch.state),
        run: async () => {
          const result = await api.post('/launch');
          if (!result.ok) {
            Object.assign(launch, {
              state: 'failed', message: result.status === 409 ? 'Un lancement est déjà en cours' : result.body.error ?? `HTTP ${result.status}`,
            });
          }
          await follow();
        },
      },
      {
        type: 'status', label: 'Lancement',
        visible: () => launch.state !== 'idle',
        value: () => api.tr(launch.message || launch.state),
      },
      { type: 'section', key: 'mode', label: 'Mode et farming' },
      {
        type: 'choice', key: 'mode', label: 'Mode',
        choices: [
          { value: 'mpw18', label: 'Farming mpw18 (par défaut)' },
          { value: 'mpw4', label: 'Farming mpw4' },
          { value: 'free', label: 'Jeu libre' },
          { value: 'mine', label: 'Mine fermée' },
        ],
      },
      // Each mode's settings, apart from choosing the mode: in a dialog.
      {
        type: 'dialog', label: 'Farming mpw18', title: 'Configuration : farming mpw18',
        options: [
          {
            type: 'number', key: 'highestStage', label: 'Plus haut stage débloqué', placeholder: () => String(remembered ?? ''),
          },
          { type: 'choice', key: 'stage18', label: 'Stage mpw18', choices: () => stageChoices(18) },
          { type: 'status', label: 'Arme, gravure, réglages de combat', value: () => api.tr('à venir') },
        ],
      },
      {
        type: 'dialog', label: 'Farming mpw4', title: 'Configuration : farming mpw4',
        options: [
          {
            type: 'number', key: 'highestStage', label: 'Plus haut stage débloqué', placeholder: () => String(remembered ?? ''),
          },
          { type: 'choice', key: 'stage4', label: 'Stage mpw4', choices: () => stageChoices(4) },
        ],
      },
      {
        type: 'dialog', label: 'Mine fermée', title: 'Configuration : mine fermée',
        options: [
          { type: 'number', key: 'mineFloor', label: 'Étage à farmer', placeholder: '161' },
          {
            type: 'choice', key: 'mineArea', label: 'Zone à farmer',
            choices: [1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: String(n) })),
          },
          { type: 'status', label: 'Plumes', value: () => '3' },
        ],
      },
      {
        type: 'status', label: 'Minuteur',
        visible: () => mode() !== 'mpw18',
        value: left,
      },
      {
        type: 'buttons', label: 'Ajuster (minutes)',
        visible: () => mode() !== 'mpw18',
        buttons: [30, 5, 1, -1, -5, -30].map((m) => ({
          label: m > 0 ? `+${m}` : `−${-m}`,
          run: () => moveTimer(m),
          disabled: () => m < 0 && !farm.answer?.until,
        })),
      },
      {
        type: 'status', label: 'État',
        value: () => {
          if (farm.error) return farm.error;
          if (mode() === 'mine' && !Number(api.setting('mineFloor'))) return api.tr('Choisis l’étage et la zone');
          const answer = farm.answer;
          if (!answer) return '…';
          if (answer.mode === 'mine') {
            const warning = answer.mine?.gold === false ? ` ⚠ ${api.tr('plus de parchemin doré')}` : '';
            return api.tr(answer.mine?.message || 'Mine') + warning;
          }
          return api.tr(answer.message || 'Farming mpw18');
        },
      },
      { type: 'section', key: 'gold', label: 'Gold' },
      { type: 'status', label: 'Gold par seconde', value: goldText },
      {
        type: 'choice', key: 'goldOverlay', label: 'Overlay gold/s',
        choices: [{ value: 'on', label: 'Affiché' }, { value: 'off', label: 'Masqué' }],
      },
      { type: 'section', key: 'navigation', label: 'Navigation', folded: true },
      {
        type: 'choice', key: 'traceTaps', label: 'Enregistrer mes parcours',
        choices: [{ value: 'on', label: 'Activé' }, { value: 'off', label: 'Désactivé' }],
      },
      {
        type: 'status', label: 'Parcours enregistrés',
        value: () => {
          watchTrace();
          const answer = traced.answer;
          if (!answer) return '…';
          if (!answer.enabled) return api.tr('indisponible (passerelle sans dossier de données)');
          return api.tr('{nodes} écrans, {taps} appuis', { nodes: answer.nodes, taps: answer.taps ?? answer.edges });
        },
      },
      { type: 'section', key: 'emerald', label: 'Émeraudes', folded: true },
      {
        type: 'choice', key: 'emeraldMode', label: 'Compteur d’émeraudes',
        choices: [
          { value: '', label: 'Inchangé' },
          { value: 'cut', label: 'Coupé à la virgule' },
          { value: 'rewrite', label: 'Réécrit' },
        ],
      },
      {
        type: 'number', key: 'emeraldCount', label: 'Nombre affiché (vide : après la virgule)', placeholder: '86',
        visible: () => emeraldMode(api) === 'rewrite',
      },
      {
        type: 'status', label: 'Détection du compteur',
        visible: () => Boolean(stopEmerald),
        value: () => (emerald.found ? api.tr('détecté')
          : emerald.problem ? `${api.tr('non détecté')} (${emerald.problem})` : api.tr('non détecté')),
      },
      { type: 'section', key: 'diamond', label: 'Diamants', folded: true },
      {
        type: 'choice', key: 'diamondMode', label: 'Compteur de diamants',
        choices: [
          { value: '', label: 'Inchangé' },
          { value: 'cut', label: 'Coupé à la virgule' },
          { value: 'rewrite', label: 'Réécrit' },
        ],
      },
      {
        type: 'number', key: 'diamondCount', label: 'Nombre affiché (vide : après la virgule)', placeholder: '786',
        visible: () => modeOf(api, COUNTERS.diamond) === 'rewrite',
      },
      {
        type: 'status', label: 'Détection du compteur',
        visible: () => Boolean(stopDiamond),
        value: () => (diamond.found ? api.tr('détecté')
          : diamond.problem ? `${api.tr('non détecté')} (${diamond.problem})` : api.tr('non détecté')),
      },
    ],
    onSetting: (key, value) => {
      if (key === 'emeraldMode') setEmerald(Boolean(value));
      if (key === 'diamondMode') setDiamond(Boolean(value));
      if (key === 'highestStage') loadStages();
      if (key === 'goldOverlay') showGold();
      if (['mode', 'stage18', 'stage4', 'highestStage', 'mineFloor', 'mineArea'].includes(key)) {
        farm.error = null;
        sendMode();
      }
    },
    dispose: () => {
      setEmerald(false);
      setDiamond(false);
      stopTrace?.();
      if (poll) window.clearInterval(poll);
      window.clearTimeout(screen.timer);
      window.clearTimeout(farm.timer);
      window.clearTimeout(gold.timer);
      window.clearInterval(modeTick);
      label.remove();
      modeLabel.remove();
    },
  };
}
