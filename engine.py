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
    'copilot': [r'c[ .]*p[ .]*k', r'cp', r'process capability', r'capability (?:analysis|indices|index|study|studies|report|comparison)', r'manufacturing copilot', r'dashboards?', r'(?:show|create|build|plot) (?:\w+ ){0,4}(?:charts?|histograms?|trends?|scatter)', r'compare (?:\w+ ){0,4}(?:machines?|parts?|traces?|characteristics?)'],
    'optimization': [r'process optimi[sz]ation',
        r'(?:process(?:es)?|settings|parameters) (?:is |are |seems? |currently |still |well |fully |properly |not |never |poorly |under ){0,6}(?:optimi[sz]ed|optimal|inefficient|ineffective|unoptimized|unoptimised|suboptimal)',
        r'(?:inefficient|ineffective|unoptimized|unoptimised|suboptimal) (?:\w+ ){0,2}process(?:es)?',
        r'optimi[sz](?:e|es|ed|ing|ation) (?:\w+ ){0,4}process(?:es)?',
        r'process(?:es)? (?:\w+ ){0,3}(?:needs?|requires?) (?:\w+ ){0,2}optimi[sz](?:ing|ation)', r'(?:optimi[sz]e|best|optimal|adjust|recommend) (?:\w+ ){0,4}(?:settings|parameters|temperature|pressure|speed)', r'(?:closer|close) to (?:the )?target', r'(?:reduce|minimi[sz]e) (?:\w+ ){0,3}(?:deviation|variation from target)'],
}


# Phrase aliases and concept combinations extend the original patterns.
# A combination requires one phrase from EVERY group in the tuple.
INTENTS = {
    'predictive_spc': {
        'aliases': ['predictive quality', 'predictive spc', 'future oos', 'early warning', 'forecast quality', 'risk of failure'],
        'groups': [(['predict', 'forecast', 'anticipate', 'ahead of time', 'before', 'future', 'going to'], ['defect', 'failure', 'out of spec', 'quality', 'reject', 'scrap', 'oos']),
                   (['drift', 'deteriorating'], ['warn', 'warning', 'future', 'predict'])]},
    'batch_anomaly': {
        'aliases': ['batch anomaly', 'lot anomaly', 'anomalous batches', 'abnormal batches', 'batch comparison'],
        'groups': [(['batch', 'lot', 'work order'], ['unusual', 'abnormal', 'anomaly', 'anomalous', 'outlier', 'different', 'inconsistent', 'odd', 'strange', 'compare', 'bad'])]},
    'mislabel': {
        'aliases': ['mislabel', 'mislabeled', 'mislabelled', 'wrong label', 'mixed up labels', 'label mismatch', 'incorrect sku', 'wrong sku', 'outlier detection'],
        'groups': [(['label', 'sku', 'part type', 'declared type', 'part number'], ['wrong', 'incorrect', 'mismatch', 'mixed', 'different', 'does not match', 'do not match']),
                   (['measurement', 'reading', 'record'], ['outlier', 'unusual', 'abnormal', 'odd', 'strange'])]},
    'inspection_frequency': {
        'aliases': ['inspection frequency', 'sampling frequency', 'sampling interval', 'inspection interval', 'inspection schedule', 'sample frequency', 'over inspecting', 'over inspection'],
        'groups': [(['inspect', 'inspection', 'sample', 'sampling', 'measurement', 'check'], ['how often', 'how frequently', 'frequency', 'interval', 'too often', 'less often', 'more often', 'every hour', 'hourly', 'how many times']),
                   (['inspection', 'sampling'], ['reduce', 'increase', 'schedule', 'excessive', 'unnecessary'])]},
    'spc_interpretation': {
        'aliases': ['nelson', 'western electric', 'out of control', 'control rule', 'rule violation', 'spc interpretation', 'special cause'],
        'groups': [(['chart', 'spc', 'signal', 'control limit'], ['explain', 'interpret', 'understand', 'meaning', 'why', 'cause', 'action']),
                   (['control chart', 'spc'], ['trend', 'run', 'shift', 'alternating'])]},
    'entry_integrity': {
        'aliases': ['pencil whipping', 'data integrity', 'operator integrity', 'backfill', 'backfilled', 'fabricated data', 'made up readings', 'copy paste', 'data entry error'],
        'groups': [(['operator', 'entry', 'entries', 'reading', 'value', 'record', 'data'], ['duplicate', 'repeated', 'copied', 'suspicious', 'fake', 'fabricated', 'rounded']),
                   (['entry', 'entries', 'enter', 'typing'], ['too fast', 'late', 'delay', 'mistake', 'error', 'same time']),
                   (['operator', 'entry', 'reading'], ['identical', 'always the same', 'all the same', 'never change'])]},
    'database_health': {
        'aliases': ['sql server', 'database', 'slow query', 'slow queries', 'missing index', 'fragmentation', 'query store', 'blocking', 'deadlock', 'backup', 'database health'],
        'groups': [(['query', 'queries', 'sql', 'table', 'index'], ['slow', 'space', 'storage', 'performance', 'timeout', 'expensive', 'blocked', 'health'])]},
    'coa': {
        'aliases': ['coa', 'certificate of analysis', 'quality certificate', 'test certificate', 'analysis certificate'],
        'groups': [(['certificate'], ['generate', 'create', 'prepare', 'customer', 'export', 'download', 'lot', 'batch', 'quality', 'test'])]},
    'copilot': {
        'aliases': ['cpk', 'cp', 'capability', 'histogram', 'scatter plot', 'ewma', 'cusum', 'imr', 'i mr', 'xbar', 'x bar', 'x bar r', 'xbar r', 'x bar s', 'dashboard', 'box plot', 'normal probability plot', 'manufacturing copilot'],
        'groups': [(['chart', 'graph', 'plot', 'trend', 'statistics', 'data table'], ['show', 'create', 'build', 'view', 'draw', 'display', 'plot', 'compare', 'analyze', 'analyse']),
                   (['part', 'machine', 'trace', 'characteristic'], ['compare', 'versus', 'comparison'])]},
    'optimization': {
        'aliases': ['process optimization', 'optimal settings', 'best settings', 'setpoint', 'set point', 'closer to target', 'off target', 'not hitting target', 'process efficiency'],
        'groups': [(['process', 'machine', 'parameter', 'setting', 'temperature', 'pressure', 'speed'], ['optimize', 'optimization', 'optimized', 'optimal', 'inefficient', 'suboptimal', 'tune', 'adjust', 'recommend', 'best', 'choose', 'determine']),
                   (['measurement', 'process', 'machine', 'output'], ['closer to target', 'off target', 'center on target', 'not meeting target', 'not hitting target'])]},
}

SPELLING = {
    'proccess': 'process', 'proces': 'process', 'optmized': 'optimized',
    'optmize': 'optimize', 'optmization': 'optimization', 'optimise': 'optimize',
    'optimised': 'optimized', 'optimising': 'optimizing', 'optimisation': 'optimization',
    'databse': 'database', 'datbase': 'database', 'dashbord': 'dashboard',
    'dashbaord': 'dashboard', 'copliot': 'copilot', 'inspecton': 'inspection',
    'frequecy': 'frequency', 'frquency': 'frequency', 'anomoly': 'anomaly',
    'anomolies': 'anomalies', 'mislabled': 'mislabeled', 'certifcate': 'certificate',
    'mesurement': 'measurement', 'querry': 'query',
}
WORD_FORMS = {
    'batches': 'batch', 'lots': 'lot', 'orders': 'order', 'parts': 'part',
    'machines': 'machine', 'measurements': 'measurement', 'readings': 'reading',
    'records': 'record', 'values': 'value', 'operators': 'operator', 'labels': 'label',
    'defects': 'defect', 'failures': 'failure', 'rejects': 'reject', 'outliers': 'outlier',
    'anomalies': 'anomaly', 'certificates': 'certificate', 'dashboards': 'dashboard',
    'charts': 'chart', 'graphs': 'graph', 'parameters': 'parameter', 'settings': 'setting',
    'inspections': 'inspection', 'inspectors': 'inspector', 'indexes': 'index',
    'indices': 'index', 'backups': 'backup', 'traces': 'trace', 'characteristics': 'characteristic',
    'predicting': 'predict', 'prediction': 'predict', 'forecasting': 'forecast',
    'optimizing': 'optimize', 'comparing': 'compare', 'generating': 'generate',
    'creating': 'create', 'checking': 'check', 'inspecting': 'inspect',
    'entering': 'enter', 'entered': 'enter', 'slowness': 'slow', 'slower': 'slow',
    'improving': 'improve', 'reducing': 'reduce', 'increasing': 'increase',
}
STOP_WORDS = set('a an the is are was were be been being to for from of at by with in on and or but my our your we i it this that want need help app apps data process quality manufacturing results report reports information analysis using use show make can could would should not no do does have has get'.split())


def _one_edit(a, b):
    """One insertion/deletion/substitution or adjacent transposition only."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        mismatches = [i for i in range(len(a)) if a[i] != b[i]]
        return len(mismatches) == 1 or (len(mismatches) == 2 and
            mismatches[1] == mismatches[0] + 1 and
            a[mismatches[0]] == b[mismatches[1]] and a[mismatches[1]] == b[mismatches[0]])
    short, long = (a, b) if len(a) < len(b) else (b, a)
    return any(long[:i] + long[i + 1:] == short for i in range(len(long)))


def normalize_request(text):
    import re
    import unicodedata
    text = unicodedata.normalize('NFKC', text).lower().replace('’', "'")
    text = re.sub(r'\bc[ .]*p[ .]*k\b', 'cpk', text)
    replacements = {"isn't": 'is not', 'isnt': 'is not', "aren't": 'are not',
                    'arent': 'are not', "don't": 'do not', 'dont': 'do not',
                    "doesn't": 'does not', "can't": 'cannot', "won't": 'will not',
                    "wasn't": 'was not', "weren't": 'were not'}
    for old, new in replacements.items():
        text = re.sub(r'\b' + re.escape(old) + r'\b', new, text)
    text = re.sub(r'[-_/]', ' ', text)
    vocabulary = set(WORD_FORMS) | set(WORD_FORMS.values()) | set(SPELLING.values())
    for spec in INTENTS.values():
        for phrase in spec['aliases']:
            vocabulary.update(phrase.split())
        for groups in spec['groups']:
            for group in groups:
                for phrase in group:
                    vocabulary.update(phrase.split())
    corrections = {}
    def correct(m):
        word = m.group()
        replacement = SPELLING.get(word, word)
        if replacement == word and len(word) >= 6 and word not in vocabulary:
            candidates = sorted(w for w in vocabulary if len(w) >= 6 and _one_edit(word, w))
            if len(candidates) == 1:
                replacement = candidates[0]
        if replacement != word:
            corrections[word] = replacement
        return replacement
    text = re.sub(r'\b[a-z]+\b', correct, text)
    return re.sub(r'[^\S\n]+', ' ', text).strip(), corrections


def _canonical(text):
    import re
    return re.sub(r'\b[a-z]+\b', lambda m: WORD_FORMS.get(m.group(), m.group()), text)


def _positive_clauses(text):
    """Conservative exclusions. A negative process condition is still a need."""
    import re
    clauses = []
    # 'rather than X' denotes an excluded alternative.
    for sentence in re.split(r'[.!?;\n]+', text):
        sentence = re.sub(r'\brather than\b', ';not interested in', sentence)
        segments = re.split(r';|,|\b(?:but|however|instead)\b|\band (?=(?:i |we )?(?:want|need|show|create|generate|find|compare|reduce)\b)', sentence)
        for clause in segments:
            if re.search(r'\b(?:do not|does not|not) (?:want|need|require|looking for|interested in)\b|\bno need\b|\bwithout\b', clause):
                continue
            if re.match(r'^\s*(?:no|not)\b(?!\s+(?:only|sure|meeting|hitting)\b)', clause):
                continue
            clauses.append(clause.strip())
    return [c for c in clauses if c]


def _hits(clause, pattern):
    import re
    found = []
    for m in re.finditer(r'(?<!\w)(?:' + pattern + r')(?!\w)', clause):
        prefix = re.sub(r'\bnot (?:only|sure)\b', '', clause[:m.start()])
        if re.search(r'\b(?:no|not)\s+(?:(?:a|an|the|any)\s+)?$', prefix):
            continue
        found.append(m.group())
    return found


def analyze_customer_request(catalog, text):
    """Rank options using aliases, concept combinations, and catalog overlap.

    Scores measure rule strength, never statistical confidence. This function
    performs no network calls and does not execute any customer input.
    """
    import re
    raw = text if isinstance(text, str) else ''
    query, corrections = normalize_request(raw[:2000])
    clauses = _positive_clauses(query)
    apps = visible_apps(catalog)
    results = []
    for app in apps:
        spec = INTENTS.get(app['id'], {'aliases': [], 'groups': []})
        evidence = []
        strength = 0
        for clause in clauses:
            canonical = _canonical(clause)
            name, _ = normalize_request(app['name'])
            for alias in [name] + spec['aliases']:
                hits = _hits(canonical, re.escape(_canonical(alias)))
                if hits:
                    strength = max(strength, 20 if alias == name else 10)
                    evidence.extend(hits)
            for pattern in TEXT_RULES.get(app['id'], []):
                hits = _hits(clause, pattern)
                if hits:
                    strength = max(strength, 10)
                    evidence.extend(hits)
            for groups in spec['groups']:
                components = []
                for group in groups:
                    hits = [h for phrase in group for h in _hits(canonical, re.escape(_canonical(phrase)))]
                    if not hits:
                        break
                    components.append(hits[0])
                if len(components) == len(groups):
                    strength = max(strength, 9)
                    evidence.append(' + '.join(components))
        if evidence:
            results.append({'app': app, 'matched_phrases': list(dict.fromkeys(evidence))[:5],
                            'match_strength': strength, 'match_type': 'rules'})
    # Catalog fallback for unfamiliar descriptions or future catalog apps.
    # Requires multiple informative terms; generic 'quality' never matches alone.
    if not results and clauses:
        documents = {}
        for app in apps:
            description = ' '.join([app['name'], app['summary']] + app['outputs'])
            normalized, _ = normalize_request(description)
            documents[app['id']] = set(re.findall(r'\b[a-z]{3,}\b', _canonical(normalized))) - STOP_WORDS
        fallback_text = ' '.join(c for c in clauses if not re.search(r'\b(?:no|not)\b', c))
        qwords = set(re.findall(r'\b[a-z]{3,}\b', _canonical(fallback_text))) - STOP_WORDS
        for app in apps:
            overlap = qwords & documents[app['id']]
            rare = [w for w in overlap if sum(w in d for d in documents.values()) <= 2]
            if len(overlap) >= 2 and rare:
                results.append({'app': app, 'matched_phrases': sorted(overlap),
                                'match_strength': len(overlap), 'match_type': 'catalog'})
    results.sort(key=lambda m: -m['match_strength'])
    # Generic language gets an actionable clarification, not an invented answer.
    positive_text = ' '.join(clauses)
    followup = None
    if not results and re.search(r'\b(?:quality|scrap|rejects?|defects?|variation|spc|anomal\w*)\b', positive_text):
        followup = 'What would help most: predict future problems, investigate unusual batches, understand chart signals, or adjust process settings?'
    elif not results and query:
        followup = 'Which area do you mean: process settings, inspection timing, unusual data, charts, certificates, or database performance?'
    elif len(results) > 1:
        followup = 'Several options relate to your request. Which goal is closest to what you want to do first?'
    return {'matches': results, 'corrections': corrections, 'followup': followup,
            'normalized_request': query}


def parse_customer_request(catalog, text):
    """Backward-compatible entry point used by existing callers."""
    return analyze_customer_request(catalog, text)['matches']
