import os
import sys
import json
import pandas as pd
from neo4j import GraphDatabase
from dotenv import load_dotenv
from utils.distance import haversine
 
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
)

 
def safe_int(x):
    return int(x) if pd.notna(x) and str(x).strip() != "" else 0

def safe_float(x):
    return float(x) if pd.notna(x) and str(x).strip() != "" else 0.0

def safe_str(x):
    return str(x).strip() if pd.notna(x) else ""


def clean_json_field(value):
 
    if pd.isna(value) or value == "":
        return []

    try: 
        parsed = json.loads(value)
 
        if isinstance(parsed, str):
            parsed = json.loads(parsed)

        return parsed
    except:
        return []


def create_places(df):
    with driver.session(database=None) as session:
        for _, row in df.iterrows():

            activities = clean_json_field(row.get("Activities_JSON"))
            reviews = clean_json_field(row.get("TopReviews_JSON"))
            images = clean_json_field(row.get("LandImages_JSON"))

            session.run("""
                MERGE (p:Place {id: $id})
                SET p += $props
            """,
            id=safe_str(row.get("PlaceId")),
            props={
                "name": safe_str(row.get("Name")),
                "type": safe_str(row.get("Type")),
                "all_types": safe_str(row.get("AllTypes")),
                "address": safe_str(row.get("Address")),
                "lat": safe_float(row.get("Lat")),
                "lng": safe_float(row.get("Lng")),
                "rating": safe_float(row.get("RatingScore")),
                "review_count": safe_int(row.get("ReviewCount")),
                "operation_hours": safe_str(row.get("OperationHours")),
                "description": safe_str(row.get("Generated_Description") or row.get("Description")),
                "activities": activities,
                "reviews": reviews,
                "main_image": safe_str(row.get("MainImage")),
                "images": images,
                "price_category": safe_str(row.get("PriceCategory")),
                "price_range": safe_str(row.get("PriceRange")),
            })

 
def create_vibe(df):
    with driver.session(database=None) as session:
        for _, row in df.iterrows():
            vibe = row.get("VibeTag", "")

            if not vibe:
                continue

            session.run("""
                MERGE (v:Vibe {name: $vibe})
            """, vibe=vibe)

            session.run("""
                MATCH (p:Place {id: $id})
                MATCH (v:Vibe {name: $vibe})
                MERGE (p)-[:HAS_VIBE]->(v)
            """,
            id=row["PlaceId"],
            vibe=vibe)
 
def create_type(df):
    with driver.session(database=None) as session:
        for _, row in df.iterrows():
            types = str(row.get("Type", "")).split(",")

            for t in types:
                t = t.strip()
                if not t:
                    continue

                session.run("""
                    MERGE (t:Type {name: $type})
                """, type=t)

                session.run("""
                    MATCH (p:Place {id: $id})
                    MATCH (t:Type {name: $type})
                    MERGE (p)-[:HAS_TYPE]->(t)
                """,
                id=row["PlaceId"],
                type=t)
 
def create_near(df, threshold=2.0):
    places = df.to_dict("records")

    with driver.session(database=None) as session:
        for i in range(len(places)):
            for j in range(i + 1, len(places)):
                p1 = places[i]
                p2 = places[j]

                dist = haversine(
                    float(p1["Lat"]), float(p1["Lng"]),
                    float(p2["Lat"]), float(p2["Lng"])
                )

                if dist <= threshold:
                    dist = round(dist, 2)

                    session.run("""
                        MATCH (a:Place {id: $id1}), (b:Place {id: $id2})
                        MERGE (a)-[:NEAR {distance: $dist}]->(b)
                        MERGE (b)-[:NEAR {distance: $dist}]->(a)
                    """,
                    id1=p1["PlaceId"],
                    id2=p2["PlaceId"],
                    dist=dist)

 
if __name__ == "__main__":
    df = pd.read_csv("dataset/SoulViet_Dataset.csv")

    print("build graph")

    create_places(df)
    create_vibe(df)
    create_type(df)
    create_near(df)

    driver.close()

    print("done")