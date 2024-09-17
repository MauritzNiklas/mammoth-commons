from mammoth.datasets.dataset import Dataset


class Graph_CSH(Dataset):
    def __init__(self, nodes_df, edges_df, attributes_list):
        import networkx as nx
        self.nodes_df = nodes_df
        self.edges_df = edges_df
        self.attributes_list = attributes_list
        self.G = None

    def create_graph(self):
        import networkx as nx
        self.G = nx.DiGraph()
        nodes_for_graph = [(int(i),{attribute:self.nodes_df.loc[i,attribute] for attribute in self.attributes_list}) for i in self.nodes_df.index]
        edges_for_graph = [(int(self.edges_df.iloc[i,0]),int(self.edges_df.iloc[i,1])) for i in range(self.edges_df.shape[0])]
        self.G.add_nodes_from(nodes_for_graph)
        self.G.add_edges_from(edges_for_graph)

    def return_num_nodes(self):
        return self.nodes_df.shape[0]
    
    def return_num_edges(self):
        return self.edges_df.shape[0]