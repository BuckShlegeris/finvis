from bottle import route, run, debug, template, post, request, response, \
    view, redirect
from mongo import *
import bson
import mongoengine
import pymongo
import mongo
import excel
import finvis


@route('/entities')
@view('entity_list')
def entity_list():
    finvis.aaa.require(fail_redirect='/login')
    public_entities = Entity.objects(public=True).only("name")
    user_entities = Entity.objects(username=finvis.aaa.current_user.username,
                                   public=False).only("name")
    return {'public_entities': public_entities, 'user_entities': user_entities}


@route('/data_admin')
@view('data_admin')
def data_admin():
    finvis.aaa.require(role='admin', fail_redirect='/sorry_page')
    public_entities = Entity.objects(public=True).only('name', 'username')

    users = finvis.aaa.list_users()
    entities = {}
    for user in users:
        entities[user[0]] = Entity.objects(username=user[0])\
            .only('name', 'public')
    return {'public_entities': public_entities, 'users_entities': entities,
            'me': finvis.aaa.current_user.username}


@route('/entity.json/:entityid')
def entity_json(entityid):
    response.content_type = 'text/json'

    # WARNING: THIS ONLY WORKS BECAUSE IT IS IMPOSSIBLE TO UPDATE A FILE ATM
    # IF THAT CONDITION IS EVER WEAKEND, THIS WILL BREAK AND PEOPLE WILL BE SAD
    if request.get_header('If-None-Match') == "W/" + entityid:
        response.status = 304
        return

    # FIXME?: this doesn't verify that the user has the rights to view.
    # Should it? Not enforcing this will make embedding much easier...
    result = bson.json_util.dumps(Entity._get_collection().find_one(
        {"_id": bson.objectid.ObjectId(entityid)}))
    # obvious but slow:
    # result = bson.json_util.dumps(Entity.objects(id=entityid)[0].to_mongo())
    #return entityid
    if result == "null":
        response.status = 404
        result = '{"error":"Requested an entity that does not exist."}'

    response.add_header("ETag", "W/" + entityid)

    return result


@post('/excel_to_json.json')
def excel_to_json():
    """Return the uploaded excel file as a JSON document."""
    response.content_type = 'text/json'

    excelfile = request.files.get('excelfile')

    if excelfile is None:
        response.status = 422
        return {'error': 'No file detected. Please chose a file to upload.'}

    try:
        obj = excel.import_excel(excelfile.file.read(), 'anonymous')
    except excel.ExcelError as e:
        response.status = 422
        return {'error': str(e)}

    result = bson.json_util.dumps(obj.to_mongo())
    return result


@post('/upload')
def excel_upload():
    """Upload the file to the DB."""

    finvis.aaa.require(fail_redirect="/login")

    excelfile = request.files.get('excelfile')

    if excelfile is None:
        response.status = 422
        return 'Error: No file sent. Please submit a file.'

    try:
        obj = excel.import_excel(excelfile.file.read(),
                                 finvis.aaa.current_user.username)
    except excel.ExcelError as e:
        response.status = 422
        return 'Error: ' + e.message

    obj.save()

    target = request.headers.get('Referer', '/').strip()
    redirect(target)


@route('/download/:entity_id')
def excel_download(entity_id):
    """Download the file as Excel."""

    finvis.aaa.require(fail_redirect="/login")

    entity = Entity.objects(id=entity_id)[0]

    response.content_type = 'application/vnd.ms-excel'
    response.add_header('Content-Disposition',
                        'attachment; filename="' + entity.name + '.xls"')

    return excel.export_excel(entity)


@route('/delete/:entity_id')
def delete(entity_id):
    finvis.aaa.require(fail_redirect='/sorry_page')

    obj = Entity.objects(id=entity_id)[0]

    # you can only delete your own private documents, unless you're admin
    # public docs are protected
    if (obj.username == finvis.aaa.current_user.username and
        obj.public is False) or \
            finvis.aaa.current_user.role == 'admin':
        obj.delete()
    else:
        return 'Error: you may not delete that document.'

    target = request.headers.get('Referer', '/').strip()
    redirect(target)


@route('/set_public/:entity_id/:public')
def set_public(entity_id, public):
    finvis.aaa.require(role='admin', fail_redirect='/sorry_page')

    obj = Entity.objects(id=entity_id)[0]

    if public == '1':
        obj.public = True
    else:
        obj.public = False

    obj.save()

    target = request.headers.get('Referer', '/').strip()
    redirect(target)


### Saved state stuff
@post('/save_state')
def save_state():
    data = request.forms.get('state')
    state = SavedState.from_json(data)
    if finvis.aaa.user_is_anonymous:
        state.creator = "anonymous"
    else:
        state.creator = finvis.aaa.current_user.username

    state.save()
    result = {'url': 'http://openeconomy.org.au/s/' + str(state.id)}
    #print(result)
    response.content_type = 'text/json'
    return result


@route('/state.json/:state_id')
def state_json(state_id):
    response.content_type = 'text/json'
    if request.get_header('If-None-Match') == "W/" + state_id:
        response.status = 304
        return

    try:
        result = SavedState.objects(id=state_id).get()
    except DoesNotExist as e:
        response.status = 404
        return '{"error":"Requested a saved state that does not exist."}'

    result.visits = result.visits + 1
    result.save()

    response.add_header("ETag", "W/" + state_id)

    return bson.json_util.dumps(result.to_mongo())
