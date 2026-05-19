import { test, expect } from "@playwright/test";

test("live dashboard loads without error", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/Algo Trading/);
  await expect(page.getByText("Live Dashboard")).toBeVisible();
});

test("reports page loads and shows table or empty state", async ({ page }) => {
  await page.goto("/reports");
  // Either the table header or empty state must be present
  await expect(
    page.getByText("Reports").or(page.getByText("No reports found"))
  ).toBeVisible();
});

test("nav links are present", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Live" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Reports" })).toBeVisible();
});

test("reports page has Live day/week/month links", async ({ page }) => {
  await page.goto("/reports");
  await expect(page.getByRole("link", { name: /Live day/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /Live week/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /Live month/i })).toBeVisible();
});
