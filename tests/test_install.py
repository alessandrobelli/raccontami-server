"""Run from the repository root with:  python -m unittest discover tests

The steps the Windows installer runs once its files are in place (install/install.py). Windows paths are
handled with ntpath, so these run on any system."""

import http.server
import importlib.util
import socket
import sys
import threading
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


class ResolvePortTest(unittest.TestCase):
    def test_nothing_chosen_means_8765(self):
        self.assertEqual(8765, install.resolve_port("", None, {}).number)

    def test_a_port_chosen_by_the_installer_is_used(self):
        self.assertEqual(8766, install.resolve_port("8766", None, {}).number)

    def test_the_port_in_settings_txt_wins_over_a_new_choice(self):
        self.assertEqual(9000, install.resolve_port("8766", "RACCONTAMI_PORT=9000\n", {}).number)

    def test_a_port_set_on_the_computer_wins_over_settings_txt(self):
        self.assertEqual(9100, install.resolve_port("", "RACCONTAMI_PORT=9000\n", {"RACCONTAMI_PORT": "9100"}).number)

    def test_a_port_that_is_not_a_number_is_no_choice(self):
        self.assertEqual(8765, install.resolve_port("", "RACCONTAMI_PORT=abc\n", {}).number)


class SettingsPortTest(unittest.TestCase):
    models = install.Models(USUAL, False, False, None)

    def test_another_port_is_written_as_the_server_reads_it(self):
        text = install.settings_text(None, None, self.models, USUAL, install.Port(8766, True, False))
        self.assertEqual("8766", settings.parse(text)["RACCONTAMI_PORT"])

    def test_the_usual_port_is_not_written(self):
        text = install.settings_text(None, None, self.models, USUAL, install.Port(8765, False, False))
        self.assertNotIn("RACCONTAMI_PORT", settings.parse(text))

    def test_a_file_that_already_names_a_port_is_left_alone(self):
        old = "RACCONTAMI_PORT=9000\n"
        self.assertIsNone(install.settings_text(old, None, self.models, USUAL, install.Port(9000, True, False)))

    def test_a_port_set_on_the_computer_is_not_written(self):
        text = install.settings_text(None, None, self.models, USUAL, install.Port(9100, True, True))
        self.assertNotIn("RACCONTAMI_PORT", settings.parse(text))

    def test_the_start_file_names_the_port(self):
        self.assertIn("port 8766", install.start_file_text(HOME, HOME + "\\raccontami-server", "py.exe", 8766))


class LanguagesInstallTest(unittest.TestCase):
    models = install.Models(USUAL, False, False, None)

    def plan(self, langs):
        return install.plan(HOME, HOME + "\\raccontami-server", HOME + "\\tools\\python\\python.exe", False, False,
                            exists=lambda p: False, langs=langs)

    def venvs(self, langs):
        return sorted(s.argv[3].rsplit("\\", 1)[1] for s in self.plan(langs) if s.argv[1:3] == ["-m", "venv"])

    def test_english_alone_needs_the_server_and_qwen_environments(self):
        self.assertEqual(["env", "env-c"], self.venvs(["en"]))

    def test_turkish_alone_gets_voxcpm2_for_a_narrator_made_here(self):
        self.assertEqual(["env", "env-a"], self.venvs(["tr"]))

    def narrator_steps(self, langs, existing=(), **kw):
        steps = install.plan(HOME, HOME + "\\raccontami-server", HOME + "\\tools\\python\\python.exe", False, False,
                             exists=lambda p: p in existing, langs=langs, samples=set(), **kw)
        return [s for s in steps if any("make_narrator.py" in a for a in s.argv)]

    def test_a_language_without_a_narrator_gets_one_made(self):
        self.assertEqual("tr", self.narrator_steps(["en", "tr"])[0].argv[2])

    def test_the_narrator_is_made_after_the_models_are_there(self):
        steps = install.plan(HOME, HOME + "\\raccontami-server", "py", False, False, exists=lambda p: False,
                             langs=["tr"], samples=set())
        labels = [s.label for s in steps]
        self.assertLess(labels.index("The models for Turkish"), labels.index("A narrator for Turkish"))

    def test_the_users_description_is_passed_on(self):
        argv = self.narrator_steps(["tr"], narrator="a deep slow voice")[0].argv
        self.assertEqual("a deep slow voice", argv[argv.index("--description") + 1])

    def test_a_narrator_already_made_is_kept(self):
        made = HOME + "\\server-data\\narrators\\voxcpm2_tr_ref.wav"
        self.assertEqual([], self.narrator_steps(["tr"], existing={made}))

    def test_a_new_narrator_can_be_asked_for(self):
        made = HOME + "\\server-data\\narrators\\voxcpm2_tr_ref.wav"
        self.assertEqual(1, len(self.narrator_steps(["tr"], existing={made}, remake_narrators=True)))


    def test_the_installers_choice_replaces_the_line_in_settings_txt(self):
        self.assertEqual(["es", "tr"], install.resolve_languages("es,tr", "RACCONTAMI_LANGUAGES=en\n", {}))

    def test_without_a_choice_the_line_in_settings_txt_is_kept(self):
        self.assertEqual(["en"], install.resolve_languages("", "RACCONTAMI_LANGUAGES=en\n", {}))

    def test_without_either_english_and_italian_as_before(self):
        self.assertEqual(["en", "it"], install.resolve_languages("", None, {}))

    def test_languages_set_on_the_computer_win(self):
        self.assertEqual(["de"], install.resolve_languages("es", None, {"RACCONTAMI_LANGUAGES": "de"}))

    def test_chosen_languages_are_written_as_the_server_reads_them(self):
        text = install.settings_text(None, None, self.models, USUAL, langs=["es", "tr"])
        self.assertEqual("es,tr", settings.parse(text)["RACCONTAMI_LANGUAGES"])

    def test_a_new_choice_replaces_the_old_line_and_keeps_the_others(self):
        old = "# mine\nRACCONTAMI_TLS=0\nRACCONTAMI_LANGUAGES=en\nRACCONTAMI_ONE_JOB=1\n"
        text = install.settings_text(old, None, self.models, USUAL, langs=["en", "es"])
        self.assertEqual({"RACCONTAMI_TLS": "0", "RACCONTAMI_LANGUAGES": "en,es", "RACCONTAMI_ONE_JOB": "1"}, settings.parse(text))

    def test_the_same_choice_changes_nothing(self):
        self.assertIsNone(install.settings_text("RACCONTAMI_LANGUAGES=en,es\n", None, self.models, USUAL, langs=["en", "es"]))

    def test_the_download_is_told_the_languages(self):
        env = install.step_environment({}, HOME, self.models, langs=["es"])
        self.assertEqual("es", env["RACCONTAMI_LANGUAGES"])


class UnchangedPackagesTest(unittest.TestCase):
    def plan(self, stamps):
        return install.plan(HOME, HOME + "\\raccontami-server", "py", False, False, exists=lambda p: True,
                            langs=["en"], read=lambda p: stamps.get(p))

    def packages(self, steps):
        return [s for s in steps if "-r" in s.argv]

    def test_packages_are_installed_when_nothing_was_recorded(self):
        self.assertEqual(2, len(self.packages(self.plan({}))))

    def test_an_environment_whose_requirements_did_not_change_is_skipped(self):
        steps = self.plan({})
        stamps = {s.stamp[0]: s.stamp[1] for s in self.packages(steps)}
        self.assertEqual([], self.packages(self.plan(stamps)))

    def test_changed_requirements_are_installed_again(self):
        steps = self.plan({})
        stamps = {s.stamp[0]: "old" for s in self.packages(steps)}
        self.assertEqual(2, len(self.packages(self.plan(stamps))))


class UntickedLanguagesTest(unittest.TestCase):
    """Languages unticked in the installer on an update: their files, deleted only when the user says yes."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "raccontami"
        self.hub = self.home / "models" / "hf" / "hub"
        for repo in ("mpoyraz/wav2vec2-xls-r-300m-cv7-turkish", "openbmb/VoxCPM2"):
            d = self.hub / ("models--" + repo.replace("/", "--"))
            d.mkdir(parents=True)
            (d / "w.bin").write_bytes(b"x")
        (self.home / "server-data" / "narrators").mkdir(parents=True)
        (self.home / "server-data" / "narrators" / "voxcpm2_tr_ref.wav").write_bytes(b"y")
        for env in ("env-a", "env-c"):
            (self.home / "tts" / env / "Scripts").mkdir(parents=True)
            (self.home / "tts" / env / "Scripts" / "python.exe").write_bytes(b"")

    def removal(self, previous, langs):
        return install.removal_paths(previous, langs, str(self.home), str(self.home / "models"), self.hub)

    def test_an_unticked_language_loses_its_model_and_narrator(self):
        paths = self.removal(["en", "tr"], ["en"])
        self.assertIn(self.hub / "models--mpoyraz--wav2vec2-xls-r-300m-cv7-turkish", paths)

    def test_a_voice_model_no_language_needs_any_more_goes_too(self):
        self.assertIn(self.home / "tts" / "env-a", self.removal(["en", "tr"], ["en"]))

    def test_nothing_is_deleted_when_no_language_was_unticked(self):
        self.assertEqual([], self.removal(["en", "tr"], ["en", "tr", "es"]))


class GpusInstallTest(unittest.TestCase):
    models = install.Models(USUAL, False, False, None)

    def test_the_chosen_cards_are_written_as_the_server_reads_them(self):
        text = install.settings_text(None, None, self.models, USUAL, gpus="1")
        self.assertEqual("1", settings.parse(text)["RACCONTAMI_GPUS"])

    def test_a_new_choice_of_cards_replaces_the_old_one(self):
        text = install.settings_text("RACCONTAMI_GPUS=0\nRACCONTAMI_TLS=0\n", None, self.models, USUAL, gpus="0,1")
        self.assertEqual({"RACCONTAMI_GPUS": "0,1", "RACCONTAMI_TLS": "0"}, settings.parse(text))

    def test_the_steps_see_only_the_chosen_cards(self):
        env = install.step_environment({}, HOME, self.models, gpus="1")
        self.assertEqual("1", env["CUDA_VISIBLE_DEVICES"])


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

    def serve(self, body: bytes):
        class Hello(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hello)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def test_a_raccontami_server_is_recognised(self):
        self.assertTrue(install.raccontami_answers(self.serve(b'{"app": "raccontami", "name": "PC"}')))

    def test_another_program_on_the_port_is_not_taken_for_one(self):
        self.assertFalse(install.raccontami_answers(self.serve(b'{"app": "something else"}')))


if __name__ == "__main__":
    unittest.main()
