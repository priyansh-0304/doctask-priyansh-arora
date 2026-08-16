# PRD: In-App Notifications v1

**Feature Owner:** Ananya Rao
**Target Date:** September 15, 2026
**Status:** In Progress

## Overview
Add a notification bell in the top nav that shows unread counts for task
assignments, comments, and due-date reminders. Notifications persist until
marked read; clicking one navigates to the relevant task.

## Scope
- Real-time badge count (WebSocket-based)
- Notification center dropdown, last 30 days
- Mark-as-read (individual and "mark all")
- Email digest fallback for users inactive >48 hours

## Out of Scope (v1)
- Push notifications (mobile)
- Per-notification-type user preferences (planned for v2)

## Acceptance Criteria
- Badge updates within 2 seconds of a triggering event
- Dropdown loads in under 500ms for up to 100 notifications
- All notification types covered: assignment, comment, due-date reminder