from flask import Flask, request

app = Flask(__name__)

@app.route("/test")
def test_route():
    return "<p>Hello, Test!</p>"

@app.route("/analyze_clip", methods=['POST'])
def hello_world():
    print(request.files)
    return "<p>Hello, World!</p>"