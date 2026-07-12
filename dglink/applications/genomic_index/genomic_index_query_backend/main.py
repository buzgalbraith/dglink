from fastapi import FastAPI
from fastapi.responses import JSONResponse
import subprocess
import logging
from Bio import SeqIO
import io
from dataclasses import dataclass, field, asdict
from pathlib import Path
import re 
import json
import os 
from neo4j import GraphDatabase
from urllib.parse import urlencode

logger = logging.getLogger()

driver = GraphDatabase.driver(
    "bolt://neo-4j:7687",
    auth=(os.environ.get("NEO4J_URI"), os.environ.get("NEO4J_PASSWORD")),
)
AVAILABLE_INDEXES = ["mantis"]

@dataclass
class SequenceQuery:
    id : str
    ensembl_id: str| None
    header : str|None
    seq: str
    length: int
    gene_symbol: str|None
    transcript_id: str|None
    biotype:str|None

@dataclass
class SampleHit:
    sample: str       
    sample_id: str     
    kmer_hits: int
    hit_fraction: float

@dataclass
class QueryResult:
    qnum: int
    num_kmers: int
    id : str
    gene_symbol: str|None
    ensemble_url: str|None
    transcript_id: str|None
    biotype:str|None
    seq: str
    header : str|None
    result_url: str
    hits: list[SampleHit] = field(default_factory=list)


    @property
    def best_hit(self) -> SampleHit | None:
        return max(self.hits, key=lambda h: h.hit_fraction, default=None)

    @property
    def is_matched(self) -> bool:
        return bool(self.hits)

def _clean_sample_id(path: str) -> str:
    return Path(path).stem

def get_gene_url(emedbl_id: str) -> str | None:

    base_id = emedbl_id.split('.')[0]
    
    if emedbl_id.startswith('ENSMUSG'):
        return f"https://www.ensembl.org/Mus_musculus/Gene/Summary?g={base_id}"
    elif emedbl_id.startswith('ENSG'):
        return f"https://www.ensembl.org/Homo_sapiens/Gene/Summary?g={base_id}"
    return None

def parse_res(raw: str, queries:list[SequenceQuery],  threshold: float = 0.0) -> list[QueryResult]:
    """
    Parse a Mantis .res file into a list of QueryResult objects.

    Args:
        raw:       Raw string content of the .res file.
        threshold: Minimum hit_fraction to include a sample (0.0 = keep all).
    """

    clean = re.sub(r",\s*([}\]])", r"\1", raw)
    entries = json.loads(clean)

    if len(entries) != len(queries):
        raise ValueError(f"Found {len(queries)} queries and {len(entries)} results, check input file format")

    results = []
    for query, entry in zip(queries, entries):
        qnum = entry["qnum"]
        num_kmers = entry["num_kmers"]
        hits = []
        for squeakr_path, kmer_hits in entry.get("res", {}).items():
            frac = round(kmer_hits / num_kmers, 4) if num_kmers > 0 else 0.0
            if frac < threshold:
                continue
            hits.append(SampleHit(
                sample=squeakr_path,
                sample_id=_clean_sample_id(squeakr_path),
                kmer_hits=kmer_hits,
                hit_fraction=frac,
            ))
        hits.sort(key=lambda h: h.hit_fraction, reverse=True)
        print("-"*100)
        if query.ensembl_id:
            ensmbl_url = get_gene_url(query.ensembl_id)
        else:
            ensmbl_url = ""
        print("-"*100)
        url = query_kg([f'"{x.sample_id}"' for x in hits])
        results.append(QueryResult(qnum=qnum,
                                   num_kmers=num_kmers,
                                   id=query.id,
                                   gene_symbol=query.gene_symbol,
                                   transcript_id=query.transcript_id,
                                   biotype=query.biotype,
                                   seq=query.seq, 
                                   header = query.header,
                                   ensemble_url=ensmbl_url,
                                   result_url=url,
                                   hits=hits))

    results.sort(key=lambda r: r.qnum)
    return results


def write_fasta(queries: list[SequenceQuery], output_path: str | Path, line_width: int = 0) -> Path:
    """
    Write a list of SequenceQuery objects to a FASTA file suitable for Mantis input.

    Args:
        queries:     Parsed sequence queries from parse_fasta().
        output_path: Destination .fa / .fasta path.
        line_width:  Wrap sequence lines at this width (60 is NCBI standard). 0 = no wrapping.

    Returns:
        The resolved output path.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as fh:
        for q in queries:
            header = q.header if q.header else q.id
            fh.write(f">{header}\n")
            seq = q.seq
            if line_width > 0:
                for i in range(0, len(seq), line_width):
                    fh.write(seq[i:i + line_width] + "\n")
            else:
                fh.write(seq + "\n")

    return output_path

def parse_fasta(raw: str) -> list[SequenceQuery]:
    """Parse FASTA or raw nucleotide input into a list of sequence dicts."""
    raw = raw.strip()
    if not raw:
        return []
 
    sequences:list[SequenceQuery] = []
 
    if raw.startswith(">"):
        handle = io.StringIO(raw)
        for record in SeqIO.parse(handle, "fasta"):
            seq_str = str(record.seq).upper()
            parts = record.description.split("|")
            sequences.append(
                SequenceQuery(
                id= record.id,
                header= record.description,
                seq= seq_str,
                length= len(seq_str),
                ensembl_id=parts[1] if len(parts) > 1 else record.id,
                gene_symbol= parts[5] if len(parts) > 5 else record.id,
                transcript_id= parts[0] if parts else record.id,
                biotype= parts[7] if len(parts) > 7 else None,
                )
            )
    else:
        # Raw nucleotide string
        ## accommodate cases where transcripts are broken by either new line or a blank line
        lines = raw.split("\n\n")
        if len(lines)<=1:
            lines = raw.split("\n")

        for i, raw_seq in enumerate(lines):
            seq_str = raw_seq.replace(" " , "").upper()
            sequences.append(
                SequenceQuery(
                id= f"query_{i}",
                header= None,
                ensembl_id=None,
                seq= seq_str,
                length= len(seq_str),
                gene_symbol= "Raw query",
                transcript_id= None,
                biotype= None,
                )
            )
 
    return sequences
 

app = FastAPI()

@app.post("/query")
def query(query_input, k, threshold, index):
    threshold = float(threshold)
    index_name = index.lower()
    assert index in AVAILABLE_INDEXES, AssertionError(f"{index_name} invalid chose from{ AVAILABLE_INDEXES }" )
    queries = parse_fasta(query_input)
    write_fasta(queries=queries, output_path='/sw/query_file')
    if index_name == "mantis":
        cmd = [
            'bash', '/sw/scripts/query_index.sh', 'query'
        ]
        subprocess.run(cmd)

    with open('/sw/query_results/query.res', mode = 'r') as f:
        raw = f.read()
    results = parse_res(raw, queries, threshold=threshold)
    return JSONResponse(content={
        "results": [asdict(r) for r in results],
        "meta": {
            "sequence_count": len(results),
            "total_kmers": sum(r.num_kmers for r in results),
            "k": k,
            "threshold": threshold,
            "index": index,
        }
    })


def neo4j_url(query, host="http://localhost:7474", run=False):
    cmd = "play" if run else "edit"
    params = urlencode({"cmd": cmd, "arg": query})
    return f"{host}/browser/?{params}"

def query_kg(syn_id: list[str] = None):
    q = f"""
        MATCH (p:Project)-[:has_specimen]->(s:specimen)-[]->(e)
        WHERE e.curie = {' OR e.curie = '.join(syn_id)}
        MATCH (s)-[]->(related)
        WHERE related:anatomical_region OR related:organism
        RETURN p, s, e, related
        """
    return neo4j_url(q)
    # records, _, _ = driver.execute_query(q,
    #     database_="neo4j",
    # )
    # print(neo4j_url(q,)    )      # loads into editor
    # print(neo4j_url(q,  run=True)) # runs immediately 
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
