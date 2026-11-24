import { test, expect, type Browser, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFileSync } from 'fs';
import { join } from 'path';

const seedIds = JSON.parse(
  readFileSync(join(__dirname, '.seed-ids.json'), 'utf-8'),
) as {
  seasonId: number;
  fixtureId: number;
  entriesSeasonId: number;
  entryBatchId: number;
};

async function login(browser: Browser, username: string, password: string) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('/login');
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForURL('/news');
  const state = await context.storageState();
  await context.close();
  return state;
}

async function expectNoViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
}

// Public pages, reachable without authentication.
const publicPages = [
  '/news',
  '/login',
  '/rules-and-constitution',
  '/privacy-policy',
  '/about',
  '/contact',
  '/status',
  '/clubs',
  '/links',
  '/divisions',
  '/winners',
  '/fixtures',
  '/standings',
  '/results',
  '/entries',
  '/administration',
  '/administration/athlete-registration-guide',
  '/administration/race-directors-guide',
  '/administration/suppliers-list',
  '/administration/team-managers-guide',
];

for (const path of publicPages) {
  test(`public page ${path} has no axe violations`, async ({ page }) => {
    await page.goto(path);
    await expect(page.locator('main')).toBeVisible();
    if (path === '/standings') {
      await expect(page.locator('#standings-table-panel [hx-trigger="load"]')).toHaveCount(0);
    }
    await expectNoViolations(page);
  });
}

test('public team results view has no axe violations', async ({ page }) => {
  await page.goto(`/results?season_id=${seedIds.seasonId}&view_mode=team`);
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('button', { name: 'Team Results' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await expectNoViolations(page);
});

test.describe('staff (admin) pages', () => {
  let state: Awaited<ReturnType<typeof login>>;
  test.beforeAll(async ({ browser }) => {
    state = await login(browser, 'admin_user', 'AdminPassword123!@#');
  });
  test.use({ storageState: async ({}, use) => { await use(state); } });

  const staffPages = [
    '/account',
    '/about/edit',
    '/contact/edit',
    '/news/create',
    '/administration/manage',
    '/admin/clubs',
    '/admin/entries',
    '/admin/club-managers',
    '/admin/links',
    '/admin/divisions',
    '/admin/winners',
  ];

  for (const path of staffPages) {
    test(`staff page ${path} has no axe violations`, async ({ page }) => {
      await page.goto(path);
      await expect(page.locator('main')).toBeVisible();
      if (['/about/edit', '/contact/edit', '/news/create'].includes(path)) {
        await expect(page.locator('.ql-editor')).toBeVisible();
      }
      await expectNoViolations(page);
    });
  }
});

test.describe('club manager (entries) pages', () => {
  let state: Awaited<ReturnType<typeof login>>;
  test.beforeAll(async ({ browser }) => {
    state = await login(browser, 'entries_manager', 'ManagerPassword123!@#');
  });
  test.use({ storageState: async ({}, use) => { await use(state); } });

  test('entries season overview has no axe violations', async ({ page }) => {
    await page.goto(`/entries/${seedIds.entriesSeasonId}`);
    await expect(page.locator('main')).toBeVisible();
    await expectNoViolations(page);
  });

  test('entries batch success page has no axe violations', async ({ page }) => {
    await page.goto(
      `/entries/${seedIds.entriesSeasonId}/batch/${seedIds.entryBatchId}/success`,
    );
    await expect(page.locator('main')).toBeVisible();
    await expectNoViolations(page);
  });

  test('entries batch receipt has no axe violations', async ({ page }) => {
    await page.goto(
      `/entries/${seedIds.entriesSeasonId}/batch/${seedIds.entryBatchId}/receipt`,
    );
    await expect(page.getByRole('heading', { name: 'Entered athletes' })).toBeVisible();
    await expectNoViolations(page);
  });
});
