import { test, expect } from '@playwright/test';
test('normal controls, replacement, reset confirmation and FHD layout',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error') errors.push(m.text());});
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'시뮬레이션 제어'})).toBeVisible();
 await expect(page.getByTestId('counted')).toHaveText('0표');
 const run=await page.getByTestId('run-id').textContent();
 await page.getByRole('button',{name:'START'}).click();
 await expect(page.getByTestId('counted')).toHaveText('2,020표');
 await page.getByRole('button',{name:'STOP'}).click();
 await expect(page.locator('.controls .badge')).toHaveText('PAUSED');
 await page.waitForTimeout(1800);
 await expect(page.getByTestId('counted')).toHaveText('2,020표');
 await page.getByRole('button',{name:'START'}).click();
 await expect(page.getByTestId('run-id')).toHaveText(run!);
 await page.locator('.diagnostics > summary').click(); await expect(page.locator('.receiver .badge')).toHaveText('SYNCED'); await page.locator('.diagnostics > summary').click();
 await expect(page.getByTestId('count-rate')).toHaveText('20.20%');
 await page.screenshot({path:'test-results/v0.4.1/analytics-fhd.png',fullPage:true});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.getByRole('button',{name:'RESET'}).click();await page.getByRole('button',{name:'취소'}).click();
 await expect(page.getByTestId('counted')).toHaveText('2,020표');
 await page.getByRole('button',{name:'RESET'}).click();await page.getByRole('button',{name:'초기화 확인'}).click();
 await expect(page.getByTestId('counted')).toHaveText('0표');
 await expect(page.getByTestId('run-id')).not.toHaveText(run!);
 await expect(page.locator('.controls .badge')).toHaveText('IDLE');
 await page.locator('.diagnostics > summary').click(); await expect(page.locator('.receiver .badge')).toHaveText('AWAITING_ACK');
 expect(errors).toEqual([]);
});
for(const [scenario,state] of [['invalid','ERROR'],['receiver-disconnect','ERROR'],['ws-disconnect','DISCONNECTED'],['ack-wait','AWAITING_ACK'],['lagging','LAGGING'],['stale','STALE']]){
 test('scenario '+scenario,async({page})=>{
  await page.goto('/');await page.getByLabel('시연 시나리오').selectOption(scenario);
  await page.getByRole('button',{name:'START'}).click();
  await expect(page.getByTestId('counted')).toHaveText('2,020표');
  if(scenario==='invalid'){
   await expect(page.locator('.controls .badge')).toHaveText(state);
   await expect(page.getByRole('alert').filter({hasText:'TOTAL_MISMATCH'})).toBeVisible();
   await expect(page.getByRole('button',{name:'START'})).toBeDisabled();
   await page.screenshot({path:'test-results/v0.4.1/error-blocked.png',fullPage:true});
  }else if(scenario==='ws-disconnect'){
   await expect(page.getByRole('button',{name:'MOCK 연결 복구'})).toBeVisible();
   await expect(page.getByRole('alert').filter({hasText:'마지막 정상 데이터'})).toBeVisible();
   await expect(page.getByRole('button',{name:'START'})).toBeDisabled();
   await page.getByRole('button',{name:'MOCK 연결 복구'}).click();
   await expect(page.getByRole('button',{name:'FE 연결 끊기'})).toBeVisible();
  }else{
   await page.locator('.diagnostics > summary').click(); await expect(page.locator('.receiver .badge')).toHaveText(state==='ERROR'?'DISCONNECTED':state);
  }
  await expect(page.getByTestId('counted')).toHaveText('2,020표');
 });
}
test('desktop and narrow layout',async({page})=>{
 await page.setViewportSize({width:1366,height:768});await page.goto('/');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await expect(page.getByRole('button',{name:'START'})).toBeVisible();
});



