// Existing game crops for gold/souls; vector symbols for the other resources.
// These symbols identify a counter, never participate in screen recognition.
import { GOLD, EMERALD, DIAMOND, SOULS } from './page_icons.js';

const symbol = (body, colour) => `data:image/svg+xml,${encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="${colour}" stroke="#738096" stroke-width="1.2">${body}</svg>`
)}`;
const stone = '<path d="M4 7 12 2 21 8 19 19 8 22 2 15Z"/><path d="m4 7 10 3 7-2M14 10l-6 12" fill="none"/>';
const feather = '<path d="M4 21C3 10 10 2 21 2c1 10-7 17-15 16Z"/><path d="M3 23 17 7M9 16v-5m3 2h5" fill="none"/>';
export const RESOURCE_ICONS = {
  gold: GOLD, diamond: DIAMOND, emerald: EMERALD,
  cubes: symbol('<path d="m12 2 10 5v10l-10 5-10-5V7Z"/><path d="m2 7 10 5 10-5M12 12v10" fill="none"/>', '#a9d9f2'),
  crystals: symbol('<path d="m7 4 5-3 5 3 1 15-6 4-6-4Z"/><path d="M12 1v22M7 4l5 3 5-3" fill="none"/>', '#d2a2fa'),
  dice: symbol('<rect x="3" y="3" width="18" height="18" rx="3"/><g fill="#263044"><circle cx="7" cy="7" r="1.5"/><circle cx="17" cy="7" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="7" cy="17" r="1.5"/><circle cx="17" cy="17" r="1.5"/></g>', '#f4f2e4'),
  dragon_power: symbol('<path d="m3 18 4-8-2-7 8 4 6-4 2 8-4 4-2 7-4-5Z"/><circle cx="15" cy="10" r="1" fill="white"/>', '#e97b43'),
  dragon_spark: symbol('<path d="m14 1-11 13h8l-1 9L22 9h-9Z"/>', '#ffda62'),
  black_mana: symbol('<path d="M12 2C9 8 3 12 4 17c1 7 15 7 16 0 1-5-5-9-8-15Z"/><path d="M8 13q-3 5 2 6" fill="none" stroke="#c4a1ff"/>', '#302344'),
};
for (const [colour, icon] of Object.entries(SOULS)) RESOURCE_ICONS[`soul_${colour}`] = icon;
for (const [colour, fill] of Object.entries({ green: '#65ce73', blue: '#5baaff', red: '#f06767', yellow: '#f5db61' })) {
  RESOURCE_ICONS[`stone_${colour}`] = symbol(stone, fill);
}
for (const [colour, fill] of Object.entries({ white: '#faf7ec', green: '#65ce73', purple: '#ba82ee', black: '#292638' })) {
  RESOURCE_ICONS[`feather_${colour}`] = symbol(feather, fill);
}
