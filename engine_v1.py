"""Deterministic catalog validation and recommendation rules. No AI calls."""
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

GOALS = {
    'predict': 'Predict future quality problems',
    'unusual': 'Find unusual measurements or batches',
    'frequency': 'Evaluate how often to inspect',
    'signals': 'Understand control-chart signals',
    'integrity': 'Investigate data-entry patterns',
    'database': 'Investigate SQL Server health or slowness',
    'certificate': 'Create a Certificate of Analysis',
    'dashboard': 'Request charts, comparisons, or dashboards',
    'optimize': 'Find process settings closer to target',
    'other': 'Something else / I am not sure',
}
SCOPES = {
    'individual': 'Individual measurements or records',
    'batch': 'Batches, lots, or work orders',
    'part_type': 'Whether measurements fit the declared part type',
    'unsure': 'I am not sure',
}
DATA = {
    'yes': 'Yes, we have the relevant data',
    'no': 'No, we do not have that data yet',
    'unsure': 'I am not sure what data we have',
}

def valid_url(value):
    if not isinstance(value, str) or any(c.isspace() for c in value):
        return False
    try:
        p = urlsplit(value)
        return p.scheme == 'https' and bool(p.hostname) and not p.username and not p.password
    except ValueError:
        return False

def load_catalog(path):
    catalog = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(catalog, dict) or not isinstance(catalog.get('apps'), list):
        raise ValueError('Catalog must contain an apps list.')
    ids = set()
    for app in catalog['apps']:
        for key in ('id', 'name', 'summary', 'why', 'limitations'):
            if not isinstance(app.get(key), str) or not app[key].strip():
                raise ValueError('Each app needs a non-empty ' + key)
        if app['id'] in ids:
            raise ValueError('Duplicate app ID: ' + app['id'])
        ids.add(app['id'])
        for key in ('goals', 'scopes', 'required_data', 'outputs', 'customizations'):
            if not isinstance(app.get(key), list) or not all(isinstance(x, str) for x in app[key]):
                raise ValueError(app['id'] + ': ' + key + ' must be a list of strings')
        if not app['goals'] or set(app['goals']) - (set(GOALS) - {'other'}):
            raise ValueError(app['id'] + ': invalid goals')
        if set(app['scopes']) - (set(SCOPES) - {'unsure'}):
            raise ValueError(app['id'] + ': invalid scopes')
        for key in ('enabled', 'approved'):
            if not isinstance(app.get(key), bool):
                raise ValueError(app['id'] + ': ' + key + ' must be true or false')
        for key in ('demo_url', 'contact_url'):
            if app.get(key) and not valid_url(app[key]):
                raise ValueError(app['id'] + ': ' + key + ' must be an HTTPS URL')
    if catalog.get('contact_url') and not valid_url(catalog['contact_url']):
        raise ValueError('contact_url must be an HTTPS URL')
    for key in ('preview_mode', 'contact_supports_app_parameter'):
        if not isinstance(catalog.get(key), bool):
            raise ValueError(key + ' must be true or false')
    return catalog

def visible_apps(catalog):
    return [a for a in catalog['apps'] if a['enabled'] and
            (catalog['preview_mode'] or a['approved'])]

def recommend(catalog, goal, scope='unsure'):
    """Match goals exactly; scope restricts apps only when known and configured."""
    if goal not in GOALS or scope not in SCOPES or goal == 'other':
        return []
    return [a for a in visible_apps(catalog) if goal in a['goals'] and
            (scope == 'unsure' or not a['scopes'] or scope in a['scopes'])]

def contact_link(catalog, app=None):
    url = (app or {}).get('contact_url') or catalog.get('contact_url', '')
    if not valid_url(url):
        return None
    if app and catalog['contact_supports_app_parameter']:
        parts = urlsplit(url)
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != 'app']
        query.append(('app', app['id']))
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return url


def data_question(goal):
    return {
        'database': 'Do you use SQL Server for the database you want to assess?',
        'certificate': 'Do you have test results, specifications, and the production identifiers for the certificate?',
        'dashboard': 'Do you have measurements with timestamps, specifications, and part/machine context?',
        'optimize': 'Do you have measurements linked to process settings and targets by part and machine?',
        'frequency': 'Do you have timestamped measurements and a standards workbook linked by Part Number?',
        'integrity': 'Do your records include operator, entry timestamp, and measurement values?',
        'other': 'Do you already have data related to the problem?',
    }.get(goal, 'Do you collect measurements for this process?')

def readiness_message(goal, answer):
    if goal == 'database':
        return {'no': 'This app is for SQL Server. You can explore its demo, but ask Hertzler about feasibility for your database platform.',
                'unsure': 'Explore Demo Database first. Confirm your database platform with your team before considering a live assessment.',
                'yes': 'Explore Demo Database first; live use also needs appropriate connectivity and diagnostic permissions.'}[answer]
    if answer == 'no':
        return 'You can explore the demo. Hertzler can discuss what data to collect before adapting an app to your process.'
    if answer == 'unsure':
        return 'A conversation with Hertzler can establish whether your available data fits.'
    return 'Having data does not by itself confirm readiness; review the requirements below.'
