from flask import Flask, Response
import requests
import zipfile
import json
import io

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
    html_output = f'{version_data}Login Image:<br>'
    html_output += f'<img src="{login_sorted[0][0]}" alt="Login Image" style="max-width: 500px;">'
    html_output += '''
        <form action="/getmainScenePicture" method="post">
            <button type="submit">getmainScenePicture</button>
        </form>
    '''
    return html_output

@app.route('/getmainScenePicture', methods=['POST'])
def getmainScenePicture():
    URL = "https://res.snakesvc.com/assets/res.json"
    assetsUrl = 'https://res.snakesvc.com/assets'

    response = requests.get(URL)

    mainScene = []

     # Open the zip file from the response content
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        # Read the JSON file within the zip archive
        with zip_file.open('res.json') as json_file:
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

if __name__ == '__main__':
    app.run(debug=True)
