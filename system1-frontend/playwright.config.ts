import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./tests/browser',fullyParallel:false,workers:1,reporter:[['list'],['json',{outputFile:'test-results/v0.4.1/browser-results.json'}]],outputDir:'test-results/v0.4.1/artifacts',use:{baseURL:'http://127.0.0.1:5173',viewport:{width:1920,height:1080},launchOptions:{executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',args:['--disable-crash-reporter','--no-first-run']},screenshot:'only-on-failure'}});


