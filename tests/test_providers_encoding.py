"""Regressão da decodificação da saída de reg.exe na descoberta Epic."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src import providers


class EpicRegistryEncodingTests(unittest.TestCase):
    def test_epic_registry_output_uses_loss_tolerant_windows_encoding(self) -> None:
        expected = Path(r"C:\Epic\Crème")
        raw = ("HKEY_LOCAL_MACHINE\\SOFTWARE\\Epic\n"
               + "    Location    REG_SZ    C:\\Epic\\Crème\n").encode("mbcs")

        def fake_run(*_args, **kwargs):
            self.assertTrue(kwargs.get("text"))
            self.assertTrue(kwargs.get("capture_output"))
            encoding = kwargs.get("encoding")
            errors = kwargs.get("errors")
            self.assertIsNotNone(encoding, "reg.exe precisa de encoding explícito")
            self.assertEqual(errors, "replace")
            decoded = raw.decode(encoding, errors)
            return SimpleNamespace(stdout=decoded, returncode=0)

        with patch.object(providers.subprocess, "run", side_effect=fake_run):
            roots = providers._epic_roots()

        self.assertIn(expected, roots)


if __name__ == "__main__":
    unittest.main()
