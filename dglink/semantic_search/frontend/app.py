from flask import Flask, render_template, request, jsonify
import requests
import ast

app = Flask(__name__)

BACKEND_URL = "http://backend:8000/"


def process_results(raw_results):
    processed = []
    for row in raw_results:
        processed_row = []
        for ent in row:
            try:
                load = ast.literal_eval(ent.split(":", 1)[1].strip())
                for key in load:
                    val = load[key]
                    if (key.split(" ")[-1] == "iri") \
                        or \
                        (key.split(" ")[-1] == "project_url") \
                        or \
                        (key.split(" ")[-1] == "evidence"):
                        processed_row.append(
                            {
                                "text": f"{val}",
                                "field": key,
                                "url": val,  # store the actual url
                            }
                        )
                    else:
                        processed_row.append(
                            {
                                "text": f"{key}: {val}",
                                "url": None,  # store the actual url
                            }
                        )
            except:
                processed_row.append({"text": ent, "url": None})  # store the actual url
        processed.append(processed_row)
    return processed


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    form_data = {
        "Agent": "",
        "Relation": "",
        "OtherAgent": "",
        "QueryType": "Subject",  # default selection
    }
    if request.method == "POST":
        form_data["Agent"] = request.form.get("Agent", "")
        form_data["Relation"] = request.form.get("Relation", "")
        form_data["OtherAgent"] = request.form.get("OtherAgent", "")
        form_data["QueryType"] = request.form.get("QueryType", "Subject")
        agent = request.form.get("Agent")
        relation = request.form.get("Relation")
        other_agent = request.form.get("OtherAgent")
        query_type = request.form.get("QueryType")
        response = requests.get(
            f"{BACKEND_URL}/query",
            params={
                "agent": agent,
                "relation": relation,
                "other_agent": other_agent,
                "query_type": query_type,
            },
        )
        data = response.json()
        raw_result = data["message"]
        result = process_results(raw_results=raw_result)

    return render_template("index.html", result=result, form_data=form_data)


@app.route("/autocomplete")
def autocomplete():
    query = request.args.get("query", "")
    completion_type = request.args.get("inputId", "").lower()
    response = requests.get(
        f"{BACKEND_URL}/autoComplete",
        params={
            "query": query,
            "completion_type": completion_type,
        },
    )
    data = response.json()
    return data


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
