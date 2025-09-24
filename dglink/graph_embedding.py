"""
goal is to train an embedding model and use that as a proxy for related study prediction.

going to w
"""

from pykeen.triples import TriplesFactory
from pykeen.pipeline import pipeline
import torch
import numpy as np
from itertools import combinations
import gzip
import torch


all_project_ids = [
    "syn2343195",  ## large project
    "syn5562324",  ## small project
    "syn27761862",  ## small project
    "syn4939874",  ## large project
    # "syn4939876",  ## locked
    "syn4939906",  ## small
    # "syn4939916",  ## locked
    "syn7217928",  ## large
    "syn8016635",  ## small
    # "syn11638893",  ## locked
    "syn11817821",  ## large
    # "syn21641813",  ## locked
    # "syn21642027",  ## locked
    "syn21650493",  ## large
    "syn21984813",  ## large
    # "syn23639889",  ## locked
    # "syn51133914",  ## locked
    "syn52740594",  ## large
]


def train_embedding_model(
    edge_path="dglink/resources/edges.tsv",
    model_name="TransE",
    epochs=20,
    save=True,
    save_path="dglink/resources/embedding_test",
):
    """Trains a network embedding model with the PyKEEN pipeline. Return the model and entity_to_id mapping"""
    ## split the dataset
    tf = TriplesFactory.from_path(edge_path)
    training, testing = tf.split()
    training, testing, validation = tf.split([0.8, 0.1, 0.1])

    ## train the model
    result = pipeline(
        training=training,
        testing=testing,
        validation=validation,
        model=model_name,
        stopper="early",
        epochs=epochs,
    )
    if save:
        result.save_to_directory(save_path)
    return result.model, result.training.entity_to_id


def load_entity_to_id(save_path="dglink/resources/embedding_test"):
    """reads in entity to id mapping as dictionary"""
    id_path = f"{save_path}/training_triples/entity_to_id.tsv.gz"
    entity_to_id = {}
    with gzip.open(id_path, "rt", encoding="utf-8") as f:
        for line in f.readlines()[1:]:
            id, term = line.strip().split("\t")
            entity_to_id[term] = int(id)
    return entity_to_id


def load_embedding_model(save_path="dglink/resources/embedding_test"):
    """loads embedding model and entity_to_id mapping"""
    model = torch.load(f"{save_path}/trained_model.pkl", weights_only=False)
    entity_to_id = load_entity_to_id(save_path=save_path)
    return model, entity_to_id


def id_to_embedding(entity_to_id, model, id_1, id_2):
    """Get a numpy vector of entity embeddings for two given ids."""

    entity_ids = [entity_to_id[id_1], entity_to_id[id_2]]
    entity_embeddings = model.entity_representations[0]
    return entity_embeddings(indices=torch.as_tensor(entity_ids)).detach().cpu().numpy()


def l2(a, b):
    """simple l2 distance metric"""
    res = np.sum((a - b) ** 2)
    return np.sqrt(res)


if __name__ == "__main__":
    train = False
    if train:
        model, entity_to_id = train_embedding_model(
            edge_path="dglink/resources/pulled_edges_whole.tsv",
            model_name="TransE",
            epochs=20,
        )
    else:
        model, entity_to_id = load_embedding_model(
            save_path="dglink/resources/embedding_test"
        )
    for id_1, id_2 in combinations(all_project_ids, 2):
        embed_1, embed_2 = id_to_embedding(
            entity_to_id=entity_to_id, model=model, id_1=id_1, id_2=id_2
        )
        distance = l2(embed_1, embed_2)
        print(f"distance between projects {id_1} and {id_2} is {distance}")
