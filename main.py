from sanic import Sanic
from sanic import response
from github import Github
from pyld import jsonld
from pyld.jsonld import JsonLdProcessor
# from rdflib.plugin import register, Parser
# from rdflib import Graph, ConjunctiveGraph
from sanic_jinja2 import SanicJinja2
import requests
import json
import re
import os, sys

LOG_SETTINGS = dict(
    version=1,
    disable_existing_loggers=False,
    loggers={
        "sanic.root": {"level": "INFO", "handlers": ["console", "consolefile"]},
        "sanic.error": {
            "level": "INFO",
            "handlers": ["error_console", "error_consolefile"],
            "propagate": True,
            "qualname": "sanic.error",
        },
        "sanic.access": {
            "level": "INFO",
            "handlers": ["access_console", "access_consolefile"],
            "propagate": True,
            "qualname": "sanic.access",
        },
    },
    handlers={
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "generic",
            "stream": sys.stdout,
        },
        "error_console": {
            "class": "logging.StreamHandler",
            "formatter": "generic",
            "stream": sys.stderr,
        },
        "access_console": {
            "class": "logging.StreamHandler",
            "formatter": "access",
            "stream": sys.stdout,
        },
        "consolefile": {
            'class': 'logging.FileHandler',
            'filename': "/vagrant/reprolib/console.log",
            "formatter": "generic",
        },
        "error_consolefile": {
            'class': 'logging.FileHandler',
            'filename': "/vagrant/reprolib/error.log",
            "formatter": "generic",
        },
        "access_consolefile": {
            'class': 'logging.FileHandler',
            'filename': "/vagrant/reprolib/access.log",
            "formatter": "access",
        },
    },
    formatters={
        "generic": {
            "format": "%(asctime)s [%(process)d] [%(levelname)s] %(message)s",
            "datefmt": "[%Y-%m-%d %H:%M:%S %z]",
            "class": "logging.Formatter",
        },
        "access": {
            "format": "%(asctime)s - (%(name)s)[%(levelname)s][%(host)s]: "
                      + "%(request)s %(message)s %(status)d %(byte)d",
            "datefmt": "[%Y-%m-%d %H:%M:%S %z]",
            "class": "logging.Formatter",
        },
    },
)

app = Sanic(log_config=LOG_SETTINGS)
jinja = SanicJinja2(app)
item_resp = {}
# register('json-ld', Parser, 'rdflib_jsonld.parser', 'JsonLDParser')
f1 = open("/vagrant/reprolib/user_credentials.txt", "r")
GITHUB_TOKEN = f1.read()
f1.close()


@app.route("/")
async def test(request):
    hostname = request.headers['host']
    act_names = {'activities': [], 'protocols': []}
    git = Github(GITHUB_TOKEN)
    org = git.get_organization('ReproNim')
    repo = org.get_repo('schema-standardization')
    # repo_contents = repo.get_contents('')
    repo_activities = repo.get_contents('activities')
    for activity in repo_activities:
        act_names['activities'].append(hostname+'/'+activity.name)
    repo_protocols = repo.get_contents('activity-sets')
    for protocol in repo_protocols:
        act_names['protocols'].append(hostname + '/' + protocol.name)
    return jinja.render("home.html", request, data=act_names)


@app.route('/contexts/generic')
async def get_generic_context(request):
    git = Github(GITHUB_TOKEN)
    org = git.get_organization('ReproNim')
    repo = org.get_repo('schema-standardization')
    gen_context = repo.get_contents('contexts/generic')
    context_content = requests.get(gen_context.download_url)
    return response.json(context_content.json())


@app.route('/activities/<act_folder>/<act_context>')
async def get_activity_context(request, act_folder, act_context):
    git = Github(GITHUB_TOKEN)
    org = git.get_organization('ReproNim')
    repo = org.get_repo('schema-standardization')
    gen_context = repo.get_contents('activities/'+act_folder+'/'+act_context)
    act_context_content = requests.get(gen_context.download_url)
    return response.json(act_context_content.json())


@app.route('/activity/<act_name>/item/<item_id>')
async def get_item(request, act_name, item_id):
    hostname = request.headers['host']
    git = Github(GITHUB_TOKEN)
    org = git.get_organization('ReproNim')
    repo = org.get_repo('schema-standardization')
    filename, file_extension = os.path.splitext(item_id)
    if not file_extension: # render html
        item_content = repo.get_contents('activities/' + act_name + '/items/' + item_id)
        i = requests.get(item_content.download_url)
        item_json = i.json()
        print(89, item_json['responseOptions'])
        # if isinstance(item_json['responseOptions'], str):
        #     item_json['responseOptions'] = \
        #         (requests.get(item_json['responseOptions'])).json()
        return jinja.render("field.html", request, data=item_json)
    elif file_extension == '.jsonld':
        item_content = repo.get_contents(
            'activities/' + act_name + '/items/' + filename)
        i = requests.get(item_content.download_url)
        item_jsonld = i.json()
        context = item_jsonld['@context']
        item_jsonld['@context'] = []
        if isinstance(context, dict) is False:
            for c in context:
                c = c.replace('https://raw.githubusercontent.com/ReproNim/schema'
                              '-standardization/master',
                              request.scheme + '://' + hostname)
                print(c)
                item_jsonld['@context'].append(c)
        return response.json(item_jsonld)


@app.route('/activity/<act_name>')
async def get_activity(request, act_name):
    hostname = request.headers['host']
    git = Github(GITHUB_TOKEN)
    org = git.get_organization('ReproNim')
    repo = org.get_repo('schema-standardization')
    filename, file_extension = os.path.splitext(act_name)
    act_name_lower = re.sub(r'\W+', '', filename).lower()
    if not file_extension:
        print('html')
        # html
        try:
            act_contents = repo.get_contents('activities/' + act_name)
            for item in act_contents:
                if item.download_url is not None:
                    i = requests.get(item.download_url)
                    try:
                        item_resp[item.name] = i.json()
                    except json.decoder.JSONDecodeError:
                        print("Didn't pass JSON", item.download_url, i)
            expanded = jsonld.expand(item_resp[act_name_lower + '_schema'])
            item_q = []
            for field in expanded[0]['https://schema.repronim.org/order'][0][
                '@list']:
                fc = requests.get(field['@id'])
                field_json = fc.json()
                item_q.append(field_json['question'])
            activity = {
                'prefLabel': expanded[0][
                    'http://www.w3.org/2004/02/skos/core#prefLabel'][0]['@value'],
                'preamble': expanded[0]['http://schema.repronim.org/preamble'][0][
                    '@value'],
                'order': item_q,
            }
            return jinja.render("activity.html", request, data=activity)
            # return response.json(act_contents)
        except:
            print('error getting contents')
            return response.text('Could not fetch data. Check activity name')

    elif file_extension == '.jsonld':
        # jsonld
        try:
            act_contents = repo.get_contents('activities/' + filename)
            for item in act_contents:
                if item.download_url is not None:
                    i = requests.get(item.download_url)
                    try:
                        item_resp[item.name] = i.json()
                    except json.decoder.JSONDecodeError:
                        print("Didn't pass JSON", item.download_url, i)
            context = item_resp[act_name_lower + '_schema']['@context']
            item_resp[act_name_lower + '_schema']['@context'] = []
            if isinstance(context, dict) is False:
                for c in context:
                    c = c.replace(
                        'https://raw.githubusercontent.com/ReproNim/schema'
                        '-standardization/master',
                        request.scheme + '://' + hostname)
                    item_resp[act_name_lower + '_schema']['@context'].append(c)
            return response.json(item_resp[act_name_lower + '_schema'])
        except:
            print('Could not fetch activity file')
            return response.text('Could not fetch data. Check activity name')


@app.route('/activity/<act_name>/item/<item_id>.ttl')
async def get_item_ttl(request, act_name, item_id):
    git = Github(GITHUB_TOKEN)
    org = git.get_organization('ReproNim')
    repo = org.get_repo('schema-standardization')
    item_contents = repo.get_contents('activities/' + act_name + '/items')
    for item in item_contents:
        i = requests.get(item.download_url)
        try:
            item_resp[item.name] = i.json()
        except json.decoder.JSONDecodeError:
            print("Didn't pass JSON", item.download_url, i)

    total_context = {}  # to store the expanded context
    context = item_resp[item_id]['@context']
    if isinstance(context, dict) is False:
        for c in context:
            context_content = requests.get(c)
            rc = context_content.json()
            total_context.update(rc['@context'])

    compacted = jsonld.compact(item_resp[item_id], total_context)
    # ttl_result = jsonld.to_rdf(compacted, {format: 'application/rdf+xml'})

    # g = Graph().parse("https://schema.org/Person.jsonld", format="json-ld")
    print ('`````````')
    print(g)
    ttl_result = g.serialize(indent=4)
    return response.text(ttl_result)


@app.route('/protocol/<proto_name>.jsonld')
async def get_protocol_jsonld(request, proto_name):
    git = Github(GITHUB_TOKEN)
    org = git.get_organization('ReproNim')
    repo = org.get_repo('schema-standardization')
    protocol_contents = repo.get_contents('activity-sets/' + proto_name)
    for item in protocol_contents:
        i = requests.get(item.download_url)
        try:
            item_resp[item.name] = i.json()
        except json.decoder.JSONDecodeError:
            print("Didn't pass JSON", item.download_url, i)

    total_context = {}  # to store the expanded context
    context = item_resp['voice_pilot_context']['@context']
    # active_context = JsonLdProcessor.process_context(act_ctx, context)
    print('GET CONTEXT -----', context)
    if isinstance(context, dict) is False:
        # if a list, iterate and get the remote contexts
        for c in context:
            context_content = requests.get(c)
            rc = context_content.json()
            total_context.update(rc['@context'])

    compacted = jsonld.compact(item_resp['voice_pilot_context'], total_context,
                               {'base': "https://raw.githubusercontent.com/ReproNim/schema-standardization/master/activities/"})
    print('-------COMPACTED----')
    print(compacted)
    return response.json(compacted)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
