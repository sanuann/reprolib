from sanic import Sanic
from sanic import response
from sanic.log import logger
from pyld import jsonld
from sanic_jinja2 import SanicJinja2
from difflib import get_close_matches
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
activity_map = {}

async def replace_url(file_content, request):
    gh_url = "https://raw.githubusercontent.com/ReproNim/reproschema/master"
    hostname = await determine_env(request.headers['host'])
    for attribute, value in file_content.items():
        # if value is str, replace substring
        if isinstance(value, str) and gh_url in value:
            value = value.replace(gh_url, 'https://' + hostname)
            # print(107, attribute, '-', value)
            file_content[attribute] = value
        # if value is list, replace substring in list of strings
        if isinstance(value, list):
            new_list = []
            is_present = False
            for c in value:
                if gh_url in c:
                    is_present = True
                    c = c.replace(gh_url, 'https://' + hostname)
                    new_list.append(c)
            if is_present:
                file_content[attribute] = new_list
            else:
                file_content[attribute] = value

        # if value is dict, repeat process
        if isinstance(value, dict):
            file_content[attribute] = await replace_url(value, request)
    return file_content


async def determine_env(hostname):
    if '0.0.0.0' in hostname:
        return hostname
    else:
        return hostname + '/rl'


@app.route("/update")
def update(request):
    import subprocess as sp
    out = sp.run(['git', 'pull'], cwd='/opt/reproschema', capture_output=True)
    if out.returncode == 0:
        logger.info(out)
    else:
        logger.error(out)
    return response.json(out.__dict__, ensure_ascii=False, escape_forward_slashes=False)


@app.route("/")
async def test(request):
    hostname = await determine_env(request.headers['host'])
    api_list = {'activities': [], 'protocols': []}
    for activity in next(os.walk('/opt/reproschema/activities'))[1]:
        act_dict = {
            'name': activity,
            'html_path': 'https://' + hostname + '/activities/' +
                         activity,
            'jsonld_path': 'https://' + hostname + '/activities/' +
                        activity + '.jsonld',
            'ttl_path': 'https://' + hostname + '/activities/' +
                        activity + '.ttl',
            'ui': 'https://schema.repronim.org/ui/#/activities/0/?url='+'https://' + hostname + '/activities/' + activity
        }

        api_list['activities'].append(act_dict)

    # sort in place alphabetically
    api_list['activities'].sort(key=lambda i: i['name'].lower())

    for protocol in next(os.walk('/opt/reproschema/protocols'))[1]:
        protocol_dict = {
            'name': protocol,
            'html_path': 'https://' + hostname + '/protocols/' +
                         protocol,
            'jsonld_path': 'https://' + hostname + '/protocols/' +
                         protocol + '.jsonld',
            'ttl_path': 'https://' + hostname + '/protocols/' +
                         protocol + '.jsonld',
            'ui': 'https://schema.repronim.org/ui/#/?url='+'https://' + hostname + '/protocols/' + protocol
        }
        api_list['protocols'].append(protocol_dict)
    # sort in place alphabetically
    api_list['protocols'].sort(key=lambda i: i['name'].lower())
    return jinja.render("index.html", request, data=api_list)


@app.route('/contexts/generic')
async def get_generic_context(request):
    response_headers = {'Content-type': 'application/ld+json'}
    with open("/opt/reproschema/contexts/generic", "r") as f1:
        file_content = json.load(f1)
    new_file = await replace_url(file_content, request)
    return response.json(new_file, ensure_ascii=False,
                         escape_forward_slashes=False, headers=response_headers)


@app.route('/protocols/<proto_folder>/<proto_context>')
async def get_protocol_context(request, proto_folder, proto_context):
    response_headers = {'Content-type': 'application/ld+json'}
    with open("/opt/reproschema/protocols/" + proto_folder + '/' +
              proto_context, "r") as f1:
        file_content = json.load(f1)
    new_file = await replace_url(file_content, request)
    return response.json(new_file, ensure_ascii=False,
                         escape_forward_slashes=False, headers=response_headers)


@app.route('/activities/<act_folder>/<act_context>')
async def get_activity_context(request, act_folder, act_context):
    response_headers = {'Content-type': 'application/ld+json'}
    with open("/opt/reproschema/activities/" + act_folder
              + '/' + act_context, "r") as f2:
        file_content = json.load(f2)
    new_file = await replace_url(file_content, request)
    return response.json(new_file, ensure_ascii=False,
                         escape_forward_slashes=False, headers=response_headers)


@app.route('/activities/<act_name>/items/<item_id>')
async def get_item(request, act_name, item_id):
    view_options = 1  # default view is html
    response_headers = {'Content-type': 'application/ld+json'}
    filename, file_extension = os.path.splitext(item_id)
    if request.headers.get('accept') == 'application/json' or \
            request.headers.get('accept') == 'application/ld+json':
        view_options = 2
    else:
        if not file_extension:
            view_options = 1  # html view
        elif file_extension == '.jsonld':
            view_options = 2
    try:
        with open("/opt/reproschema/activities/" + act_name
                  + '/items/' + filename, "r") as f2:
            file_content = json.load(f2)
            print(178, file_content)
            new_file = await replace_url(file_content, request)
    except:
        print('error getting contents')
        return response.text('Could not fetch data. Check item name')

    if view_options == 1:
        # render html
        return jinja.render("field.html", request, data=new_file)

    elif view_options == 2:
        return response.json(new_file, ensure_ascii=False,
                             escape_forward_slashes=False, headers=response_headers)


@app.route('/activities/<act_name>')
async def get_activity(request, act_name):
    hostname = await determine_env(request.headers['host'])
    filename, file_extension = os.path.splitext(act_name)

    for activity in next(os.walk('./opt/reproschema/activities'))[1]:
        # print(136, activity, next(os.walk('./opt/reproschema/activities/' + activity)))
        act_walks = next(os.walk('./opt/reproschema/activities/' + activity))

        for file in act_walks[2]: # loop over all files in the activity directory
            if file.endswith('_schema'):
                # print(150, file, os.path.join(act_walks[0], file))
                with open(os.path.join(act_walks[0], file), "r") as fa:
                    try:
                        act_schema = json.load(fa)
                        # print(155, act_schema['@id'])
                        activity_map[act_schema['@id']] = os.path.join(act_walks[0], file)
                    except Exception as e:
                        logger.error('error in json', file, e)
    matched_id = get_close_matches(filename, list(activity_map.keys()), 3, 0.2)[0]
    # print(269, activity_map[matched_id]) # returns path of matched file id

    with open(activity_map[matched_id], "r") as f5:
        try:
            file_content = json.load(f5)
            new_file = await replace_url(file_content, request)
        except ValueError:
            print('error!!')


    view_options = 1 # default view is html
    response_headers = {'Content-type': 'application/ld+json'}
    # if '_schema' in filename:
    #     activity_dir = filename.split('_schema')[0]
    #     activity_name = filename
    # else:
    #     activity_dir = filename
    #     activity_name = re.sub('[^A-Za-z0-9]+', '', filename)+'_schema' #remove special characters

    if request.headers.get('accept') == 'application/json' or \
            request.headers.get('accept') == 'application/ld+json':
        view_options = 2
    else:
        if not file_extension:
            view_options = 1 # html view
        elif file_extension == '.jsonld':
            view_options = 2
        elif file_extension == '.ttl':
            view_options = 3
    # act_name_lower = re.sub(r'\W+', '', filename).lower()
    # try:
    #     for root, dirs, files in os.walk(
    #             './opt/reproschema/activities/' + activity_dir):
    #         for file in files:
    #             if file == activity_name:
    #                 with open(os.path.join(root, file), "r") as fa:
    #                     try:
    #                         file_content = json.load(fa)
    #                         new_file = await replace_url(file_content, request)
    #                     except ValueError:
    #                         print('error!!')
    # except ValueError:
    #     return response.text('Error! check activity name')

    if view_options == 1:
        # html
        print('html view')
        try:
            item_q = []
            for field in new_file['ui']['order']:
                with open("/opt/reproschema/activities/" + act_name
                          + '/items/' + field, "r") as f2:
                    field_content = json.load(f2)
                item_q.append(field_content['question'])
            new_file['ui']['order'] = item_q
            return jinja.render("activity.html", request, data=new_file)
        except Exception as e:
            print('error in contents to render html', e)
            logger.error(e)
            return response.json(new_file, ensure_ascii=False,
                                 escape_forward_slashes=False,
                                 headers=response_headers)

    elif view_options == 2:
        print('in json ')
        # jsonld
        return response.json(new_file, ensure_ascii=False,
                             escape_forward_slashes=False, headers=response_headers)

    elif view_options == 3:
        try:
            #print('in turtle ', new_file)
            # turtle
            normalized_file = jsonld.normalize(
                new_file, {'base': 'https://' + hostname + '/activities/' + filename + '/', 'algorithm': 'URDNA2015', 'format':
                    'application/n-quads'})
            return response.text(normalized_file, headers=response_headers)
        except Exception as e:
            print(e)
            raise


@app.route('/protocols/<proto_name>')
async def get_protocol(request, proto_name):
    view_options = 1  # default view is html
    response_headers = {'Content-type': 'application/ld+json'}
    filename, file_extension = os.path.splitext(proto_name)
    if request.headers.get('accept') == 'application/json' or \
            request.headers.get('accept') == 'application/ld+json':
        view_options = 2
    else:
        if not file_extension:
            view_options = 1  # html view
        elif file_extension == '.jsonld':
            view_options = 2
    try:
        for root, dirs, files in os.walk(
                '/opt/reproschema/protocols/'+ filename):
            for file in files:
                if file.endswith('_schema'):
                    # print(72, root, file)
                    with open(os.path.join(root, file), "r") as fa:
                        try:
                            file_content = json.load(fa)
                            new_file = await replace_url(file_content, request)
                            # print(122, new_file)
                        except ValueError:
                            print('error!!')
    except ValueError:
        return response.text('Error! check protocol name')

    if view_options == 1:
        # html. for time being it renders jsonld
        try:
            # TODO
            return jinja.render("field.html", request, data=new_file)
        except Exception as e:
            logger.error(e)
            # if it raises an Exception then deliver the jsonld
            return response.json(new_file, ensure_ascii=False,
                                 escape_forward_slashes=False,
                                 headers=response_headers)

    elif view_options == 2:
        # jsonld
        return response.json(new_file, ensure_ascii=False,
                             escape_forward_slashes=False, headers=response_headers)


@app.route('/terms/<term_name>')
async def get_terms(request, term_name):
    view_options = 1  # default view is html
    response_headers = {'Content-type': 'application/ld+json'}
    filename, file_extension = os.path.splitext(term_name)
    if request.headers.get('accept') == 'application/json' or \
            request.headers.get('accept') == 'application/ld+json':
        view_options = 2
    else:
        if not file_extension:
            view_options = 1  # html view
        elif file_extension == '.jsonld':
            view_options = 2
    with open("/opt/reproschema/terms/" + filename, "r") as f1:
        file_content = json.load(f1)
    new_file = await replace_url(file_content, request)
    if view_options == 1:
        # html. for time being it renders jsonld
        try:
            # TODO
            return jinja.render("field.html", request, data=new_file)
        except Exception as e:
            logger.error(e)
            # if it raises an Exception then deliver the jsonld
            return response.json(new_file, ensure_ascii=False,
                                 escape_forward_slashes=False,
                                 headers=response_headers)

    elif view_options == 2:
        # jsonld
        return response.json(new_file, ensure_ascii=False,
                             escape_forward_slashes=False, headers=response_headers)


@app.route('/resources/<r_name>')
async def get_resources(request, r_name):
    response_headers = {'Content-type': 'application/ld+json'}
    with open("/opt/reproschema/resources/" + r_name, "r") as f1:
        file_content = json.load(f1)
        return response.json(file_content, ensure_ascii=False,
                         escape_forward_slashes=False, headers=response_headers)

if __name__ == "__main__":
    logger.info("Starting reprolib-server")
    app.run(host="0.0.0.0", port=8000)

