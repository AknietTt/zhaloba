# AutoPark — Complaint Management System

## Register
product

## Purpose
Internal admin dashboard for AutoPark (city bus operator) to manage, track, and respond to citizen complaints about bus service quality. Connects complaints from Telegram bot to 1C ERP waybill data.

## Target Users
- AutoPark operations administrators
- Dispatchers reviewing driver complaints
- Management reviewing statistics and driver performance

## Product Goals
1. Give admins a single view of all citizen complaints
2. Enable two-way chat with complainants via Telegram
3. Surface 1C waybill data (driver, route, bus) per complaint
4. Provide actionable statistics — which routes/drivers have most complaints

## Brand Personality
Professional, trustworthy, utilitarian. Not flashy. Should feel like a serious operations tool — dense but readable, efficient, calm. Think Linear or Plane.so rather than a colorful marketing site.

## Anti-References
- Consumer-facing apps (bright colors, playful)
- Bootstrap admin templates (generic, cheap)
- Dashboards with animation for animation's sake

## Accessibility
- Russian/Kazakh-speaking operators
- Desktop-first (used on monitors in dispatch centers)
- WCAG AA contrast minimums

## Tech Stack
React 18, TypeScript, Vite, plain CSS (no Tailwind), FastAPI backend, SQLite, Telegram Bot API, 1C ERP integration
