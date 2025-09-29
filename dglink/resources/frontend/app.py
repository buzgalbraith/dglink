from flask import Flask, render_template, request
import requests

app = Flask(__name__)

BACKEND_URL = "http://backend:8000/query"

@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    if request.method == "POST":
        agent = request.form.get("Agent")
        relation = request.form.get("Relation") 
        other_agent = request.form.get("OtherAgent") 
        query_type = request.form.get("QueryType")  
        response = requests.get(BACKEND_URL, params={"agent": agent, 'relation': relation, 'other_agent':other_agent , "query_type":query_type})
        data = response.json()
        result = data["message"]

    return render_template("index.html", result=result)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
