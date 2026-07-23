import torch
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv
import re

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
)
import re

def parse_price_range(price_range):
    if not price_range:
        return 0, 0

    try:
        price_range = price_range.lower().replace(" ", "")
 
        match = re.findall(r'\d+', price_range)

        if len(match) >= 2:
            min_price = int(match[0])
            max_price = int(match[1])
 
            if "k" in price_range:
                min_price *= 1000
                max_price *= 1000

            return min_price, max_price

        elif len(match) == 1:
            price = int(match[0])
            if "k" in price_range:
                price *= 1000
            return price, price

    except:
        pass

    return 0, 0

def export_graph():
    with driver.session() as session:
 
        node_result = session.run("""
            MATCH (p:Place)
            OPTIONAL MATCH (p)-[:HAS_VIBE]->(v)
            OPTIONAL MATCH (p)-[:HAS_TYPE]->(t)

            RETURN p.id AS id,
                   p.name AS name,
                   p.lat AS lat,
                   p.lng AS lng,
                   p.rating AS rating,
                   p.review_count AS review_count,
                   p.price_range AS price_range,
                   p.description AS description,
                   collect(DISTINCT v.name) AS vibes,
                   collect(DISTINCT t.name) AS types
        """)

        nodes = []
        for record in node_result:
            price_min, price_max = parse_price_range(record["price_range"]) 
            nodes.append({
                "PlaceId": record["id"],
                "Name": record["name"],
                "Lat": record["lat"],
                "Lng": record["lng"],
                "RatingScore": record["rating"],
                "ReviewCount": record["review_count"],
                "PriceMin": price_min,
                "PriceMax": price_max,
                "Generated_Description": record["description"],
                "VibeTag": record["vibes"],
                "Type": record["types"]
            })
 
        edge_result = session.run("""
            MATCH (a:Place)-[r:NEAR]->(b:Place)
            RETURN a.id AS src,
                   b.id AS dst,
                   r.distance AS distance
        """)

        edges = [dict(record) for record in edge_result]

        graph_data = {
            "nodes": nodes,
            "edges": edges
        }

        torch.save(graph_data, "graph.pt") 


if __name__ == "__main__":
    export_graph()
    driver.close()