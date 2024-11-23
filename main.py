import requests
import networkx as nx
import matplotlib.pyplot as plt
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from webdriver_manager.chrome import ChromeDriverManager
import json

TOKEN_FILE_PATH = "bearer_token.json"
BEARER_TOKEN = None
HEADERS = {"Authorization": f"Bearer {BEARER_TOKEN}"}
EDGE_THRESHOLD = 50
MAX_RELATIONS = 8

user_home = os.path.expanduser("~")
chrome_profile_path = os.path.join(user_home, "AppData", "Local", "Google", "Chrome", "User Data")


def save_bearer_token(token):
    with open(TOKEN_FILE_PATH, 'w') as f:
        json.dump({"BEARER_TOKEN": token}, f)


def load_bearer_token():
    global BEARER_TOKEN
    if os.path.exists(TOKEN_FILE_PATH):
        with open(TOKEN_FILE_PATH, 'r') as f:
            data = json.load(f)
            BEARER_TOKEN = data.get("BEARER_TOKEN")
            HEADERS["Authorization"] = f"Bearer {BEARER_TOKEN}"
    return BEARER_TOKEN


def renew_bearer_token():
    global BEARER_TOKEN
    user_home = os.path.expanduser("~")
    chrome_profile_path = os.path.join(user_home, "AppData", "Local", "Google", "Chrome", "User Data")
    capabilities = DesiredCapabilities.CHROME
    capabilities["goog:loggingPrefs"] = {"performance": "ALL"}
    options = Options()
    options.add_argument(f"--user-data-dir={chrome_profile_path}")
    options.add_argument("--profile-directory=Default")
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )

    try:
        url = "https://app.cielo.finance/feed"
        driver.get(url)
        logs = driver.get_log("performance")

        for log in logs:
            message = json.loads(log["message"])
            params = message.get("message", {}).get("params", {})
            request = params.get("request", {})
            headers = request.get("headers", {})

            if "Authorization" in headers:
                bearer_token = headers["Authorization"]
                if bearer_token.startswith("Bearer "):
                    BEARER_TOKEN = bearer_token.split(' ')[1]
                    save_bearer_token(BEARER_TOKEN)
                    HEADERS["Authorization"] = f"Bearer {BEARER_TOKEN}"
                    return BEARER_TOKEN
    finally:
        driver.quit()


def fetch_wallet_data(wallet):
    url = f"https://feed-api.cielo.finance/v1/{wallet}/related-wallets"
    try:
        response = requests.get(url, headers=HEADERS)

        if response.status_code == 401:
            print("Token expiré. Renouvellement du token...")
            new_token = renew_bearer_token()
            if new_token:
                response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            if response.status_code == 400 and "unable to track wallet with high tx number" in response.text:
                print(
                    f"Erreur: Impossible de suivre le portefeuille {wallet} en raison d'un nombre trop élevé de transactions.")
                return []  # Retourne une liste vide si l'erreur spécifique est rencontrée
            print(f"Erreur: L'API a renvoyé le code de statut {response.status_code} pour le portefeuille {wallet}")
            print(f"Réponse: {response.text}")
            return []
        return response.json().get("data", {}).get('items', [])
    except requests.exceptions.RequestException as e:
        print(f"Erreur réseau lors de la récupération du portefeuille {wallet}: {e}")
        return []
    except ValueError as e:
        print(f"Erreur de décodage JSON pour le portefeuille {wallet}: {e}")
        print(f"Réponse: {response.text}")
        return []


def filter_and_aggregate_edges(wallet, items, max_relations):
    edges = []
    total_inflow = 0

    for relation in items:
        wallet2 = relation["wallet"]
        total_in = relation["inflow"]
        total_out = relation["outflow"]
        if total_in + total_out >= EDGE_THRESHOLD:
            edges.append((wallet, wallet2, {"total_in": total_in, "total_out": total_out}))
            total_inflow += total_in

    edges = sorted(edges, key=lambda x: x[2]["total_in"] + x[2]["total_out"], reverse=True)
    top_edges = edges[:max_relations - 1]
    last_inflow = sum(edge[2]["total_in"] for edge in edges[max_relations - 1:])
    last_outflow = sum(edge[2]["total_out"] for edge in edges[max_relations - 1:])

    if last_inflow + last_outflow > 0:
        top_edges.append((wallet, "last", {"total_in": last_inflow, "total_out": last_outflow}))

    return top_edges


def build_graph(edges):
    G = nx.Graph()
    for edge in edges:
        G.add_edge(edge[0], edge[1], **edge[2])
        G.nodes[edge[0]]["total"] = G.nodes.get(edge[0], {}).get("total", 0) + edge[2]["total_in"] + edge[2][
            "total_out"]
        G.nodes[edge[1]]["total"] = G.nodes.get(edge[1], {}).get("total", 0) + edge[2]["total_in"] + edge[2][
            "total_out"]
    return G


def visualize_graph(G, wallet):
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
    total_inflow = sum(data["total_in"] for _, _, data in G.edges(data=True))
    for node in G.nodes:
        if node == wallet:
            node_colors.append((1, 0.4, 0.4))
        elif node == "last":
            node_colors.append((0.7, 0.7, 0.7))
        else:
            total_in = sum([data["total_in"] for _, _, data in G.edges(node, data=True)])
            opacity = total_in / total_inflow if total_inflow > 0 else 0.1
            node_colors.append((1 - opacity, 1, 1 - opacity, 1))

    plt.figure(figsize=(30, 30))
    nx.draw_networkx_nodes(G, pos, node_size=node_sizes, node_color=node_colors, edgecolors="black")
    nx.draw_networkx_edges(G, pos, width=edge_widths, alpha=0.5, edge_color="gray")

    shortened_labels = {node: f"{node[:5]}...{node[-5:]}" if node != "last" else "Others" for node in G.nodes}
    nx.draw_networkx_labels(G, pos, labels=shortened_labels, font_size=12, font_color="black", font_weight="bold")

    edge_labels = {(u, v): f"{d['total_in']:.2f} | {d['total_out']:.2f}" for u, v, d in G.edges(data=True)}
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=10, label_pos=0.75)

    plt.axis("off")
    plt.show()


def recursive_analysis(wallet, depth=1, max_depth=3, G=None):
    if G is None:
        G = nx.Graph()
    if depth > max_depth:
        return
    items = fetch_wallet_data(wallet)
    top_edges = filter_and_aggregate_edges(wallet, items, MAX_RELATIONS)
    for edge in top_edges:
        G.add_edge(edge[0], edge[1], **edge[2])

    for _, neighbor, _ in top_edges[:-1]:
        if neighbor != wallet and not G.has_node(neighbor):
            recursive_analysis(neighbor, depth=depth + 1, max_depth=max_depth, G=G)
    return G

if __name__ == "__main__":
    load_bearer_token()
    main_wallet = input("In wallet : ")
    G = recursive_analysis(main_wallet, depth=1, max_depth=3)

    visualize_graph(G, main_wallet)


