import ssl
import tempfile
import unittest
from pathlib import Path

from raccontami_sync import serve
from raccontami_sync.tls import ensure_certificate, fingerprint, short_code

try:
    import cryptography  # noqa: F401
    HAVE_CRYPTOGRAPHY = True
except ImportError:  # part of the server's environment, not of the GitHub check
    HAVE_CRYPTOGRAPHY = False


class ShortCodeTest(unittest.TestCase):
    def test_the_code_is_the_start_of_the_fingerprint_in_fours(self):
        self.assertEqual("0123-4567-89ab-cdef", short_code("0123456789abcdef" + "0" * 48))


class ServeOptionsTest(unittest.TestCase):
    def test_the_link_is_encrypted_unless_switched_off(self):
        self.assertTrue(serve.wants_tls({}))

    def test_zero_switches_encryption_off(self):
        self.assertFalse(serve.wants_tls({"RACCONTAMI_TLS": "0"}))

    def test_the_port_stays_the_usual_one(self):
        self.assertEqual(8765, serve.options({})["port"])

    def test_the_port_can_be_set(self):
        self.assertEqual(9000, serve.options({"RACCONTAMI_PORT": "9000"})["port"])


@unittest.skipUnless(HAVE_CRYPTOGRAPHY, "needs the cryptography package")
class CertificateTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.data = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_the_first_start_makes_a_certificate_and_a_key(self):
        cert, key = ensure_certificate(self.data)
        self.assertTrue(cert.exists() and key.exists())

    def test_the_same_certificate_is_used_on_the_next_start(self):
        first = fingerprint(ensure_certificate(self.data)[0])
        self.assertEqual(first, fingerprint(ensure_certificate(self.data)[0]))

    def test_the_fingerprint_is_a_sha256_in_hex(self):
        self.assertRegex(fingerprint(ensure_certificate(self.data)[0]), r"^[0-9a-f]{64}$")

    def test_certificate_and_key_belong_together(self):
        cert, key = ensure_certificate(self.data)
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(cert, key)  # raises when they do not match

    def test_two_servers_have_different_certificates(self):
        with tempfile.TemporaryDirectory() as other:
            self.assertNotEqual(fingerprint(ensure_certificate(self.data)[0]), fingerprint(ensure_certificate(Path(other))[0]))


if __name__ == "__main__":
    unittest.main()
