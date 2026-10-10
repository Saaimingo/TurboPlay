"""Contrato de honestidade do dry-run: nenhuma escrita ou falsa reconfiguração."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from src import pipeline
from src.models import Game, Profile


class DryRunTests(unittest.TestCase):
    def test_existing_state_is_reported_without_claiming_reconfiguration(self) -> None:
        game = Game(id="dry-game", title="Fixture", exe_path=r"C:\fixture\game.exe",
                    folder=r"C:\fixture", source="steam", api="DX12", pe_bits=64)
        profile = Profile(game_id=game.id, decision="DLSS5_MFG", reason="fixture",
                          layers=["DLSSNR_FORK", "SM86"])
        state = {game.id: {"decision": "DLSS5_MFG"}}

        with patch.object(pipeline, "detect_gpu", return_value={"vendor": "nvidia", "series": 30}), \
                patch.object(pipeline, "scan_all", return_value=[game]), \
                patch.object(pipeline, "classify", side_effect=lambda item: item), \
                patch.object(pipeline, "_load_state", return_value=state), \
                patch.object(pipeline, "decide", return_value=profile), \
                patch.object(pipeline, "is_state_current", return_value=(True, "current")), \
                patch.object(pipeline, "reconfigure_optiscaler") as reconfigure, \
                patch.object(pipeline, "_save_state") as save_state:
            result = pipeline.run_full(auto_apply=True, dry_run=True)

        note = " ".join(result["games"][0]["notes"]).lower()
        self.assertIn("dry-run", note)
        self.assertIn("sem reconfiguração", note)
        self.assertNotIn("config revalidada", note)
        reconfigure.assert_not_called()
        save_state.assert_not_called()


if __name__ == "__main__":
    unittest.main()
