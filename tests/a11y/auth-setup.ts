import { chromium } from '@playwright/test';

// One login per role for the entire run, including all device projects.
export default async function setup() {
  const browser = await chromium.launch();
  try {
    for (const [key, username, password] of [
      ['UI_ADMIN_AUTH_STATE', 'admin_user', 'AdminPassword123!@#'],
      ['UI_MANAGER_AUTH_STATE', 'entries_manager', 'ManagerPassword123!@#'],
    ]) {
      const context = await browser.newContext();
      try {
        const page = await context.newPage();
        await page.goto('http://localhost:8000/login');
        await page.fill('input[name="username"]', username);
        await page.fill('input[name="password"]', password);
        await page.click('button[type="submit"]');
        await page.waitForURL('http://localhost:8000/news');
        process.env[key] = JSON.stringify(await context.storageState());
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
}
