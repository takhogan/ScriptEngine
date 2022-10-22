ALLOWED_IPS = set([
    '10.0.0.98',
    '10.0.0.117',
    '10.0.0.8'
])


@app.route('/run', methods=['GET'])
def list_run_scripts():
    if request.remote_addr not in ALLOWED_IPS:
        print('blocked ip : ', request.remote_addr)
        resp = jsonify({'message': 'Configure server to allow requests'})
        resp.status_code = 400
        return resp
    return (subprocess.check_output(['ls']), 201)

@app.route('/run/<scriptname>')
def run_script(scriptname):
    if request.remote_addr not in ALLOWED_IPS:
        print('blocked ip : ', request.remote_addr)
        resp = jsonify({'message': 'Configure server to allow requests'})
        resp.status_code = 400
        return resp
    return (scriptname, 201)
