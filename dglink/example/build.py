import gilda
import pandas

fname = "CTF-UCF-Cenix-CompleteCompoundData-all passes in one tab_ to release_FINAL_cleaned.xlsx"


def ground_entries(entries):
    name_to_id = {}
    for compound in set(entries):
        anns = gilda.annotate(compound)
        if anns:
            name_to_id[compound] = (
                anns[0].matches[0].term.db,
                anns[0].matches[0].term.id,
            )
            print(compound, anns[0].matches[0].term.db, anns[0].matches[0].term.id)
        else:
            name_to_id[compound] = None
            print(compound, "NO MATCH")
    return name_to_id


def get_ctf_ucf():
    df = pandas.read_excel(fname, sheet_name="Single Agent Set 2 Raw Data")
    entries = ground_entries(df.compound)
    project_id = "synapse.project:ucf"
    node_project = (project_id, "Project")
    node_entries = [
        (f"{nsid[0]}:{nsid[1]}", "Compound")
        for name, nsid in entries.items()
        if nsid is not None
    ]
    relations = [
        (project_id, f"{nsid[0]}:{nsid[1]}", "has_compound")
        for name, nsid in entries.items()
        if nsid is not None
    ]
    return [node_project] + node_entries, relations


def get_nf_ac_crispr():
    df = pandas.read_excel(
        "NF2-_AC-CRISPR-A19 drug treatment.xlsx", sheet_name="Sheet1", skiprows=1
    )
    entries = ground_entries(df.Drug)
    project_id = "synapse.project:ac"
    node_project = (project_id, "Project")
    node_entries = [
        (f"{nsid[0]}:{nsid[1]}", "Compound")
        for name, nsid in entries.items()
        if nsid is not None
    ]
    relations = [
        (project_id, f"{nsid[0]}:{nsid[1]}", "has_compound")
        for name, nsid in entries.items()
        if nsid is not None
    ]
    return [node_project] + node_entries, relations


def get_nf_synodos():
    df = pandas.read_csv("Synodos_DrugScreen_processed_data.tsv", sep="\t")
    entries = ground_entries(df.drug)
    project_id = "synapse.project:synodos"
    node_project = (project_id, "Project")
    node_entries = [
        (f"{nsid[0]}:{nsid[1]}", "Compound")
        for name, nsid in entries.items()
        if nsid is not None
    ]
    relations = [
        (project_id, f"{nsid[0]}:{nsid[1]}", "has_compound")
        for name, nsid in entries.items()
        if nsid is not None
    ]
    return [node_project] + node_entries, relations


if __name__ == "__main__":
    nodes1, relations1 = get_ctf_ucf()
    nodes2, relations2 = get_nf_ac_crispr()
    nodes3, relations3 = get_nf_synodos()
    nodes = [["curie:ID", ":LABEL"]] + nodes1 + nodes2 + nodes3
    relations = (
        [[":START_ID", ":END_ID", ":TYPE"]] + relations1 + relations2 + relations3
    )
    # Dump nodes into nodes.tsv and relations into edges.tsv
    with open("nodes.tsv", "w") as f:
        for row in nodes:
            f.write("\t".join(row) + "\n")
    with open("edges.tsv", "w") as f:
        for row in relations:
            f.write("\t".join(row) + "\n")
