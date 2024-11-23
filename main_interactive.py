import requests
import networkx as nx
import plotly.graph_objects as go
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
        print(f"Connexions pour {wallet}: {data}")
        return data.get("data", {}).get("items", [])
    except Exception as e:
        print(f"Erreur réseau: {e}")
        return []


def filter_main_wallet(level_wallets, main_wallet):
    return [wallet for wallet in level_wallets if wallet["wallet"].lower() != main_wallet.lower()]


def build_wallet_tree(wallet):
    G = nx.Graph()
    G.add_node(wallet)
    print(f"Ajout du wallet principal : {wallet}")

    level1_wallets = fetch_wallet_data(wallet)
    level1_wallets = filter_main_wallet(level1_wallets, wallet)

    for rel in level1_wallets[:7]:
        wallet_n1 = rel["wallet"]
        inflow_n1 = rel["inflow"]
        outflow_n1 = rel["outflow"]
        G.add_node(wallet_n1)
        G.add_edge(wallet, wallet_n1, inflow=inflow_n1, outflow=outflow_n1)
        print(f"Ajout du wallet de niveau 1 : {wallet_n1} et connexion avec {wallet}")

        level2_wallets = fetch_wallet_data(wallet_n1)
        level2_wallets = filter_main_wallet(level2_wallets, wallet)

        for rel2 in level2_wallets[:7]:
            wallet_n2 = rel2["wallet"]
            if wallet_n2 == wallet or wallet_n2 == wallet_n1:
                continue
            inflow_n2 = rel2["inflow"]
            outflow_n2 = rel2["outflow"]
            G.add_node(wallet_n2)
            G.add_edge(wallet_n1, wallet_n2, inflow=inflow_n2, outflow=outflow_n2)
            print(f"Ajout du wallet de niveau 2 : {wallet_n2} et connexion avec {wallet_n1}")

    return G


def visualize_wallet_tree(G, main_wallet):
    G.remove_edges_from(nx.selfloop_edges(G))
    isolated_nodes = list(nx.isolates(G))
    if isolated_nodes:
        G.remove_nodes_from(isolated_nodes)

    if main_wallet not in G:
        print(f"Erreur : le portefeuille principal {main_wallet} n'existe pas dans le graphe.")
        return

    pos = nx.spring_layout(G, k=0.3, iterations=100)

    max_size = 50
    min_size = 10
    node_sizes = [
        max(min_size, min(max_size, 800 * (G.degree(node) / 2))) for node in G.nodes
    ]

    node_colors = [
        "red" if node == main_wallet else "blue" if main_wallet in G.neighbors(node) else "green"
        for node in G.nodes
    ]

    labels = {
        node: node[:6] + "..." + node[-4:] if node != main_wallet else "Main Wallet"
        for node in G.nodes
    }

    # Texte de survol pour les nœuds
    hover_text = {}
    for node in G.nodes:
        if node == main_wallet:
            hover_text[node] = f"{node}: Main Wallet"
        else:
            total_in = sum(G[u][v]["inflow"] for u in G.neighbors(node) if u != node)
            total_out = sum(G[u][v]["outflow"] for u in G.neighbors(node) if u != node)
            hover_text[node] = f"Address: {node}\nTotal In: {total_in}\nTotal Out: {total_out}"

    # Texte de survol pour les arêtes
    edge_x = []
    edge_y = []
    edge_text = []
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.append(x0)
        edge_x.append(x1)
        edge_y.append(y0)
        edge_y.append(y1)

        inflow = G[edge[0]][edge[1]].get("inflow", 0)
        outflow = G[edge[0]][edge[1]].get("outflow", 0)
        edge_text.append(f"Inflow: {inflow}\nOutflow: {outflow}")

    node_x = []
    node_y = []
    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)

    trace_edges = go.Scatter(
        x=edge_x,
        y=edge_y,
        line=dict(width=0.5, color='gray'),
        hoverinfo='text',
        mode='lines',
        text=edge_text
    )

    trace_nodes = go.Scatter(
        x=node_x,
        y=node_y,
        mode='markers+text',
        hoverinfo='text',
        marker=dict(
            showscale=True,
            colorscale='YlGnBu',
            size=node_sizes,
            color=node_colors,
            line_width=2
        ),
        text=[labels[node] for node in G.nodes()],
        textposition="top center"
    )

    layout = go.Layout(
        title=f"Wallet Network of {main_wallet}",
        showlegend=False,
        hovermode='closest',
        margin=dict(b=0, t=0, l=0, r=0),
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(showgrid=False, zeroline=False)
    )

    fig = go.Figure(data=[trace_edges, trace_nodes], layout=layout)
    fig.show()


if __name__ == "__main__":
    load_bearer_token()
    main_wallet = input("Wallet to explore : ")
    wallet_graph = build_wallet_tree(main_wallet)
