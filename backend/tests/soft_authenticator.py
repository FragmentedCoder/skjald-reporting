"""A software passkey for tests: real ES256 signatures and CBOR, no browser.

It produces the same JSON a browser's navigator.credentials.create() and .get()
return, so py_webauthn's real verification runs against it.
"""

from __future__ import annotations

import hashlib
import json
import os

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url

FLAG_USER_PRESENT = 0x01
FLAG_USER_VERIFIED = 0x04
FLAG_ATTESTED_DATA = 0x40


class SoftAuthenticator:
    def __init__(self, rp_id: str, origin: str) -> None:
        self.rp_id = rp_id
        self.origin = origin
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(16)
        self.sign_count = 0

    def _cose_public_key(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        x, y = numbers.x.to_bytes(32, "big"), numbers.y.to_bytes(32, "big")
        return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: x, -3: y})  # COSE EC2 key, ES256, P-256

    def _client_data(self, kind: str, challenge: str) -> bytes:
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": self.origin, "crossOrigin": False}
        ).encode()

    def _auth_data(self, flags: int, extra: bytes = b"") -> bytes:
        rp_id_hash = hashlib.sha256(self.rp_id.encode()).digest()
        return rp_id_hash + bytes([flags]) + self.sign_count.to_bytes(4, "big") + extra

    def register(self, options: dict) -> dict:
        client_data = self._client_data("webauthn.create", options["challenge"])
        attested = (
            bytes(16)  # AAGUID: none
            + len(self.credential_id).to_bytes(2, "big")
            + self.credential_id
            + self._cose_public_key()
        )
        auth_data = self._auth_data(
            FLAG_USER_PRESENT | FLAG_USER_VERIFIED | FLAG_ATTESTED_DATA, attested
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "attestationObject": bytes_to_base64url(attestation),
                "transports": ["usb"],
            },
            "clientExtensionResults": {},
        }

    def authenticate(self, options: dict) -> dict:
        self.sign_count += 1
        client_data = self._client_data("webauthn.get", options["challenge"])
        auth_data = self._auth_data(FLAG_USER_PRESENT | FLAG_USER_VERIFIED)
        signature = self.key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
                "userHandle": None,
            },
            "clientExtensionResults": {},
        }
