// npm run test:night —— 与 jest.config.js 相同，只是额外把整机时钟钉在深夜 23:47，
// 用来证明整套测试不依赖墙上时间（tests/helpers/night-clock.js）。
const base = require('./jest.config.js');

module.exports = Object.assign({}, base, {
  setupFiles: [base.setupFiles[0], '<rootDir>/tests/helpers/night-clock.js'],
});
