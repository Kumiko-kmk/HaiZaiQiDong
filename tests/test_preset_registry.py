from __future__ import annotations

import unittest

from presets.registry import PresetRegistry
from tests.support import RegistryTestCase, write_preset


class PresetRegistryOrderingTests(RegistryTestCase):
    def test_untagged_and_unknown_imports_follow_the_other_group(self) -> None:
        write_preset(self.root, "known-warrior", tags=["战士"], menu_order=1)
        write_preset(self.root, "known-other", tags=["其他"], menu_order=18)
        write_preset(self.root, "imported-a", tags=["导入", "SVG"])
        write_preset(self.root, "untagged-z")
        registry = PresetRegistry(self.root)

        self.assertEqual(
            [preset.id for preset in registry.list_presets()],
            ["known-warrior", "known-other", "imported-a", "untagged-z"],
        )


if __name__ == "__main__":
    unittest.main()
