from neo4j import GraphDatabase
import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class Neo4jService:
    def __init__(self):
        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USER")
        password = os.getenv("NEO4J_PASSWORD")

        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    #   cluster bằng graph (WCC)
    def get_clusters(self, place_ids):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (p:Place)
                WHERE p.id IN $ids

                CALL {
                    WITH p
                    MATCH (p)-[:NEAR*0..]->(connected)
                    WHERE connected.id IN $ids
                    RETURN collect(DISTINCT connected) AS cluster
                }

                RETURN cluster
                """,
                ids=place_ids
            )

            clusters = []
            for record in result:
                cluster_nodes = record["cluster"]
                cluster_ids = [node["id"] for node in cluster_nodes]
                clusters.append(cluster_ids)

            return clusters