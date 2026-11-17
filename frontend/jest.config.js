module.exports = {
  preset: 'jest-preset-angular',
  setupFilesAfterEnv: ['<rootDir>/setup-jest.ts'],
  testMatch: ['<rootDir>/src/**/*.spec.ts'],
  collectCoverageFrom: ['src/app/core/**/*.ts', '!src/app/core/**/*.spec.ts', '!src/app/core/models.ts'],
  coverageThreshold: { global: { branches: 80, functions: 80, lines: 80, statements: 80 } }
};
