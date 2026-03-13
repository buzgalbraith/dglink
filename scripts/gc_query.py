import requests
import json

GC_API = "https://general.datacommons.cancer.gov/v1/graphql/"

## get program names ## 
query = """
{
  programs(first: 10, offset: 0) {
    program_name
    program_acronym
  }
}
"""
## get program count ## 

query = """
{
  programsCount
}
"""
query = """
{
  studies(first: 10, offset: 0) {
      study_id
      study_name
      funding_source_program_name
  }
}
"""
## get program count ## 



response = requests.post(GC_API, json={"query": query})
response.raise_for_status()

data = response.json()
print(json.dumps(data, indent=2))
