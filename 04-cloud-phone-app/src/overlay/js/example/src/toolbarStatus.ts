// The toolbar's colours: the round trip's and the connection LED's. No
// React, no DOM.
import { LEVEL_COLORS } from './styles';

export function pingColor(ms) {
  if (ms === null) return '#8a919c';
  if (ms < 60) return '#34c759';
  if (ms < 150) return '#ff9f0a';
  return '#ff453a';
}

// The LED on ↻: the status's colour when something is wrong (error, wait),
// green while the video plays, orange while it connects.
export function ledColor(problem, connected) {
  return problem && problem.level !== 'info' ? LEVEL_COLORS[problem.level]
    : connected ? '#34c759' : '#ff9f0a';
}
