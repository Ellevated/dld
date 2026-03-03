export default {
  mutate: ['src/**/*.ts', 'src/**/*.js', '!src/**/*.test.*', '!src/**/*.spec.*'],
  testRunner: 'vitest',
  reporters: ['clear-text', 'html'],
  thresholds: { high: 80, low: 60, break: 40 },
  concurrency: 4,
};
