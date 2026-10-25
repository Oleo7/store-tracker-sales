// Actual shipped HTML/JavaScript must have no sending or tracking UI.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
for (const forbidden of [
  '/email-proposal', '/reminder-email', '/api/brevo', 'sendReminderEmail',
  'getPlannedEmailContext', 'email-modal-backdrop', 'd-reminder-btn',
  'email-performance-panel', 'emailClickNoOrderActive', 'view-settings',
  'first_opened_at', 'stockfiller_click_count', 'product_sheet_click_count',
]) assert.ok(!html.includes(forbidden), forbidden);
for (const retained of ['mailto:', 'email_last_order', 'Mejl',
  '/planning/activities', '/planning/route-apply', '/contacts',
  'customerCanExecutePlanned', 'priority_score']) assert.ok(html.includes(retained), retained);
for (const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)) {
  if (match[1].trim()) new vm.Script(match[1]);
}
console.log('Email removal frontend: no send/tracking UI; manual contact and planning retained; syntax PASS');
