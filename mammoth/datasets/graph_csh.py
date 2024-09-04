from mammoth.datasets.dataset import Dataset
import networkx as nx


class Graph_CSH(Dataset):
    def __init__(self, nodes_list, edges_list, attributes_list):
        self.nodes_list = nodes_list
        self.edges_list = edges_list
        self.attributes_list = attributes_list
        self.G = None

    def create_graph(self):
        self.G = nx.DiGraph()
        nodes_for_graph = [(int(i),{attribute:self.nodes_list.loc[i,attribute] for attribute in self.attributes_list}) for i in self.nodes_list.index]
        edges_for_graph = [(int(self.edges_list.iloc[i,0]),int(self.edges_list.iloc[i,1])) for i in range(self.edges_list.shape[0])]
        self.G.add_nodes_from(nodes_for_graph)
        self.G.add_edges_from(edges_for_graph)

    def return_num_nodes(self):
        return self.nodes_list.shape[0]
    
    def return_num_edges(self):
        return self.edges_list.shape[0]