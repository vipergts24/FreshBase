import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from core.agent import BuilderPod


def test_parallel_builder_pods():
    """
    Verifies that multiple BuilderPod instances running in parallel
    do not contaminate each other's directories due to os.chdir.
    """
    root1 = os.path.abspath("temp_root1")
    root2 = os.path.abspath("temp_root2")

    # Cleanup
    for r in [root1, root2]:
        if os.path.exists(r):
            shutil.rmtree(r)
        os.makedirs(r)

    try:

        def run_agent(root, filename, content):
            pod = BuilderPod(project_root=root, interactive=False)
            # Simulate a <FILE> response
            agent_output = f"<FILE><PATH>{filename}</PATH><CODE>{content}</CODE></FILE>"
            pod._apply_files(agent_output)

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(run_agent, root1, "file1.txt", "CONTENT1")
            f2 = executor.submit(run_agent, root2, "file2.txt", "CONTENT2")

            f1.result()
            f2.result()

        # Check results
        assert os.path.exists(os.path.join(root1, "file1.txt"))
        assert not os.path.exists(os.path.join(root1, "file2.txt"))

        assert os.path.exists(os.path.join(root2, "file2.txt"))
        assert not os.path.exists(os.path.join(root2, "file1.txt"))

        with open(os.path.join(root1, "file1.txt"), "r") as f:
            assert f.read() == "CONTENT1"

        with open(os.path.join(root2, "file2.txt"), "r") as f:
            assert f.read() == "CONTENT2"

    finally:
        # Cleanup
        for r in [root1, root2]:
            if os.path.exists(r):
                shutil.rmtree(r)


if __name__ == "__main__":
    test_parallel_builder_pods()
    print("Concurrency test PASSED")
