import requests
import json

GC_API = "https://general.datacommons.cancer.gov/v1/graphql/"

def gql(query: str, variables: dict = None) -> dict:
    resp = requests.post(GC_API, json={"query": query, **({"variables": variables} if variables else {})})
    resp.raise_for_status()
    return resp.json()["data"]

def get_studies_for_program(program_name: str) -> list[dict]:
    data = gql("""
        query ($program_names: [String]) {
          studies(program_names: $program_names, first: 1000, offset: 0) {
            phs_accession
            study_name
            study_acronym
          }
        }
    """, {"program_names": [program_name]})
    return data["studies"]

def get_all_files_for_study(phs_accession: str, page_size: int = 1000) -> list[dict]:
    files, offset = [], 0
    while True:
        data = gql("""
            query ($phs_accession: String, $first: Int, $offset: Int) {
              files(phs_accession: $phs_accession, first: $first, offset: $offset) {
                file_id
                file_name
                file_type
                file_size
                drs_uri
              }
            }
        """, {"phs_accession": phs_accession, "first": page_size, "offset": offset})
        batch = data["files"]
        files.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return files

def get_program_with_files(program_name: str) -> dict:
    studies = get_studies_for_program(program_name)
    print(f"Found {len(studies)} studies for program '{program_name}'")

    result = {"program_name": program_name, "studies": []}
    for study in studies:
        phs = study["phs_accession"]
        print(f"  Fetching files for {phs} ({study['study_name']})...")
        files = get_all_files_for_study(phs)
        print(f"    -> {len(files)} files")
        result["studies"].append({**study, "files": files})

    return result

if __name__ == "__main__":
    PROGRAM_NAME = "Human Tumor Atlas Network"  # change me
    result = get_program_with_files(PROGRAM_NAME)
    print(json.dumps(result, indent=2))
