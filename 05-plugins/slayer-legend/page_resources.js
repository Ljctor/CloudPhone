// Only icons cut from real Slayer Legend captures belong here. Unknown
// icons stay absent until a capture of their actual screen is available.
import { GOLD, SOULS } from './page_icons.js';

// Emerald icon, 22x20 pixels, from fixtures/battle_emerald.txt. Its dark
// battle-bar background is made transparent; the shape is unchanged.
const EMERALD_GAME = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABYAAAAUCAYAAACJfM0wAAACDElEQVR42rWUy2tTQRTGf2futfUNUeqiiCZXRbIp1ZiItCCC/4CvqxbXFbdarOBaKLQVd4IroUo1sfV/8BWsSZsuRBdyiQ9ceJHSmoUkkxkXV1okpCSYzmbgnDMfZ77znU+SiV7qxqB1nU4eBVCvGzp9FICFjQGWDQB2Wy0MBpaij5no8vK75L+Bg7HQqkH1b+x6aL25HlmXinVBj/+yU1dGALBzUcwUdrI9vZcgEzYdjyQTvVRrGmsba8a+7bP+rQCGl3iWyESgEinInyygrItxuvEmt0rLHQcno24unI6BbMNSw1LD5Xdj7eCybQk4OBXaqcd9DJUXeX7wC7lEEkcs52UeULhUyd04hjEKxDD95MjacNcdXmUHV998YvpEf8QXdc6wwAwZ8uYzAAPqELM3+zCAP/OuocemVKg9UUpEc475hnxef+TseAHHuhjrtqgKq6gsV9DiULVd5Ej/LbYoJSglpN3DYKAmGmy1fbmJCC66Ie7nimRHU7SlY6/QJc6Eg4PmcvEthk10P+xGA2kOMP5A4Cv4E++5NFFCZhXe65i0rOPgRWizXoqL5QWexo/i3y/BiiY7msK/WwSzGYUmfi8m7a30bZehO4vYrmgpstf61x78AGJbkNJK+5u32rkfWnfYRX/QrNJdBO9Rc69oyYS8bI+Uv/+0CoVIhLX/ZQfcDSD+andbtv0Hp1nF+cn2q2IAAAAASUVORK5CYII=';

export const RESOURCE_ICONS = { gold: GOLD, emerald: EMERALD_GAME };
for (const [colour, icon] of Object.entries(SOULS)) RESOURCE_ICONS[`soul_${colour}`] = icon;
