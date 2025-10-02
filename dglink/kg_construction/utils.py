"""utility code for KG construction scripts"""

import pandas
import chardet
import os
from synapseutils import walk


def read_csv_auto(path, nbytes=100 * 1024 * 1024, **kwargs):
    """
    Reads a CSV (or TSV) file with automatic encoding detection.
    """
    # Detect encoding
    with open(path, "rb") as f:
        rawdata = f.read(nbytes)
    ## deal with empty file
    if len(rawdata) < 1:
        return None
    result = chardet.detect(rawdata)
    encoding = result["encoding"]
    ## check if there are comments
    comment = None
    with open(path, "rb") as f:
        first_byte = f.read(1)
        is_comment = first_byte == b"#"
    if is_comment:
        comment = "#"
    # Fall back if detection fails
    if encoding is None:
        encoding = "latin1"
    sample_lines = 3
    with open(path, "r", encoding=encoding, errors="ignore") as f:
        all_lines = f.readlines()

    n = min(sample_lines, len(all_lines))
    lines = all_lines[:n]

    header_idx = 0
    max_alpha = -1
    if "sep" in kwargs:
        delimiter = "\t"
    else:
        delimiter = ","
    for i, line in enumerate(lines):
        # Split and count how many entries look like text vs numbers
        parts = [p.strip() for p in line.split(delimiter)]
        alpha_count = sum(not p.replace(".", "", 1).isdigit() for p in parts if p)
        if alpha_count > max_alpha:
            max_alpha = alpha_count
            header_idx = i
    df = pandas.read_csv(
        path, encoding=encoding, comment=comment, header=header_idx, **kwargs
    )
    return df


def read_xlsx_auto(path, sample_rows=20, **kwargs):
    preview = pandas.read_excel(path, sheet_name=None, header=None, nrows=sample_rows)
    df_dict = {}
    for sheet_name in preview:
        header_idx = 0
        max_alpha = -1
        for i, row in preview[sheet_name].iterrows():
            values = row.dropna().astype(str)
            # Count how many look like text instead of numbers
            alpha_count = sum(not v.replace(".", "", 1).isdigit() for v in values)
            if alpha_count > max_alpha:
                max_alpha = alpha_count
                header_idx = i
        df_dict[sheet_name] = pandas.read_excel(
            path, sheet_name=sheet_name, header=header_idx, **kwargs
        )
    return df_dict


def file_reader(obj, max_size_bytes=100 * 1024 * 1024):
    """
    reads in files from a synapse file object. Returns files as a dictionary for working with sheets
    """
    if obj is None:
        return {}
    if obj.path is None:
        return {}
    file_size = os.path.getsize(obj.path)
    if file_size > max_size_bytes:
        print("file to large to read")
        return {}
    ext = os.path.splitext(obj.path)[-1]
    if ext == ".tsv":
        df = {"Sheet1": read_csv_auto(obj.path, sep="\t")}
    elif ext == ".csv":
        try:
            df = {"Sheet1": read_csv_auto(obj.path)}
        except:
            df = {"Sheet1": read_csv_auto(obj.path, sep="\t")}
    elif ext == ".xlsx":
        ## reads in all sheets at once
        df = read_xlsx_auto(obj.path)
    elif ext == ".xls":
        try:
            df = pandas.read_excel(obj.path, engine="xlrd")
            if type(df) != dict:
                df = {"Sheet1": df}
        ## anecdotal there seem to be a lot of these that are just mislabeled tsv
        except:
            df = {"Sheet1": read_csv_auto(obj.path, sep="\t")}
    return df


def get_project_files(syn, project_syn_id, file_types):
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
                if os.path.splitext(filename[0])[1] in file_types:
                    project_files.add(filename)
    return project_files


def load_existing_nodes(node_path="dglink/resources/nodes.tsv"):
    """loads existing set of nodes as a dictionary"""
    if not os.path.exists(node_path):
        return dict()
    df = pandas.read_csv(node_path, sep="\t", index_col=False)
    df = df.fillna(value="")
    # set index as first col assuming that is the id
    df = df.set_index(df.columns[0])
    nodes = dict()
    for curie, row in df.iterrows():
        nodes[curie] = dict()
        for i, col in enumerate(df.columns):
            val = row.iloc[i]
            if ":string[]" in col:
                val = set(str(val).replace('"', "").replace("'", "").split(";"))
            nodes[curie][col] = val
    return nodes


def load_existing_edges(edge_path="dglink/resources/edges.tsv"):
    """read in the files with edges as set"""
    if not os.path.exists(edge_path):
        return set()
    existing_relations = set()
    with open(edge_path, "r") as f:
        for row in f.readlines()[1:]:
            existing_relations.add(tuple(row.strip().split("\t")))
    return existing_relations


def write_nodes(nodes: str, node_path: dict):
    """writes a set of nodes to a given location"""
    with open(node_path, "w") as f:
        first_key = next(iter(nodes))
        keys = nodes[first_key].keys()
        f.write("curie:ID\t" + "\t".join(keys) + "\n")
        for curie in nodes:
            write_str = f"{curie}\t"
            for col in nodes[curie]:
                val = nodes[curie][col]
                if type(val) == set:
                    val = f'"{";".join(val)}"'
                write_str += f"{val}\t"
            f.write(write_str[:-1] + "\n")


def write_edges(edges, edge_path="dglink/resources/edges.tsv"):
    edges = [(":START_ID", ":END_ID", ":TYPE")] + list(edges)
    with open(edge_path, "w") as f:
        for row in edges:
            f.write("\t".join(row) + "\n")
