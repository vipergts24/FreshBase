import os
from litellm import embedding
from db.vector_store import get_or_create_table

def chunk_text(text: str, chunk_size=1000, overlap=100) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks

def index_repo():
    """
    Parses the repository, limits scan to text/code files, chunks them,
    and pushes their embeddings into LanceDB.
    """
    
    if not os.environ.get("OPENAI_API_KEY"):
        raise Exception("OPENAI_API_KEY environment variable is not set. Please export it to generate embeddings.")

    root_dir = os.getcwd()
    
    # Passing recreate=True for the MVP so running `fresh index` cleanly updates everything
    table = get_or_create_table(recreate=True)
    records_to_insert = []
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Ignore common hidden directories and environments
        dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in ('venv', '__pycache__', 'node_modules')]
        
        for file in filenames:
            # Focus on primarily code text formats for MVP
            if not file.endswith(('.py', '.md', '.json', '.txt', '.js', '.ts', '.html', '.css', '.toml')):
                continue
                
            file_path = os.path.join(dirpath, file)
            rel_path = os.path.relpath(file_path, root_dir)
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                continue
                
            chunks = chunk_text(content)
            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                    
                response = embedding(
                    model="text-embedding-ada-002", 
                    input=[chunk]
                )
                vector = response['data'][0]['embedding']
                
                records_to_insert.append({
                    "id": f"{rel_path}_{i}",
                    "file_path": rel_path,
                    "text": chunk,
                    "vector": vector
                })
    
    if records_to_insert:
        table.add(records_to_insert)
        return len(records_to_insert)
    return 0

def reindex_files(file_paths: list[str]):
    """
    Delta Sync: Flushes a specific set of modified files back into LanceDB,
    replacing their old vector embeddings.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        return
        
    table = get_or_create_table(recreate=False)
    root_dir = os.getcwd()
    records_to_insert = []
    
    for rel_path in file_paths:
        # 1. Delete old vectors for this specific file
        try:
            table.delete(f"file_path = '{rel_path}'")
        except Exception:
            pass
            
        full_path = os.path.join(root_dir, rel_path)
        if not os.path.exists(full_path):
            continue
            
        # 2. Re-chunk and embed the new file content
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            chunks = chunk_text(content)
            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                    
                response = embedding(
                    model="text-embedding-ada-002", 
                    input=[chunk]
                )
                vector = response['data'][0]['embedding']
                
                records_to_insert.append({
                    "id": f"{rel_path}_{i}",
                    "file_path": rel_path,
                    "text": chunk,
                    "vector": vector
                })
        except Exception as e:
            print(f"Vector Delta Sync failed for {rel_path}: {str(e)}")
            
    if records_to_insert:
        table.add(records_to_insert)
