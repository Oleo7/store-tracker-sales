# Sales-only removal of automatic email proposals and Brevo

This change applies only to `Oleo7/store-tracker-sales`. It does not modify or
configure the original Store Tracker deployment or its Google Sheets database.
Merge and deployment remain separate approvals.

## Removed

- Proposal drafting/sending/settings endpoints, modal, templates, warnings and
  retry flow; related Flask authentication allowlist entries and startup workers.
- Brevo HTTP client, webhook, reconciliation, sender/test-recipient configuration.
- The three provider worksheets and all production readers, writers, cache
  dependencies, migration dependencies and customer-rename dependencies.
- Open/click attribution, tracking panels/filters and engagement-driven priority,
  channel recommendations and follow-up timing. Ordinary order-based reminders
  and customer promises are NOT removed.
- The email-specific identity repair tool and obsolete integration tests. Generic
  worksheet, authentication and email-address validation tests were retained in
  `tests/test_crm_utils.py`; remaining tests were adapted to the new contracts.

## Preserved

- Customer and seller email addresses, buyerEmail, email_last_order, mailto links,
  and manually logged or planned Mejl contacts. This application sends no email.
- V3.5 business potential, non-email contact priority, pre-contact analytics
  snapshots, customer ownership, order sync, calendar, both route engines,
  transaction/lease safeguards and sales-coaching results.
- Existing contact IDs, planned activities, suggestions, state events and audit
  history. Old automated contacts keep their inert `email_id`/`crm_email` markers
  so they cannot become human dialogues or influence sales attribution.
- One EMPTY `active_email_intent_event` slot in the historic context-hash format.
  It accepts no input and reads no tracking data. Removing it would gratuitously
  change non-email suggestion identities and break historical workflow links.
- All 31 order columns, product settings and route_proposals.

## Database copy migration

Only the explicitly designated copy should be changed; never use the original
CRM_DATABASE. Remove `email_messages`, `email_recipients`, `email_events`, and the
22 settings rows used exclusively by proposal templates/links. Retain the six
SKU catalog settings and all unrelated tables and historical rows. Do not delete
or reinterpret historical contacts when dropping provider tables.

This database is no longer compatible with the pre-removal application: use this
PR's version when connecting the copy. No Render service is updated by this PR.
Old documentation and screenshots describe earlier releases and are not the
current runtime contract; this document supersedes their email-specific portions.

## Verification

Unit tests enforce that core reads and manual email/contact writes succeed with
all three retired sheets absent, never recreate/read them, never make a provider
request, preserve pre-contact priority, and remain idempotent. Tests additionally
prove that tracking data, even if reintroduced into an old workbook, cannot change
current priorities or route source fingerprints. Desktop/mobile browser tests
exercise the shipped HTML and JavaScript against an isolated synthetic CRM.

## Independent deep audit and regression closure

A second source-wide audit of current production modules, scripts, frontend,
88 test files and historical documentation found extra effects from old
automatic email records after the provider APIs had been removed. PR #1 now
isolates these rows using saved email_id / activity_source=crm_email markers.
Historical sends cannot contribute to live priority features, last-contact
dates, followup commitments, route exclusions, customer timelines, calendars,
contact logs, freezer observations or sales statistics. Manually logged email
contacts remain supported.

Sales analytics and calibration also reject historical recommendations whose
primary or covered triggers derive from retired email open/click, product-sheet
click or Stockfiller click tracking; historical worksheet rows are not modified.
Regression tests enforce that these legacy events cannot be used as approximate
contact priority snapshots or receive sales calibration attribution.

Deliberate inert compatibility fields remain: sales_activities.email_id,
activity_source=crm_email, old resolved_by_type=email, and the empty
active_email_intent_event value in legacy suggestion context hashes. Removing
these without a separate data migration would misclassify old automated sends
or orphan historical suggestion identities. None calls an email provider.

Historical documentation predating this removal, including earlier priority
specifications and archived QA reports, does not describe current runtime.

Route-save decision fingerprints also ignore inert automatic dispatch rows and
legacy email-open/click suggestion rows, while still responding to real seller
contacts and active recommendation changes. A dedicated regression checks this.
