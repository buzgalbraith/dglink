import pandas
import re
from itertools import combinations
from graph_embedding import check_related_study_exists
RESOURCE_DIR = 'dglink/graph_embedding/resources/'
def get_projects_to_edges():
    """get mapping project_id -> entity -> edge_type, which is used for calculating jacquard sim"""
    all_project_ids = set(filter(lambda x:re.match(r'^syn\d*$',str(x)) is not None, edges_df[':START_ID'].unique())) | \
        set(filter(lambda x:re.match(r'^syn\d*$', str(x)) is not None, edges_df[':END_ID'].unique()))
    ## mapping project_id -> entity -> edge_type 
    project_to_edges_map = {
        project_id : dict() for project_id in all_project_ids
    }
    for project_id in all_project_ids:
        # get edges where that project (or its wiki ) is the hed node
        head_edges = edges_df.loc[edges_df[':START_ID'].isin([project_id, f'{project_id}:Wiki']), ]
        for x, _ in head_edges.groupby(by=[':END_ID', ':TYPE']).first().itertuples():
            if x[0] not in project_to_edges_map[project_id]:
                project_to_edges_map[project_id][x[0]] = set()
            project_to_edges_map[project_id][x[0]].add(x[1])
        # get edges where that project (or its wiki) is the tail node
        tail_edges = edges_df.loc[edges_df[':END_ID'].isin([project_id, f'{project_id}:Wiki']), ]
        for x, _ in tail_edges.groupby(by=[':START_ID', ':TYPE']).first().itertuples():
            if x[0] not in project_to_edges_map[project_id]:
                project_to_edges_map[project_id][x[0]] = set()
            project_to_edges_map[project_id][x[0]].add(x[1])
    return project_to_edges_map, all_project_ids

def get_edge_weights():
    ## get a dictionary weight mapping for each edge type
    edge_weights = {
        e_type:1 for e_type in  edges_df[':TYPE'].unique()
    }
    ## for now just up re-weighting a few node-types
    edge_weights['mentions'] = 0.5
    edge_weights['has_fundingAgency'] = 2
    edge_weights['has_institutions'] = 2
    edge_weights['has_diseaseFocus'] = 2
    edge_weights['has_manifestation'] = 2
    edge_weights['has_initiative'] = 3
    edge_weights['usesTool'] = 3
    return edge_weights

def jacquard_sim(pid_1, pid_2):
    intersection_score = 0
    union_score = 0
    all_entities_combined = set(project_to_edges_map[pid_1].keys()) | set(project_to_edges_map[pid_2].keys())
    for entity in all_entities_combined:
        types_1 = project_to_edges_map[pid_1].get(entity, set())
        types_2 = project_to_edges_map[pid_2].get(entity, set())
        
        # Sum weights for intersection 
        for edge_type in (types_1 & types_2):
            intersection_score += edge_weights.get(edge_type, 1)
        
        # Sum weights for union
        for edge_type in (types_1 | types_2):
            union_score += edge_weights.get(edge_type, 1)
    return intersection_score / union_score if union_score > 0 else 0

if __name__ == "__main__":
    edges_df = pandas.read_csv(
    f'{RESOURCE_DIR}/non_related_projects_edges.tsv',
    sep='\t'
    )
    project_to_edges_map, all_project_ids = get_projects_to_edges()
    edge_weights = get_edge_weights()
    res = []
    related_project_edges_df = pandas.read_csv(f"{RESOURCE_DIR}/related_project_edges.tsv", sep="\t")
    for pid_1, pid_2 in combinations(all_project_ids, 2):
        jacquard_score = jacquard_sim(pid_1=pid_1, pid_2=pid_2)
        has_related_study = check_related_study_exists(related_project_edges_df, pid_1, pid_2)
        res.append(
            {
                'id1' : pid_1,
                'id2' : pid_2,
                'entity_id1' : len(project_to_edges_map[pid_1]),
                'entity_id2' : len(project_to_edges_map[pid_2]),               
                'jacquard_score': jacquard_score, 
                'has_related_study' : has_related_study,
            }
        )

    df = pandas.DataFrame.from_records(res)
    df.sort_values(by=['jacquard_score'])
    n = 5
    df[(df['entity_id2']>n) & (df['entity_id1']>n)].sort_values(by=['jacquard_score']).to_csv('jac.csv')
    df.sort_values(by=['has_related_study', 'jacquard_score']).to_csv('jac.csv')

