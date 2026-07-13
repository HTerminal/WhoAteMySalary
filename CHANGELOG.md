# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [1.0.0]
### Added
- First public release of **Mail Money Tracker** (PyQt5 desktop app).
- Reads bank/transaction-alert emails over IMAP and turns them into transactions.
- Dashboard: KPIs (money out / credit-card bills / money in / net / count), an
  interactive donut, month-by-month bars, incoming-by-source, an expandable
  merchant tree, and highlighted large transactions.
- Global search + clickable KPI cards → searchable, sortable transaction lists.
- Review queue: every new transaction appears for you to verify, with a
  pre-filled category and a desktop notification.
- Merchant memory: remembers the category you chose for a payee.
- Credit-card bill payments tracked in their own bucket (not double-counted).
- Native calendar date-range with today highlighted; date + time on every row.
- Sign in with **Google** or **Microsoft (OAuth2)**, or a **Gmail app password**.
- Parser page with a live tester and custom rules.
- Robust background checker (auto-retry, never dies).
