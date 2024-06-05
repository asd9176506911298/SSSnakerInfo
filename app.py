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
    
    # Fetch the zip file from the URL
    response = requests.get(URL)
    
    # Open the zip file from the response content
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        # Read the JSON file within the zip archive
        with zip_file.open('res.json') as json_file:
            content = json_file.read()
            res = json.loads(content.decode("utf-8"))
    
    # Extract version information
    version = res['version']
    version_data = (
        f"branch: {version['branch']}<br>"
        f"short_id: {version['short_id']}<br>"
        f"datetime: {version['datetime']}<br>"
        f"msg: {version['msg']}"
    )
    
    # Return the formatted version data as an HTML response
    return Response(version_data, mimetype='text/html')

if __name__ == '__main__':
    app.run(debug=True)
