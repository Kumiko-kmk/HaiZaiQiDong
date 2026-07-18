from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from core import app_paths


class FrozenPresetSyncTests(TestCase):
    def test_existing_builtin_mirror_is_upgraded_and_retired_files_removed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "bundle"
            user = root / "user"
            bundled_data = bundle / "presets" / "data"
            user_data = user / "presets" / "data"
            bundled_data.mkdir(parents=True)
            user_data.mkdir(parents=True)

            current = bundled_data / "sts2_honed_blade.json"
            current.write_text('{"revision": 2}', encoding="utf-8")
            (user_data / current.name).write_text('{"revision": 1}', encoding="utf-8")
            retired = user_data / "sts2_difficulties.json"
            retired.write_text("{}", encoding="utf-8")
            legacy_custom = user_data / "my_legacy_preset.json"
            legacy_custom.write_text("{}", encoding="utf-8")

            with (
                patch.object(app_paths, "is_frozen", return_value=True),
                patch.object(app_paths, "bundle_root", return_value=bundle),
                patch.object(app_paths, "user_data_root", return_value=user),
            ):
                result = app_paths.presets_data_dir()

            self.assertEqual(result, user_data)
            self.assertEqual(
                (user_data / current.name).read_text(encoding="utf-8"),
                '{"revision": 2}',
            )
            self.assertFalse(retired.exists())
            self.assertTrue(legacy_custom.exists())

    def test_unchanged_builtin_is_left_untouched(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "bundle"
            user = root / "user"
            bundled_data = bundle / "presets" / "data"
            user_data = user / "presets" / "data"
            bundled_data.mkdir(parents=True)
            user_data.mkdir(parents=True)

            source = bundled_data / "sts2_current.json"
            target = user_data / source.name
            source.write_text('{"revision": 2}', encoding="utf-8")
            target.write_text('{"revision": 2}', encoding="utf-8")
            original_mtime = target.stat().st_mtime_ns

            with (
                patch.object(app_paths, "is_frozen", return_value=True),
                patch.object(app_paths, "bundle_root", return_value=bundle),
                patch.object(app_paths, "user_data_root", return_value=user),
            ):
                app_paths.presets_data_dir()

            self.assertEqual(target.stat().st_mtime_ns, original_mtime)
