"""Calendar integration stub.

Replace with Google Calendar API or Microsoft Graph:
  - Google: google-api-python-client + OAuth scope
    https://www.googleapis.com/auth/calendar.readonly, then
    events().list(calendarId="primary", timeMin=..., timeMax=...)
  - Microsoft Graph: msal + GET /me/calendarview?startDateTime=&endDateTime=

Return strings like "09:00–09:30 Standup" so the brief agent and agenda UI
need no changes when the real integration lands.
"""


def todays_events() -> list[str]:
    return []
