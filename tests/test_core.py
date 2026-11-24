import json
from pathlib import Path
import pytest
from click.testing import CliRunner
from litkit.cli import main
from litkit.config import init_project
from litkit.db import database, ensure_work, metric, counts
from litkit.quality import composite, score_source, score_quote
from litkit.openalex import Client, FetchError


def test_missing_and_veto(tmp_path):
    p = init_project(tmp_path)
    with database(p.db_path) as con:
        w = ensure_work(con, local_key='x')
        assert score_source(con, w, p)['score'] is None
        metric(con, w, 'openalex', 'fwci', 2)
        s = score_source(con, w, p)
        assert s['score'] == 1
        assert s['coverage'] == pytest.approx(.2)
        con.execute('UPDATE works SET peer_reviewed=0 WHERE id=?', (w,))
        assert score_source(con, w, p)['score'] == .5
        con.execute('UPDATE works SET is_retracted=1 WHERE id=?', (w,))
        assert score_source(con, w, p)['score'] == 0


def test_cache_budget_redaction(tmp_path):
    import httpx
    p = init_project(tmp_path)
    def respond(request):
        return httpx.Response(200, json={'id':'https://openalex.org/W1', 'echo':'secret-value'})
    c = Client(p, secrets={'openalex_api_key':'secret-value'}, max_calls=1,
               transport=httpx.MockTransport(respond))
    assert c.get('works/W1')['id'].endswith('W1')
    assert c.get('works/W1')['id'].endswith('W1')
    with pytest.raises(FetchError, match='budget'):
        c.get('works/W2')
    assert 'secret-value' not in ''.join(x.read_text() for x in p.path('cache_dir').glob('*.json'))
    c = Client(p, offline=True, secrets={})
    assert c.get('works/W1')['id'].endswith('W1')
    with pytest.raises(FetchError, match='Offline'):
        c.get('works/W2')


def test_cli_import_idempotent_lossless(tmp_path):
    old = tmp_path/'old'
    (old/'raw/_staging').mkdir(parents=True)
    source = {'key':'a','doi':'10.1234/a','extra':{'unknown':[1, None]},'bibtex':'@article{a,title={A}}'}
    quote = {'id':'Q001','source_key':'a','quote':'words','provenance':'measured','check':'p1'}
    (old/'raw/_staging/consolidated-evidence.json').write_text(json.dumps({'sources':[source],'quotes':[quote],'excluded':[]}))
    (old/'measurements.json').write_text(json.dumps({'measurements':[{'id':'M001','quotation_id':'Q001','source_key':'a','value':1}]}))
    runner = CliRunner()
    root = tmp_path/'project'
    assert runner.invoke(main,['init',str(root)]).exit_code == 0
    for _ in range(2):
        result = runner.invoke(main,['--project',str(root),'import-legacy',str(old)])
        assert result.exit_code == 0, result.output
    with database(root/'litkit.db') as con:
        assert counts(con)['works'] == 1
        assert counts(con)['quotes'] == 1
        assert json.loads(con.execute('SELECT legacy_json FROM works').fetchone()[0]) == source
        assert con.execute('SELECT peer_reviewed FROM works').fetchone()[0] is None
        s = score_quote(con,'Q001',init_project(root))
        assert s['components']['replication']['transformed'] is None
        assert s['components']['verbatim']['transformed'] is None
    assert runner.invoke(main,['--project',str(root),'export']).exit_code == 0
    assert (root/'exports/works.jsonl').exists()
