export default {
    preset: 'ts-jest',
    testEnvironment: 'node',
    rootDir: './src',
    testMatch: ['**/__tests__/**/*.test.ts'],
    moduleNameMapper: {
        '^(\\.{1,2}/.*)\\.js$': '$1'
    },
    transform: {
        '^.+\\.tsx?$': ['ts-jest', {
            tsconfig: './tsconfig.test.json'
        }]
    }
}
