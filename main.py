import requests
import networkx as nx
import matplotlib.pyplot as plt

bearer_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJhZGRyZXNzIjoiMHhhMGMzOGI3YzIzOWQ5ZGI3YmE1YTMwNzEzMjdiNzBlMzNlMWQ2ZWUyIiwiaXNzIjoiaHR0cHM6Ly9hcGkudW5pd2hhbGVzLmlvLyIsInN1YiI6InVzZXIiLCJwbGFuIjoiYmFzaWMiLCJiYWxhbmNlIjowLCJpYXQiOjE3MzIyMDA0MzMsImV4cCI6MTczMjIxMTIzM30.UNoMQRLDC6-5c9mFSFV82yUhBN7uRroV2ZjTmR9Fhho"
wallet = "0x9cb8d9bae84830b7f5f11ee5048c04a80b8514ba"
headers = {"Authorization": f"Bearer {bearer_token}"}

response = requests.get(f"https://feed-api.cielo.finance/v1/{wallet}/related-wallets", headers=headers)
try:
    items = response.json()["data"]['items']

    edges = []
    total_inflow = 0
    for relation in items:
        wallet2 = relation["wallet"]
        total_in = relation["inflow"]
        total_out = relation["outflow"]

        if total_in + total_out >= 50:
            edges.append((wallet, wallet2, {"total_in": total_in, "total_out": total_out}))
            total_inflow += total_in

    edges = sorted(edges, key=lambda x: x[2]["total_in"] + x[2]["total_out"], reverse=True)
    print(edges)
    top_edges = edges[:7]
    last_inflow = sum(edge[2]["total_in"] for edge in edges[7:])
    last_outflow = sum(edge[2]["total_out"] for edge in edges[7:])

    if last_inflow + last_outflow > 0:
        top_edges.append((wallet, "last", {"total_in": last_inflow, "total_out": last_outflow}))

    G = nx.Graph()
    for edge in top_edges:
        G.add_edge(edge[0], edge[1], **edge[2])
        G.nodes[edge[0]]["total"] = G.nodes.get(edge[0], {}).get("total", 0) + edge[2]["total_in"] + edge[2]["total_out"]
        G.nodes[edge[1]]["total"] = G.nodes.get(edge[1], {}).get("total", 0) + edge[2]["total_in"] + edge[2]["total_out"]

    pos = nx.kamada_kawai_layout(G, weight=None)

    max_node_size = 20000
    node_sizes = [
        G.nodes[node].get("total", 1) / max([G.nodes[n].get("total", 1) for n in G.nodes()]) * max_node_size
        for node in G.nodes()
    ]

    max_edge_weight = max((data["total_in"] + data["total_out"]) for _, _, data in G.edges(data=True))
    max_width = 15
    edge_widths = [
        (data["total_in"] + data["total_out"]) / max_edge_weight * max_width
        for _, _, data in G.edges(data=True)
    ]

    node_colors = []
    for node in G.nodes:
        if node == wallet:
            node_colors.append((1, 0.4, 0.4))
        elif node == "last":
            node_colors.append((0.7, 0.7, 0.7))
        else:
            total_in = sum([data["total_in"] for _, _, data in G.edges(node, data=True)])
            opacity = total_in / total_inflow if total_inflow > 0 else 0.1
            node_colors.append((1-opacity, 1, 1-opacity, 1))

    plt.figure(figsize=(30, 30))
    nx.draw_networkx_nodes(G, pos, node_size=node_sizes, node_color=node_colors, edgecolors="black")
    nx.draw_networkx_edges(G, pos, width=edge_widths, alpha=0.5, edge_color="gray")

    shortened_labels = {node: f"{node[:5]}...{node[-5:]}" if node != "last" else "Others" for node in G.nodes}
    nx.draw_networkx_labels(G, pos, labels=shortened_labels, font_size=12, font_color="black", font_weight="bold")

    edge_labels = {(u, v): f"{d['total_in']:.2f} | {d['total_out']:.2f}" for u, v, d in G.edges(data=True)}
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=10, label_pos=0.75)

    plt.axis("off")
    plt.show()
except:
    print("Not working")