"""
Reads in existing graph from `dglink/resources/` merges the edges into a combined df then saves one tsv with only the related project edges and another with out them (for training the model)
"""
import pandas 
import os 
import subprocess
from shlex import split

resource_dir = 'dglink'
save_dir = 'dglink/graph_embedding/resources'

if __name__ == "__main__":
    ## make a directory to store the results and copy all existing edges
    os.makedirs(save_dir, exist_ok=True)
    cmd = f'cp -r {resource_dir}/*edges*.tsv {save_dir}'
    subprocess.run(cmd, shell=True)

    ## merges all edges into one df 
    frames = [] 
    for frame in map(lambda x: f'{save_dir}/{x}',filter(lambda x: 'edges' in x ,os.listdir(save_dir))):
        frames.append(pandas.read_csv(frame, sep='\t'))
    df = pandas.concat(frames)
    ## remove the original files to avoid confusion
    cmd = f'rm {save_dir}/*'
    subprocess.run(cmd, shell=True)
    ## make to tsv files one with all edges that are not on related projects another with only related project edges
    related_edges = df[df[':TYPE']=='has_relatedStudies']
    non_related_edges = df[df[':TYPE']!='has_relatedStudies']
    related_edges.to_csv(f'{save_dir}/related_project_edges.tsv',sep='\t', index=False)
    non_related_edges.to_csv(f'{save_dir}/non_related_projects_edges.tsv',sep='\t', index=False)