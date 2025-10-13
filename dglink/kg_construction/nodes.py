import os
import pandas

ENTITY_ATTRIBUTES = [
    "curie:ID",
    ":LABEL",
    "grounded_entity_name",
    "raw_texts:string[]",
    "columns:string[]",
    "iri",
    "file_id:string[]",
]
PROJECT_ATTRIBUTES = ["curie:ID", ":LABEL"]


class Node:
    def __init__(self, attribute_names: list = None, attributes: dict = None):
        if attribute_names is not None:
            self.attribute_names = attribute_names
            self.attributes = {attribute: "" for attribute in self.attribute_names}
            if attributes is not None:
                for i, attribute in enumerate(self.attribute_names):
                    if type(attributes) == dict:
                        if attribute in attributes:
                            self.attributes[attribute] = attributes[attribute]
                        else:
                            self.attributes[attribute] = ""
                    else:
                        self.attributes[attribute] = attributes[i]
        elif attributes is not None:
            self.attributes = attributes
            self.attribute_names = [attribute for attribute in self.attributes]
        else:
            self.attribute_names = []
            self.attributes = {}

    def __getitem__(self, key: str):
        return self.attributes[key]

    def __setitem__(self, key, value):
        self.attributes[key] = value

    def __delitem__(self, key):
        del self.attributes[key]

    def __len__(self):
        return len(self.attribute_names)

    def __str__(self):
        return str(self.attributes)

    def get_attribute_names(self):
        print(", ".join(self.attribute_names))


class NodeSet:
    def __init__(
        self, node_set_name: str = "", node_type: str = "", attributes: list = []
    ):
        self.node_set_name = node_set_name
        self.path = ""
        self.nodes = dict()
        self.node_type = node_type
        self.attributes = attributes

    def __getitem__(self, key: str):
        return self.nodes[key]

    def __len__(self):
        return len(self.nodes)

    def __str__(self):
        rep = ""
        for node in self.nodes:
            rep += f"{node}:{str(self.nodes[node])}\n"
        return rep

    def update_nodes(self, new_node, new_node_id):
        self.set_attributes = [x for x in self.attributes if "string[]" in x]
        if new_node_id in self.nodes:
            for attribute in self.set_attributes:
                if new_node[attribute].replace('"', "").replace("'", "") != "":
                    self.nodes[new_node_id][attribute].add(new_node[attribute])
        else:
            self.nodes[new_node_id] = dict()
            for attribute in self.attributes:
                if attribute not in self.set_attributes:
                    self.nodes[new_node_id][attribute] = new_node[attribute]
                else:
                    if new_node[attribute] != "":
                        self.nodes[new_node_id][attribute] = set([new_node[attribute]])
                    else:
                        self.nodes[new_node_id][attribute] = set()

    def load_node_set(self, path):
        self.path = path
        if os.path.exists(self.path):
            df = pandas.read_csv(self.path, sep="\t", index_col=False)
            df = df.fillna(value="")
            # df = df.set_index(self.attributes[0])
            if len(self.attributes) == 0:
                self.attributes = df.columns
            # set index as first col assuming that is the id
            for _, row in df.iterrows():
                curie = row.iloc[0]
                self.nodes[curie] = Node(attribute_names=self.attributes)
                for i, attribute in enumerate(self.attributes):
                    val = row.iloc[i]
                    if ":string[]" in attribute:
                        val = set(str(val).replace('"', "").replace("'", "").split(";"))
                    self.nodes[curie][attribute] = val

    def write_node_set(self, path):
        with open(path, "w") as f:
            f.write("\t".join(self.attributes) + "\n")
            for curie in self.nodes:
                write_str = f""
                for col in self.attributes:
                    val = self.nodes[curie][col]
                    if type(val) == set:
                        if len(val) > 20:
                            val = list(val)[:20]  ## limit max number of elements to 20
                        val = f'"{";".join(val)}"'
                    ## take out any weird line breaks

                    write_str += val.replace("\n", "") + "\t"
                f.write(write_str[:-1] + "\n")
