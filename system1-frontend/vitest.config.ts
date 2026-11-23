import { defineConfig } from 'vitest/config';
export default defineConfig({test:{include:['tests/*.test.ts'],reporters:['default','json'],outputFile:{json:'test-results/v0.4.1/unit-results.json'}}});


