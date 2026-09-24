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

# Extend these phrase rules as customers use new wording. No external service.
TEXT_RULES = {
    'predictive_spc': [r'predictive spc', r'(?:predict|forecast|anticipate|prevent)\w* (?:\w+ ){0,5}(?:quality|defects?|failures?|out of spec|oos)', r'future (?:\w+ ){0,3}(?:risk|quality|defects?)', r'early warning'],
    'batch_anomaly': [r'batch anomaly detection', r'(?:unusual|abnormal|anomalous|outlier|bad) (?:\w+ ){0,3}(?:batches|batch|lots|lot)', r'(?:batches|batch|lots|lot) (?:\w+ ){0,4}(?:unusual|abnormal|different|outliers?)'],
    'mislabel': [r'mislabel\w*', r'(?:wrong|incorrect|mixed up|mismatched) (?:\w+ ){0,3}(?:labels?|parts?|types?)', r'(?:unusual|abnormal|outlier) (?:measurements?|records?|readings?)', r'(?:parts?|measurements?) (?:\w+ ){0,4}(?:declared type|declared part|label mismatch)'],
    'inspection_frequency': [r'(?:inspection|sampling) (?:frequency|interval|schedule)', r'how (?:often|frequently) (?:\w+ ){0,5}(?:inspect|sample|check)', r'(?:inspect|sample|checking|inspecting) (?:too often|too much|less|more|every|hourly)', r'(?:reduce|increase|adjust|optimize|optimise) (?:\w+ ){0,3}(?:inspections|sampling|inspection frequency)'],
    'spc_interpretation': [r'spc auto interpretation', r'(?:explain|interpret|understand) (?:\w+ ){0,5}(?:control chart|chart signals?|nelson|rule violations?)', r'(?:nelson|western electric|control chart) (?:rules?|signals?|violations?)', r'out of control'],
    'entry_integrity': [r'(?:operator|data|entry) (?:\w+ ){0,2}integrity', r'pencil whipping', r'(?:repeated|duplicate|copied|fabricated|suspicious|rounded) (?:\w+ ){0,2}(?:entries|values|readings|records|data)', r'(?:entry|entering|entered) (?:\w+ ){0,2}(?:errors?|too fast)', r'backfill\w*'],
    'database_health': [r'database health', r'sql server', r'(?:database|queries|query) (?:\w+ ){0,3}(?:slow|slowness|performance|blocking|space)', r'(?:slow|blocked|expensive) (?:database|queries|query)', r'missing indexes?', r'index fragmentation', r'query store'],
    'coa': [r'coa', r'certificates? of analysis', r'(?:create|generate|prepare) (?:\w+ ){0,3}certificates?'],
    'copilot': [r'manufacturing copilot', r'dashboards?', r'(?:show|create|build|plot) (?:\w+ ){0,4}(?:charts?|histograms?|trends?|scatter)', r'compare (?:\w+ ){0,4}(?:machines?|parts?|traces?|characteristics?)'],
    'optimization': [r'process optimi[sz]ation', r'(?:optimi[sz]e|best|optimal|adjust|recommend) (?:\w+ ){0,4}(?:settings|parameters|temperature|pressure|speed)', r'(?:closer|close) to (?:the )?target', r'(?:reduce|minimi[sz]e) (?:\w+ ){0,3}(?:deviation|variation from target)'],
}

def parse_customer_request(catalog, text):
    """Return visible catalog matches and literal evidence, not probabilities.

    Independent clauses allow multiple needs. Simple negation handling is
    intentionally conservative; complex language should use the guided flow.
    """
    import re
    import unicodedata
    if not isinstance(text, str) or not text.strip():
        return []
    def normalize(value):
        value = unicodedata.normalize('NFKC', value).lower().replace('’', "'")
        value = re.sub(r"\b(?:don't|dont|do not|not interested in|not looking for|no need for)\b", 'not', value)
        value = re.sub(r'[-_/]', ' ', value)
        return re.sub(r'\s+', ' ', value).strip()
    query = normalize(text[:2000])
    clauses = re.split(r'[.!?;,\n]+|\b(?:but|however|instead|rather than)\b', query)
    results = []
    for app in visible_apps(catalog):
        patterns = [re.escape(normalize(app['name']))] + TEXT_RULES.get(app['id'], [])
        evidence = []
        for clause in clauses:
            for pattern in patterns:
                for match in re.finditer(r'(?<!\w)(?:' + pattern + r')(?!\w)', clause):
                    before = clause[:match.start()]
                    # "not only" and "not sure" are not exclusions.
                    before = re.sub(r'\bnot (?:only|sure)\b', '', before)
                    if re.search(r'\b(?:not|no|without)\b(?:\s+\w+){0,5}\s*$', before):
                        continue
                    phrase = match.group().strip()
                    if phrase not in evidence:
                        evidence.append(phrase)
        if evidence:
            results.append({'app': app, 'matched_phrases': evidence})
    return results
