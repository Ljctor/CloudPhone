// Small icons for a section's or the plugin's icon (plugins.ts: icon) and
// for the gold and soul rates. The emerald, the diamond and the plugin's
// sword are pixel art drawn here, each an SVG data URL, one rect per pixel.
// The gold coin and the four souls are the game's own, cut pixel for pixel
// from 480x1040 captures as small PNG data URLs, their background made
// clear: the coin from the battle screen, left of the gold earned, outside
// its black outline; the souls from the Soul Weapon screen's souls row,
// y 491-515, unmixed from the row's dark background, the box's corners left
// out. No other part of a capture is kept.

// rows: one string per pixel row, a character per pixel ('.' clear);
// palette: character -> CSS colour.
function sprite(rows, palette) {
  const rects = rows.flatMap((row, y) => [...row].map((c, x) => (palette[c]
    ? `<rect x="${x}" y="${y}" width="1" height="1" fill="${palette[c]}"/>` : ''))).join('');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${rows[0].length} ${rows.length}" `
    + `shape-rendering="crispEdges">${rects}</svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

const png = (data) => `data:image/png;base64,${data}`;

// The game's gold coin, 18x18.
export const GOLD = png('iVBORw0KGgoAAAANSUhEUgAAABIAAAASCAYAAABWzo5XAAACXklEQVR42p2Uy0tUURjAf+fcxzyc0cYcx2jUpIaSLIoW4aoiiB6b3Lht717oPwgicButg6AWRdAqCGqtQSUIKj0U0RmdSVPHuY9zT4sz3TQfSAcO33e/890f3/keR7D/0vvYxWGNmsMtcRBIA6hnZwCQl72m1bjV3itWK784ef/nrv/FXpHoTwWjuLaRtmNktQ5tPYj+8X1BGkC/HjBfvRLOj7L+YAQAhQXAkVsd0NYDtTVm5z1KQ5MxJwYVCgWWXjlQLBKlHhJ8GEHWrGZECSM3F+F2nqi+jpU7xfGBt1RqIYCQf6JZetS8TnGMrScmEifp4CQdwuQ6zr2jcB14ukyidA7tTfNyrDfOhgC0/+6sSW7kEXxxkOk0bg7QCgD/agYIkRurQB/4y0AVsZSg6840K/UICeA0t1VQqIplIMCmHxAMFQm8BQKvjN1dwu7OoqZMXawumBzJmyAAWElCwUe5EUp4hEGAjhQtg50Ei2XcLUUydxptS7StsRoKbA3CJulkt4EAkipWpRQEgSLoSGGlW7d1iLuz6VIurlv/BzSRAwTZgkLOKtySxpZr2NV5SGWxMhlT4w0fW1jYCMTzBfoeq78gMTwR86KbEdwFWjqJfiwj83mc7n5zNl2FDQ+upWL/crkcgwRA+/AEYb2NsN6Gd6KP8NsmYTJNPdFOo9Gg0WggF6uIVgnlGbYWbMRoeVdDxt0dzF3BrswRXupEvqkQZcAOmm6DWRgHfI248XnHdOw9ax8vwMVjhDNThI6FEwTmar5JqTvw/cCh3Q18UWwqplpi+Ouhn5H/fo9+AxPI2vGtxsonAAAAAElFTkSuQmCC');

// The game's souls, by colour: green, blue, red, white.
export const SOULS = {
  green: png('iVBORw0KGgoAAAANSUhEUgAAAA8AAAAPCAYAAAA71pVKAAACa0lEQVR42oWTS0hUYRTHf/ebh+L4YGY0SR1f5KCEkUlhMpIZI0EpkQWK29BFEbSKlhG4KyLapLkITAqK6IU4GCZcLKgINLB85KT4SJsxHWted+7XYrhQKfVfHc7hd16co/AfuT2FHQKcCVgSiMVPqt9nxJTtgYKuZFC4ASQyVnDE2bb4IvhUIXF5Ql14B2A2gN0eV4uOya8ju9ztrkYARQgAtHCY6QdL/qJjO5rmn38DaAYQBhyDtuLW7LelrTmNKd44Z9sv8LhjBOueGHkHczBZTMWWVBOlLblNBmMyjAPny+47mq1cbbzH+5DKqrbM3fmb9FW9JJIRJr43QDgQTc66IWoDcxt9lHlc9QAnew7LD+E38sxsvXz1wyenomNyLDokLwZPS0PNvTWyubdGuj0FY25PQaVZQXF7r1QNA/QHrpMm0rGJDDKFHafZht1qp/Ozl322ui2LFYrCLWuWhYQlTFG0krXNNZSExkrUTwSN/aFDpGwkKEnJQ5c6WlQDlBFQOswurxPF9GfGgbU7uOylVMbrCMZXqNt59K+aevWkulArFKtAsShYpIVsmwOv8wSp6TmsxkOEo2sMrPtIs2j0fOwlti6Z7l8en1QXagHE3LMVXySooSU0bo/2YiOLckoop4TBjUFaHa0AyAkr/kfLIYm4ZtQ3gxyX6I2RzTjhENz40s2upmIAZkIzDDGKyLJiXRZMqvOZvzevJM/RNZzf4KhfUoNJpxQUenMxpcDsk69oCf0hwJQ6f2oLDFDuKbykI/PyGxzn9J+SpdffOyfVuW6ACk9+tXHP28IVnsLjOgSSj0ClAf5LvwDJMPvjw/zr7gAAAABJRU5ErkJggg=='),
  blue: png('iVBORw0KGgoAAAANSUhEUgAAAA8AAAAPCAYAAAA71pVKAAACYElEQVR42n2ST0jTcQDFP9/fftvc3HROUzdNLVFCizAP8TsESmD2R0GsJOhgFwW7dKhbQUEQgXmpDgqFVESlRmAEGaWnfv09RIL9c8pYs3LDuTbdfpu/dcilgvZO7/Ae7/F4gg1QXKEc8n1VH7tKlQZhpAmdXARj/km1L62RNjLrcWbcJUqtMNIEkBK4Mivaet3lyru0Rk4Td7nSkeb27Z291mW+GFsAIOy5j5BM2CqP1zKprjUDZFa09UpmB4loM+cu2tlZKXP+epDRD4s4Ko0sSWuLijRxlSsv7VVdyrzcgrPwN6kMGwATPTaODIIzAq8eDZAQKcITfUjawglpuXK3Y1uHcrCuDm1TJo1VgltdVm52WjlzN86nNxG62yGrdg8IA5YtLSwBkqtUaQBaDaYs9jUWA6AoBTizBIW5giKnRKFj/V0lYeCqrfxYWUqH2yO/YG6ORELDH9BYSsbZVSKY9pk4fQNCngipZIyUFkAI4jKAZHYC0HMqnwlvlCsPEtTvMAKC5t1/U/IcK4kx79NhLca4JOCzrmsgJ6k+OsWBvRIuZ4yQbiKkm+gf1Wmtl8nKhuTsa/TYPN+/qc2zfvWjpKcYJxkDoEB/S39/kJoaK9XVK0k5OdB3GXRtnujUneHVJwnGf44gGZpY8L/AUhTmWs9h8s3jAJTmmnky5MIuD/Pl2UmxejBDJORTrZaciDF7a4NsdRH1DGAM30POyyUlZgiFvSS9Z0kE3l+KhHzP1z1JYZnSajBbBjM27wdgwfPwAjpjM9Pq2Eb//3fPH9PqECDc2mI7gAECcY0g/8EfRGnXoG+ogwQAAAAASUVORK5CYII='),
  red: png('iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAACb0lEQVR42o2TXUhTYRjHf+djZ9/zY3NzKowIpQ921UUsWCREImkZheBNeCEKGXTRXdcVREVkN5l1UZCFNkiri6ILY4EwgqDuDaTSo46t7Zxw8+ycLk6ubII9dy/P+/6eP//3/0jsUMlIeDDm9lViAd+5RU2f+7cv7QSIuX0VHMIYIsGYzx9c1LTM332hdmKoh4q4hIPh31cSm70TAW98tqDPp5fUQ9sCkpFQD8BAffCFLKwDIopDxBLgcVa3IW4v07pWhcjVx6FIHIFLQ8G6RL9SZm13lLZb0/BxntzYNTymxFReo06RQLc6ajyIeXyRoaa6q2ejBoYL5C95eD2NbBm4W1rY/+ApPHmEIgi0K4rnh0PJLmpaRgRINodvDIR8n85G/TA+hUtsJHDnIc67KXC3oD5/B9ksR4fP4xAE3LIIluUHEG0nhF7nphsjI+RoAL/fPnd24m5tBaCxu3ur4aFIXAToD/g73IIEmsrX+GG8hQJ6sUjZMMDpJFAqkbt/HWZnMQQomSaYVja9pn4WAYKSLeS74QTAXFjAOzODMjFRndaQA/r6qFgWhvVHhZgMhQ/8FCycssgHy0GbomCOjsKbFCgumExB10nUQDvWSB+VisVkrphKr6zcq+bg9p5dVpMsIZm2kv4Ll8GVs0dkMrA3QSl1hWeqzHi22AuQVpdfVgFdrc3WQL2X93qZgy4nimTQuy9oS89v8K1cYW61zHiuOIfJzRpAMhweRhQGTzf4Eq8KOk5R4JTH/oV1eYOpvI5ZsTrTy6s1yyRsSaJsRhHFi8f93mMlA95q+pm0qqbsrDQd2Q6w/QqHInH+s34Bf0LcK53YfvwAAAAASUVORK5CYII='),
  white: png('iVBORw0KGgoAAAANSUhEUgAAAAoAAAALCAYAAABGbhwYAAABUklEQVR42l2QPUsCcQDGf3en4t0iekYtRYKL3gdIaqugoGgp+gTVWtYXaKu+SDX1MlU2HbZJYoPgiVIO4gv/W4RDuFP+DcEVPevD86rwB2enRWkYBpPJBM/zEEJwfXOrAEQA9vd2JcDq2nooeiuXEUL8uuxsb8lKpSK73a60bVvati2llNJ1XdloNGTx5FgCRPKWBYDjOORyOWKxGO12G9d1yWazbGxs0mw6Up1fWGA8HpNIJNB1nXg8TjqdJggCUqkUyysrzM7OEcksZsIa0WgUVVUJggDDMKjX66iqws8YBTRNA8D3fQCEEGHKdDpF0zTUptPENE0AWq0WnU6H4XCIrscBGAwGCCGIVKvvWJbFUqEQ3mGaJr7v43keD/d33D88KtpM2jwfjUZ81Gokk0ny+Ty9Xo+vr09eSy9cXF4pAAr/cHR4IAPfpz/o8/RcCvlvtr+ULpddlSwAAAAASUVORK5CYII='),
};

export const EMERALD = sprite([
  '...ooo...',
  '..oLLGo..',
  '.oLGGGDo.',
  'oLGGGGGDo',
  'oGGGGGGDo',
  'oGGGGGDDo',
  '.oGGGDDo.',
  '..oGDDo..',
  '...ooo...',
], { o: '#0b4a22', L: '#b8ffcf', G: '#2fd16a', D: '#159447' });

export const DIAMOND = sprite([
  '..ooooo..',
  '.oWLLLDo.',
  'oWLLLLLDo',
  'oLLLLLLDo',
  '.oLLLLDo.',
  '..oLLDo..',
  '...oLo...',
  '....o....',
], { o: '#1d4f8a', W: '#ffffff', L: '#8fe3ff', D: '#3ba7e0' });

export const SWORD = sprite([
  '........W',
  '.......WL',
  '......WL.',
  '.....WL..',
  'o...WL...',
  '.o.WL....',
  '..oL.....',
  '.oHo.....',
  'oH..o....',
], { W: '#ffffff', L: '#b8c4d6', o: '#7a4a1a', H: '#c98a3a' });
