"""Run from the repository root with:  python -m unittest discover tests

The steps the Windows installer runs once its files are in place (install/install.py). Windows paths are
handled with ntpath, so these run on any system."""

import importlib.util
import socket
import sys
import unittest
from pathlib import Path

from raccontami_sync import settings

_spec = importlib.util.spec_from_file_location("install_steps", Path(__file__).resolve().parent.parent / "install" / "install.py")
install = importlib.util.module_from_spec(_spec)
sys.modules["install_steps"] = install  # its dataclasses look their module up there
_spec.loader.exec_module(install)

HOME = "C:\\Users\\Niccol\u00f2\\raccontami"
USUAL = HOME + "\\models"


class FullFolderTest(unittest.TestCase):
    def test_the_last_backslash_is_dropped(self):
        self.assertEqual("D:\\models", install.full_folder("D:\\models\\"))

    def test_a_drive_root_keeps_its_backslash(self):
        self.assertEqual("E:\\", install.full_folder("E:\\."))

    def test_a_stray_quote_from_the_command_line_is_dropped(self):
        self.assertEqual("D:\\my models", install.full_folder('D:\\my models"'))


class ResolveModelsTest(unittest.TestCase):
    def test_nothing_chosen_means_the_usual_folder(self):
        m = install.resolve_models(HOME, "", None, {})
        self.assertEqual((USUAL, False), (m.folder, m.chosen))

    def test_a_folder_chosen_elsewhere_is_used(self):
        m = install.resolve_models(HOME, "E:\\big models\\", None, {})
        self.assertEqual(("E:\\big models", True), (m.folder, m.chosen))

    def test_choosing_the_usual_folder_is_no_choice(self):
        self.assertFalse(install.resolve_models(HOME, USUAL.upper() + "\\", None, {}).chosen)

    def test_the_folder_in_settings_txt_wins_over_a_new_choice(self):
        text = "RACCONTAMI_MODELS=F:\\models\n"
        self.assertEqual("F:\\models", install.resolve_models(HOME, "E:\\other", text, {}).folder)

    def test_a_folder_set_on_the_computer_wins_over_settings_txt(self):
        env = {"RACCONTAMI_MODELS": "G:\\from-env"}
        self.assertEqual("G:\\from-env", install.resolve_models(HOME, "", "RACCONTAMI_MODELS=F:\\models\n", env).folder)


class SettingsFileTest(unittest.TestCase):
    def models(self, folder=USUAL, chosen=False, from_env=False):
        return install.Models(folder, chosen, from_env, None)

    def test_a_new_file_is_the_template(self):
        self.assertIn("# Settings of the Raccontami server", install.settings_text(None, None, self.models(), USUAL))

    def test_a_new_file_names_a_chosen_folder_as_the_server_reads_it(self):
        text = install.settings_text(None, None, self.models("E:\\Modelli di Niccol\u00f2", True), USUAL)
        self.assertEqual("E:\\Modelli di Niccol\u00f2", settings.parse(text)["RACCONTAMI_MODELS"])

    def test_a_file_that_already_names_a_folder_is_left_alone(self):
        old = "# mine\nRACCONTAMI_MODELS=F:\\models\n"
        self.assertIsNone(install.settings_text(old, None, self.models("F:\\models", True), USUAL))

    def test_a_file_without_a_folder_gains_the_chosen_one(self):
        text = install.settings_text("# mine\nRACCONTAMI_TLS=0\n", None, self.models("E:\\m", True), USUAL)
        self.assertEqual({"RACCONTAMI_TLS": "0", "RACCONTAMI_MODELS": "E:\\m"}, settings.parse(text))

    def test_settings_in_an_earlier_start_file_move_into_the_new_file(self):
        bat = "@echo off\nset RACCONTAMI_HOME=C:\\x\nset RACCONTAMI_ONE_JOB=1\n"
        self.assertEqual({"RACCONTAMI_ONE_JOB": "1"}, settings.parse(install.settings_text(None, bat, self.models(), USUAL)))

    def test_a_folder_set_on_the_computer_is_not_written(self):
        text = install.settings_text(None, None, self.models("G:\\from-env", True, True), USUAL)
        self.assertNotIn("RACCONTAMI_MODELS", settings.parse(text))


class BatchFileTest(unittest.TestCase):
    def test_it_switches_its_window_to_utf8_before_any_path(self):
        self.assertTrue(install.batch_bytes("set X=1").startswith(b"@echo off\r\nchcp 65001 > nul\r\n"))

    def test_an_accent_is_written_as_utf8_without_a_mark(self):
        self.assertIn("Niccol\u00f2".encode("utf-8"), install.batch_bytes("set H=C:\\Niccol\u00f2"))

    def test_lines_end_the_windows_way(self):
        self.assertNotIn(b"\n", install.batch_bytes("a\nb").replace(b"\r\n", b""))


class PlanTest(unittest.TestCase):
    def plan(self, existing=(), **kw):
        args = dict(home=HOME, repo=HOME + "\\raccontami-server", python=HOME + "\\tools\\python\\python.exe",
                    skip_models=False, phone_models=False)
        args.update(kw)
        return install.plan(exists=lambda p: p in existing, **args)

    def labels(self, steps):
        return [s.label for s in steps]

    def test_a_new_install_makes_the_three_environments(self):
        made = [s for s in self.plan() if s.argv[1:3] == ["-m", "venv"]]
        self.assertEqual(3, len(made))

    def test_an_existing_environment_is_not_made_again(self):
        steps = self.plan(existing={HOME + "\\env\\Scripts\\python.exe"})
        self.assertNotIn([HOME + "\\tools\\python\\python.exe", "-m", "venv", HOME + "\\env"], [s.argv for s in steps])

    def test_pytorch_is_installed_only_when_the_check_fails(self):
        torch = [s for s in self.plan() if "torch==2.11.0" in s.argv][0]
        self.assertIsNotNone(torch.unless)

    def test_skip_models_leaves_out_the_download(self):
        self.assertFalse(any("prefetch.py" in a for s in self.plan(skip_models=True) for a in s.argv))

    def test_phone_models_are_built_only_when_asked_for(self):
        self.assertFalse(any("export_phone_model.py" in a for s in self.plan() for a in s.argv))


class EnvironmentTest(unittest.TestCase):
    def test_a_chosen_folder_is_passed_to_the_download(self):
        env = install.step_environment({}, HOME, install.Models("E:\\m", True, False, None))
        self.assertEqual("E:\\m", env["RACCONTAMI_MODELS"])

    def test_without_a_choice_the_download_follows_the_server_default(self):
        env = install.step_environment({"RACCONTAMI_MODELS": "x"}, HOME, install.Models(USUAL, False, False, None))
        self.assertNotIn("RACCONTAMI_MODELS", env)


class ServerRunningTest(unittest.TestCase):
    def test_a_listening_port_is_seen(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen()
            self.assertTrue(install.port_in_use(s.getsockname()[1]))


if __name__ == "__main__":
    unittest.main()
