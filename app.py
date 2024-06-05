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
    
    return html_output

if __name__ == '__main__':
    app.run(debug=True)
