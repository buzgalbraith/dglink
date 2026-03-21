import os

# import pandas
import polars as pl


class Edge:
    def __init__(self, attribute_names: list, attributes: dict = None):
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
        self,
        attributes: list = [],
        edge_set_name: str = "",
        edge_type: str = "",
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

    def update_edges(self, new_edge: dict, new_edge_id=None):
        self.set_attributes = [x for x in self.attributes if "string[]" in x]
        new_edge_id_1 = new_edge_id or new_edge.get(":START_ID", "no_start")
        new_edge_id_2 = new_edge_id or new_edge.get(":END_ID", "no_end")
        new_edge_id_3 = new_edge_id or new_edge.get(":TYPE", "no_type")
        new_edge_id = f"{new_edge_id_1}_{new_edge_id_2}:{new_edge_id_3}" or new_edge_id
        if new_edge_id in self.edges:
            for attribute in self.set_attributes:
                attr_val = new_edge.get(attribute, "")
                if attribute not in self.set_attributes:
                    ## standardize empty data representation
                    if attr_val.replace('"', "").replace("'", "") != "":
                        self.edges[new_edge_id][attribute].add(attr_val)
                else:
                    attr_val = set([attr_val]) if type(attr_val) == str else attr_val
                    self.edges[new_edge_id][attribute] = self.edges[new_edge_id][
                        attribute
                    ].union(attr_val)
        else:
            self.edges[new_edge_id] = dict()
            for attribute in self.attributes:
                attr_val = new_edge.get(attribute, "")
                if attribute not in self.set_attributes:
                    self.edges[new_edge_id][attribute] = attr_val
                else:
                    if attr_val != "":
                        attr_val = (
                            set([attr_val]) if type(attr_val) == str else attr_val
                        )
                        self.edges[new_edge_id][attribute] = set(attr_val)
                    else:
                        self.edges[new_edge_id][attribute] = set()

    def load_edge_set(self, path):
        self.path = path
        if os.path.exists(self.path):
            df = pl.read_csv(self.path, separator="\t")
            df = df.fill_null("")

            if len(self.attributes) == 0:
                self.attributes = df.columns

            # Process rows efficiently with Polars
            for row in df.iter_rows(named=True):
                # curie = row[self.attributes[0]]
                new_edge_id_1 = row.get(":START_ID", "no_start")
                new_edge_id_2 = row.get(":END_ID", "no_end")
                new_edge_id_3 = row.get(":TYPE", "no_type")
                edge_id = f"{new_edge_id_1}_{new_edge_id_2}:{new_edge_id_3}"
                self.edges[edge_id] = dict()

                for attribute in self.attributes:
                    val = row.get(attribute, "")

                    if ":string[]" in attribute:
                        val = set(str(val).replace('"', "").replace("'", "").split(";"))

                    self.edges[edge_id][attribute] = val

    def write_edge_set(self, path, pascalify:bool = False):
        if pascalify:
            self.pascalify_edges()
        with open(path, "w") as f:
            f.write("\t".join(self.attributes) + "\n")
            for curie in self.edges:
                write_str = ""
                for col in self.attributes:
                    val = self.edges[curie][col]
                    if type(val) == set:
                        if len(val) > 20:
                            val = list(val)[:20] ## take max of 20 ## 
                        joined = ";".join(v for v in val if v)  
                        val = f'"{joined}"' if joined else ""
                    elif val is None or val == 'None':
                        val = ''
                    write_str += f"{val}".replace("\n", "") + "\t"
                write_str = write_str.replace('""', '')
                f.write(write_str[:-1] + "\n")   

    def pascalify_edges(self):
        pascalify = lambda x: "".join(w.capitalize() for w in x.replace("biolink:", "").split("_"))
        edges = {}
        for edge_id in self.edges:
            edge_rep = self.edges[edge_id]
            raw_label = edge_rep[':TYPE']
            edge_rep[':TYPE'] = pascalify(raw_label)
            edge_rep['raw_type'] = raw_label
            edges[edge_id] = edge_rep
        self.edges = edges