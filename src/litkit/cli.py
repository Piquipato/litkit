"""Click entry point. All machine output is JSON; no LLM synthesis is performed."""
import base64
import json
from pathlib import Path
import click
from . import db
from .config import init_project, load_project


def emit(value):
    click.echo(json.dumps(value,ensure_ascii=False,indent=2))


class SafeGroup(click.Group):
    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except (ValueError, OSError) as exc:
            # Raw HTTP/credential-bearing exceptions are never rendered here.
            from .config import load_secrets
            text = str(exc)
            for secret in load_secrets().values():
                if secret:
                    text = text.replace(secret,'[REDACTED]')
            raise click.ClickException(text) from None


@click.group(cls=SafeGroup)
@click.option('--project',type=click.Path(path_type=Path),help='Literature project directory.')
@click.option('--offline',is_flag=True,help='Only read cached HTTP responses; never access network.')
@click.option('--max-calls',type=click.IntRange(min=0),default=100,show_default=True,help='Global HTTP attempt budget for this invocation, including retries.')
@click.pass_context
def main(ctx, project, offline, max_calls):
    ctx.ensure_object(dict)
    ctx.obj.update(root=project,offline=offline,max_calls=max_calls)


def project(ctx):
    return load_project(ctx.obj['root'])


@main.command('init')
@click.argument('directory',type=click.Path(path_type=Path))
@click.option('--name')
def initialize(directory,name):
    p = init_project(directory,name)
    with db.database(p.db_path) as con:
        emit({'project':str(p.root),'database':str(p.db_path),'counts':db.counts(con)})


@main.command()
@click.pass_context
def status(ctx):
    p = project(ctx)
    with db.database(p.db_path) as con:
        emit({'project':str(p.root),'counts':db.counts(con),'implemented_providers':['openalex'],'llm_enabled':False})


@main.command('import-legacy')
@click.argument('directory',type=click.Path(exists=True,file_okay=False,path_type=Path))
@click.pass_context
def legacy(ctx,directory):
    from .legacy import import_legacy
    p = project(ctx)
    with db.database(p.db_path) as con:
        summary = import_legacy(con,directory)
    emit(summary)


@main.command('export')
@click.option('--output',type=click.Path(path_type=Path))
@click.pass_context
def export_data(ctx,output):
    p = project(ctx)
    output = output or p.path('export_dir')
    output.mkdir(parents=True,exist_ok=True)
    data = {'schema_version':db.SCHEMA_VERSION,'tables':{}}
    with db.database(p.db_path) as con:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for table in tables:
            rows = []
            for row in con.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
                item = dict(row)
                for key,value in list(item.items()):
                    if isinstance(value,bytes):
                        item[key] = {'encoding':'base64','data':base64.b64encode(value).decode('ascii')}
                    elif key.endswith('_json') and value is not None:
                        item[key] = json.loads(value)
                rows.append(item)
            data['tables'][table] = rows
            (output/(table+'.jsonl')).write_text(''.join(db.dumps(r)+'\n' for r in rows),encoding='utf-8')
    (output/'project.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    emit({'output':str(output),'counts':{k:len(v) for k,v in data['tables'].items()}})


@main.command()
@click.argument('ids',nargs=-1)
@click.option('--limit',type=click.IntRange(min=1))
@click.pass_context
def enrich(ctx,ids,limit):
    from .openalex import Client,enrich as run
    p = project(ctx)
    client = Client(p,offline=ctx.obj['offline'],max_calls=ctx.obj['max_calls'])
    try:
        with db.database(p.db_path) as con:
            summary = run(con,client,db.select_works(con,ids,limit=limit))
    finally:
        client.close()
    emit(summary)
    if summary['errors']:
        ctx.exit(1)


@main.command()
@click.argument('ids',nargs=-1)
@click.option('--direction',type=click.Choice(['both','references','citations']),default='both')
@click.option('--max-new',type=click.IntRange(min=0))
@click.option('--max-citing',type=click.IntRange(min=0))
@click.pass_context
def snowball(ctx,ids,direction,max_new,max_citing):
    from .openalex import Client,snowball as run
    p = project(ctx)
    client = Client(p,offline=ctx.obj['offline'],max_calls=ctx.obj['max_calls'])
    try:
        with db.database(p.db_path) as con:
            summary = run(con,client,db.select_works(con,ids),max_new if max_new is not None else p.get('snowball.max_new_works_per_run'),max_citing if max_citing is not None else p.get('snowball.max_citing_per_work'),direction)
    finally:
        client.close()
    emit(summary)
    if summary['errors']:
        ctx.exit(1)


@main.command()
@click.option('--png',is_flag=True,help='Also render PNG (requires plot extra).')
@click.pass_context
def graph(ctx,png):
    from .graph import export_graph
    p = project(ctx)
    if png:
        try:
            import matplotlib
        except ImportError:
            raise click.ClickException('PNG needs the optional plot dependency: pip install litkit[plot]') from None
    with db.database(p.db_path) as con:
        emit(export_graph(con,p,png))


@main.command()
@click.option('--limit',type=click.IntRange(min=1),default=50)
@click.pass_context
def rank(ctx,limit):
    from .graph import rank as run
    p = project(ctx)
    with db.database(p.db_path) as con:
        result = run(con,p)
    p.path('export_dir').mkdir(parents=True,exist_ok=True)
    (p.path('export_dir')/'rank.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    emit({'total':len(result),'results':result[:limit]})


@main.command()
@click.option('--entity',type=click.Choice(['source','quote','all']),default='all')
@click.pass_context
def quality(ctx,entity):
    from .quality import score_source,score_quote,save_score
    p = project(ctx)
    result = {}
    with db.database(p.db_path) as con:
        for kind,table,fn in [('source','works',score_source),('quote','quotes',score_quote)]:
            if entity not in ('all',kind):
                continue
            records = []
            for row in con.execute(f'SELECT id FROM {table} ORDER BY id').fetchall():
                scored = fn(con,row[0],p)
                save_score(con,kind,row[0],scored,p)
                records.append({'id':row[0],**scored})
            result[kind] = records
    p.path('export_dir').mkdir(parents=True,exist_ok=True)
    path = p.path('export_dir')/'quality.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    emit({'output':str(path),'counts':{k:len(v) for k,v in result.items()}})
