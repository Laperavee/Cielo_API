import networkx as nx
import matplotlib.pyplot as plt
import random


def create_tree_graph():
    # Initialisation du graphe
    G = nx.Graph()

    # Création du noyau central (n0)
    G.add_node("n0")

    # Création des 5 nœuds de premier niveau (n1)
    for i in range(1, 6):
        n1 = f"n1_{i}"
        G.add_node(n1)
        G.add_edge("n0", n1)  # Liaison avec le noyau central

        # Création des 2 nœuds de second niveau (n2) pour chaque n1
        for j in range(1, 3):
            n2 = f"n2_{i}_{j}"
            G.add_node(n2)
            G.add_edge(n1, n2)  # Liaison avec le nœud de premier niveau

    return G


def visualize_graph(G):
    # Mise en page pour la visualisation
    pos = nx.spring_layout(G)

    # Couleurs des nœuds
    node_colors = []
    for node in G.nodes:
        if node == "n0":
            node_colors.append("red")  # Noyau central
        elif node.startswith("n1"):
            node_colors.append("blue")  # Niveaux n1
        else:
            node_colors.append("green")  # Niveaux n2

    # Dessin du graphe
    plt.figure(figsize=(10, 10))
    nx.draw(
        G,
        pos,
        with_labels=True,
        node_size=800,
        node_color=node_colors,
        font_size=10,
        font_weight="bold",
        edge_color="gray",
    )
    plt.title("Structure du graphe en arbre")
    plt.show()


if __name__ == "__main__":
    # Créer le graphe
    graph = create_tree_graph()

    # Visualiser le graphe
    visualize_graph(graph)
