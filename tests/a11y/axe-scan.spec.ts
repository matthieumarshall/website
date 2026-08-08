import { test, expect, type Page } from '@playwright/test';
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

async function login(page: Page, username: string, password: string) {
  await page.goto('/login');
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', password);
  await page.click('button[type="submit"]');
  await page.waitForLoadState('networkidle');
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
  '/clubs',
  '/links',
  '/divisions',
  '/winners',
  '/fixtures',
  '/standings',
  '/results',
  '/entries',
];

for (const path of publicPages) {
  test(`public page ${path} has no axe violations`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState('networkidle');
    await expectNoViolations(page);
  });
}

test.describe('staff (admin) pages', () => {
  test.beforeEach(async ({ page }) => {
    await login(page, 'admin_user', 'AdminPassword123!@#');
  });

  const staffPages = [
    '/account',
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
      await page.waitForLoadState('networkidle');
      await expectNoViolations(page);
    });
  }
});

test.describe('club manager (entries) pages', () => {
  test.beforeEach(async ({ page }) => {
    await login(page, 'entries_manager', 'ManagerPassword123!@#');
  });

  test('entries season overview has no axe violations', async ({ page }) => {
    await page.goto(`/entries/${seedIds.entriesSeasonId}`);
    await page.waitForLoadState('networkidle');
    await expectNoViolations(page);
  });

  test('entries batch success page has no axe violations', async ({ page }) => {
    await page.goto(
      `/entries/${seedIds.entriesSeasonId}/batch/${seedIds.entryBatchId}/success`,
    );
    await page.waitForLoadState('networkidle');
    await expectNoViolations(page);
  });

  test('entries batch receipt has no axe violations', async ({ page }) => {
    await page.goto(
      `/entries/${seedIds.entriesSeasonId}/batch/${seedIds.entryBatchId}/receipt`,
    );
    await page.waitForLoadState('networkidle');
    await expectNoViolations(page);
  });
});
