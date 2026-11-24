"""Bounded OpenAlex client. Credentials never enter cache keys or diagnostics."""
import json
import re
import time
from urllib.parse import quote
import httpx
from . import db
from .config import load_secrets


class FetchError(RuntimeError):
    pass


class Client:
    def __init__(self, project, *, offline=False, max_calls=100, secrets=None, transport=None):
        self.project, self.offline, self.max_calls = project, offline, max_calls
        self.secrets = load_secrets(project) if secrets is None else secrets
        self.calls = 0
        self.last = 0.
        self.http = httpx.Client(timeout=project.get('http.timeout_s'),transport=transport,follow_redirects=False)
        self.cache = project.path('cache_dir')
        self.cache.mkdir(parents=True, exist_ok=True)

    def clean(self, value):
        text = db.dumps(value)
        for secret in self.secrets.values():
            if secret:
                text = text.replace(secret,'[REDACTED]')
                text = text.replace(quote(secret,safe=''),'[REDACTED]')
        return json.loads(text)

    def get(self, endpoint, params=None):
        if not re.fullmatch(r'works(?:/[A-Za-z0-9._~%:/()\-]+)?',endpoint):
            raise FetchError('Invalid OpenAlex endpoint')
        params = dict(params or {})
        if any(k in params for k in ('api_key','mailto')):
            raise FetchError('Credentials must be supplied through secrets')
        key = db.digest(db.dumps([endpoint,params]))
        path = self.cache/(key+'.json')
        if path.exists():
            cached = json.loads(path.read_text(encoding='utf-8'))
            age = time.time()-cached['cached_at']
            if self.offline or age < self.project.get('http.cache_ttl_days')*86400:
                return cached['payload']
        if self.offline:
            raise FetchError('Offline cache miss')
        if self.secrets.get('openalex_api_key'):
            params['api_key'] = self.secrets['openalex_api_key']
        if self.secrets.get('contact_email'):
            params['mailto'] = self.secrets['contact_email']
        for attempt in range(self.project.get('http.max_retries')+1):
            if self.calls >= self.max_calls:
                raise FetchError('HTTP call budget exhausted')
            interval = self.project.get('http.min_interval_s',{}).get('api.openalex.org',.12)
            time.sleep(max(0,interval-(time.monotonic()-self.last)))
            self.calls += 1
            self.last = time.monotonic()
            try:
                response = self.http.get('https://api.openalex.org/'+endpoint,params=params)
            except httpx.HTTPError:
                if attempt == self.project.get('http.max_retries'):
                    raise FetchError('OpenAlex network request failed') from None
                time.sleep(min(2**attempt,8))
                continue
            if response.status_code == 200:
                try:
                    payload = self.clean(response.json())
                except ValueError:
                    raise FetchError('OpenAlex returned invalid JSON') from None
                tmp = path.with_suffix('.tmp')
                tmp.write_text(db.dumps({'cached_at':time.time(),'payload':payload}),encoding='utf-8')
                tmp.replace(path)
                return payload
            if response.status_code not in (429,500,502,503,504):
                raise FetchError(f'OpenAlex HTTP {response.status_code}')
            if attempt < self.project.get('http.max_retries'):
                time.sleep(min(2**attempt,8))
        raise FetchError('OpenAlex retry limit reached')

    def close(self):
        self.http.close()


def apply(con, wid, payload):
    db.add_identifier(con,wid,'openalex',payload.get('id'))
    db.add_identifier(con,wid,'doi',payload.get('doi'))
    con.execute('UPDATE works SET title=COALESCE(title,?),year=COALESCE(year,?),is_retracted=COALESCE(?,is_retracted),updated_at=? WHERE id=?',
                (payload.get('display_name'),payload.get('publication_year'),payload.get('is_retracted'),db.utcnow(),wid))
    for name,value in {'fwci':payload.get('fwci'),'citation_percentile':(payload.get('citation_normalized_percentile') or {}).get('value'),'cited_by_count':payload.get('cited_by_count')}.items():
        db.metric(con,wid,'openalex',name,value,provenance={'openalex_id':payload.get('id')})
    con.execute('INSERT INTO enrichments(work_id,source,at,outcome,payload_json) VALUES(?,?,?,?,?)',(wid,'openalex',db.utcnow(),'ok',db.dumps(payload)))


def enrich(con, client, works):
    result = {'ok':0,'skipped':0,'errors':[]}
    for w in works:
        oa = con.execute("SELECT value FROM identifiers WHERE work_id=? AND scheme='openalex'",(w['id'],)).fetchone()
        identifier = 'https://doi.org/'+w['doi'] if w['doi'] else (oa[0] if oa else None)
        if not identifier:
            result['skipped'] += 1
            continue
        try:
            payload = client.get('works/'+quote(identifier,safe=':/'))
            apply(con,w['id'],payload)
            result['ok'] += 1
        except FetchError as exc:
            result['errors'].append({'work':w['id'],'error':str(exc)})
            if 'budget' in str(exc):
                break
    result['http_calls'] = client.calls
    return result


def snowball(con, client, works, max_new, max_citing, direction='both'):
    result = {'new_works':0,'edges_added':0,'errors':[],'truncated':False}
    for w in works:
        row = con.execute("SELECT payload_json FROM enrichments WHERE work_id=? AND source='openalex' AND outcome='ok' ORDER BY at DESC LIMIT 1",(w['id'],)).fetchone()
        if not row:
            result['errors'].append({'work':w['id'],'error':'Enrich seed first'})
            continue
        payload = db.loads(row[0])
        def add(identifier, citing, metadata=None):
            other = db.resolve(con,identifier)
            if other is None:
                if result['new_works'] >= max_new:
                    result['truncated'] = True
                    return
                other = db.ensure_work(con,openalex=identifier,doi=(metadata or {}).get('doi'),title=(metadata or {}).get('display_name'),year=(metadata or {}).get('publication_year'))
                result['new_works'] += 1
            before = con.total_changes
            db.edge(con,other if citing else w['id'],w['id'] if citing else other,'openalex')
            result['edges_added'] += con.total_changes-before
            if metadata:
                apply(con,other,metadata)
        if direction in ('both','references'):
            for identifier in payload.get('referenced_works',[]):
                add(identifier,False)
        if direction in ('both','citations') and payload.get('id'):
            fetched, cursor = 0, '*'
            while fetched < max_citing and cursor:
                try:
                    page = client.get('works',{'filter':'cites:'+db.short_oa(payload['id']),'per-page':min(200,max_citing-fetched),'cursor':cursor,'sort':'cited_by_count:desc'})
                except FetchError as exc:
                    result['errors'].append({'work':w['id'],'error':str(exc)})
                    break
                records = page.get('results',[])
                for item in records[:max_citing-fetched]:
                    add(item['id'],True,item)
                fetched += len(records)
                next_cursor = page.get('meta',{}).get('next_cursor')
                if not records or next_cursor == cursor:
                    break
                cursor = next_cursor
            if fetched >= max_citing:
                result['truncated'] = True
    result['http_calls'] = client.calls
    return result
