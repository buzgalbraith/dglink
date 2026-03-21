#!/bin/bash 

# uv run scripts/gc_metadata_assemble.py \
#     # && \
    uv run scripts/gc_tabular_assemble.py \
    && \
    cp nci_gc_graph/* ./dglink/resources/graph