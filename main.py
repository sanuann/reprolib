from sanic import Sanic
from sanic import response
from sanic.log import logger
from pyld import jsonld
from sanic_jinja2 import SanicJinja2
import requests
import json
import re
import os, sys
from sanic_cors import CORS

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
CORS(app)

jinja = SanicJinja2(app)
item_resp = {}


# '{uri.scheme}://{uri.netloc}/'.format(uri=parsed_uri)

async def determine_env(hostname):
    if '0.0.0.0' in hostname:
        print(86, 'local', hostname)
        return hostname
    else:
        return hostname + '/rl'


@app.route("/")
async def test(request):
    hostname = await determine_env(request.headers['host'])
    api_list = {'activities': [], 'protocols': []}
    for activity in next(os.walk('/opt/schema-standardization/activities'))[1]:
        api_list['activities'].append(request.scheme + '://' + hostname +
                                      '/activity/' + activity)
    for protocol in next(os.walk('/opt/schema-standardization/activity-sets'))[1]:
        api_list['protocols'].append(request.scheme + '://' + hostname +
                                     '/protocol/' + protocol)
    return jinja.render("home.html", request, data=api_list)


@app.route('/contexts/generic')
async def get_generic_context(request):
    with open("/opt/schema-standardization/contexts/generic", "r") as f1:
        context_content = json.load(f1)
    return response.json(context_content)


@app.route('/activities/<act_folder>/<act_context>')
async def get_activity_context(request, act_folder, act_context):
    with open("/opt/schema-standardization/activities/" + act_folder
              + '/' + act_context, "r") as f2:
        act_context_content = json.load(f2)
    return response.json(act_context_content)


@app.route('/activity/<act_name>/item/<item_id>')
async def get_item(request, act_name, item_id):
    filename, file_extension = os.path.splitext(item_id)
    if not file_extension:
        # render html
        try:
            with open("/opt/schema-standardization/activities/" + act_name
                      + '/items/' + filename, "r") as f2:
                item_json = json.load(f2)
            expanded = jsonld.expand(item_json)
            if isinstance(item_json['responseOptions'], str):
                item_json['responseOptions'] = (requests.get(expanded[0]
                ["https://schema.repronim.org/valueconstraints"][0]['@id'])).json()
            item = {
                'prefLabel': expanded[0][
                    'http://www.w3.org/2004/02/skos/core#prefLabel'][0][
                    '@value'], # considering default as english fro now
                'question': expanded[0]['http://schema.org/question'][0]['@value'],
                'responseOptions': item_json['responseOptions']
            }
            return jinja.render("field.html", request, data=item)
        except:
            print('error getting contents')
            return response.text('Could not fetch data. Check item name')

    elif file_extension == '.jsonld':
        with open("/opt/schema-standardization/activities/" + act_name
                  + '/items/' + filename, "r") as f2:
            item_json = json.load(f2)
        context = item_json['@context']
        item_json['@context'] = []
        if isinstance(context, dict) is False:
            for c in context:
                c = c.replace('https://raw.githubusercontent.com/ReproNim/schema-'
                        'standardization/master', 'https://sig.mit.edu/rl')
                item_json['@context'].append(c)
        return response.json(item_json)


@app.route('/activity/<act_name>')
async def get_activity(request, act_name):
    filename, file_extension = os.path.splitext(act_name)
    act_name_lower = re.sub(r'\W+', '', filename).lower()
    if not file_extension:
        # html
        try:
            with open("/opt/schema-standardization/activities/" + act_name
                      + '/' + act_name_lower + '_schema', "r") as f2:
                act_schema_content = json.load(f2)
            expanded = jsonld.expand(act_schema_content)
            item_q = []
            for field in expanded[0]['https://schema.repronim.org/order'][0][
                '@list']:
                fc = requests.get(field['@id']) # fetch from local repo??
                field_json = fc.json()
                item_q.append(field_json['question'])
            # print(180,item_q)
            activity = {
                'prefLabel': expanded[0][
                    'http://www.w3.org/2004/02/skos/core#prefLabel'][0]['@value'],
                'preamble': expanded[0]['https://schema.repronim.org/preamble'][0][
                    '@value'],
                'order': item_q,
            }
            return jinja.render("activity.html", request, data=activity)
        except:
            print('error getting contents')
            return response.text('Could not fetch data. Check activity name1')

    elif file_extension == '.jsonld':
        # jsonld
        try:
            with open("/opt/schema-standardization/activities/" + filename
                      + '/' + act_name_lower + '_schema', "r") as fa:
                act_schema_contents = json.load(fa)
            context = act_schema_contents['@context']
            act_schema_contents['@context'] = []
            if isinstance(context, dict) is False:
                for c in context:
                    c = c.replace(
                        'https://raw.githubusercontent.com/ReproNim/schema'
                        '-standardization/master',
                        'https://sig.mit.edu/rl')
                    act_schema_contents['@context'].append(c)
            return response.json(act_schema_contents)
        except:
            print('Could not fetch activity file')
            return response.text('Could not fetch data. Check activity name')


@app.route('/protocol/<proto_name>')
async def get_protocol(request, proto_name):
    filename, file_extension = os.path.splitext(proto_name)
    if not file_extension:
        print('html')
        # html. for time being it renders jsonld
        try:
            with open("/opt/schema-standardization/activity-sets/" + filename
                      + '/' + filename + '_schema', "r") as f1:
                proto_schema_contents = json.load(f1)

            context = proto_schema_contents['@context']
            proto_schema_contents['@context'] = []
            if isinstance(context, dict) is False:
                for c in context:
                    c = c.replace(
                        'https://raw.githubusercontent.com/ReproNim/schema'
                        '-standardization/master',
                        'https://sig.mit.edu/rl')
                    proto_schema_contents['@context'].append(c)
            return response.json(proto_schema_contents)
        except:
            print('error getting contents')
            return response.text('Could not fetch data. Check protocol name')

    elif file_extension == '.jsonld':
        # jsonld
        try:
            with open("/opt/schema-standardization/activity-sets/" + filename
                      + '/' + filename + '_schema', "r") as f1:
                proto_schema_contents = json.load(f1)

            context = proto_schema_contents['@context']
            proto_schema_contents['@context'] = []
            if isinstance(context, dict) is False:
                for c in context:
                    c = c.replace(
                        'https://raw.githubusercontent.com/ReproNim/schema'
                        '-standardization/master',
                        'https://sig.mit.edu/rl')
                    proto_schema_contents['@context'].append(c)
            return response.json(proto_schema_contents)
        except:
            print('error getting contents')
            return response.text('Could not fetch data. Check protocol name')


if __name__ == "__main__":
    logger.info("Starting reprolib-server")
    app.run(host="0.0.0.0", port=8000)

