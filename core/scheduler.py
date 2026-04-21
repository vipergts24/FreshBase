"""
IntentScheduler: Dependency-Aware Intent Classification.

Analyzes pending intents to determine which can safely execute in parallel
and which must run sequentially due to shared file dependencies.

Tier 1: Vector Store file overlap detection (free, local math).
Tier 2: LLM semantic classification for ambiguous intents (cheap fallback).
"""

from db.vector_store import search_code
from litellm import completion
from core.config import get_global_model
from rich.console import Console

console = Console()


class IntentScheduler:
    """
    Classifies a list of intents into execution groups.
    Each group is a sequential chain (intents within share dependencies).
    Different groups can safely execute in parallel.
    """

    def classify(self, intents, tracker=None) -> list[list]:
        """
        Takes a list of Intent ORM objects and returns execution groups.

        Returns:
            list[list[Intent]]: Groups of intents. Each group runs sequentially.
            Different groups run in parallel.
        """
        if len(intents) <= 1:
            return [intents]

        # Tier 1: Vector Store file overlap detection
        intent_files = {}
        ambiguous_intents = []

        for intent in intents:
            file_hits = self._get_relevant_files(intent.description, tracker)
            if file_hits:
                intent_files[intent.id] = file_hits
            else:
                ambiguous_intents.append(intent)

        # Tier 2: LLM classification for ambiguous intents
        if ambiguous_intents and intent_files:
            llm_classifications = self._llm_classify(
                ambiguous_intents, intents, intent_files, tracker
            )
            for intent_id, files in llm_classifications.items():
                intent_files[intent_id] = files

        # Build dependency graph from file overlaps
        groups = self._build_groups(intents, intent_files)

        console.print(
            f"[bold cyan]Scheduler: {len(intents)} intents classified into "
            f"{len(groups)} execution group(s).[/bold cyan]"
        )
        for i, group in enumerate(groups):
            ids = [str(intent.id) for intent in group]
            console.print(f"  Group {i + 1}: Intent(s) {', '.join(ids)}")

        return groups

    def _get_relevant_files(self, description: str, tracker=None) -> set[str]:
        """
        Query the vector store to find which files are semantically
        related to this intent description. Returns a set of file paths.
        """
        results = search_code(description, limit=3)
        file_paths = set()
        for result in results:
            path = result.get("file_path", "")
            if path:
                file_paths.add(path)

        # Track embedding API usage
        if tracker:
            # Estimate ~15 tokens per intent description for ada-002
            est_tokens = max(len(description.split()) * 2, 15)
            tracker.record_embedding("text-embedding-ada-002", est_tokens)

        return file_paths

    def _llm_classify(
        self, ambiguous, all_intents, known_files, tracker=None
    ) -> dict[int, set[str]]:
        """
        For intents where the vector store returned no file matches,
        ask the LLM to predict which files they will likely modify.
        """
        known_summary = ""
        for intent_id, files in known_files.items():
            known_summary += f"  Intent {intent_id}: {', '.join(files)}\n"

        ambiguous_summary = ""
        for intent in ambiguous:
            ambiguous_summary += f"  Intent {intent.id}: {intent.description}\n"

        prompt = (
            "You are a dependency classifier for a code orchestration system.\n\n"
            "The following intents have been matched to files:\n"
            f"{known_summary}\n"
            "The following intents could NOT be matched to specific files:\n"
            f"{ambiguous_summary}\n"
            "For each unmatched intent, predict which file(s) it will likely "
            "create or modify. Respond in this exact format, one per line:\n"
            "INTENT_ID: file1.py, file2.py\n"
            "If an intent is truly independent, respond with:\n"
            "INTENT_ID: INDEPENDENT\n"
        )

        try:
            model = get_global_model()
            response = completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            raw = response.choices[0].message.content

            # Track LLM usage for classification
            if tracker:
                tracker.record_llm(model, response)

            classifications = {}
            for line in raw.strip().split("\n"):
                if ":" not in line:
                    continue
                parts = line.split(":", 1)
                try:
                    intent_id = int(parts[0].strip())
                except ValueError:
                    continue

                files_str = parts[1].strip()
                if files_str.upper() == "INDEPENDENT":
                    classifications[intent_id] = set()
                else:
                    files = {f.strip() for f in files_str.split(",") if f.strip()}
                    classifications[intent_id] = files

            return classifications
        except Exception as e:
            console.print(
                f"[dim]Scheduler LLM classification failed: {e}. "
                f"Treating ambiguous intents as independent.[/dim]"
            )
            return {intent.id: set() for intent in ambiguous}

    def _build_groups(self, intents, intent_files) -> list[list]:
        """
        Build execution groups using Union-Find on file overlaps.
        Intents sharing any file end up in the same sequential group.
        """
        # Map each intent to a group leader using union-find
        parent = {intent.id: intent.id for intent in intents}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            root_a, root_b = find(a), find(b)
            if root_a != root_b:
                parent[root_b] = root_a

        # Build file-to-intent reverse index
        file_to_intents = {}
        for intent_id, files in intent_files.items():
            for filepath in files:
                if filepath not in file_to_intents:
                    file_to_intents[filepath] = []
                file_to_intents[filepath].append(intent_id)

        # Union intents that share any file
        for filepath, intent_ids in file_to_intents.items():
            for i in range(1, len(intent_ids)):
                union(intent_ids[0], intent_ids[i])

        # Collect groups preserving original queue order
        intent_map = {intent.id: intent for intent in intents}
        group_map = {}
        for intent in intents:
            root = find(intent.id)
            if root not in group_map:
                group_map[root] = []
            group_map[root].append(intent)

        return list(group_map.values())
