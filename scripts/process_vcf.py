"""
extract KG information from the uncompressed VCF files.
"""

from dglink.core.constants import syn, REPORT_PATH
from dglink import load_graph, NodeSet, EdgeSet, write_graph
import vcf
import polars as pl
import os
import tqdm


def parse_vcf_file(file_id: str, node_set: NodeSet, edge_set: EdgeSet):
    try:
        obj = syn.get(file_id)
    except:
        return node_set, edge_set, 0
    if obj.path is None:
        return node_set, edge_set, 0
    study_id = obj.get("studyId", ["study_id_missing"])[0]
    ## remove after testing for now just add project node
    node_set.update_nodes(
        {
            "curie:ID": study_id,
            ":LABEL": "Project",
            "name": study_id,
            "source:string[]": "vcf",
        }
    )

    with open(obj.path, mode="r") as f:
        vcf_reader = vcf.Reader(f)
    ## extract reference and vcf format nodes and edges
    meta = vcf_reader.metadata
    vcf_format = meta.get("fileformat", "vcf_format_missing")
    reference = meta.get("reference", "reference_fasta_missing")
    vcf_cmnds = meta.get("source", ["vcf_command_missing"])
    node_set.update_nodes(
        {
            "curie:ID": vcf_format,
            ":LABEL": "VCF_file_format",
            "name": vcf_format,
            "file_id:string[]": file_id,
            "source:string[]": "vcf",
        }
    )
    node_set.update_nodes(
        {
            "curie:ID": reference,
            ":LABEL": "VCR_reference",
            "name": reference,
            "file_id:string[]": file_id,
            "source:string[]": "vcf",
        }
    )
    ## extract the sources
    for source in vcf_cmnds:
        node_set.update_nodes(
            {
                "curie:ID": source,
                ":LABEL": "VCF_command",
                "name": source,
                "file_id:string[]": file_id,
                "source:string[]": "vcf",
            }
        )
    ## source and commands are similar so merge to one node type
    ## extract the commands
    cmnds = meta.get("GATKCommandLine", [])
    for cmnd in cmnds:
        cmnd_id = cmnd.get("ID", "missing_command")
        node_set.update_nodes(
            {
                "curie:ID": cmnd_id,
                ":LABEL": "VCF_command",
                "name": cmnd_id,
                "file_id:string[]": file_id,
                "source:string[]": "vcf",
            }
        )
        vcf_cmnds.append(cmnd_id)
    ## go through all possible samples
    for sample in vcf_reader.samples:
        ## add sample as node
        node_set.update_nodes(
            {
                "curie:ID": sample,
                ":LABEL": "sample",
                "name": sample,
                "file_id:string[]": file_id,
                "source:string[]": "vcf",
            }
        )
        ## add edge between sample and project
        edge_set.update_edges(
            {
                ":START_ID": study_id,
                ":END_ID": sample,
                ":TYPE": "has_sample",
                "source:string[]": "vcf",
            }
        )
        ## add edges from each sample to the file format and reference
        edge_set.update_edges(
            {
                ":START_ID": sample,
                ":END_ID": vcf_format,
                ":TYPE": "has_vcf_format",
                "source:string[]": "vcf",
            }
        )
        edge_set.update_edges(
            {
                ":START_ID": sample,
                ":END_ID": reference,
                ":TYPE": "has_vcf_reference",
                "source:string[]": "vcf",
            }
        )
        ## add each of the command ids to the sample
        for vcf_cmnd in vcf_cmnds:
            edge_set.update_edges(
                {
                    ":START_ID": sample,
                    ":END_ID": vcf_cmnd,
                    ":TYPE": "has_vcf_command",
                    "source:string[]": "vcf",
                }
            )
    return node_set, edge_set, 1


if __name__ == "__main__":
    # node_set, edge_set = load_graph(
    #     resource_path="dglink/resources/graph/",
    #     node_name="nodes.tsv",
    #     edge_name="edges.tsv",
    # )
    node_set = NodeSet()
    edge_set = EdgeSet()
    processed = 0
    files_df = pl.read_csv(
        os.path.join(REPORT_PATH, "file_type_report.tsv"), separator="\t"
    ).filter(pl.col("extension").eq(".vcf"))
    i = 0
    for file_id in tqdm.tqdm(files_df["syn_id"]):
        node_set, edge_set, could_process = parse_vcf_file(
            file_id=file_id, node_set=node_set, edge_set=edge_set
        )
        ## iteratively update
        if i % 100 == 0:
            write_graph(node_set=node_set, edge_set=edge_set)
        i = i + 1
        processed += could_process
    write_graph(node_set=node_set, edge_set=edge_set)
    print(f"Processed {processed} VCF files out of {i}")
