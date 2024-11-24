import requests
import networkx as nx
import matplotlib.pyplot as plt
import os
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from webdriver_manager.chrome import ChromeDriverManager

TOKEN_FILE_PATH = "bearer_token.json"
BEARER_TOKEN = None
HEADERS = {"Authorization": f"Bearer {BEARER_TOKEN}"}
EDGE_THRESHOLD = 50

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
                    print(BEARER_TOKEN)
    finally:
        driver.quit()

def fetch_wallet_data(wallet):
    url = f"https://feed-api.cielo.finance/v1/{wallet}/related-wallets"
    try:
        response = requests.get(url, headers=HEADERS)

        if response.status_code == 401:
            print("Token expiré. Renouvellement du token...")
            renew_bearer_token()
            response = requests.get(url, headers=HEADERS)
        if response.status_code != 200:
            print(f"Erreur: API {response.status_code}, {response.text}")
            return []
        data = response.json()
        return data.get("data", {}).get("items", [])
    except Exception as e:
        print(f"Erreur réseau: {e}")
        return []

def filter_main_wallet(level_wallets, main_wallet):
    return [wallet for wallet in level_wallets if wallet["wallet"].lower() != main_wallet.lower()]

def build_wallet_tree(wallet):
    G = nx.Graph()
    G.add_node(wallet)

    level1_wallets = fetch_wallet_data(wallet)
    level1_wallets = filter_main_wallet(level1_wallets, wallet)

    for rel in level1_wallets[:7]:
        wallet_n1 = rel["wallet"]
        G.add_node(wallet_n1)
        G.add_edge(wallet, wallet_n1, inflow=rel["inflow"], outflow=rel["outflow"])

        level2_wallets = fetch_wallet_data(wallet_n1)
        level2_wallets = filter_main_wallet(level2_wallets, wallet)

        for rel2 in level2_wallets[:7]:
            wallet_n2 = rel2["wallet"]
            if wallet_n2 == wallet or wallet_n2 == wallet_n1:
                continue
            G.add_node(wallet_n2)
            G.add_edge(wallet_n1, wallet_n2, inflow=rel2["inflow"], outflow=rel2["outflow"])

    return G

def visualize_wallet_tree(G, main_wallet):
    G.remove_edges_from(nx.selfloop_edges(G))
    isolated_nodes = list(nx.isolates(G))
    if isolated_nodes:
        G.remove_nodes_from(isolated_nodes)

    if main_wallet not in G:
        print(f"Erreur : le portefeuille principal {main_wallet} n'existe pas dans le graphe.")

    try:
        pos = nx.kamada_kawai_layout(G)
    except nx.NetworkXException:
        print("spring")
        pos = nx.spring_layout(G, k=0.8, iterations=200)
    node_sizes = [800 if node == main_wallet else 400 for node in G.nodes]
    node_colors = [
        "red" if node == main_wallet else "blue" if main_wallet in G.neighbors(node) else "green"
        for node in G.nodes
    ]

    labels = {
        node: node[:6] + "..." + node[-4:] if node != main_wallet else "Main Wallet"
        for node in G.nodes
    }

    edge_labels = {}
    for edge in G.edges(data=True):
        wallet1, wallet2, data = edge
        inflow = data.get("inflow", 0)
        outflow = data.get("outflow", 0)
        edge_labels[(wallet1, wallet2)] = f"Inflow: {round(inflow,2)}\nOutflow: {round(outflow,2)}"

    plt.figure(figsize=(30, 30))
    nx.draw(
        G,
        pos,
        with_labels=True,
        labels=labels,
        node_size=node_sizes,
        node_color=node_colors,
        edge_color="gray",
        font_size=10,
        font_weight="bold",
    )

    nx.draw_networkx_edge_labels(
        G,
        pos,
        edge_labels=edge_labels,
        font_size=8,
        font_weight="bold",
        verticalalignment="center",
        horizontalalignment="center",
    )

    plt.legend(
        handles=[
            plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="red", markersize=10, label="Main Wallet"),
            plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="blue", markersize=10, label="Level 1 Wallet"),
            plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="green", markersize=10, label="Level 2 Wallet"),
        ],
        loc="best",
    )
    plt.show()

if __name__ == "__main__":
    load_bearer_token()
    main_wallet = input("Wallet to explore : ")
    wallet_graph = build_wallet_tree(main_wallet)
    visualize_wallet_tree(wallet_graph, main_wallet)
