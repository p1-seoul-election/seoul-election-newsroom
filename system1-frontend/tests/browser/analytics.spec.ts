import {test,expect} from '@playwright/test';
test('analytics uses only received data, ranks/gap, district pending and locked official statistics',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 await page.goto('/');
 await expect(page.getByTestId('candidate-gap')).toContainText('비교 불가');
 await expect(page.getByTestId('trend')).toHaveAttribute('data-observations','1');
 await expect(page.getByTestId('demographic-lock')).toBeVisible();
 await expect(page.getByTestId('diagnostics')).not.toHaveAttribute('open','');
 await expect(page.getByText('실제 시간대별 투표율 데이터 검증 중')).toBeVisible();
 await expect(page.locator('.district-grid button')).toHaveCount(25);
 await page.getByRole('button',{name:'동작구 준비 중'}).click();
 await expect(page.locator('.district-detail')).toContainText('SEOUL_D20');
 await expect(page.locator('.district-detail')).toContainText('시뮬레이션 데이터 준비 중');
 await page.getByRole('button',{name:'START'}).click();
 await expect(page.getByTestId('candidate-gap')).toContainText('100표 · 5.00%p');
 await expect(page.getByTestId('candidate-1')).toContainText('1,000');
 await expect(page.getByTestId('candidate-1')).toContainText('50.00%');
 await expect(page.getByTestId('trend')).toHaveAttribute('data-observations','2');
 await expect(page.getByTestId('trend')).toHaveAttribute('data-valid-observations','1');
 await expect(page.locator('.trend circle')).toHaveCount(5);
 await expect(page.locator('.controls .badge')).toHaveText('PAUSED');
 const paused=await page.getByTestId('playback-clock').textContent();
 await page.waitForTimeout(1200);
 await expect(page.getByTestId('playback-clock')).toHaveText(paused!);
 await expect(page.getByTestId('count-rate')).toHaveText('20.20%');
 await expect(page.getByTestId('demographic-lock')).toBeVisible();
 await expect(page.getByTestId('demographic-chart')).toHaveCount(0);
 await page.getByRole('button',{name:'RESET'}).click();await page.getByRole('button',{name:'초기화 확인'}).click();
 await expect(page.getByTestId('trend')).toHaveAttribute('data-observations','1');
 await expect(page.getByTestId('playback-clock')).toHaveText('00:00');
 expect(errors).toEqual([]);
});
test('diagnostics closed cannot hide an error, error cannot add a trend point',async({page})=>{
 await page.goto('/');await page.getByLabel('시연 시나리오').selectOption('invalid');await page.getByRole('button',{name:'START'}).click();
 await expect(page.getByRole('alert')).toContainText('TOTAL_MISMATCH');
 await expect(page.getByTestId('diagnostics')).not.toHaveAttribute('open','');
 await expect(page.getByTestId('trend')).toHaveAttribute('data-observations','2');
 await expect(page.getByTestId('counted')).toHaveText('2,020표');
 await page.locator('.diagnostics > summary').click();
 await expect(page.locator('.events')).toContainText('REJECTED');
 await page.screenshot({path:'test-results/v0.4.1/diagnostics-error.png',fullPage:true});
});
test('FHD and laptop captures, district and statistics panels remain accessible',async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:'START'}).click();await expect(page.locator('.controls .badge')).toHaveText('PAUSED');
 await page.screenshot({path:'test-results/v0.4.1/analytics-fhd.png',fullPage:true});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.setViewportSize({width:1366,height:768});await page.screenshot({path:'test-results/v0.4.1/analytics-laptop.png',fullPage:true});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:'test-results/v0.4.1/analytics-mobile.png',fullPage:true});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await expect(page.getByTestId('demographic-lock')).toBeVisible();
});
test('completion at 100 percent cannot expose unverified demographic content in the browser',async({page})=>{
 // Test-only entry interception; never shipped as an app endpoint or demo scenario.
 await page.route('**/src/main.tsx',route=>route.fulfill({contentType:'application/javascript',body:
  "import React from '/node_modules/.vite/deps/react.js'; import {createRoot} from '/node_modules/.vite/deps/react-dom_client.js'; import {DemographicAnalytics} from '/src/DemographicAnalytics.tsx'; createRoot(document.getElementById('root')).render(React.createElement(DemographicAnalytics,{state:'COMPLETED',countRate:100,statistics:{evidence:{available:true,electionId:'0020260603',officialSourceVerified:true,independentlyVerified:false},sourceUrl:'https://example.org/test-only',basis:'TEST ONLY',groups:[{label:'TEST_PRIVATE_GROUP',turnoutPct:73.12}]}}));"
 }));
 await page.goto('/');
 await expect(page.getByTestId('demographic-lock')).toBeVisible();
 await expect(page.getByTestId('demographic-chart')).toHaveCount(0);
 await expect(page.locator('body')).not.toContainText('TEST_PRIVATE_GROUP');
 await expect(page.locator('body')).not.toContainText('73.12');
});

