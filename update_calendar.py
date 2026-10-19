"""Build a subscribed women's college basketball iCalendar from ESPN's public scoreboard.
The ESPN endpoint is unofficial and may change. Broadcast links are service homepages.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re
import requests

START = date(2026, 10, 19)
END = date(2027, 4, 8)
API = 'https://site.api.espn.com/apis/site/v2/sports/basketball/womens-college-basketball/scoreboard'
TEAM_IDS = set()  # populated by ESPN team directory when available
TEAM_NAMES = {'connecticut', 'uconn', 'south carolina', 'ucla', 'usc', 'southern california', 'lsu', 'texas', 'notre dame', 'duke'}
SERVICE_LINKS = [
    ('peacock', 'https://www.peacocktv.com/watch'),
    ('big ten plus', 'https://www.bigtenplus.com/'),
    ('b1g+', 'https://www.bigtenplus.com/'),
    ('big ten network', 'https://www.fox.com/'),
    ('btn', 'https://www.fox.com/'),
    ('fs1', 'https://www.fox.com/'),
    ('fs2', 'https://www.fox.com/'),
    ('fox', 'https://www.fox.com/'),
    ('espn', 'https://www.espn.com/watch/'),
    ('sec network', 'https://www.espn.com/watch/'),
    ('acc network', 'https://www.espn.com/watch/'),
    ('abc', 'https://www.espn.com/watch/'),
]

def normalize(text):
    return re.sub(r'[^a-z0-9 ]+', '', str(text).lower()).strip()

def selected(competitors):
    for entry in competitors:
        team = entry.get('team') or {}
        for key in ('displayName', 'shortDisplayName', 'name'):
            value = normalize(team.get(key, ''))
            if value in TEAM_NAMES or any(value.startswith(n + ' ') for n in TEAM_NAMES):
                return True
    return False

def escape(value):
    return str(value).replace('\\', '\\\\').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')

def fold(line):
    pieces, current = [], ''
    for char in line:
        if len((current + char).encode('utf-8')) > 75:
            pieces.append(current)
            current = ' ' + char
        else:
            current += char
    pieces.append(current)
    return '\r\n'.join(pieces)

def get_games():
    session = requests.Session()
    session.headers['User-Agent'] = 'PersonalWomensBasketballCalendar/1.0'
    games = {}
    successful = 0
    day = START
    while day <= END:
        last = min(day + timedelta(days=6), END)
        try:
            response = session.get(API, params={'dates': f'{day:%Y%m%d}-{last:%Y%m%d}', 'limit': 500}, timeout=30)
            response.raise_for_status()
            data = response.json()
            successful += 1
            for event in data.get('events', []):
                competitions = event.get('competitions') or []
                if not competitions:
                    continue
                competitors = competitions[0].get('competitors') or []
                if len(competitors) >= 2 and selected(competitors):
                    games[str(event['id'])] = event
        except (requests.RequestException, ValueError) as exc:
            print(f'WARNING: {day} to {last}: {exc}')
        day = last + timedelta(days=1)
    if successful == 0 or not games:
        raise RuntimeError('No usable selected-team games found. Existing calendar will not be replaced.')
    return games

def make_calendar(games):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//WBB Calendar//Apple Subscription//EN',
             'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'X-WR-CALNAME:Women’s Basketball 2026–27',
             'X-WR-TIMEZONE:America/Los_Angeles', 'REFRESH-INTERVAL;VALUE=DURATION:PT12H',
             'X-PUBLISHED-TTL:PT12H']
    for game_id, event in sorted(games.items(), key=lambda x: x[1].get('date', '')):
        competition = event['competitions'][0]
        competitors = competition['competitors']
        home = next((x for x in competitors if x.get('homeAway') == 'home'), competitors[0])
        away = next((x for x in competitors if x.get('homeAway') == 'away'), competitors[-1])
        home_name = home.get('team', {}).get('displayName', 'Home')
        away_name = away.get('team', {}).get('displayName', 'Away')
        tipoff = datetime.fromisoformat(event['date'].replace('Z', '+00:00'))
        finish = tipoff + timedelta(hours=2, minutes=15)
        broadcasts = []
        for item in competition.get('broadcasts') or []:
            broadcasts.extend(item.get('names') or [])
        for item in competition.get('geoBroadcasts') or []:
            label = (item.get('media') or {}).get('shortName')
            if label:
                broadcasts.append(label)
        broadcasts = list(dict.fromkeys(broadcasts))
        network = ', '.join(broadcasts) if broadcasts else 'Not announced'
        combined = ' '.join(broadcasts).lower()
        service = next((url for label, url in SERVICE_LINKS if label in combined), '')
        details = next((link.get('href') for link in event.get('links', []) if link.get('href')), '')
        notes = '\n'.join([
            'Network: ' + network,
            'Streaming service: ' + (service or 'Not confirmed'),
            'Game information: ' + details,
            'Streaming link may open a service homepage rather than the live game.',
            'Game duration is estimated. Verify TV listings and tipoff before watching.',
        ])
        lines.extend([
            'BEGIN:VEVENT', f'UID:espn-wbb-{game_id}@asiacook4-stack.github.io',
            f'DTSTAMP:{stamp}', f'DTSTART:{tipoff:%Y%m%dT%H%M%SZ}',
            f'DTEND:{finish:%Y%m%dT%H%M%SZ}',
            'SUMMARY:' + escape('🏀 ' + away_name + ' at ' + home_name),
            'DESCRIPTION:' + escape(notes),
        ])
        if service or details:
            lines.append('URL:' + (service or details))
        lines.extend(['BEGIN:VALARM', 'ACTION:DISPLAY', 'DESCRIPTION:Tipoff in 30 minutes',
                      'TRIGGER:-PT30M', 'END:VALARM', 'END:VEVENT'])
    lines.append('END:VCALENDAR')
    return '\r\n'.join(fold(line) for line in lines) + '\r\n'

if __name__ == '__main__':
    games = get_games()
    Path('calendar.ics').write_bytes(make_calendar(games).encode('utf-8'))
    print(f'Updated calendar with {len(games)} games')
