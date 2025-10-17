import os
import pandas
from dglink.core.constants import EDGE_ATTRIBUTES


class Edge:
    def __init__(self, attribute_names: list = EDGE_ATTRIBUTES, attributes: dict = None):
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


class EdgeSet:
    def __init__(
        self, edge_set_name: str = "", edge_type: str = "", attributes: list = EDGE_ATTRIBUTES
    ):
        self.edge_set_name = edge_set_name
        self.path = ""
        self.edges = dict()
        self.edge_type = edge_type
        self.attributes = attributes

    def __getitem__(self, key: str):
        return self.edges[key]

    def __len__(self):
        return len(self.edges)

    def __str__(self):
        rep = ""
        for edge in self.edges:
            rep += f"{edge}:{str(self.edges[edge])}\n"
        return rep

    def update_edges(self, new_edge:dict, new_edge_id = None):
        self.set_attributes = [x for x in self.attributes if "string[]" in x]
        new_edge_id_1 = new_edge_id or new_edge.get(':START_ID', 'no_start')
        new_edge_id_2 = new_edge_id or new_edge.get(':END_ID', 'no_end')
        new_edge_id_3 = new_edge_id or new_edge.get(':TYPE', 'no_type')
        new_edge_id = f'{new_edge_id_1}_{new_edge_id_2}:{new_edge_id_3}' or new_edge_id
        if new_edge_id in self.edges:
            for attribute in self.set_attributes:
                attr_val = new_edge.get(attribute, "")
                if attr_val.replace('"', "").replace("'", "") != "":
                    self.edges[new_edge_id][attribute].add(attr_val)
        else:
            self.edges[new_edge_id] = dict()
            for attribute in self.attributes:
                attr_val = new_edge.get(attribute, "")
                if attribute not in self.set_attributes:
                    self.edges[new_edge_id][attribute] = attr_val
                else:
                    if attr_val != "":
                        self.edges[new_edge_id][attribute] = set(attr_val)
                    else:
                        self.edges[new_edge_id][attribute] = set()

    def load_edge_set(self, path):
        self.path = path
        if os.path.exists(self.path):
            df = pandas.read_csv(self.path, sep="\t", index_col=False)
            df = df.fillna(value="")
            # df = df.set_index(self.attributes[0])
            if len(self.attributes) == 0:
                self.attributes = df.columns
            # set index as first col assuming that is the id
            for _, row in df.iterrows():
                head = row.iloc[0]
                tail = row.iloc[1]
                relation = row.iloc[2]
                edge_id = f'{head}_{tail}_{relation}'
                self.edges[edge_id] = Edge(attribute_names=self.attributes)
                for i, attribute in enumerate(self.attributes):
                    val = row.iloc[i]
                    if ":string[]" in attribute:
                        val = set(str(val).replace('"', "").replace("'", "").split(";"))
                    self.edges[edge_id][attribute] = val

    def write_edge_set(self, path):
        with open(path, "w") as f:
            f.write("\t".join(self.attributes) + "\n")
            for edge_id in self.edges:
                write_str = f""
                for col in self.attributes:
                    val = self.edges[edge_id][col]
                    if type(val) == set:
                        if len(val) > 20:
                            val = list(val)[:20]  ## limit max number of elements to 20
                        val = f'"{";".join(val)}"'
                    ## take out any weird line breaks

                    write_str += val.replace("\n", "") + "\t"
                f.write(write_str[:-1] + "\n")
