import json
import httpx
import networkx as nx
import pytest
from litkit import db
from litkit.config import init_project
from litkit.openalex import Client, apply, snowball, FetchError
from litkit.graph import export_graph, rank
from litkit.legacy import import_legacy


def test_snowball_budget_graph_rank(tmp_path):
    p = init_project(tmp_path)
    def response(request):
        return httpx.Response(200,json={'results':[{'id':'https://openalex.org/W3','display_name':'Third','referenced_works':['https://openalex.org/W1']}], 'meta':{'next_cursor':None}})
    with db.database(p.db_path) as con:
        wid = db.ensure_work(con,openalex='W1',local_key='seed',status='corpus')
        apply(con,wid,{'id':'https://openalex.org/W1','referenced_works':['https://openalex.org/W2','https://openalex.org/W4']})
        client = Client(p,max_calls=1,secrets={},transport=httpx.MockTransport(response))
        result = snowball(con,client,db.select_works(con),1,1)
        assert result['new_works'] == 1
        assert result['truncated']
        assert con.execute('SELECT COUNT(*) FROM works').fetchone()[0] == 2
        output = export_graph(con,p)
        assert output['edges'] == 1
        restored = nx.read_graphml(p.path('graph_dir')/'citations.graphml')
        assert restored.has_edge('seed','oa:W2')
        ranked = rank(con,p)
        assert ranked[0]['components']['cited_by_corpus']['raw'] == 1
        assert ranked[0]['components']['quality_prior']['raw'] is None
        assert ranked[0]['coverage'] < 1
        assert client.calls == 1


def test_http_error_never_discloses_secret(tmp_path):
    p = init_project(tmp_path)
    def response(request):
        raise httpx.ConnectError('leaked secret-key '+str(request.url))
    p.config['http']['max_retries'] = 0
    client = Client(p,secrets={'openalex_api_key':'secret-key'},transport=httpx.MockTransport(response))
    with pytest.raises(FetchError) as exc:
        client.get('works/W1')
    assert 'secret-key' not in str(exc.value)
    assert 'api_key' not in str(exc.value)


def test_enrich_offline_after_identifier_added(tmp_path):
    from litkit.openalex import enrich
    p = init_project(tmp_path)
    with db.database(p.db_path) as con:
        db.ensure_work(con,local_key='seed',doi='10.1234/abc',status='corpus')
        transport = httpx.MockTransport(lambda r: httpx.Response(200,json={'id':'https://openalex.org/W1','doi':'https://doi.org/10.1234/abc'}))
        online = Client(p,secrets={},transport=transport)
        assert enrich(con,online,db.select_works(con))['ok'] == 1
        offline = Client(p,secrets={},offline=True)
        result = enrich(con,offline,db.select_works(con))
        assert result['ok'] == 1
        assert result['http_calls'] == 0


def test_no_graph_edges_empty_and_isolates(tmp_path):
    p = init_project(tmp_path)
    with db.database(p.db_path) as con:
        assert export_graph(con,p)['nodes'] == 0
        db.ensure_work(con,local_key='x')
        assert export_graph(con,p)['communities'] == 1


def test_transform_invalid_and_weight_renormalization():
    from litkit.quality import composite
    rules = {'a':{'weight':.2},'b':{'weight':.8}}
    result = composite({'a':.5},rules)
    assert result['score'] == .5
    assert result['coverage'] == .2
    assert composite({'a':float('nan')},rules)['score'] is None
    with pytest.raises(ValueError):
        composite({}, {'a':{'weight':-1}})
