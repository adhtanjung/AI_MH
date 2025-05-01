import os
import pandas as pd
import json
from openai import OpenAI
import chromadb
from dotenv import load_dotenv
import numpy as np
from pathlib import Path

# Load environment variables
load_dotenv()

def clean_nan(item):
    """Convert NaN values to empty strings for JSON serialization"""
    if isinstance(item, float) and np.isnan(item):
        return ""
    return item

def main():
    # Set up OpenAI client
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Get script directory and set up paths using Path for cross-platform compatibility
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    project_dir = script_dir.parent
    data_dir = project_dir / "app" / "data"
    chroma_db_dir = project_dir / "app" / "chroma_db"

    # Ensure directories exist
    data_dir.mkdir(exist_ok=True)
    chroma_db_dir.mkdir(exist_ok=True)

    # Read Excel data - using absolute path
    print("Reading Excel data...")
    excel_path = data_dir / "2. AI_MentalHealth_Data_Seed.xlsx"
    print(f"Looking for Excel file at: {excel_path}")

    try:
        df_problems = pd.read_excel(excel_path, sheet_name="1.1 Problems")
    except FileNotFoundError:
        print(f"Error: Excel file not found at {excel_path}")
        print("Please ensure the file exists in the correct location.")
        return

    # Clean NaN values
    df_problems = df_problems.fillna("")

    # Convert to JSON-like records
    problems = []
    for _, row in df_problems.iterrows():
        problem = {
            "problem_id": str(row["problem_id"]),
            "problem_name": row["problem_name"],
            "description": row["description"]
        }
        problems.append(problem)

    # Save as JSON to same directory as script
    json_path = script_dir  / "problems.json"
    with open(json_path, "w") as f:
        json.dump(problems, f, indent=2)

    print(f"Converted {len(problems)} problems to JSON. Saved to {json_path}")

    # Generate embeddings for each problem
    print("Generating embeddings...")
    embeddings = []
    documents = []
    ids = []
    metadatas = []

    for problem in problems:
        # Combine problem name and description for embedding
        text_to_embed = f"{problem['problem_name']} {problem['description']}"

        # Get embedding from OpenAI
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=text_to_embed
        )

        # Extract embedding from response
        embedding = response.data[0].embedding
        embeddings.append(embedding)

        # Store other data for ChromaDB
        documents.append(text_to_embed)
        ids.append(problem["problem_id"])
        metadatas.append({
            "problem_id": problem["problem_id"],
            "problem_name": problem["problem_name"]
        })

    # Set up ChromaDB using absolute path
    print("Setting up ChromaDB...")
    print(f"ChromaDB directory: {chroma_db_dir}")
    chroma_client = chromadb.PersistentClient(path=str(chroma_db_dir))

    # Create or get collection
    collection = chroma_client.get_or_create_collection(name="problems_collection")

    # Add documents with embeddings
    collection.add(
        embeddings=embeddings,
        documents=documents,
        ids=ids,
        metadatas=metadatas
    )

    print(f"Successfully added {len(problems)} problems to ChromaDB collection 'problems_collection'")

if __name__ == "__main__":
    main()