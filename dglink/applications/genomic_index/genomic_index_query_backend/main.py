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

logger = logging.getLogger()

AVAILABLE_INDEXES = ["mantis"]

@dataclass
class SequenceQuery:
    id : str
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
    transcript_id: str|None
    biotype:str|None
    seq: str
    header : str|None
    hits: list[SampleHit] = field(default_factory=list)


    @property
    def best_hit(self) -> SampleHit | None:
        return max(self.hits, key=lambda h: h.hit_fraction, default=None)

    @property
    def is_matched(self) -> bool:
        return bool(self.hits)

def _clean_sample_id(path: str) -> str:
    return Path(path).stem

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
        results.append(QueryResult(qnum=qnum,
                                   num_kmers=num_kmers,
                                   id=query.id,
                                   gene_symbol=query.gene_symbol,
                                   transcript_id=query.transcript_id,
                                   biotype=query.biotype,
                                   seq=query.seq, 
                                   header = query.header,
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

        
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

