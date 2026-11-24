"""Provisional quality, with missingness and a complete transform trace."""
import math
from . import db


def transform(raw, rule):
    if raw is None:
        return None
    try:
        v = float(raw)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(v) or v < 0:
        return None
    kind = rule.get('transform','identity01')
    cap = rule.get('cap',1)
    if cap <= 0:
        raise ValueError('Transform cap must be positive')
    if kind == 'linear_cap':
        v /= cap
    elif kind == 'log_cap':
        v = math.log1p(v)/math.log1p(cap)
    elif kind != 'identity01':
        raise ValueError(f'Unknown transform: {kind}')
    return min(1.,max(0.,v))


def composite(raw, rules):
    parts = {}
    for k,r in rules.items():
        w = float(r['weight'])
        if not math.isfinite(w) or w < 0:
            raise ValueError('Weights must be finite and non-negative')
        parts[k] = {'raw':raw.get(k),'transformed':transform(raw.get(k),r),'weight':w,'transform':r.get('transform','identity01'),'cap':r.get('cap')}
    total = sum(x['weight'] for x in parts.values())
    available = sum(x['weight'] for x in parts.values() if x['transformed'] is not None)
    for p in parts.values():
        p['effective_weight'] = p['weight']/available if available and p['transformed'] is not None else 0
    return {'score':sum(p['transformed']*p['effective_weight'] for p in parts.values() if p['transformed'] is not None) if available else None,'coverage':available/total if total else 0.,'components':parts}


def score_source(con, wid, project):
    row = con.execute('SELECT * FROM works WHERE id=?',(wid,)).fetchone()
    raw, provenance = {}, {}
    for m in con.execute('SELECT * FROM metrics WHERE work_id=? ORDER BY at',(wid,)):
        raw[m['name']] = db.loads(m['value_json'])
        provenance[m['name']] = {'provider':m['source'],'at':m['at'],'provenance':db.loads(m['provenance_json'])}
    result = composite(raw,project.get('quality.source'))
    result['metric_provenance'] = provenance
    result['pre_multiplier_score'] = result['score']
    result['peer_reviewed'] = None if row['peer_reviewed'] is None else bool(row['peer_reviewed'])
    result['retracted'] = None if row['is_retracted'] is None else bool(row['is_retracted'])
    multiplier = project.get('quality.non_peer_reviewed_multiplier') if row['peer_reviewed'] == 0 else 1.
    if row['is_retracted'] == 1:
        multiplier = 0.
        result['score'] = 0.
    elif result['score'] is not None:
        result['score'] *= multiplier
    result['multiplier'] = multiplier
    result['provisional'] = project.get('quality.provisional')
    result['low_coverage'] = result['coverage'] < project.get('quality.low_coverage_threshold')
    return result


def score_quote(con, qid, project):
    q = con.execute('SELECT * FROM quotes WHERE id=?',(qid,)).fetchone()
    legacy = db.loads(q['legacy_json'],{})
    raw = {'evidence_class':project.get('quality.class_scores').get(q['evidence_class']),
           'chain_depth':1/(1+q['chain_depth']) if q['chain_depth'] is not None and q['chain_depth'] >= 0 else None,
           'uncertainty':project.get('quality.uncertainty_scores').get(legacy.get('uncertainty_type')),
           'condition_match':legacy.get('condition_match_score'),
           'replication':legacy.get('independent_replications')}
    check = con.execute('SELECT result FROM quote_checks WHERE quote_id=? AND method=? ORDER BY at DESC LIMIT 1',(qid,'verbatim')).fetchone()
    raw['verbatim'] = {'pass':1.,'fail':0.}.get(check[0]) if check else None
    rules = {k:dict(v) for k,v in project.get('quality.quote').items()}
    rules['replication']['transform'] = 'linear_cap'
    result = composite(raw,rules)
    result['observations'] = {'evidence_class':q['evidence_class'],'chain_depth':q['chain_depth'],'uncertainty_type':legacy.get('uncertainty_type'),'verbatim_check':check[0] if check else None}
    result['inherited_source'] = score_source(con,q['work_id'],project)
    result['provisional'] = True
    result['low_coverage'] = result['coverage'] < project.get('quality.low_coverage_threshold')
    return result


def save_score(con, entity, eid, result, project):
    con.execute('INSERT INTO scores VALUES (?,?,?,?,?,?,?)',(entity,eid,db.utcnow(),project.get('quality.rule_version'),result['score'],result['coverage'],db.dumps(result)))
