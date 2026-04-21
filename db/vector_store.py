import os
import lancedb
import pyarrow as pa

VECTOR_DB_DIR = ".fresh/lancedb"


def get_vector_db():
    if not os.path.exists(".fresh"):
        os.makedirs(".fresh")
    return lancedb.connect(VECTOR_DB_DIR)


def get_or_create_table(recreate=False):
    db = get_vector_db()

    if recreate and "code_chunks" in db.table_names():
        db.drop_table("code_chunks")

    schema = pa.schema(
        [
            pa.field(
                "vector", pa.list_(pa.float32(), 1536)
            ),  # OpenAI standard dimension
            pa.field("id", pa.string()),
            pa.field("file_path", pa.string()),
            pa.field("text", pa.string()),
        ]
    )

    if "code_chunks" in db.table_names():
        return db.open_table("code_chunks")
    else:
        return db.create_table("code_chunks", schema=schema)


from litellm import embedding


def search_code(query: str, limit: int = 5):
    """
    Embeds the user's english intent and performs a similarity search
    against the codebase LanceDB index.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        return []

    db = get_vector_db()
    if "code_chunks" not in db.table_names():
        return []

    table = db.open_table("code_chunks")

    try:
        response = embedding(model="text-embedding-ada-002", input=[query])
        query_vector = response["data"][0]["embedding"]

        # LanceDB vector search returns a list of dictionaries
        results = table.search(query_vector).limit(limit).to_list()
        return results
    except Exception as e:
        print(f"Vector search failed: {e}")
        return []
