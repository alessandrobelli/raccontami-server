"""The server's own certificate, so the app and the server talk over an encrypted link.

There is no public name for a computer at home and nobody to vouch for it, so the server makes
its certificate itself on the first start and keeps it in the data folder. The app does not ask
"who signed this?" but "is this the certificate I was paired with?": it remembers the SHA-256
of the certificate (its fingerprint). To pair, the reader compares a short code, the start of
that fingerprint, between this window and the app.

Losing the two files only means pairing again; they are made anew on the next start.
"""

from __future__ import annotations

import datetime
import hashlib
import os
import ssl
from pathlib import Path

CERT, KEY = "tls-cert.pem", "tls-key.pem"
YEARS = 20


def ensure_certificate(data: Path) -> tuple[Path, Path]:
    """The certificate and key files in [data], made on the first call. Needs the "cryptography" package."""
    cert, key = data / CERT, data / KEY
    if cert.exists() and key.exists():
        return cert, key
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    private = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Raccontami server")])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(private.public_key())
        .serial_number(x509.random_serial_number())
        # a day back: a phone whose clock runs a little behind must not find it "not yet valid"
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365 * YEARS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        # the address of a computer at home changes, so no address is written in: the app checks the fingerprint
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("raccontami.local")]), critical=False)
        .sign(private, hashes.SHA256())
    )
    data.mkdir(parents=True, exist_ok=True)
    key_tmp, cert_tmp = key.with_name(key.name + ".tmp"), cert.with_name(cert.name + ".tmp")
    key_tmp.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
    try:
        os.chmod(key_tmp, 0o600)  # the key is the server's identity; on Windows the data folder's own rights apply
    except OSError:
        pass
    cert_tmp.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    os.replace(key_tmp, key)
    os.replace(cert_tmp, cert)
    return cert, key


def fingerprint(cert: Path) -> str:
    """SHA-256 of the certificate as the app sees it in the handshake (hex, lower case): what the app remembers."""
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text(encoding="ascii"))).hexdigest()


def digit_code(fp: str) -> str:
    """The start of a fingerprint as digits in groups of four, to compare by eye:
    "0458 4939 0331 2265 6608". The same 64 bits as the older code in letters and digits
    (short_code), written as a number of 20 digits: digits are compared with fewer mistakes."""
    return " ".join(f"{int(fp[:16], 16):020d}"[i:i + 4] for i in range(0, 20, 4))


def short_code(fp: str) -> str:
    """The code as apps before version 0.2 show it: "3fa9-07c2-b1d4-88e0". Still said next to the
    digits, so that an app not yet updated can be paired."""
    return "-".join(fp[i:i + 4] for i in range(0, 16, 4))
