"""Lossless, transactional ingestion of the consolidated legacy evidence ledger."""
import json
import re
from pathlib import Path
from . import db


def insert_preserved(con, table, data):
    old = con.execute(f'SELECT legacy_json FROM {table} WHERE id=?', (data['id'],)).fetchone()
    if old:
        if old[0] != data['legacy_json']:
            raise ValueError(f'Conflicting legacy record {table}:{data["id"]}; refusing overwrite')
        return
    cols = ','.join(data)
    con.execute(f'INSERT INTO {table} ({cols}) VALUES ({",".join("?" for _ in data)})', tuple(data.values()))


def import_legacy(con, root):
    root = Path(root).resolve()
    evidence_path = root/'raw/_staging/consolidated-evidence.json'
    measurements_path = root/'measurements.json'
    evidence = json.loads(evidence_path.read_text(encoding='utf-8-sig'))
    measurements = json.loads(measurements_path.read_text(encoding='utf-8-sig'))
    con.execute('CREATE TABLE IF NOT EXISTS legacy_documents (path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, content BLOB NOT NULL)')
    for path in (evidence_path, measurements_path):
        data = path.read_bytes()
        name = str(path.relative_to(root)).replace('\\','/')
        old = con.execute('SELECT sha256 FROM legacy_documents WHERE path=?',(name,)).fetchone()
        if old and old[0] != db.digest(data):
            raise ValueError(f'Legacy document changed: {name}; import into a fresh project')
        con.execute('INSERT OR IGNORE INTO legacy_documents VALUES (?,?,?)',(name,db.digest(data),data))
    mapping = {}
    for s in evidence['sources']:
        key = s['key']
        existing = con.execute('SELECT legacy_json FROM works WHERE local_key=?',(key,)).fetchone()
        if existing and existing[0] and existing[0] != db.dumps(s):
            raise ValueError(f'Conflicting source {key}')
        bib = s.get('bibtex','')
        title = re.search(r'\btitle\s*=\s*\{(.*?)\}',bib,re.I|re.S)
        year = re.search(r'\byear\s*=\s*[{\"]?(\d{4})',bib,re.I)
        wid = db.ensure_work(con,local_key=key,doi=s.get('doi'), title=s.get('title') or (title[1] if title else None),year=int(year[1]) if year else None,status='corpus')
        preserved = con.execute('SELECT legacy_json FROM works WHERE id=?',(wid,)).fetchone()[0]
        if preserved and preserved != db.dumps(s):
            raise ValueError(f'Duplicate identifier would merge distinct source records: {key}')
        mapping[key] = wid
        # No venue or publication-type heuristic establishes peer review.
        peer = s.get('peer_reviewed') if type(s.get('peer_reviewed')) is bool else None
        retracted = s.get('is_retracted') if type(s.get('is_retracted')) is bool else None
        con.execute('UPDATE works SET flag=?,bibtex=?,summary=?,topics_json=?,legacy_json=?,peer_reviewed=COALESCE(peer_reviewed,?),is_retracted=COALESCE(is_retracted,?) WHERE id=?',
                    (s.get('flag'),bib,s.get('summary'),db.dumps(s.get('topics')),db.dumps(s),peer,retracted,wid))
        if s.get('file'):
            path = (root/s['file']).resolve()
            if not path.is_relative_to(root):
                raise ValueError('Legacy file escapes input directory')
            if path.is_file():
                data = path.read_bytes()
                con.execute('INSERT OR IGNORE INTO files(id,work_id,path,kind,sha256,bytes,at) VALUES(?,?,?,?,?,?,?)',
                            (db.digest(wid+str(path)),wid,str(path),path.suffix.lstrip('.'),db.digest(data),len(data),db.utcnow()))
    for q in evidence['quotes']:
        fields = dict(id=q['id'], work_id=mapping[q['source_key']], legacy_json=db.dumps(q),added_at=db.utcnow())
        for k in ('location','quote','parameter','uncertainty','chain','explanation','topic','origin','ocr_note','chain_depth'):
            fields[k] = q.get(k)
        fields.update(value_json=db.dumps(q.get('value')),model_value_json=db.dumps(q.get('value_model_units')),unit=q.get('model_units'),n_json=db.dumps(q.get('n')),conditions_json=db.dumps(q.get('conditions')),evidence_class=q.get('provenance'),use_note=q.get('use'))
        insert_preserved(con,'quotes',fields)
    for m in measurements['measurements']:
        fields = dict(id=m['id'],quote_id=m.get('quotation_id'),work_id=mapping.get(m.get('source_key')),parameter=m.get('parameter'),value_json=db.dumps(m.get('value')),unit=m.get('unit'),conditions_json=db.dumps(m.get('conditions')),uncertainty_json=db.dumps(m.get('reported_uncertainty')),transferable=m.get('transferable_to_experiment'),note=m.get('eligibility_note'),legacy_json=db.dumps(m))
        insert_preserved(con,'measurements',fields)
    for x in evidence.get('excluded',[]):
        con.execute('INSERT OR IGNORE INTO excluded VALUES (?,?,?)',(db.digest(db.dumps(x)),x.get('reason'),db.dumps(x)))
    return {'sources':len(evidence['sources']),'quotes':len(evidence['quotes']),'measurements':len(measurements['measurements']),'excluded':len(evidence.get('excluded',[]))}
