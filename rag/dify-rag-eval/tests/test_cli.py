from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dify_rag_eval.cli import load_dotenv


class DotenvTests(unittest.TestCase):
    def test_loads_values_without_overriding_explicit_environment(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "TAAS_API_KEY=from-file\n"
                "export DIFY_API_BASE_URL='https://api.dify.ai/v1'\n",
                encoding="utf-8",
            )
            environ = {"TAAS_API_KEY": "from-shell"}

            load_dotenv(path, environ)

        self.assertEqual(environ["TAAS_API_KEY"], "from-shell")
        self.assertEqual(environ["DIFY_API_BASE_URL"], "https://api.dify.ai/v1")


if __name__ == "__main__":
    unittest.main()
