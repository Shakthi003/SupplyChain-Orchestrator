from dotenv import load_dotenv
import os
load_dotenv()

from neo4j import GraphDatabase

uri = os.getenv("NEO4J_URI")
user = os.getenv("NEO4J_USER")
password = os.getenv("NEO4J_PASSWORD")

try:
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    with driver.session() as session:
        result = session.run("RETURN 'Neo4j is connected and working!' AS msg")
        print(result.single()["msg"])
    driver.close()
    print("Neo4j API: OK")
except Exception as e:
    print(f"ERROR: {e}")
