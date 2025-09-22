"""
This will download all files related to the drug screening projects
"""
import synapseclient
from synapseutils import walk
import os
import tqdm
from programatic_build import file_reader, get_project_files
import gilda
import pandas
from functools import lru_cache
from indra.ontology.bio import bio_ontology


syn = synapseclient.login()


FILE_TYPES = [
    ".tsv",
    ".xls",
    ".xlsx",
    ".csv",
]


all_project_ids = [
    "syn2343195", ## large project
    "syn5562324", ## small project
    "syn27761862", ## small project
    "syn4939874",   ## large project
    "syn4939876", ## locked
    "syn4939906", ## small
    "syn4939916", ## locked
    "syn7217928", ## large
    "syn8016635", ## small
    "syn11638893", ## locked
    "syn11817821", ## large
    "syn21641813", ## locked
    "syn21642027", ## locked
    "syn21650493", ## large
    "syn21984813", ## large
    "syn23639889", ## locked
    "syn51133914", ## locked
    "syn52740594", ## large 
]


def check_df_readable(df, max_unnamed = 2):
    """determine if a given data frame was correctly read in"""
    if len(df.columns) < 1: 
        return False, df
    unnamed_count = sum(df.columns.str.contains('Unnamed', case=False))
    can_read = False
    if unnamed_count > max_unnamed:
        print("cant read")
        df = None
    else:
        print("can read")
        df = df.select_dtypes(include=["object", "string"]).dropna()
        can_read = True
    return can_read, df

@lru_cache(maxsize=None)
def cached_annotate(val):
    """cached inner function for grounding with gilda"""
    anns = gilda.annotate(str(val))
    if anns:
        nsid = anns[0].matches[0].term
        return f"{nsid.db}:{nsid.id}",bio_ontology.get_type(nsid.db, nsid.id)
    return None, None

def apply_ground(row):
    """method for applying grounding to data frame"""
    result = {}  
    for col in row.index:
        result[f"{col}_entity"], result[f"{col}_type"] = cached_annotate(row[col])
    return pandas.Series(result)

def filter_df(df, base_cols, nan_percentage=0.1, max_types = 5 ):
    """filter the raw entity df removing columns with less than some percentage of entites found or more than some number of types"""
    ## filter out cols with less than 10% rows successfully grounded
    res = df.loc[:, df.count()/len(df) >= nan_percentage] 
    base_cols = [x for x in base_cols if f"{x}_type" in res.columns]
    ## filter out columns with more than some set number of max entity types
    cols_to_drop = []
    for base in base_cols:
        if res[f'{base}_type'].nunique() > max_types:
            cols_to_drop.extend([f"{base}_type", f"{base}_entity"])
    final = res.drop(columns=cols_to_drop)
    base_cols = [x for x in base_cols if f"{x}_type" in final.columns]
    return final, base_cols

def extract_df_graph(df, cols, project_id):
    """extract nodes and edges form df"""
    file_nodes = set()
    file_edges = set()

    for _, row in df.iterrows():
        for col in cols:
            entity = row[f"{col}_entity"]
            entity_type = row[f"{col}_type"]
            if (not pandas.isna(entity)) & (not pandas.isna(entity_type)):
                file_nodes.add((entity, entity_type))
                file_edges.add((project_id, entity, f"has_{entity_type}"))

    return file_nodes, file_edges


if __name__ == "__main__":
    files_read = [] 
    entity_cols = [] 
    nodes = set()
    relations = set()
    for project_id in all_project_ids:
        ## add the project id directly
        nodes.add((project_id, "Project"))
        ## load all files for a given project 
        project_files = get_project_files(syn=syn, project_syn_id=project_id)
        for p_file in project_files:
            ## this function can throw an error depending on file permissions
            try:
                obj = syn.get(p_file[1])
                
            except:
                obj = None
                files_read.append(
                        {'project_id' : project_id,
                         'file_id' : '_',
                         'file_path' : str(p_file),
                         'can_read' : False,
                         'reason' : 'Locked',
                         'sheet' : 'all'}
                        )
                continue
            ## read in the file
            df_dict = file_reader(obj)
            ## record cases where can't read in 
            if len(df_dict) < 1:
                files_read.append(
                        {'project_id' : project_id,
                         'file_id' : "_",
                         'file_path' : p_file,
                         'can_read' : False,
                         'reason' : 'Locked', 
                         'sheet' : 'all'}
                        )
            ## loop over dictionary of data frames
            for sheet in df_dict:
                df = df_dict[sheet]
                ## determine if the file was read in correctly 
                df_read, df = check_df_readable(df)
                reason = 'good' if df_read else 'look_into'
                ## adding to a list of what files can actually be read 
                files_read.append(
                        {'project_id' : project_id,
                         'file_id' : obj.id,
                         'file_path' : str(obj.path),
                         'can_read' : df_read,
                         'reason' : reason,
                         'sheet' : sheet}
                        )
                if df is not None:
                    base_cols = df.columns
                    ## ground data frame
                    entity_df = df.apply(apply_ground, axis = 1 )
                    entity_df, base_cols = filter_df(entity_df, base_cols)
                    file_nodes, file_relations = extract_df_graph(entity_df, base_cols, project_id)
                    ## add new nodes to overall graph 
                    nodes = nodes | file_nodes
                    relations = relations | file_relations
                    ## save cols for tractability
                    for col in base_cols:
                        entity_cols.append(
                                {'project_id' : project_id,
                                 'file_id' : obj.id,
                                 'file_path' : str(obj.path),
                                 'sheet' : sheet,
                                 'col' : col
                                 }
                                )

    
    nodes = [["curie:ID", ":LABEL"]] + list(nodes)
    relations = [[":START_ID", ":END_ID", ":TYPE"]] + list(relations)
    # # # Dump nodes into nodes.tsv and relations into edges.tsv
    with open("dglink/resources/pulled_nodes.tsv", "w") as f:
        for row in nodes:
            f.write("\t".join(row) + "\n")
    with open("dglink/resources/pulled_edges.tsv", "w") as f:
        for row in relations:
            f.write("\t".join(row) + "\n")

    ## write out the reports
    files_df = pandas.DataFrame(data = files_read)
    cols_df = pandas.DataFrame(data = entity_cols)
    files_df.to_csv('file_report.tsv' ,sep='\t', index=False)
    cols_df.to_csv('col_report.tsv' ,sep='\t', index = False)
    ## other stats 
    # total_counts = files_df.groupby("project_id")["file_path"].nunique()
    # read_counts = files_df[files_df['can_read']].groupby("project_id")["file_path"].nunique()

    # count_cols = cols_df.groupby(["project_id", "file_path", "sheet"])["col"].nunique()
    # count_files_with_cols = cols_df.groupby("project_id")["file_path"].nunique()
    
    

    
            
            
                
