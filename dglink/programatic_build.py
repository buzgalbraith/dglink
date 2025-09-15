"""
Goals:
    1. pull the required info using the synapse api
    2. run the functionality of build.py
"""

import synapseclient
from synapseutils import walk
import os
import pandas
import gilda

FILE_TYPES = [
    ".tsv",
    # '.txt',
    ".xls",
    ".xlsx",
    ".csv",
]


def get_project_files(syn, project_syn_id):
    """
    returns a set of all files associated with a given synapse project id.
    """
    project_files = set()
    for _, _, filenames in walk(
        syn=syn,
        synId=project_syn_id,
        includeTypes=[
            "file",
        ],
    ):
        if len(filenames) > 0:
            for filename in filenames:
                if os.path.splitext(filename[0])[1] in FILE_TYPES:
                    project_files.add(filename)
    return project_files


def get_entity_grounder():
    """
    makes a grounder for the names of different types of entites used for finding cols
    """
    ## Name grounder.
    base_entities = {
        "compound": gilda.Term(
            "chemical compound",
            "chemical compound",
            "CHEBI",
            "CHEBI:37577",
            "compound",
            "synonym",
            "chebi",
        ),
        "gene": gilda.Term(
            "Gene", "Gene", "MESH", "MESH:D005796", "Gene", "synonym", "mesh"
        ),
        "cell line": gilda.Term(
            "cell line",
            "cell line",
            "MESH",
            "MESH:D002460",
            "cell line",
            "synonym",
            "mesh",
        ),
    }
    alternative_entity_names = {
        "compound": ["drug", "compound", "chemical compound"],
        "gene": ["gene", "target",'target(s)', "genetic material", "criston"],
        "cell line": ["cell line", "cellline", "cell_line"],
    }
    terms = []
    for entity_name in base_entities:
        for alternative_name in alternative_entity_names[entity_name]:
            term = gilda.Term(
                alternative_name,
                alternative_name,
                base_entities[entity_name].db,
                base_entities[entity_name].id,
                base_entities[entity_name].entry_name,
                base_entities[entity_name].status,
                None,
            )
            terms.append(term)
    return gilda.make_grounder(terms)


def ground_entries(entries):
    """
    use gilda to ground existing entites
    """
    name_to_id = {}
    for entity in set(entries):
        anns = gilda.annotate(entity)
        if anns:
            name_to_id[entity] = (
                anns[0].matches[0].term.db,
                anns[0].matches[0].term.id,
            )
        else:
            name_to_id[entity] = None
            print(entity)
    return name_to_id


def file_reader(obj):
    """
    reads in files from a synapse file object. Returns files as a dictionary for working with sheets
    """
    ext = os.path.splitext(obj.path)[-1]
    if ext == ".tsv":
        df = {"Sheet1": pandas.read_csv(obj.path, sep="\t")}
    
    elif ext == ".xlsx":
        ## reads in all sheets at once 
        df = pandas.read_excel(obj.path, sheet_name=None)
    ## work around for cases where need to skip lines
    for sheet_name in df:
        if ("Unnamed" in df[sheet_name].columns[0]) & (
            "Unnamed" in df[sheet_name].columns[1]
        ):
            df[sheet_name] = pandas.read_excel(
                obj.path, sheet_name=sheet_name, skiprows=1
            )  ## load all sheets
    return df


def process_enteries(project_id, entries, entity_type):
    """
    process found enteties into lists of nodes and relations
    """
    node_project = (project_id, "Project")
    node_entries = set([
        (f"{nsid[0]}:{nsid[1]}", entity_type)
        for name, nsid in entries.items()
        if nsid is not None
    ])
    relations = set([
        (project_id, f"{nsid[0]}:{nsid[1]}", f"has_{entity_type}")
        for name, nsid in entries.items()
        if nsid is not None
    ])
    return set([node_project]) | node_entries, relations


if __name__ == "__main__":
    ## login/validate synapse client
    syn = synapseclient.login()

    ## projects we are intrested in adding to the graph
    projects_to_check = [
        "syn2343195",
        "syn5562324",
        "syn27761862",
    ]

    ## could use this function to get all files for each project.
    # project_files = get_project_files(syn=syn, project_syn_id=PROJECT_SYN_ID)

    ## for now we are just intrested in adding these three files from those projects
    selected_files = [
        "syn6138237",
        "syn5562327",
        "syn30384693",
    ]
    ## get a grounder for col names to entity types
    entity_grounder = get_entity_grounder()
    ## lets focous on one example file from that project
    # nodes = [["curie:ID", ":LABEL"]]
    # relations = [[":START_ID", ":END_ID", ":TYPE"]]
    nodes = set()
    relations = set()
    for i, project_id in enumerate(projects_to_check):
        ## when expanding this have another loop here over all the files pulled for each project
        file_id = selected_files[i]
        obj = syn.get(file_id)
        df_dict = file_reader(obj)
        ## extra loop in case there are multiple sheets
        for sheet in df_dict:
            df = df_dict[sheet].fillna('') ## fill na with '' for now. 

            ## keep only string types
            # df = df.select_dtypes(include=["object", "string"])
            # import ipdb; ipdb.set_trace()
            # for val in df.iloc[0].items():
            #     anns = gilda.annotate(val[1])
            #     if anns:
            #         print(val)
            #         print(anns)


            ## find cols that represent enteties in the KG
            # import ipdb; ipdb.set_trace()
            for col in df.columns:
                entity_type_match = entity_grounder.ground(gilda.process.normalize(col))
                if len(entity_type_match) > 0:
                    entries = ground_entries(df[col])
                    project_nodes, project_relations = process_enteries(
                        project_id=project_id,
                        entries=entries,
                        entity_type=entity_type_match[0].term.entry_name,
                    )
                    nodes = nodes | project_nodes
                    relations = relations | project_relations
    nodes = [["curie:ID", ":LABEL"]] + list(nodes)
    relations = [[":START_ID", ":END_ID", ":TYPE"]] + list(relations)
    # # # Dump nodes into nodes.tsv and relations into edges.tsv
    with open("dglink/resources/nodes.tsv", "w") as f:
        for row in nodes:
            f.write("\t".join(row) + "\n")
    with open("dglink/resources/edges.tsv", "w") as f:
        for row in relations:
            f.write("\t".join(row) + "\n")
