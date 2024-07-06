from flask import Flask, Response, request
import requests
import zipfile
import json
import io
import re

app = Flask(__name__)

@app.route('/')
def index():
    # URL of the JSON file within a zip archive
    URL = "https://res.snakesvc.com/assets/res.json"
    assetsUrl = 'https://res.snakesvc.com/assets'
    # Fetch the zip file from the URL
    response = requests.get(URL)
    
    login = []

    # Open the zip file from the response content
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        # Read the JSON file within the zip archive
        with zip_file.open('res.json') as json_file:
            content = json_file.read()
            res = json.loads(content.decode("utf-8"))
            print('downloaded')
            for i in res['files']:
                if i.startswith('login'):
                    if i.endswith('.png'):
                        md5 = res['files'][i]['md5']
                        size = res['files'][i]['size']
                        path_Dot = i.split('.')
                        imageName = path_Dot[0] + '.' + md5 + '.' + path_Dot[1]
                        filePath = assetsUrl + '/' + imageName
                        login.append((filePath, size))
                        print(filePath, size)
    
    login_sorted = sorted(login, key=lambda x: x[1], reverse=True)
    print(login_sorted[0])
    
    # Extract version information
    version = res['version']
    version_data = (
        f"branch: {version['branch']}<br>"
        f"short_id: {version['short_id']}<br>"
        f"datetime: {version['datetime']}<br>"
        f"msg: {version['msg']}<br>"
    )

    # Construct HTML to display version information and login image
    html_output = f'<h1 style="font-size: 24px;">Cdn Version(UnPublish Version)</h1>'
    html_output += f'{version_data}Login Image:<br>'
    html_output += f'<img src="{login_sorted[0][0]}" alt="Login Image" style="max-width: 500px;">'
    html_output += '''
        <form action="/getmainScenePicture" method="post">
            <button type="submit" style="width: 300px; height: 50px; font-size: 20px; padding: 10px 20px;">Get Main Scene Pictures</button>
        </form>
        <form action="/currentMobileVersion" method="post">
            <button type="submit" style="width: 300px; height: 50px; font-size: 20px; padding: 10px 20px;">Get Current Version</button>
        </form>
        <form action="/query" method="post">
            <input type="text" name="short_id" placeholder="Enter short_id" required>
            <button type="submit" style="width: 100px; height: 30px; font-size: 16px; padding: 5px 10px;">Query</button>
        </form>
    '''
    return html_output

@app.route('/currentMobileVersion', methods=['POST'])
def currentMobileVersion():
    data = bytes([
    0x46, 0x46, 0x46, 0x46, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 
    0x77, 0x18, 0x8B, 0xEC, 0x00, 0x05, 0x00, 0x00, 0x00, 0x17, 0x31, 0x2E, 
    0x32, 0x01, 0x1A, 0x05, 0x31, 0x2E, 0x2E, 0x31, 0x2E, 0x33, 0x10, 0x11, 
    0x0A, 0x06, 0x76, 0x31, 0x0A, 0x02, 0x10, 0x00, 0x12
])
    # Send the POST request
    res = requests.post(url='https://game.snakesvc.com/api/front/v1/version/GetReview', data=data)
    r = res.text

    r = r[30:]
    r = r[-13::-1]

    filter = re.findall(r'[a-z0-9]{8}',r)
    short_id = filter[1]


    assetsUrl = 'https://res.snakesvc.com/assets'
    fileName = f'res.{short_id}.json'
    URL = f'https://res.snakesvc.com/res-version/{fileName}'
    response = requests.get(URL)

    login = []
    
    # Open the zip file from the response content
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file: 
        # Read the JSON file within the zip archive
        with zip_file.open(fileName) as json_file:
            content = json_file.read()
            res = json.loads(content.decode("utf-8"))
            for i in res['files']:
                if i.startswith('login'):
                    if i.endswith('.png'):
                        md5 = res['files'][i]['md5']
                        size = res['files'][i]['size']
                        path_Dot = i.split('.')
                        imageName = path_Dot[0] + '.' + md5 + '.' + path_Dot[1]
                        filePath = assetsUrl + '/' + imageName
                        login.append((filePath, size))
                        print(filePath, size)
    
    login_sorted = sorted(login, key=lambda x: x[1], reverse=True)
    print(login_sorted[0])
    
    # Extract version information
    version = res['version']
    version_data = (
        f"branch: {version['branch']}<br>"
        f"short_id: {version['short_id']}<br>"
        f"datetime: {version['datetime']}<br>"
        f"msg: {version['msg']}<br>"
    )

    # Construct HTML to display version information and login image
    html_output = f'<h1 style="font-size: 24px;">Current Mobile Version</h1>'
    html_output += f'{version_data}Login Image:<br>'
    html_output += f'<img src="{login_sorted[0][0]}" alt="Login Image" style="max-width: 500px;">'
    html_output += '''
        <form action="/getmainScenePicture" method="post">
            <input type="hidden" name="short_id" value="''' + short_id + '''">
            <button type="submit" style="width: 300px; height: 50px; font-size: 20px; padding: 10px 20px;">Get Main Scene Pictures</button>
        </form>
        <form action="/" method="get">
            <button type="submit" style="width: 500px; height: 50px; font-size: 20px; padding: 10px 20px;">Cdn Version(UnPublish Version)</button>
        </form>
        <form action="/query" method="post">
            <input type="text" name="short_id" placeholder="Enter short_id" required>
            <button type="submit" style="width: 100px; height: 30px; font-size: 16px; padding: 5px 10px;">Query</button>
        </form>
    '''
    return html_output

@app.route('/getmainScenePicture', methods=['POST'])
def getmainScenePicture():
    assetsUrl = 'https://res.snakesvc.com/assets'
    if 'short_id' in request.form:
        short_id = request.form.get('short_id')
        fileName = f'res.{short_id}.json'
        URL = f'https://res.snakesvc.com/res-version/{fileName}'
    else:
        fileName = 'res.json'
        URL = "https://res.snakesvc.com/assets/res.json"
        
    response = requests.get(URL)

    mainScene = []

     # Open the zip file from the response content
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        # Read the JSON file within the zip archive
        with zip_file.open(fileName) as json_file:
            content = json_file.read()
            res = json.loads(content.decode("utf-8"))
            print('downloaded')
            for i in res['files']:
                if i.endswith('.png'):
                    if i.startswith('mainScene'):
                        md5 = res['files'][i]['md5']
                        size = res['files'][i]['size']
                        path_Dot = i.split('.')
                        imageName = path_Dot[0] + '.' + md5 + '.' + path_Dot[1]
                        filePath = assetsUrl + '/' + imageName
                        if i.startswith('mainScene'):
                            mainScene.append((filePath, size))
        
    mainScene_sorted = sorted(mainScene, key=lambda x: x[1], reverse=True)
    # Construct HTML to display images in multiple rows
    html_output = "<div style='display: flex; flex-wrap: wrap;'>"
    for i in mainScene_sorted:
        html_output += f'<div style="flex: 1 1 100px; margin: 5px;"><img src="{i[0]}" style="max-width: 100%;"></div>'
    html_output += "</div>"
    
    return html_output

@app.route('/query', methods=['POST'])
def query_short_id():
    assetsUrl = 'https://res.snakesvc.com/assets'
    short_id = request.form['short_id']
    fileName = f'res.{short_id}.json'
    URL = f'https://res.snakesvc.com/res-version/{fileName}'
    response = requests.get(URL)

    if response.status_code == 404:
        return '<h1 style="font-size: 24px;">Error Short_id</h1>'

    login = []
    
    # Open the zip file from the response content
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file: 
        # Read the JSON file within the zip archive
        with zip_file.open(fileName) as json_file:
            content = json_file.read()
            res = json.loads(content.decode("utf-8"))
            for i in res['files']:
                if i.startswith('login'):
                    if i.endswith('.png'):
                        md5 = res['files'][i]['md5']
                        size = res['files'][i]['size']
                        path_Dot = i.split('.')
                        imageName = path_Dot[0] + '.' + md5 + '.' + path_Dot[1]
                        filePath = assetsUrl + '/' + imageName
                        login.append((filePath, size))
                        print(filePath, size)
    
    login_sorted = sorted(login, key=lambda x: x[1], reverse=True)
    print(login_sorted[0])
    
    # Extract version information
    version = res['version']
    version_data = (
        f"branch: {version['branch']}<br>"
        f"short_id: {version['short_id']}<br>"
        f"datetime: {version['datetime']}<br>"
        f"msg: {version['msg']}<br>"
    )

    # Construct HTML to display version information and login image
    html_output = f'<h1 style="font-size: 24px;">Query Specify {short_id}  Version</h1>'
    html_output += f'{version_data}Login Image:<br>'
    html_output += f'<img src="{login_sorted[0][0]}" alt="Login Image" style="max-width: 500px;">'
    html_output += '''
        <form action="/getmainScenePicture" method="post">
            <input type="hidden" name="short_id" value="''' + short_id + '''">
            <button type="submit" style="width: 300px; height: 50px; font-size: 20px; padding: 10px 20px;">Get Main Scene Pictures</button>
        </form>
        <form action="/currentMobileVersion" method="post">
            <button type="submit" style="width: 300px; height: 50px; font-size: 20px; padding: 10px 20px;">Get Current Version</button>
        </form>
        <form action="/" method="get">
            <button type="submit" style="width: 500px; height: 50px; font-size: 20px; padding: 10px 20px;">Cdn Version(UnPublish Version)</button>
        </form>
        <form action="/query" method="post">
            <input type="text" name="short_id" placeholder="Enter short_id" required>
            <button type="submit" style="width: 100px; height: 30px; font-size: 16px; padding: 5px 10px;">Query</button>
        </form>
    '''
    return html_output


if __name__ == '__main__':
    app.run(debug=True)
