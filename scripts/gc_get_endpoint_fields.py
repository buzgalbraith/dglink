import requests

GC_API = "https://general.datacommons.cancer.gov/v1/graphql/"

TYPE_NAME = "Study"  # change to Program, Participant, File, Sample, etc.

query = """
query ($type: String!) {
  __type(name: $type) {
    name
    fields {
      name
      type {
        name
        kind
        ofType { name kind }
      }
    }
  }
}
"""

resp = requests.post(GC_API, json={"query": query, "variables": {"type": TYPE_NAME}})
resp.raise_for_status()

fields = resp.json()["data"]["__type"]["fields"]
for f in fields:
    t = f["type"]
    type_name = t["name"] or t["ofType"]["name"]
    print(f"{f['name']}: {type_name}")
