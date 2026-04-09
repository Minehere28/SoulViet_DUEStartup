import torch
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
)
def export_graph():
    with driver.session() as session:
 
        node_result = session.run("""
            MATCH (p:Place)
            RETURN p.id AS id,
                   p.name AS name,
                   p.lat AS lat,
                   p.lng AS lng,
                   p.rating AS rating,
                   p.review_count AS review_count,
                   p.price_category AS price_category,
                   p.price_range AS price_range
        """)
        nodes = [dict(record) for record in node_result]
 
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