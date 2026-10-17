// Slayer Legend plugin, page side: loaded by the Cloud Phone page (see
// plugins.ts in part 04 for the API). Two features:
// - "Lancer le jeu": the gateway starts the game and brings it to the
//   battle screen (TAP TO START, then Confirm on the latest save).
// - Rewrite the emerald counter: the game's counter is covered with the
//   bar's colour and, at the game's size for that many digits, either the
//   digits after its comma (leading zeros dropped) or a number the user
//   chose are written over it, on this screen only. Nothing is sent to
//   Android.
import { AREA, findEmeraldMask } from './emerald_mask.js';

const ENGLISH = {
  'Lancer le jeu': 'Launch the game',
  'Lancer': 'Launch',
  'Lancement': 'Launch',
  'Réécrire le compteur d’émeraudes': 'Rewrite the emerald counter',
  'Nombre affiché (vide : après la virgule)': 'Number shown (empty: after the comma)',
  'Compteur d’émeraudes': 'Emerald counter',
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
// Cap height of the drawn font, as a fraction of its font size.
const CAP_HEIGHT = 0.72;

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
function glyphs(rgba, width, height) {
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
  const level = low + (high - low) * 0.5;
  const ink = (x, y) => lum(x, y) > level;
  const used = (x) => {
    for (let y = 0; y < height; y++) if (ink(x, y)) return true;
    return false;
  };
  const list = [];
  for (let x = 0; x < width; x++) {
    if (!used(x)) continue;
    let to = x;
    while (to + 1 < width && used(to + 1)) to++;
    list.push({ from: x, to });
    x = to;
  }
  return { list, ink };
}

// A "0": one hole through the middle. Down its centre column, ink at the
// top and the bottom with no ink in between (an 8 has ink in the middle,
// a 6 or a 9 a hole on one half only).
function isZero(glyph, ink, height) {
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

// The chosen number in the game's style: 1,234,567.
function grouped(value) {
  return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// Every 250 ms, finds the emerald counter and covers it with the bar's
// colour in api.layer, then writes over it, at the game's size for that many
// digits: the chosen number if there is one, else the digits after the
// comma, copied from the video, without leading zeros ("284,086" shows 86).
// Returns a function that stops it.
function startEmeraldMask(api, state) {
  const box = document.createElement('div');
  box.style.cssText = 'position:absolute;display:none;overflow:visible;white-space:nowrap;color:#fff;'
    + 'font-family:"Arial Black","Arial",sans-serif;font-weight:900;line-height:1;'
    + 'text-shadow:0 0 1px #000,0 0 1px #000;align-items:center;box-sizing:border-box';
  const copy = document.createElement('canvas');
  copy.style.cssText = 'display:block;image-rendering:pixelated';
  const label = document.createElement('span');
  box.append(copy, label);
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
    const wanted = String(api.setting('emeraldCount') ?? '').replace(/\D/g, '').replace(/^0+(?=\d)/, '');
    if (mask?.number && mask.decimals) {
      const k = api.screenWidth() / 360;
      const number = mask.number;
      // Digit height the game uses for 6 digits, then for the shown number.
      const sixDigitHeight = digitsShown(number) <= 5 ? number.digitHeight / SHORT_NUMBER_SCALE : number.digitHeight;
      const heightFor = (digits) => (digits <= 5 ? sixDigitHeight * SHORT_NUMBER_SCALE : sixDigitHeight);
      Object.assign(box.style, {
        display: 'flex', left: `${number.x * k}px`, top: `${number.y * k}px`,
        // Wide enough to hide the game's number; the new one may be longer.
        minWidth: `${number.width * k}px`, height: `${number.height * k}px`,
        background: mask.color, paddingLeft: `${k}px`,
      });
      if (wanted) {
        copy.style.display = 'none';
        label.style.display = '';
        label.textContent = grouped(wanted);
        box.style.fontSize = `${(heightFor(wanted.length) / CAP_HEIGHT) * k}px`;
      } else {
        label.style.display = 'none';
        drawDecimals(mask, rgba, areaWidth, heightFor, k);
      }
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
  const drawDecimals = (mask, rgba, areaWidth, heightFor, k) => {
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
    const { list, ink } = glyphs(crop, box360.width, box360.height);
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
    Object.assign(copy.style, {
      display: 'block',
      width: `${(copy.width / sourceScale) * zoom * k}px`,
      height: `${(copy.height / sourceScale) * zoom * k}px`,
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
        const answer = await api.get('/emerald-mask');
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
      const found = pixels ? findEmeraldMask(pixels, area.width, area.height, scale, why) : null;
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
  setEmerald(api.setting('emeraldMask'));

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

  return {
    options: [
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
      { type: 'toggle', key: 'emeraldMask', label: 'Réécrire le compteur d’émeraudes' },
      {
        type: 'number', key: 'emeraldCount', label: 'Nombre affiché (vide : après la virgule)', placeholder: '86',
        visible: () => Boolean(stopEmerald),
      },
      {
        type: 'status', label: 'Compteur d’émeraudes',
        visible: () => Boolean(stopEmerald),
        value: () => (emerald.found ? api.tr('détecté')
          : emerald.problem ? `${api.tr('non détecté')} (${emerald.problem})` : api.tr('non détecté')),
      },
    ],
    onSetting: (key, value) => {
      if (key === 'emeraldMask') setEmerald(value);
    },
    dispose: () => {
      setEmerald(false);
      if (poll) window.clearInterval(poll);
    },
  };
}
