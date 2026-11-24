"""Citation graph exports and explainable candidate frontier ranking."""
import html
import math
import networkx as nx
from . import db
from .quality import composite, score_source


def build(con, project):
    graph = nx.DiGraph()
    for w in db.select_works(con,status='all'):
        if w['status'] != 'corpus' and not project.get('graph.include_candidates'):
            continue
        graph.add_node(w['id'],title=w['title'] or w['id'],status=w['status'])
    for e in con.execute('SELECT citing,cited FROM edges'):
        if e[0] in graph and e[1] in graph:
            graph.add_edge(*e)
    undirected = graph.to_undirected()
    if undirected.number_of_edges():
        communities = nx.community.louvain_communities(undirected,seed=project.get('graph.louvain_seed'),resolution=project.get('graph.louvain_resolution'))
    else:
        communities = [{n} for n in undirected]
    for i,community in enumerate(sorted(communities,key=lambda c:sorted(c))):
        for n in community:
            graph.nodes[n]['community'] = i
    return graph


def export_graph(con, project, png=False):
    graph = build(con,project)
    out = project.path('graph_dir')
    out.mkdir(parents=True,exist_ok=True)
    nx.write_graphml(graph,out/'citations.graphml')
    maximum = project.get('graph.html_max_nodes')
    view = graph.subgraph(list(graph)[:maximum])
    pos = nx.spring_layout(view,seed=project.get('graph.louvain_seed')) if len(view) else {}
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 1000" role="img" aria-label="Citation graph">']
    def xy(n):
        x,y = pos[n]
        return 600+float(x)*510,500+float(y)*420
    for a,b in view.edges:
        x,y = xy(a); u,v = xy(b)
        svg.append(f'<line x1="{x}" y1="{y}" x2="{u}" y2="{v}" stroke="#bcc5d0"/>')
    for n,attrs in view.nodes(data=True):
        x,y = xy(n)
        svg.append(f'<circle cx="{x}" cy="{y}" r="5" fill="hsl({attrs["community"]*137%360},65%,40%)"><title>{html.escape(n+": "+attrs["title"])}</title></circle>')
    svg.append('</svg>')
    rows = ''.join(f'<li>{html.escape(n)} — {html.escape(d["title"])} (community {d["community"]})</li>' for n,d in view.nodes(data=True))
    (out/'citations.html').write_text('<!doctype html><meta charset="utf-8"><title>litkit citation graph</title><h1>Citation graph</h1><p>Edges point from citing to cited in GraphML. Layout is undirected; hover for labels. Louvain is descriptive, not evidence quality.</p>'+f'<p>Showing {len(view)} of {len(graph)} nodes.</p>'+''.join(svg)+'<ul>'+rows+'</ul>',encoding='utf-8')
    paths = [str(out/'citations.graphml'),str(out/'citations.html')]
    if png:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,ax = plt.subplots(figsize=(12,10))
        nx.draw_networkx(view,pos,ax=ax,with_labels=False,node_size=30,node_color=[d['community'] for _,d in view.nodes(data=True)],arrows=True,width=.5)
        fig.savefig(out/'citations.png',dpi=160)
        plt.close(fig)
        paths.append(str(out/'citations.png'))
    return {'nodes':len(graph),'edges':graph.number_of_edges(),'communities':len({d['community'] for _,d in graph.nodes(data=True)}),'paths':paths}


def rank(con, project):
    graph = build(con,project)
    corpus = {n for n,d in graph.nodes(data=True) if d['status']=='corpus'}
    corpus_refs = {r for n in corpus for r in graph.successors(n)}
    results = []
    for n,d in graph.nodes(data=True):
        if n in corpus:
            continue
        quality = score_source(con,n,project)
        keywords = project.get('frontier.keywords')
        metadata = con.execute("SELECT payload_json FROM enrichments WHERE work_id=? AND source='openalex' AND outcome='ok' ORDER BY at DESC LIMIT 1",(n,)).fetchone()
        payload = db.loads(metadata[0],{}) if metadata else {}
        reference_ids = payload.get('referenced_works')
        known_refs = {db.resolve(con,r) for r in reference_ids} if isinstance(reference_ids,list) else None
        raw = {'cited_by_corpus':len(set(graph.predecessors(n)) & corpus),'cites_corpus':len(known_refs & corpus) if known_refs is not None else None,'coupling':len(known_refs & corpus_refs) if known_refs is not None else None,'relevance':sum(k.casefold() in d['title'].casefold() for k in keywords)/len(keywords) if keywords else None,'quality_prior':quality['score']}
        rules = {k:{'weight':w,'transform':'linear_cap' if k in project.get('frontier.caps') else 'identity01','cap':project.get('frontier.caps').get(k,1)} for k,w in project.get('frontier.weights').items()}
        item = composite(raw,rules)
        if quality['retracted']:
            item['score'] = 0.
        item.update(id=n,title=d['title'],community=d['community'],source_quality=quality,provisional=True)
        results.append(item)
    return sorted(results,key=lambda x:(-(x['score'] if x['score'] is not None else -1),x['id']))
