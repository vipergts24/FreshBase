
import unittest
from unittest.mock import patch
from core.git_utils import is_git_repo

class TestGitUtils(unittest.TestCase):
    
    @patch('core.git_utils.run_git_command')
    def test_is_git_repo(self, mock_run_git_command):
        # Mocking the run_git_command to return a success code 0
        mock_run_git_command.return_value = (0, '', '')
        
        # Since the mock simulates a git repo, is_git_repo should return True
        result = is_git_repo()
        
        # Assertion
        self.assertTrue(result)

if __name__ == '__main__':
    unittest.main()
