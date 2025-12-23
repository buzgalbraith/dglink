"""
extract KG information from the uncompressed VCF files.
"""

from dglink import load_graph
import re
from dglink.core.vcf_data import get_vcf_data

vcf_formats = [".vcf", ".gvcf", ".vcf.gz", ".gvcf.gz"]
vcf_pattern = f"({'|'.join(re.escape(s) for s in vcf_formats)})$"


if __name__ == "__main__":

    node_set, edge_set = load_graph(
        resource_path="dglink/resources/graph/",
        node_name="nodes.tsv",
        edge_name="edges.tsv",
    )
    node_set, edge_set, reports = get_vcf_data(
        project_ids=["a"],
        node_set=node_set,
        edge_set=edge_set,
        process_compressed_files=False,
        process_variants=False,
    )
